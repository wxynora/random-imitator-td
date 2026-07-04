from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.game.config import GameConfig
from random_imitator_td.game.contracts import validate_action_plan
from random_imitator_td.data.reveal_pools import P2_REVEAL_RESULTS
from random_imitator_td.game.engine import AIRDROP_OUTCOME_WEIGHTS, GameEngine
from random_imitator_td.game.experience import make_player_note, update_player_note
from random_imitator_td.game.player_view import build_card_selection_view, parse_player_text_action_plan
from random_imitator_td.game.zombie_behaviors import POLE_VAULTING_SPENT_STATUS
from random_imitator_td.game.models import AirdropInstance, PendingImitator, PlantInstance, RevealResultDef, ZombieInstance
from random_imitator_td.players.scripted_player import ScriptedPlayer
from scripts.sim_balance import PressureScriptedPlayer, build_wave_schedule, config_for_level


class ImitatorPvzP2Tests(unittest.TestCase):
    def test_advance_until_can_fast_forward_560_ticks(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        summary = engine.advance_until(max_ticks=560)
        self.assertEqual(summary["advanced_ticks"], 560)
        self.assertEqual(engine.state.tick, 560)

    def test_empty_wave_schedule_does_not_auto_win(self) -> None:
        engine = GameEngine(wave_schedule=[])
        summary = engine.advance_until(max_ticks=5)
        self.assertEqual(summary["advanced_ticks"], 5)
        self.assertFalse(engine.state.wave_state["completed"])
        self.assertFalse(engine.state.game_over)

    def test_apply_action_plan_plants_pending_imitator(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_1",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])
        self.assertTrue(result["accepted"])
        self.assertEqual(engine.state.grid[(3, 3)][0], "i")
        self.assertEqual(engine.config.imitator_cost, 0)
        self.assertEqual(engine.state.sun, engine.config.initial_sun)
        self.assertEqual(result["advance_summary"]["from_tick"], 0)
        self.assertEqual(result["advance_summary"]["to_tick"], engine.config.plant_action_ticks)
        self.assertEqual(result["advance_summary"]["advanced_ticks"], engine.config.plant_action_ticks)
        self.assertEqual(result["executed_actions"][0]["slot_id"], "imitator_1")

    def test_apply_action_plan_accepts_model_player_aliases(self) -> None:
        config = GameConfig(card_slot_count=2)
        engine = GameEngine(config=config, wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_aliases",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "row": "3", "col": "4", "card": 2}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        self.assertTrue(result["accepted"])
        self.assertEqual(engine.state.grid[(3, 4)][0], "i")
        self.assertEqual(result["executed_actions"][0]["slot_id"], "imitator_2")
        round_record = result["observation"]["player_experience"]["recent_rounds"][0]
        self.assertEqual(
            round_record["actions"][0],
            {"action": "plant_imitator", "lane": 3, "col": 4, "slot_id": "imitator_2"},
        )

    def test_shovel_removes_revealed_plant_and_frees_cell(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        plant = PlantInstance("p1", "flower_pot", lane=3, col=4, hp=300)
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 4)] = plant.entity_id
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_shovel_plant",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "shovel_plant", "row": "3", "col": "4"}],
            },
            observation_id=observation["observation_id"],
        )

        self.assertTrue(result["accepted"])
        self.assertIsNone(engine.state.grid[(3, 4)])
        self.assertNotIn("p1", engine.state.plants)
        self.assertEqual(result["advance_summary"]["advanced_ticks"], engine.config.shovel_action_ticks)
        self.assertIn("shovel_plant", observation["valid_actions"])
        shoveled_event = next(event for event in result["events"] if event["type"] == "plant_shoveled")
        self.assertEqual(shoveled_event["plant_type"], "flower_pot")
        round_events = result["observation"]["player_experience"]["recent_rounds"][0]["result_events"]
        self.assertIn("plant_shoveled", [event["type"] for event in round_events])

    def test_shovel_pending_imitator_cancels_reveal(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        planted = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_plant_before_shovel",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
            },
            observation_id=observation["observation_id"],
        )

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": planted["observation"]["observation_id"],
                "action_plan_id": "plan_shovel_pending",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "shovel_plant", "lane": 3, "col": 3}],
            },
            observation_id=planted["observation"]["observation_id"],
        )

        self.assertTrue(result["accepted"])
        self.assertIsNone(engine.state.grid[(3, 3)])
        self.assertFalse(engine.state.pending_imitators)
        self.assertFalse([event for event in engine.state.scheduled_events if event.get("type") == "imitator_reveal"])
        shoveled_event = next(event for event in result["events"] if event["type"] == "imitator_shoveled")
        self.assertTrue(shoveled_event["reveal_cancelled"])

    def test_player_experience_records_round_result_into_next_observation(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)], run_id="record_rounds")
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_record_round",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"], real_elapsed_seconds=4.5)

        experience = result["observation"]["player_experience"]
        self.assertEqual(len(experience["recent_rounds"]), 1)
        round_record = experience["recent_rounds"][0]
        self.assertEqual(round_record["observation_id"], observation["observation_id"])
        self.assertEqual(round_record["action_plan_id"], "plan_record_round")
        self.assertEqual(round_record["from_tick"], 0)
        self.assertEqual(round_record["to_tick"], result["observation"]["tick"])
        self.assertNotIn("real_elapsed_seconds", round_record)
        self.assertEqual(round_record["stop_reason"], "action_plan_completed")
        self.assertEqual(round_record["actions"][0]["action"], "plant_imitator")
        self.assertEqual(round_record["executed_actions"][0]["slot_id"], "imitator_1")
        self.assertFalse(round_record["failed_actions"])
        self.assertTrue(any(event["type"] == "imitator_planted" for event in round_record["result_events"]))

    def test_player_experience_records_failed_round_result(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        for slot_id in engine.state.cooldowns:
            engine.state.cooldowns[slot_id] = 999
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_failed_round",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        recent_round = result["observation"]["player_experience"]["recent_rounds"][0]
        self.assertEqual(recent_round["stop_reason"], "action_failed")
        self.assertEqual(recent_round["failed_actions"][0]["reason"], "cooldown_not_ready")
        self.assertTrue(any(event["type"] == "action_failed" for event in recent_round["result_events"]))

    def test_wait_stop_reason_names_strong_event(self) -> None:
        engine = GameEngine(wave_schedule=[(5, "normal", 3)])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_wait_for_wave",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "wait", "max_wait_ticks": 20}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        self.assertEqual(result["advance_summary"]["stop_reason"], "wait_strong_event")
        self.assertEqual(result["observation"]["reason"], ["wait_strong_event"])
        self.assertEqual(
            result["observation"]["player_experience"]["recent_rounds"][0]["stop_reason"],
            "wait_strong_event",
        )

    def test_wait_stop_reason_names_wait_limit(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_wait_limit",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "wait", "max_wait_ticks": 3}],
            },
            observation_id=observation["observation_id"],
        )

        self.assertEqual(result["advance_summary"]["stop_reason"], "wait_max_wait_ticks")

    def test_round_result_events_keep_attack_sun_and_death_facts(self) -> None:
        config = GameConfig(auto_collect_sun=True, sky_sun_interval_ticks=1)
        engine = GameEngine(config=config, wave_schedule=[])
        plant = PlantInstance("p1", "peashooter", lane=3, col=3, hp=300, next_attack_tick=1)
        zombie = ZombieInstance("z1", "normal", lane=3, x=5.0, hp=20)
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 3)] = plant.entity_id
        engine.state.zombies[zombie.entity_id] = zombie
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_wait_attack",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "wait", "max_wait_ticks": 5}],
            },
            observation_id=observation["observation_id"],
        )

        event_types = [
            event["type"]
            for event in result["observation"]["player_experience"]["recent_rounds"][0]["result_events"]
        ]
        self.assertIn("plant_produced_sun", event_types)
        self.assertIn("plant_attack_fired", event_types)
        self.assertIn("zombie_died", event_types)

    def test_full_round_history_is_kept_while_observation_window_is_limited(self) -> None:
        engine = GameEngine(wave_schedule=[])
        observation = engine.run_until_decision()
        for index in range(10):
            result = engine.apply_action_plan(
                {
                    "schema_version": 1,
                    "observation_id": observation["observation_id"],
                    "action_plan_id": f"plan_wait_{index}",
                    "interrupt_policy": "interrupt_on_emergency",
                    "actions": [{"action": "wait", "max_wait_ticks": 1}],
                },
                observation_id=observation["observation_id"],
            )
            observation = result["observation"]

        self.assertEqual(len(engine.get_player_round_history()), 10)
        self.assertEqual(len(observation["player_experience"]["recent_rounds"]), 8)
        self.assertEqual(observation["player_experience"]["recent_rounds"][0]["round_id"], "round_3")
        self.assertEqual(engine.get_player_round_history()[0]["round_id"], "round_1")

    def test_player_notes_are_injected_and_editable_between_rounds(self) -> None:
        note = make_player_note(
            memory_id="loss_l1_001",
            level=1,
            player_note="第一局只记自己吃过的亏。",
            source_run_id="run_a",
            source_round_id="round_3",
            updated_tick=500,
        )
        engine = GameEngine(player_notes=[note], wave_schedule=[])
        observation = engine.run_until_decision()

        self.assertEqual(observation["player_experience"]["notes"][0]["note"], "第一局只记自己吃过的亏。")

        edited_notes = update_player_note(
            [note],
            memory_id="loss_l1_001",
            player_note="改成第二版：只保留玩家自己写的复盘。",
            updated_tick=900,
        )
        engine.set_player_notes(edited_notes)
        edited_observation = engine.run_until_decision(max_ticks=1)

        injected_note = edited_observation["player_experience"]["notes"][0]
        self.assertEqual(injected_note["note"], "改成第二版：只保留玩家自己写的复盘。")
        self.assertEqual(injected_note["source_round_id"], "round_3")
        self.assertEqual(injected_note["updated_tick"], 900)

    def test_failed_action_summary_counts_elapsed_delay(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        for slot_id in engine.state.cooldowns:
            engine.state.cooldowns[slot_id] = 200
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_1",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        result = engine.apply_action_plan(
            plan,
            observation_id=observation["observation_id"],
            real_elapsed_seconds=1.0,
        )
        self.assertEqual(result["failed_actions"][0]["reason"], "cooldown_not_ready")
        self.assertEqual(result["advance_summary"]["from_tick"], 0)
        self.assertEqual(result["advance_summary"]["to_tick"], 1)
        self.assertEqual(result["advance_summary"]["advanced_ticks"], 1)

    def test_imitator_card_slots_have_independent_cooldowns(self) -> None:
        config = GameConfig(card_slot_count=2)
        engine = GameEngine(config=config, wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_slots",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [
                {"action": "plant_imitator", "lane": 3, "col": 3},
                {"action": "plant_imitator", "lane": 3, "col": 4},
            ],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        self.assertTrue(result["accepted"])
        self.assertEqual([action["slot_id"] for action in result["executed_actions"]], ["imitator_1", "imitator_2"])
        self.assertEqual(result["advance_summary"]["advanced_ticks"], config.plant_action_ticks * 2)

    def test_card_slot_count_is_capped_by_config(self) -> None:
        config = GameConfig(card_slot_count=99, max_card_slot_count=10)
        engine = GameEngine(config=config, wave_schedule=[(9999, "normal", 3)])

        observation = engine.run_until_decision()

        self.assertEqual(observation["action_constraints"]["card_slot_count"], 10)
        self.assertEqual(len(observation["action_constraints"]["card_slots"]), 10)

    def test_direct_plant_card_costs_sun_and_places_plant(self) -> None:
        config = GameConfig(card_slot_count=2, card_loadout=("peashooter", "wallnut"))
        engine = GameEngine(config=config, wave_schedule=[])
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_direct_card",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "plant_card", "slot_id": "peashooter_1", "lane": 3, "col": 3}],
            },
            observation_id=observation["observation_id"],
        )

        plant = engine.state.plants[engine.state.grid[(3, 3)]]
        self.assertTrue(result["accepted"])
        self.assertEqual(plant.plant_id, "peashooter")
        self.assertEqual(engine.state.sun, 50)
        self.assertEqual(result["executed_actions"][0]["card_id"], "peashooter")
        self.assertIn("豌豆射手x1(100)", observation["player_view"]["text"])

    def test_roof_flower_pot_becomes_buffer_for_direct_plant(self) -> None:
        config = GameConfig(is_roof=True, card_slot_count=2, card_loadout=("flower_pot", "peashooter"))
        engine = GameEngine(config=config, wave_schedule=[])
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_roof_pot_buffer",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [
                    {"action": "plant_card", "slot_id": "flower_pot_1", "lane": 3, "col": 3},
                    {"action": "plant_card", "slot_id": "peashooter_1", "lane": 3, "col": 3},
                ],
            },
            observation_id=observation["observation_id"],
        )

        plant = engine.state.plants[engine.state.grid[(3, 3)]]
        self.assertTrue(result["accepted"])
        self.assertEqual(plant.plant_id, "peashooter")
        self.assertIn("roof_pot", plant.status.split(","))
        self.assertFalse([item for item in engine.state.plants.values() if item.plant_id == "flower_pot"])
        planted_event = [event for event in result["events"] if event["type"] == "plant_card_planted"][-1]
        self.assertTrue(planted_event["roof_pot"])
        self.assertIn("盆豌", result["observation"]["player_view"]["text"])
        self.assertIn("花盆缓冲", result["observation"]["player_view"]["text"])

    def test_roof_pot_buffer_absorbs_first_zombie_bite(self) -> None:
        engine = GameEngine(config=GameConfig(is_roof=True), wave_schedule=[])
        engine.state.tick = 10
        plant = PlantInstance("p1", "peashooter", lane=3, col=3, hp=100, status="active,roof_pot")
        zombie = ZombieInstance("z1", "normal", lane=3, x=3.0, hp=200, spawned_tick=0, target_entity_id="p1")
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 3)] = plant.entity_id
        engine.state.zombies[zombie.entity_id] = zombie

        events = engine._zombie_bite()

        self.assertEqual(plant.hp, 100)
        self.assertNotIn("roof_pot", plant.status.split(","))
        self.assertIn("roof_pot_absorbed_hit", [event.type for event in events])

    def test_roof_tile_can_damage_zombie_and_destroy_it(self) -> None:
        config = GameConfig(is_roof=True, roof_tile_damage=999)
        engine = GameEngine(config=config, wave_schedule=[])
        zombie = ZombieInstance("z1", "normal", lane=2, x=4.1, hp=200, spawned_tick=0)
        engine.state.zombies[zombie.entity_id] = zombie

        events = engine._apply_roof_tile(2, 4)

        self.assertNotIn("z1", engine.state.zombies)
        self.assertEqual(events[0].type, "roof_tile_slipped")
        self.assertEqual(events[0].payload["target_kind"], "zombie")
        self.assertTrue(events[0].payload["destroyed"])
        self.assertIn("zombie_died", [event.type for event in events])

    def test_roof_tile_is_absorbed_by_roof_pot_buffer(self) -> None:
        config = GameConfig(is_roof=True, roof_tile_damage=999)
        engine = GameEngine(config=config, wave_schedule=[])
        plant = PlantInstance("p1", "peashooter", lane=2, col=4, hp=100, status="active,roof_pot")
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(2, 4)] = plant.entity_id

        events = engine._apply_roof_tile(2, 4)

        self.assertIn("p1", engine.state.plants)
        self.assertEqual(plant.hp, 100)
        self.assertNotIn("roof_pot", plant.status.split(","))
        self.assertEqual(events[0].type, "roof_tile_slipped")
        self.assertTrue(events[0].payload["absorbed_by_roof_pot"])

    def test_occupied_cell_failure_reports_target_and_occupant(self) -> None:
        config = GameConfig(card_slot_count=2, card_loadout=("sunflower", "wallnut"))
        engine = GameEngine(config=config, wave_schedule=[])
        observation = engine.run_until_decision()

        result = engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_occupied_cell",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [
                    {"action": "plant_card", "slot_id": "sunflower_1", "lane": 3, "col": 3},
                    {"action": "plant_card", "slot_id": "wallnut_1", "lane": 3, "col": 3},
                ],
            },
            observation_id=observation["observation_id"],
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["failed_actions"][0]["reason"], "target_cell_no_longer_empty")
        self.assertEqual(result["failed_actions"][0]["lane"], 3)
        self.assertEqual(result["failed_actions"][0]["col"], 3)
        self.assertEqual(result["failed_actions"][0]["occupants"][0]["plant_id"], "sunflower")
        failed_event = next(event for event in result["events"] if event["type"] == "action_failed")
        self.assertEqual(failed_event["occupants"][0]["plant_id"], "sunflower")
        self.assertIn("动作失败(后续未执行): 3路3列已有向日葵", result["observation"]["player_view"]["text"])

    def test_player_view_renders_sun_resource_and_card_costs(self) -> None:
        config = GameConfig(initial_sun=25, card_slot_count=1, card_loadout=("cherry_bomb",))
        engine = GameEngine(config=config, wave_schedule=[])

        observation = engine.run_until_decision()

        self.assertIn("资源: 阳光25", observation["player_view"]["text"])
        self.assertIn("卡槽: 樱桃炸弹x1(150/阳光不足)", observation["player_view"]["text"])
        self.assertNotIn("缺125", observation["player_view"]["text"])

    def test_card_catalog_includes_selection_costs(self) -> None:
        engine = GameEngine(wave_schedule=[])
        observation = engine.run_until_decision()

        catalog = {
            item["card_id"]: item
            for item in observation["action_constraints"]["card_catalog"]
        }

        self.assertEqual(catalog["imitator"]["cost"], 0)
        self.assertEqual(catalog["coffee_bean"]["cost"], 75)
        self.assertEqual(catalog["sunflower"]["cost"], 50)
        self.assertEqual(catalog["plantern"]["cost"], 25)
        self.assertEqual(catalog["flower_pot"]["cost"], 25)
        self.assertEqual(catalog["cherry_bomb"]["cost"], 150)

    def test_card_selection_view_renders_catalog_prices(self) -> None:
        view = build_card_selection_view(GameConfig(card_slot_count=6, max_card_slot_count=10))

        self.assertEqual(view["format"], "card_selection_text_v1")
        self.assertIn("槽位6/10", view["text"])
        self.assertIn("模仿者(0)", view["text"])
        self.assertIn("咖啡豆(75)", view["text"])
        self.assertIn("路灯花(25)", view["text"])
        self.assertIn("花盆(25)", view["text"])
        self.assertIn("樱桃炸弹(150)", view["text"])

    def test_level_stage_config_and_wave_counts_jump_by_level(self) -> None:
        base_config = GameConfig()

        self.assertTrue(config_for_level(1, base_config).is_day)
        self.assertFalse(config_for_level(2, base_config).is_day)
        self.assertTrue(config_for_level(3, base_config).is_day)
        level4_config = config_for_level(4, base_config)
        self.assertFalse(level4_config.is_day)
        self.assertEqual(level4_config.fog_start_col, 6)
        level5_config = config_for_level(5, base_config)
        self.assertTrue(level5_config.is_day)
        self.assertTrue(level5_config.is_roof)
        level6_config = config_for_level(6, base_config)
        self.assertTrue(level6_config.is_endless)
        self.assertEqual(len(build_wave_schedule(1)), 6)
        self.assertEqual(len(build_wave_schedule(2)), 11)
        self.assertEqual(len(build_wave_schedule(3)), 18)
        self.assertEqual(len(build_wave_schedule(4)), 28)
        self.assertEqual(len(build_wave_schedule(5)), 31)
        self.assertEqual(build_wave_schedule(6), [])
        self.assertLess(max(tick for tick, _, _ in build_wave_schedule(1)), max(tick for tick, _, _ in build_wave_schedule(3)))

    def test_all_imitator_special_level_uses_endless_dynamic_waves(self) -> None:
        config = config_for_level(6, GameConfig())
        engine = GameEngine(config=config, seed="endless-dynamic", wave_schedule=build_wave_schedule(6))
        engine.state.level = 6

        summary = engine.advance_until(max_ticks=120)

        self.assertTrue(engine.config.is_endless)
        self.assertFalse(engine.state.game_over)
        self.assertEqual(engine.state.result, None)
        self.assertEqual(engine.state.wave_state["spawned_count"], 1)
        self.assertFalse(engine.state.wave_state["completed"])
        self.assertIn("zombie_spawned", [event["type"] for event in summary["events"]])

    def test_level4_fog_view_hides_and_plantern_reveals_cells(self) -> None:
        engine = GameEngine(config=config_for_level(4, GameConfig()), wave_schedule=[])
        engine.state.level = 4

        observation = engine.run_until_decision()

        self.assertIn("Lv4 场地:迷雾夜间", observation["player_view"]["text"])
        self.assertIn("地形: 迷雾6-9列", observation["player_view"]["text"])
        self.assertIn("1: 空 空 空 空 空 雾 雾 雾 雾", observation["player_view"]["text"])

        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=3, x=8.2, hp=200)
        hidden = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )
        self.assertIn("3: 空 空 空 空 空 雾 雾 雾 雾", hidden["player_view"]["text"])

        engine.state.plants["p1"] = PlantInstance("p1", "plantern", lane=3, col=7, hp=300, planted_tick=0)
        engine.state.grid[(3, 7)] = "p1"
        revealed = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )
        self.assertIn("3: 空 空 空 空 空 空 灯 普 空", revealed["player_view"]["text"])

    def test_observation_and_player_view_include_system_wave_progress(self) -> None:
        engine = GameEngine(wave_schedule=[(10, "normal", 2), (30, "buckethead", 4)])

        observation = engine.run_until_decision()

        self.assertEqual(observation["wave_progress"]["spawned"], 0)
        self.assertEqual(observation["wave_progress"]["total"], 2)
        self.assertEqual(observation["wave_progress"]["next"]["tick"], 10)
        self.assertIn("系统波次: 0/2，下一只 tick 10(约10ticks后): 2路普通僵尸", observation["player_view"]["text"])

        engine.advance_until(max_ticks=30, stop_on_event=False)
        observation = engine.build_observation(reason=["test"], events=[], advance_summary={})

        self.assertTrue(observation["wave_progress"]["completed"])
        self.assertIn("系统波次: 2/2，已结束；新增僵尸来自模仿者或特殊事件", observation["player_view"]["text"])

    def test_pending_imitator_reveals_as_peashooter(self) -> None:
        reveal_results = {
            "only_peashooter": RevealResultDef(
                "only_peashooter",
                "good",
                "plant",
                {"plant_id": "peashooter"},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[(9999, "normal", 3)])
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})
        events = engine.step_one_tick()
        self.assertEqual(engine.state.plants[engine.state.grid[(3, 3)]].plant_id, "peashooter")
        self.assertIn("reveal_spawned_plant", [event.type for event in events])

    def test_reveal_spawned_zombie_waits_until_next_tick(self) -> None:
        reveal_results = {
            "only_zombie": RevealResultDef(
                "only_zombie",
                "chaos",
                "spawn_zombie",
                {"zombie_id": "normal"},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[(9999, "normal", 3)])
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})
        events = engine.step_one_tick()
        reveal_spawn = next(event for event in events if event.type == "reveal_spawned_zombie")
        self.assertEqual(reveal_spawn.payload["flavor_text"], "模仿者这次站到了僵尸队。")
        zombie = next(iter(engine.state.zombies.values()))
        self.assertEqual(zombie.x, 3.5)
        engine.step_one_tick()
        self.assertLess(zombie.x, 3.5)

    def test_early_reveal_zombie_spawn_keeps_home_buffer(self) -> None:
        reveal_results = {
            "only_zombie": RevealResultDef(
                "only_zombie",
                "chaos",
                "spawn_zombie",
                {"zombie_id": "normal"},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[])
        engine.state.level = 2
        imitator = PendingImitator("i1", 3, 1, 300, 0, 1)
        engine.state.grid[(3, 1)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})

        events = engine.step_one_tick()

        spawn = next(event for event in events if event.type == "reveal_spawned_zombie")
        self.assertEqual(spawn.payload["x"], 3.5)

    def test_early_reveal_pressure_caps_clustered_bad_rolls(self) -> None:
        engine = GameEngine(wave_schedule=[])
        engine.state.level = 2
        engine.state.tick = 200
        engine.state.zombies["z1"] = ZombieInstance("z1", "football", lane=1, x=7.0, hp=1400)
        engine.state.zombies["z2"] = ZombieInstance("z2", "buckethead", lane=2, x=7.0, hp=1300)

        adjusted = engine._adjust_reveal_weights(
            {
                "chaos_buckethead_zombie": 10,
                "chaos_pole_vaulting_zombie": 10,
                "chaos_football_zombie": 10,
                "chaos_zomboss": 10,
            }
        )

        self.assertEqual(adjusted["chaos_buckethead_zombie"], 1)
        self.assertEqual(adjusted["chaos_pole_vaulting_zombie"], 1)
        self.assertEqual(adjusted["chaos_football_zombie"], 0)
        self.assertEqual(adjusted["chaos_zomboss"], 0)

    def test_boss_reveal_can_delay_first_action(self) -> None:
        engine = GameEngine(wave_schedule=[])
        result = RevealResultDef(
            "boss",
            "chaos",
            "boss_event",
            {"boss_id": "zomboss", "duration_ticks": 200, "action_interval_ticks": 40, "first_action_delay_ticks": 90},
            1,
        )

        event = engine._spawn_boss_event(result, "cause")

        boss = next(iter(engine.state.boss_events.values()))
        self.assertEqual(boss.next_action_tick, 90)
        self.assertEqual(event.payload["action_interval_ticks"], 40)

    def test_wave_spawn_does_not_include_reveal_flavor_text(self) -> None:
        engine = GameEngine(wave_schedule=[(1, "normal", 3)])

        events = engine.step_one_tick()
        wave_spawn = next(event for event in events if event.type == "zombie_spawned")

        self.assertNotIn("flavor_text", wave_spawn.payload)

    def test_reveal_pool_does_not_hide_high_level_results(self) -> None:
        reveal_results = {
            "late_chaos": RevealResultDef(
                "late_chaos",
                "chaos",
                "spawn_zombie",
                {"zombie_id": "buckethead"},
                1,
                min_level=99,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[(9999, "normal", 3)])
        engine.state.level = 1
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})

        events = engine.step_one_tick()

        self.assertIn("reveal_spawned_zombie", [event.type for event in events])
        self.assertEqual(next(iter(engine.state.zombies.values())).zombie_id, "buckethead")

    def test_observation_includes_current_zombie_glossary(self) -> None:
        engine = GameEngine(wave_schedule=[])
        zombie = ZombieInstance("z1", "pole_vaulting", lane=3, x=6.0, hp=500)
        engine.state.zombies[zombie.entity_id] = zombie

        observation = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )

        self.assertIn("pole_vaulting", observation["zombie_glossary"])
        self.assertEqual(set(observation["zombie_glossary"]["pole_vaulting"]), {"special", "trait"})
        self.assertIn("跳过", observation["zombie_glossary"]["pole_vaulting"]["trait"])

    def test_lane_observation_flags_home_entry_edge_without_lawnmower(self) -> None:
        engine = GameEngine(wave_schedule=[])
        engine.state.lawnmowers[3] = False
        zombie = ZombieInstance("z1", "normal", lane=3, x=0.305, hp=200)
        engine.state.zombies[zombie.entity_id] = zombie

        observation = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )

        lane3 = next(lane for lane in observation["lanes"] if lane["lane"] == 3)
        self.assertEqual(lane3["home_eta_ticks"], 30)
        self.assertEqual(lane3["lane_alerts"][0]["type"], "home_entry_edge")
        self.assertEqual(lane3["lane_alerts"][0]["severity"], "emergency")
        self.assertIn("无推车", lane3["lane_alerts"][0]["message"])

    def test_lane_observation_does_not_flag_home_entry_edge_when_mower_exists_or_eta_is_high(self) -> None:
        engine = GameEngine(wave_schedule=[])
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=3, x=0.305, hp=200)

        observation = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )
        lane3 = next(lane for lane in observation["lanes"] if lane["lane"] == 3)
        self.assertEqual(lane3["lane_alerts"], [])

        engine.state.lawnmowers[3] = False
        engine.state.zombies["z1"].x = 0.41
        observation = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )
        lane3 = next(lane for lane in observation["lanes"] if lane["lane"] == 3)
        self.assertEqual(lane3["home_eta_ticks"], 40)
        self.assertEqual(lane3["lane_alerts"], [])

    def test_zombie_glossary_has_trait_text_for_all_registered_zombies(self) -> None:
        engine = GameEngine(wave_schedule=[])
        for index, zombie_id in enumerate(engine.zombie_defs, start=1):
            engine.state.zombies[f"z{index}"] = ZombieInstance(
                f"z{index}",
                zombie_id,
                lane=((index - 1) % engine.config.lanes) + 1,
                x=6.0,
                hp=engine.zombie_defs[zombie_id].hp,
            )

        observation = engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "test"},
        )

        self.assertEqual(set(observation["zombie_glossary"]), set(engine.zombie_defs))
        for zombie_id, glossary in observation["zombie_glossary"].items():
            with self.subTest(zombie_id=zombie_id):
                self.assertNotEqual(glossary["trait"], "特殊行为以数据表为准。")
                self.assertTrue(glossary["trait"])

        self.assertIn("普通火力处理时间长", observation["zombie_glossary"]["buckethead"]["trait"])
        self.assertIn("对空命中后落地", observation["zombie_glossary"]["balloon"]["trait"])

    def test_default_reveal_pool_has_no_blank_and_is_chaotic(self) -> None:
        total_weight = sum(result.weight for result in P2_REVEAL_RESULTS.values())
        direct_good_weight = sum(
            result.weight
            for result in P2_REVEAL_RESULTS.values()
            if result.category in {"good", "rare_good"}
        )
        non_direct_good_weight = total_weight - direct_good_weight

        self.assertNotIn("bad_blank", P2_REVEAL_RESULTS)
        self.assertIn("bad_lily_pad", P2_REVEAL_RESULTS)
        self.assertIn("bad_grave_buster", P2_REVEAL_RESULTS)
        self.assertIn("bad_flower_pot", P2_REVEAL_RESULTS)
        self.assertIn("bad_sea_shroom", P2_REVEAL_RESULTS)
        self.assertIn("bad_plantern", P2_REVEAL_RESULTS)
        self.assertIn("bad_magnet_shroom", P2_REVEAL_RESULTS)
        self.assertIn("bad_fume_shroom", P2_REVEAL_RESULTS)
        self.assertIn("bad_ice_shroom", P2_REVEAL_RESULTS)
        self.assertIn("bad_doom_shroom", P2_REVEAL_RESULTS)
        self.assertNotIn("bad_coffee_bean", P2_REVEAL_RESULTS)
        self.assertIn("good_split_pea", P2_REVEAL_RESULTS)
        self.assertIn("rare_threepeater", P2_REVEAL_RESULTS)
        self.assertIn("rare_chomper", P2_REVEAL_RESULTS)
        self.assertIn("rare_cactus", P2_REVEAL_RESULTS)
        self.assertIn("rare_cattail", P2_REVEAL_RESULTS)
        self.assertIn("rare_blover", P2_REVEAL_RESULTS)
        self.assertIn("rare_spikeweed", P2_REVEAL_RESULTS)
        self.assertIn("rare_tallnut", P2_REVEAL_RESULTS)
        self.assertIn("rare_umbrella_leaf", P2_REVEAL_RESULTS)
        self.assertIn("rare_jalapeno", P2_REVEAL_RESULTS)
        self.assertIn("chaos_football_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_gargantuar_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_dancing_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_ducky_tube_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_bungee_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_pogo_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_balloon_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_catapult_zombie", P2_REVEAL_RESULTS)
        self.assertIn("chaos_zomboni_zombie", P2_REVEAL_RESULTS)
        self.assertLessEqual(direct_good_weight / total_weight, 0.45)
        self.assertGreaterEqual(non_direct_good_weight / total_weight, 0.55)

    def test_early_low_levels_cap_high_pressure_reveal_weights(self) -> None:
        engine = GameEngine(wave_schedule=[])
        base_weights = {key: result.weight for key, result in P2_REVEAL_RESULTS.items()}

        engine.state.level = 2
        engine.state.tick = 619
        early_adjusted = engine._adjust_reveal_weights(base_weights)
        self.assertEqual(early_adjusted["chaos_pole_vaulting_zombie"], 2)
        self.assertEqual(early_adjusted["chaos_football_zombie"], 1)
        self.assertEqual(base_weights["chaos_pole_vaulting_zombie"], 7)
        self.assertEqual(base_weights["chaos_football_zombie"], 3)

        engine.state.level = 3
        self.assertEqual(engine._adjust_reveal_weights(base_weights), base_weights)

        engine.state.level = 2
        engine.state.tick = 620
        self.assertEqual(engine._adjust_reveal_weights(base_weights), base_weights)

    def test_peashooter_instant_hits_nearest_zombie(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        plant = PlantInstance("p1", "peashooter", lane=3, col=3, hp=300, next_attack_tick=1)
        far = ZombieInstance("z_far", "normal", lane=3, x=8.0, hp=200)
        near = ZombieInstance("z_near", "normal", lane=3, x=4.0, hp=200)
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 3)] = plant.entity_id
        engine.state.zombies[far.entity_id] = far
        engine.state.zombies[near.entity_id] = near
        engine.step_one_tick()
        self.assertEqual(near.hp, 180)
        self.assertEqual(far.hp, 200)

    def test_repeater_hits_twice_and_snow_pea_slows(self) -> None:
        engine = GameEngine(wave_schedule=[])
        repeater = PlantInstance("p1", "repeater", lane=3, col=3, hp=300, next_attack_tick=1)
        snow_pea = PlantInstance("p2", "snow_pea", lane=2, col=3, hp=300, next_attack_tick=1)
        target = ZombieInstance("z1", "normal", lane=3, x=5.0, hp=200)
        slowed = ZombieInstance("z2", "normal", lane=2, x=5.0, hp=200)
        engine.state.plants[repeater.entity_id] = repeater
        engine.state.grid[(3, 3)] = repeater.entity_id
        engine.state.plants[snow_pea.entity_id] = snow_pea
        engine.state.grid[(2, 3)] = snow_pea.entity_id
        engine.state.zombies[target.entity_id] = target
        engine.state.zombies[slowed.entity_id] = slowed

        engine.step_one_tick()

        self.assertEqual(target.hp, 160)
        self.assertEqual(slowed.hp, 180)
        self.assertIn("slowed", slowed.status)
        self.assertAlmostEqual(slowed.x, 4.995)

    def test_threepeater_and_fume_shroom_use_special_attack_shapes(self) -> None:
        engine = GameEngine(wave_schedule=[])
        threepeater = PlantInstance("p1", "threepeater", lane=3, col=3, hp=300, next_attack_tick=1)
        fume = PlantInstance("p2", "fume_shroom", lane=5, col=3, hp=300, next_attack_tick=1, status="active,awake")
        targets = [
            ZombieInstance("z1", "normal", lane=2, x=5.0, hp=200),
            ZombieInstance("z2", "normal", lane=3, x=5.0, hp=200),
            ZombieInstance("z3", "normal", lane=4, x=5.0, hp=200),
            ZombieInstance("z4", "normal", lane=5, x=4.0, hp=200),
            ZombieInstance("z5", "normal", lane=5, x=6.5, hp=200),
        ]
        engine.state.plants[threepeater.entity_id] = threepeater
        engine.state.grid[(3, 3)] = threepeater.entity_id
        engine.state.plants[fume.entity_id] = fume
        engine.state.grid[(5, 3)] = fume.entity_id
        for zombie in targets:
            engine.state.zombies[zombie.entity_id] = zombie

        events = engine.step_one_tick()

        self.assertEqual([target.hp for target in targets], [180, 180, 180, 180, 180])
        self.assertEqual([event.type for event in events].count("plant_attack_fired"), 5)

    def test_jalapeno_reveal_and_coffee_woken_ice_shroom(self) -> None:
        jalapeno_reveal = {
            "only_jalapeno": RevealResultDef(
                "only_jalapeno",
                "rare_good",
                "plant",
                {"plant_id": "jalapeno"},
                1,
            )
        }
        engine = GameEngine(reveal_results=jalapeno_reveal, wave_schedule=[])
        lane_target = ZombieInstance("z1", "buckethead", lane=3, x=7.0, hp=1370)
        other_lane = ZombieInstance("z2", "buckethead", lane=2, x=7.0, hp=1370)
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.zombies[lane_target.entity_id] = lane_target
        engine.state.zombies[other_lane.entity_id] = other_lane
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})

        events = engine.step_one_tick()

        self.assertIn("plant_triggered", [event.type for event in events])
        self.assertNotIn(lane_target.entity_id, engine.state.zombies)
        self.assertIn(other_lane.entity_id, engine.state.zombies)

        ice_reveal = {
            "only_ice": RevealResultDef(
                "only_ice",
                "bad",
                "plant",
                {"plant_id": "ice_shroom"},
                1,
            )
        }
        config = GameConfig(card_slot_count=1, card_loadout=("coffee_bean",))
        ice_engine = GameEngine(config=config, reveal_results=ice_reveal, wave_schedule=[])
        zombie = ZombieInstance("z3", "normal", lane=3, x=7.0, hp=200)
        ice_imitator = PendingImitator("i2", 3, 3, 300, 0, 1)
        ice_engine.state.zombies[zombie.entity_id] = zombie
        ice_engine.state.grid[(3, 3)] = "i2"
        ice_engine.state.pending_imitators["i2"] = ice_imitator
        ice_engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i2", "tick": 1})
        ice_engine.step_one_tick()
        self.assertEqual(ice_engine.state.plants[ice_engine.state.grid[(3, 3)]].plant_id, "ice_shroom")

        observation = ice_engine.build_observation(
            reason=["test"],
            events=[],
            advance_summary={"from_tick": 1, "to_tick": 1, "advanced_ticks": 0, "stop_reason": "test"},
        )
        result = ice_engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_wake_ice",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "plant_card", "slot_id": "coffee_bean_1", "lane": 3, "col": 3}],
            },
            observation_id=observation["observation_id"],
        )

        self.assertTrue(result["accepted"])
        self.assertIsNone(ice_engine.state.grid[(3, 3)])
        self.assertIn("frozen_until_", zombie.status)

    def test_potato_mine_and_squash_trigger_from_engine(self) -> None:
        engine = GameEngine(wave_schedule=[])
        potato = PlantInstance("p1", "potato_mine", lane=3, col=4, hp=300, planted_tick=0)
        squash = PlantInstance("p2", "squash", lane=2, col=4, hp=300, planted_tick=0)
        potato_target = ZombieInstance("z1", "normal", lane=3, x=4.4, hp=200)
        squash_target = ZombieInstance("z2", "normal", lane=2, x=5.4, hp=200)
        engine.state.tick = 149
        engine.state.plants[potato.entity_id] = potato
        engine.state.grid[(3, 4)] = potato.entity_id
        engine.state.plants[squash.entity_id] = squash
        engine.state.grid[(2, 4)] = squash.entity_id
        engine.state.zombies[potato_target.entity_id] = potato_target
        engine.state.zombies[squash_target.entity_id] = squash_target

        events = engine.step_one_tick()

        self.assertNotIn(potato.entity_id, engine.state.plants)
        self.assertNotIn(squash.entity_id, engine.state.plants)
        self.assertNotIn(potato_target.entity_id, engine.state.zombies)
        self.assertNotIn(squash_target.entity_id, engine.state.zombies)
        self.assertEqual([event.type for event in events].count("plant_triggered"), 2)

    def test_coffee_bean_wakes_target_cell_sleeping_mushroom(self) -> None:
        config = GameConfig(card_slot_count=1, card_loadout=("coffee_bean",))
        engine = GameEngine(config=config, wave_schedule=[])
        shroom = PlantInstance("p1", "puff_shroom", lane=3, col=4, hp=300, next_attack_tick=1)
        target = ZombieInstance("z1", "normal", lane=3, x=5.0, hp=200)
        engine.state.plants[shroom.entity_id] = shroom
        engine.state.grid[(3, 4)] = shroom.entity_id
        engine.state.zombies[target.entity_id] = target
        observation = engine.run_until_decision()
        self.assertIn("plant_card", observation["valid_actions"])
        self.assertEqual(observation["action_constraints"]["card_slots"][0]["card_id"], "coffee_bean")
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_coffee",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_card", "slot_id": "coffee_bean_1", "lane": 3, "col": 4}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        event_types = [event["type"] for event in result["events"]]
        self.assertTrue(result["accepted"])
        self.assertEqual(result["executed_actions"][0]["card_id"], "coffee_bean")
        self.assertIn("plant_status_changed", event_types)
        self.assertIn("awake", shroom.status)
        self.assertEqual(target.hp, 180)

    def test_coffee_bean_does_not_wake_adjacent_sleeping_mushroom(self) -> None:
        config = GameConfig(card_slot_count=1, card_loadout=("coffee_bean",))
        engine = GameEngine(config=config, wave_schedule=[])
        shroom = PlantInstance("p1", "puff_shroom", lane=3, col=4, hp=300, next_attack_tick=1)
        engine.state.plants[shroom.entity_id] = shroom
        engine.state.grid[(3, 4)] = shroom.entity_id
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_coffee_adjacent",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_card", "slot_id": "coffee_bean_1", "lane": 3, "col": 3}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        self.assertTrue(result["accepted"])
        self.assertNotIn("awake", shroom.status.split(","))
        self.assertTrue(
            any(
                event["type"] == "plant_triggered"
                and event.get("effect") == "no_sleeping_mushroom_to_wake"
                for event in result["events"]
            )
        )

    def test_coffee_bean_without_sleeping_mushroom_is_conditional_miss(self) -> None:
        config = GameConfig(card_slot_count=1, card_loadout=("coffee_bean",))
        engine = GameEngine(config=config, wave_schedule=[])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_coffee_miss",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_card", "slot_id": "coffee_bean_1", "lane": 3, "col": 3}],
        }

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        self.assertTrue(
            any(
                event["type"] == "plant_triggered"
                and event.get("effect") == "no_sleeping_mushroom_to_wake"
                for event in result["events"]
            )
        )

    def test_pole_vaulting_jumps_over_first_blocker(self) -> None:
        engine = GameEngine(wave_schedule=[])
        blocker = PlantInstance("p1", "wallnut", lane=3, col=4, hp=4000)
        zombie = ZombieInstance("z1", "pole_vaulting", lane=3, x=4.5, hp=340)
        engine.state.plants[blocker.entity_id] = blocker
        engine.state.grid[(3, 4)] = blocker.entity_id
        engine.state.zombies[zombie.entity_id] = zombie

        events = engine.step_one_tick()

        self.assertEqual(zombie.x, 3.0)
        self.assertIn(POLE_VAULTING_SPENT_STATUS, zombie.status)
        self.assertIn(blocker.entity_id, engine.state.plants)
        self.assertIn("pole_vaulted", [event.type for event in events])

    def test_jack_explosion_and_gargantuar_throw_imp(self) -> None:
        engine = GameEngine(wave_schedule=[])
        plant = PlantInstance("p1", "wallnut", lane=3, col=4, hp=4000)
        jack = ZombieInstance("z1", "jack_in_the_box", lane=3, x=4.5, hp=500, spawned_tick=0)
        gargantuar = ZombieInstance("z2", "gargantuar", lane=4, x=8.0, hp=1500, spawned_tick=0)
        engine.state.tick = 29
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 4)] = plant.entity_id
        engine.state.zombies[jack.entity_id] = jack
        engine.state.zombies[gargantuar.entity_id] = gargantuar

        events = engine.step_one_tick()

        event_types = [event.type for event in events]
        self.assertIn("jack_in_the_box_exploded", event_types)
        self.assertNotIn(plant.entity_id, engine.state.plants)
        self.assertNotIn(jack.entity_id, engine.state.zombies)
        self.assertIn("zombie_spawned_by_special", event_types)
        self.assertTrue(any(zombie.zombie_id == "imp" for zombie in engine.state.zombies.values()))
        self.assertIn("imp_thrown", gargantuar.status)

    def test_second_batch_zombie_specials_run_in_engine(self) -> None:
        engine = GameEngine(wave_schedule=[])
        bungee_target = PlantInstance("p1", "peashooter", lane=2, col=4, hp=300)
        catapult_target = PlantInstance("p2", "wallnut", lane=4, col=5, hp=4000)
        blocker = PlantInstance("p3", "wallnut", lane=3, col=4, hp=4000)
        cactus = PlantInstance("p4", "cactus", lane=3, col=2, hp=300, next_attack_tick=41)
        bungee = ZombieInstance("z1", "bungee", lane=2, x=4.0, hp=450, spawned_tick=0)
        dancing = ZombieInstance("z2", "dancing", lane=1, x=7.0, hp=500, spawned_tick=0)
        catapult = ZombieInstance("z3", "catapult", lane=4, x=8.0, hp=850, spawned_tick=0)
        balloon = ZombieInstance("z4", "balloon", lane=3, x=4.5, hp=290, spawned_tick=0)
        engine.state.tick = 9
        for plant in (bungee_target, catapult_target, blocker, cactus):
            engine.state.plants[plant.entity_id] = plant
            engine.state.grid[(plant.lane, plant.col)] = plant.entity_id
        for zombie in (bungee, dancing, catapult, balloon):
            engine.state.zombies[zombie.entity_id] = zombie

        bungee_events = engine.step_one_tick()
        self.assertIn("bungee_stole_plant", [event.type for event in bungee_events])
        self.assertNotIn(bungee_target.entity_id, engine.state.plants)
        self.assertNotIn(bungee.entity_id, engine.state.zombies)

        engine.state.tick = 29
        dancing_events = engine.step_one_tick()
        self.assertIn("zombie_spawned_by_special", [event.type for event in dancing_events])
        self.assertTrue(any(zombie.zombie_id == "backup_dancer" for zombie in engine.state.zombies.values()))

        engine.state.tick = 39
        catapult_events = engine.step_one_tick()
        self.assertIn("catapult_launched_basketball", [event.type for event in catapult_events])
        self.assertEqual(catapult_target.hp, 3920)

        balloon_events = engine.step_one_tick()
        self.assertIn("zombie_status_changed", [event.type for event in balloon_events])
        self.assertIn("balloon_popped", balloon.status)
        self.assertEqual(balloon.target_entity_id, blocker.entity_id)

    def test_plain_projectiles_do_not_target_airborne_balloon_but_anti_air_does(self) -> None:
        engine = GameEngine(wave_schedule=[])
        peashooter = PlantInstance("p1", "peashooter", lane=3, col=2, hp=300, next_attack_tick=1)
        balloon = ZombieInstance("z1", "balloon", lane=3, x=5.0, hp=290, spawned_tick=0)
        engine.state.plants[peashooter.entity_id] = peashooter
        engine.state.grid[(3, 2)] = peashooter.entity_id
        engine.state.zombies[balloon.entity_id] = balloon

        events = engine.step_one_tick()

        self.assertNotIn("plant_attack_fired", [event.type for event in events])
        self.assertNotIn("balloon_popped", balloon.status)

        cactus = PlantInstance("p2", "cactus", lane=3, col=1, hp=300, next_attack_tick=2)
        engine.state.plants[cactus.entity_id] = cactus
        engine.state.grid[(3, 1)] = cactus.entity_id
        events = engine.step_one_tick()

        self.assertIn("plant_attack_fired", [event.type for event in events])
        self.assertIn("balloon_popped", balloon.status)

    def test_blover_removes_airborne_balloons_from_reveal(self) -> None:
        reveal_results = {
            "only_blover": RevealResultDef(
                "only_blover",
                "rare_good",
                "plant",
                {"plant_id": "blover"},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[(9999, "normal", 3)])
        balloon = ZombieInstance("z1", "balloon", lane=2, x=5.0, hp=290, spawned_tick=0)
        normal = ZombieInstance("z2", "normal", lane=2, x=5.0, hp=200, spawned_tick=0)
        engine.state.zombies[balloon.entity_id] = balloon
        engine.state.zombies[normal.entity_id] = normal
        imitator = PendingImitator("i1", 2, 3, 300, 0, 1)
        engine.state.pending_imitators[imitator.entity_id] = imitator
        engine.state.grid[(2, 3)] = imitator.entity_id

        events = engine.step_one_tick()

        event_types = [event.type for event in events]
        self.assertIn("plant_triggered", event_types)
        self.assertNotIn(balloon.entity_id, engine.state.zombies)
        self.assertIn(normal.entity_id, engine.state.zombies)

    def test_magnet_spikeweed_umbrella_and_tallnut_counters(self) -> None:
        engine = GameEngine(wave_schedule=[])
        magnet = PlantInstance("p1", "magnet_shroom", lane=3, col=3, hp=300, next_attack_tick=1, status="active,awake")
        bucket = ZombieInstance("z1", "buckethead", lane=3, x=7.0, hp=1370, spawned_tick=0)
        engine.state.plants[magnet.entity_id] = magnet
        engine.state.grid[(3, 3)] = magnet.entity_id
        engine.state.zombies[bucket.entity_id] = bucket

        events = engine.step_one_tick()

        self.assertIn("plant_triggered", [event.type for event in events])
        self.assertIn("metal_removed", bucket.status)
        self.assertLess(bucket.hp, 1370)

        engine = GameEngine(wave_schedule=[])
        spike = PlantInstance("p2", "spikeweed", lane=3, col=4, hp=300, next_attack_tick=1)
        zomboni = ZombieInstance("z2", "zomboni", lane=3, x=4.2, hp=1350, spawned_tick=0)
        engine.state.plants[spike.entity_id] = spike
        engine.state.grid[(3, 4)] = spike.entity_id
        engine.state.zombies[zomboni.entity_id] = zomboni

        events = engine.step_one_tick()

        self.assertIn("plant_triggered", [event.type for event in events])
        self.assertNotIn(spike.entity_id, engine.state.plants)
        self.assertNotIn(zomboni.entity_id, engine.state.zombies)

        engine = GameEngine(wave_schedule=[])
        target = PlantInstance("p3", "peashooter", lane=2, col=4, hp=300)
        umbrella = PlantInstance("p4", "umbrella_leaf", lane=2, col=5, hp=300)
        bungee = ZombieInstance("z3", "bungee", lane=2, x=4.0, hp=450, spawned_tick=0)
        engine.state.tick = 9
        for plant in (target, umbrella):
            engine.state.plants[plant.entity_id] = plant
            engine.state.grid[(plant.lane, plant.col)] = plant.entity_id
        engine.state.zombies[bungee.entity_id] = bungee

        events = engine.step_one_tick()

        self.assertIn("bungee_blocked_by_umbrella", [event.type for event in events])
        self.assertIn(target.entity_id, engine.state.plants)

        engine = GameEngine(wave_schedule=[])
        wallnut = PlantInstance("p5", "wallnut", lane=3, col=4, hp=4000)
        pogo = ZombieInstance("z4", "pogo", lane=3, x=4.5, hp=500, spawned_tick=0)
        engine.state.plants[wallnut.entity_id] = wallnut
        engine.state.grid[(3, 4)] = wallnut.entity_id
        engine.state.zombies[pogo.entity_id] = pogo
        jumped_events = engine.step_one_tick()
        self.assertIn("pogo_jumped", [event.type for event in jumped_events])

        engine = GameEngine(wave_schedule=[])
        tallnut = PlantInstance("p6", "tallnut", lane=3, col=4, hp=8000)
        blocked_pogo = ZombieInstance("z5", "pogo", lane=3, x=4.5, hp=500, spawned_tick=0)
        engine.state.plants[tallnut.entity_id] = tallnut
        engine.state.grid[(3, 4)] = tallnut.entity_id
        engine.state.zombies[blocked_pogo.entity_id] = blocked_pogo
        blocked_events = engine.step_one_tick()
        self.assertNotIn("pogo_jumped", [event.type for event in blocked_events])
        self.assertEqual(blocked_pogo.target_entity_id, tallnut.entity_id)

    def test_reveal_spawned_zomboss_boss_event_acts_and_ends(self) -> None:
        reveal_results = {
            "only_zomboss": RevealResultDef(
                "only_zomboss",
                "chaos",
                "boss_event",
                {"boss_id": "zomboss", "duration_ticks": 4, "action_interval_ticks": 1},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[(9999, "normal", 3)])
        plant = PlantInstance("p1", "wallnut", lane=3, col=4, hp=4000)
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 4)] = plant.entity_id
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})

        reveal_events = engine.step_one_tick()
        boss_event = next(event for event in reveal_events if event.type == "reveal_spawned_boss_event")
        self.assertEqual(boss_event.payload["flavor_text"], "模仿者把场面叫大了，僵王博士也来签到。")
        self.assertEqual(len(engine.state.boss_events), 1)

        summon_events = engine.step_one_tick()
        self.assertIn("boss_event_action", [event.type for event in summon_events])
        self.assertTrue(any(event.payload.get("action") == "summon_zombie" for event in summon_events))
        self.assertTrue(any(zombie.zombie_id == "normal" for zombie in engine.state.zombies.values()))

        smash_events = engine.step_one_tick()
        smash_event = next(
            event for event in smash_events if event.type == "boss_event_action" and event.payload["action"] == "smash_cell"
        )
        self.assertEqual(smash_event.payload["destroyed_type"], "plant")
        self.assertNotIn(plant.entity_id, engine.state.plants)
        self.assertIsNone(engine.state.grid[(3, 4)])

        engine.step_one_tick()
        ended_events = engine.step_one_tick()
        self.assertIn("boss_event_ended", [event.type for event in ended_events])
        self.assertFalse(engine.state.boss_events)

    def test_boss_event_blocks_win_until_it_ends(self) -> None:
        reveal_results = {
            "only_zomboss": RevealResultDef(
                "only_zomboss",
                "chaos",
                "boss_event",
                {"boss_id": "zomboss", "duration_ticks": 2, "action_interval_ticks": 10},
                1,
            )
        }
        engine = GameEngine(reveal_results=reveal_results, wave_schedule=[])
        engine.state.wave_state = {"spawned_count": 0, "total": 1, "completed": True}
        imitator = PendingImitator("i1", 3, 3, 300, 0, 1)
        engine.state.grid[(3, 3)] = "i1"
        engine.state.pending_imitators["i1"] = imitator
        engine.state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1", "tick": 1})

        engine.step_one_tick()
        self.assertFalse(engine.state.game_over)
        engine.step_one_tick()
        self.assertFalse(engine.state.game_over)
        engine.step_one_tick()
        self.assertEqual(engine.state.result, "won")

    def test_lawnmower_clears_entire_lane_in_engine_tick(self) -> None:
        engine = GameEngine(wave_schedule=[])
        first = ZombieInstance("z1", "normal", lane=3, x=0.0, hp=200)
        second = ZombieInstance("z2", "conehead", lane=3, x=0.0, hp=640)
        behind = ZombieInstance("z3", "buckethead", lane=3, x=2.0, hp=1370)
        other_lane = ZombieInstance("z4", "normal", lane=4, x=2.0, hp=200)
        for zombie in (first, second, behind, other_lane):
            engine.state.zombies[zombie.entity_id] = zombie

        events = engine.step_one_tick()

        event_types = [event.type for event in events]
        self.assertIn("lawnmower_triggered", event_types)
        self.assertIn("lawnmower_cleared_lane", event_types)
        self.assertFalse(engine.state.lawnmowers[3])
        self.assertFalse(engine.state.game_over)
        self.assertNotIn("z1", engine.state.zombies)
        self.assertNotIn("z2", engine.state.zombies)
        self.assertNotIn("z3", engine.state.zombies)
        self.assertIn("z4", engine.state.zombies)

    def test_run_recap_summarizes_loss_without_player_notes(self) -> None:
        engine = GameEngine(wave_schedule=[], run_id="loss_recap")
        engine.state.lawnmowers[3] = False
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=3, x=0.0, hp=200)

        engine.step_one_tick()

        recap = engine.build_run_recap()
        self.assertEqual(recap["run_id"], "loss_recap")
        self.assertEqual(recap["result"], "lost")
        self.assertEqual(recap["loss_lane"], 3)
        self.assertTrue(any("game lost" in line for line in recap["key_events"]))

    def test_game_over_stops_ticks_and_does_not_repeat_loss(self) -> None:
        engine = GameEngine(wave_schedule=[])
        engine.state.lawnmowers[3] = False
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=3, x=0.0, hp=200)
        engine.state.zombies["z2"] = ZombieInstance("z2", "conehead", lane=3, x=0.0, hp=640)

        events = engine.step_one_tick()

        self.assertEqual([event.type for event in events].count("game_lost"), 1)
        self.assertEqual(engine.state.result, "lost")
        terminal_tick = engine.state.tick
        self.assertEqual(engine.step_one_tick(), [])
        self.assertEqual(engine.state.tick, terminal_tick)

    def test_action_plan_stops_when_decision_delay_loses(self) -> None:
        engine = GameEngine(wave_schedule=[])
        observation = engine.run_until_decision()
        engine.state.lawnmowers[3] = False
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=3, x=0.01, hp=200)
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_delay_loss",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 1}],
        }

        result = engine.apply_action_plan(
            plan,
            observation_id=observation["observation_id"],
            real_elapsed_seconds=45,
        )

        self.assertEqual(engine.state.result, "lost")
        self.assertEqual(result["advance_summary"]["stop_reason"], "delay_lost")
        self.assertFalse(result["need_next_decision"])
        self.assertEqual(result["executed_actions"], [])
        self.assertIsNone(engine.state.grid[(3, 1)])
        self.assertNotIn("imitator_planted", [event["type"] for event in result["events"]])

    def test_player_can_end_game_without_decision_delay_and_restart_from_level_1(self) -> None:
        engine = GameEngine(wave_schedule=[], run_id="manual_end")
        engine.state.level = 4
        observation = engine.run_until_decision()
        plan = {
            "schema_version": 1,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_end_game",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "end_game", "reason": "bad opening"}],
        }

        result = engine.apply_action_plan(
            plan,
            observation_id=observation["observation_id"],
            real_elapsed_seconds=45,
        )

        self.assertEqual(engine.state.result, "ended_by_player")
        self.assertEqual(engine.state.tick, 0)
        self.assertFalse(result["need_next_decision"])
        self.assertEqual(result["advance_summary"]["stop_reason"], "ended_by_player")
        self.assertEqual(result["observation"]["game_status"], "ended_by_player")
        self.assertEqual(result["observation"]["valid_actions"], [])
        end_event = next(event for event in result["events"] if event["type"] == "game_ended_by_player")
        self.assertEqual(end_event["restart_level"], 1)
        self.assertEqual(end_event["reason"], "bad opening")
        self.assertNotIn("action_delay_charged", [event["type"] for event in result["events"]])
        self.assertEqual(engine.build_run_recap()["result"], "ended_by_player")

    def test_player_view_renders_board_text_and_first_seen_traits(self) -> None:
        engine = GameEngine(wave_schedule=[])
        plant = PlantInstance("p1", "peashooter", lane=3, col=3, hp=300)
        zombie = ZombieInstance("z1", "normal", lane=3, x=3.0, hp=200, target_entity_id="p1")
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 3)] = plant.entity_id
        engine.state.zombies[zombie.entity_id] = zombie

        observation = engine.run_until_decision()

        view = observation["player_view"]
        self.assertEqual(view["format"], "board_text_v1")
        self.assertIn("列: 1 2 3 4 5 6 7 8 9", view["text"])
        self.assertIn("3: 空 空 豌+普咬 空 空 空 空 空 空", view["text"])
        self.assertIn("卡槽:", view["text"])
        self.assertIn("动作:", view["text"])
        self.assertEqual(
            {(item["kind"], item["id"]) for item in view["new_unit_traits"]},
            {("plant", "peashooter"), ("zombie", "normal")},
        )

        next_observation = engine.build_observation(reason=[], events=[], advance_summary={})
        self.assertEqual(next_observation["player_view"]["new_unit_traits"], [])

    def test_player_view_renders_pending_imitator_and_zombie_stack(self) -> None:
        engine = GameEngine(wave_schedule=[])
        engine.run_until_decision()
        engine.apply_action_plan(
            {
                "schema_version": 1,
                "observation_id": "obs_1",
                "action_plan_id": "plan_view_stack",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "plant_imitator", "lane": 2, "col": 4}],
            },
            observation_id="obs_1",
        )
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=2, x=4.0, hp=200)
        engine.state.zombies["z2"] = ZombieInstance("z2", "normal", lane=2, x=4.1, hp=200)

        observation = engine.build_observation(reason=[], events=[], advance_summary={})

        self.assertIn("2: 空 空 空 模+普x2", observation["player_view"]["text"])

    def test_player_view_puts_reveal_events_before_board(self) -> None:
        engine = GameEngine(wave_schedule=[])

        observation = engine.build_observation(
            reason=[],
            events=[
                {
                    "type": "reveal_spawned_zombie",
                    "lane": 3,
                    "x": 4.5,
                    "zombie_type": "normal",
                    "flavor_text": "模仿者这次站到了僵尸队。",
                }
            ],
            advance_summary={},
        )

        text = observation["player_view"]["text"]
        self.assertLess(text.index("事件:"), text.index("列: 1 2 3 4 5 6 7 8 9"))
        self.assertIn("3路4.5列开奖: 模仿者这次站到了僵尸队。", text)

    def test_player_view_explains_shovel_failures_and_jack_explosion(self) -> None:
        engine = GameEngine(wave_schedule=[])

        observation = engine.build_observation(
            reason=[],
            events=[
                {
                    "type": "jack_in_the_box_exploded",
                    "lane": 2,
                    "x": 7.1,
                    "destroyed_plants": ["p1", "p2"],
                    "destroyed_imitators": ["i1"],
                },
                {"type": "action_failed", "reason": "target_cell_empty"},
            ],
            advance_summary={},
        )

        text = observation["player_view"]["text"]
        self.assertIn("2路小丑盒爆炸，摧毁2个植物和1个未开奖模仿者", text)
        self.assertIn("动作失败(后续未执行): 该格没有可铲植物或未开奖模仿者", text)
        self.assertIn("咖啡豆会唤醒目标格的沉睡蘑菇", text)
        self.assertIn("铲子只移除植物/未开奖模仿者", text)
        self.assertIn("动作失败会中断后续动作", text)
        self.assertIn("已发生的推进保留", text)

    def test_player_view_reports_zombie_death_and_imitator_destroyed(self) -> None:
        engine = GameEngine(wave_schedule=[])

        observation = engine.build_observation(
            reason=[],
            events=[
                {"type": "zombie_died", "zombie_type": "conehead", "lane": 3, "x": 4.2},
                {"type": "imitator_destroyed_before_reveal", "lane": 2, "col": 5},
            ],
            advance_summary={},
        )

        self.assertIn("3路4.2列 路障僵尸被消灭", observation["player_view"]["text"])
        self.assertIn("2路5列未开奖模仿者被吃掉", observation["player_view"]["text"])

    def test_player_view_marks_unarmed_potato_mine(self) -> None:
        engine = GameEngine(wave_schedule=[])
        potato = PlantInstance("p1", "potato_mine", lane=5, col=4, hp=300, planted_tick=0)
        engine.state.tick = 20
        engine.state.plants[potato.entity_id] = potato
        engine.state.grid[(5, 4)] = potato.entity_id

        observation = engine.build_observation(reason=[], events=[], advance_summary={})

        self.assertIn("5: 空 空 空 土待 空 空 空 空 空", observation["player_view"]["text"])

    def test_night_stage_keeps_mushrooms_awake_in_engine_and_view(self) -> None:
        config = GameConfig(is_day=False)
        engine = GameEngine(config=config, wave_schedule=[])
        plant = PlantInstance("p1", "puff_shroom", lane=3, col=3, hp=300, next_attack_tick=1)
        zombie = ZombieInstance("z1", "normal", lane=3, x=5.0, hp=200)
        engine.state.plants[plant.entity_id] = plant
        engine.state.grid[(3, 3)] = plant.entity_id
        engine.state.zombies[zombie.entity_id] = zombie

        observation = engine.build_observation(reason=[], events=[], advance_summary={})

        self.assertIn("场地:夜间", observation["player_view"]["text"])
        self.assertIn("3: 空 空 小 空 普", observation["player_view"]["text"])
        self.assertNotIn("小睡", observation["player_view"]["text"])
        events = engine.step_one_tick()
        self.assertIn("plant_attack_fired", [event.type for event in events])

    def test_parse_player_text_action_plan_uses_existing_contract(self) -> None:
        config = GameConfig(card_loadout=("peashooter", "coffee_bean"), card_slot_count=3)
        engine = GameEngine(config=config, wave_schedule=[])
        observation = engine.run_until_decision()

        plan = parse_player_text_action_plan(
            "种 模仿者 3-4\n种 豌豆射手 1-2\n种 咖啡豆 2-3\n开空投 5-6\n铲 4-5\n等待",
            observation=observation,
            action_plan_id="plan_text",
        )

        self.assertEqual(plan["action_plan_id"], "plan_text")
        self.assertEqual(
            plan["actions"],
            [
                {"action": "plant_imitator", "lane": 3, "col": 4},
                {"action": "plant_card", "lane": 1, "col": 2, "slot_id": "peashooter_1"},
                {"action": "plant_card", "lane": 2, "col": 3, "slot_id": "coffee_bean_1"},
                {"action": "open_airdrop", "lane": 5, "col": 6},
                {"action": "shovel_plant", "lane": 4, "col": 5},
                {"action": "wait", "max_wait_ticks": 80},
            ],
        )
        validate_action_plan(plan, config=config, observation_id=observation["observation_id"])

    def test_airdrop_pool_contains_only_strong_plants_or_zombies(self) -> None:
        forbidden_plants = {"grave_buster", "lily_pad", "flower_pot", "coffee_bean", "plantern"}
        for outcome in AIRDROP_OUTCOME_WEIGHTS:
            self.assertNotEqual(outcome, "empty")
            self.assertNotIn("zomboss", outcome)
            self.assertTrue(outcome.startswith("plant_") or outcome.startswith("zombie_"))
            if outcome.startswith("plant_"):
                self.assertNotIn(outcome.removeprefix("plant_"), forbidden_plants)

    def test_airdrop_drops_on_empty_cell_occupies_without_blocking(self) -> None:
        config = GameConfig(
            enable_airdrops=True,
            is_endless=True,
            airdrop_start_tick=1,
            airdrop_min_interval_ticks=999,
            airdrop_max_interval_ticks=999,
        )
        engine = GameEngine(config=config, wave_schedule=[], seed="airdrop-drop")

        summary = engine.advance_until(max_ticks=1)

        self.assertIn("airdrop_dropped", [event["type"] for event in summary["events"]])
        self.assertEqual(len(engine.state.airdrops), 1)
        airdrop = next(iter(engine.state.airdrops.values()))
        self.assertEqual(engine.state.grid[(airdrop.lane, airdrop.col)], airdrop.entity_id)

        zombie = ZombieInstance("zpass", "normal", lane=airdrop.lane, x=airdrop.col + 0.5, hp=200, spawned_tick=0)
        engine.state.zombies[zombie.entity_id] = zombie
        before_x = zombie.x
        move_events = engine._zombie_move()

        self.assertLess(zombie.x, before_x)
        self.assertIsNone(zombie.target_entity_id)
        self.assertNotIn("zombie_started_eating", [event.type for event in move_events])

    def test_airdrop_can_be_opened_by_player_or_passing_zombie(self) -> None:
        config = GameConfig(enable_airdrops=True, is_endless=True)
        engine = GameEngine(config=config, wave_schedule=[], seed="airdrop-open")
        airdrop = AirdropInstance("a1", lane=3, col=4, dropped_tick=0, expires_tick=500)
        engine.state.airdrops[airdrop.entity_id] = airdrop
        engine.state.grid[(3, 4)] = airdrop.entity_id
        observation = engine.run_until_decision()
        plan = parse_player_text_action_plan("开空投 3-4", observation=observation, action_plan_id="open_airdrop")

        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])

        event_types = [event["type"] for event in result["events"]]
        self.assertIn("airdrop_opened", event_types)
        self.assertFalse(engine.state.airdrops)
        self.assertNotIn("empty", [event.get("outcome") for event in result["events"]])

        engine = GameEngine(config=config, wave_schedule=[], seed="airdrop-zombie-open")
        airdrop = AirdropInstance("a2", lane=2, col=5, dropped_tick=0, expires_tick=500)
        engine.state.airdrops[airdrop.entity_id] = airdrop
        engine.state.grid[(2, 5)] = airdrop.entity_id
        engine.state.zombies["z1"] = ZombieInstance("z1", "normal", lane=2, x=5.0, hp=200, spawned_tick=0)

        events = engine.step_one_tick()

        self.assertIn("airdrop_opened", [event.type for event in events])
        self.assertFalse(engine.state.airdrops)

    def test_airdrop_is_cleared_by_bomb_without_opening(self) -> None:
        config = GameConfig(enable_airdrops=True, is_endless=True)
        engine = GameEngine(config=config, wave_schedule=[], seed="airdrop-clear")
        airdrop = AirdropInstance("a1", lane=3, col=4, dropped_tick=0, expires_tick=500)
        engine.state.airdrops[airdrop.entity_id] = airdrop
        engine.state.grid[(3, 4)] = airdrop.entity_id

        events = engine._trigger_jalapeno(3, 1, "cause_event")

        event_types = [event.type for event in events]
        self.assertIn("airdrop_cleared", event_types)
        self.assertNotIn("airdrop_opened", event_types)
        self.assertFalse(engine.state.airdrops)

    def test_level_1_has_reproducible_winning_seed_with_tool_delay(self) -> None:
        engine = GameEngine(
            seed="sim-L1-tool_45-6",
            wave_schedule=build_wave_schedule(1),
            run_id="lv1_can_win_tool45_wave_v1",
        )
        engine.state.level = 1
        player = PressureScriptedPlayer()
        observation = engine.run_until_decision()

        decisions = 0
        while not engine.state.game_over and decisions < 80 and engine.state.tick < 3000:
            plan = player.decide(observation)
            result = engine.apply_action_plan(
                plan,
                observation_id=observation["observation_id"],
                real_elapsed_seconds=45,
            )
            decisions += 1
            observation = result["observation"]

        self.assertEqual(engine.state.result, "won")
        self.assertLessEqual(decisions, 80)
        self.assertLessEqual(engine.state.tick, 3000)
        self.assertEqual(engine.build_run_recap()["result"], "won")

    def test_scripted_player_returns_valid_action_plan(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        plan = ScriptedPlayer().decide(observation)
        validate_action_plan(plan, observation_id=observation["observation_id"])


if __name__ == "__main__":
    unittest.main()
