from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.game.config import GameConfig, PHASE_ORDER, SCHEMA_VERSION
from random_imitator_td.game.contracts import (
    ContractError,
    action_failed_result,
    minimal_observation,
    normalize_action_plan,
    validate_action_plan,
    validate_action_result,
    validate_observation,
)
from random_imitator_td.game.engine import (
    cell_block_threshold,
    destroy_pending_imitator,
    place_pending_imitator,
    resolve_home_entry,
    zombie_can_bite_cell,
)
from random_imitator_td.game.events import EVENT_TYPES, Event, event_sort_key
from random_imitator_td.game.models import (
    GameState,
    PendingImitator,
    PlantDef,
    PlantInstance,
    RevealResultDef,
    ZombieDef,
    ZombieInstance,
    initial_state,
    to_jsonable,
)
from random_imitator_td.game.randomizer import ReplayRng


class ImitatorPvzP0Tests(unittest.TestCase):
    def test_models_are_json_serializable(self) -> None:
        config = GameConfig()
        state = initial_state(config)
        samples = [
            config,
            PlantDef("peashooter", 300, 14, 20, "lane_forward"),
            ZombieDef("normal", 200, 0.10, 100, 1),
            RevealResultDef("good_peashooter", "good", "plant", {"plant_id": "peashooter"}, 10),
            PlantInstance("p1", "peashooter", 3, 3, 300),
            PendingImitator("i1", 3, 4, 300, 0, 30),
            ZombieInstance("z1", "normal", 3, config.spawn_x, 200),
            Event("evt_1", 0, "scheduled_actions", "imitator_planted", "normal", {}),
            state,
        ]
        for sample in samples:
            json.dumps(to_jsonable(sample), sort_keys=True)

    def test_board_coordinate_contract(self) -> None:
        config = GameConfig()
        self.assertEqual(list(config.lanes_range()), [1, 2, 3, 4, 5])
        self.assertEqual(list(config.cols_range()), [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(config.home_x, 0.0)
        self.assertEqual(config.spawn_x, 10.0)
        self.assertEqual(cell_block_threshold(4), 4.5)
        zombie = ZombieInstance("z1", "normal", lane=2, x=4.5, hp=200)
        self.assertTrue(zombie_can_bite_cell(zombie, 2, 4))
        self.assertFalse(zombie_can_bite_cell(zombie, 1, 4))
        self.assertFalse(zombie_can_bite_cell(ZombieInstance("z2", "normal", lane=2, x=0.1, hp=200), 2, 4))
        self.assertFalse(zombie_can_bite_cell(ZombieInstance("z3", "normal", lane=2, x=4.6, hp=200), 2, 4))

    def test_same_seed_same_rng_rolls(self) -> None:
        first = ReplayRng("seed-safe")
        second = ReplayRng("seed-safe")
        pool = ["plant", "blank", "zombie"]
        weights = {"plant": 5, "blank": 2, "zombie": 1}
        self.assertEqual(
            first.roll("reveal", "imitator_reveal", pool, weights, {"lane": 3}, tick=30),
            second.roll("reveal", "imitator_reveal", pool, weights, {"lane": 3}, tick=30),
        )
        self.assertEqual(to_jsonable(first.rolls), to_jsonable(second.rolls))

    def test_replay_rng_snapshot_restores_stream_state(self) -> None:
        original = ReplayRng("snapshot-seed")
        pool = ["plant", "blank", "zombie"]
        weights = {"plant": 5, "blank": 2, "zombie": 1}
        first_roll = original.roll("reveal", "test", pool, weights, tick=1)
        restored = ReplayRng.from_snapshot(original.snapshot())

        self.assertEqual(restored.seed, "snapshot-seed")
        self.assertEqual(restored.rolls[0].selected, first_roll)
        self.assertEqual(
            restored.roll("reveal", "test", pool, weights, tick=2),
            original.roll("reveal", "test", pool, weights, tick=2),
        )

    def test_same_seed_same_event_log(self) -> None:
        first_events = self._deterministic_event_log("seed-log")
        second_events = self._deterministic_event_log("seed-log")
        self.assertEqual(to_jsonable(first_events), to_jsonable(second_events))

    def test_tick_phase_order_is_stable(self) -> None:
        self.assertEqual(
            PHASE_ORDER,
            (
                "scheduled_actions",
                "reveal",
                "plant_status",
                "plant_attack",
                "projectile",
                "zombie_status",
                "zombie_move",
                "zombie_bite",
                "lawnmower_home",
                "wave_spawn",
                "scheduler",
                "win_loss",
            ),
        )

    def test_tick_phase_order_exact_events(self) -> None:
        events = [
            Event("evt_bite", 10, "zombie_bite", "zombie_bite", "normal", {}),
            Event("evt_reveal", 10, "reveal", "imitator_revealed", "strong", {}),
            Event("evt_action", 10, "scheduled_actions", "action_started", "normal", {}),
        ]
        ordered = [event.event_id for event in sorted(events, key=event_sort_key)]
        self.assertEqual(ordered, ["evt_action", "evt_reveal", "evt_bite"])

    def test_special_behavior_event_types_are_registered(self) -> None:
        for event_type in (
            "pole_vaulted",
            "jack_in_the_box_exploded",
            "zombie_spawned_by_special",
            "reveal_spawned_boss_event",
            "boss_event_action",
            "boss_event_ended",
        ):
            self.assertIn(event_type, EVENT_TYPES)

    def test_observation_action_result_contract(self) -> None:
        observation = minimal_observation()
        validate_observation(observation)
        action_plan = {
            "schema_version": SCHEMA_VERSION,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_1",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        validate_action_plan(action_plan)
        validate_action_plan(
            {
                "schema_version": SCHEMA_VERSION,
                "observation_id": observation["observation_id"],
                "action_plan_id": "plan_end_game",
                "interrupt_policy": "interrupt_on_emergency",
                "actions": [{"action": "end_game", "reason": "restart"}],
            }
        )
        result = action_failed_result(
            action_plan_id="plan_1",
            action_index=0,
            action="plant_imitator",
            reason="target_cell_no_longer_empty",
            observation=observation,
        )
        validate_action_result(result)

    def test_action_plan_normalizes_model_player_aliases(self) -> None:
        raw_plan = {
            "schema_version": SCHEMA_VERSION,
            "observation_id": "obs_1",
            "action_plan_id": "plan_aliases",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [
                {"action": "plant_imitator", "row": "3", "col": "4", "card": 2},
                {"action": "plant_card", "row": 3, "col": 4, "card_id": "coffee_bean", "slot_id": "1"},
            ],
        }

        normalized = normalize_action_plan(
            raw_plan,
            config=GameConfig(card_slot_count=2, card_loadout=("coffee_bean",)),
            observation_id="obs_1",
        )

        self.assertEqual(
            normalized["actions"],
            [
                {"action": "plant_imitator", "lane": 3, "col": 4, "slot_id": "imitator_2"},
                {"action": "plant_card", "lane": 3, "col": 4, "slot_id": "coffee_bean_1"},
            ],
        )
        self.assertIn("row", raw_plan["actions"][0])
        self.assertIn("card", raw_plan["actions"][0])
        validate_action_plan(normalized, observation_id="obs_1")

    def test_action_plan_schema_rejects_invalid(self) -> None:
        base = {
            "schema_version": SCHEMA_VERSION,
            "observation_id": "obs_1",
            "action_plan_id": "plan_1",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        invalid_unknown_action = {**base, "actions": [{"action": "dance"}]}
        invalid_wait_order = {
            **base,
            "actions": [{"action": "wait"}, {"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        invalid_unknown_field = {**base, "surprise": True}
        invalid_action_field = {
            **base,
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3, "surprise": True}],
        }
        invalid_wait_until_field = {**base, "actions": [{"action": "wait", "until": [{"type": "next_strong_event"}]}]}
        invalid_wait_negative_ticks = {
            **base,
            "actions": [{"action": "wait", "max_wait_ticks": -1}],
        }
        invalid_end_game_combo = {
            **base,
            "actions": [{"action": "end_game"}, {"action": "wait", "max_wait_ticks": 1}],
        }
        invalid_end_game_reason = {
            **base,
            "actions": [{"action": "end_game", "reason": 123}],
        }
        invalid_interrupt_policy = {**base, "interrupt_policy": "whatever"}
        invalid_out_of_bounds = {
            **base,
            "actions": [{"action": "plant_imitator", "lane": 99, "col": 3}],
        }
        for action_plan in (
            invalid_unknown_action,
            invalid_wait_order,
            invalid_unknown_field,
            invalid_action_field,
            invalid_wait_until_field,
            invalid_wait_negative_ticks,
            invalid_end_game_combo,
            invalid_end_game_reason,
            invalid_interrupt_policy,
            invalid_out_of_bounds,
        ):
            with self.assertRaises(ContractError):
                validate_action_plan(action_plan)

    def test_action_plan_rejects_old_observation(self) -> None:
        action_plan = {
            "schema_version": SCHEMA_VERSION,
            "observation_id": "obs_old",
            "action_plan_id": "plan_1",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        with self.assertRaises(ContractError):
            validate_action_plan(action_plan, observation_id="obs_new")

    def test_observation_schema_minimal_fields(self) -> None:
        observation = minimal_observation()
        observation.pop("game_status")
        with self.assertRaises(ContractError):
            validate_observation(observation)

    def test_zombie_reaches_home_triggers_lawnmower_or_loss(self) -> None:
        config = GameConfig()
        state = initial_state(config)
        zombie = ZombieInstance("z1", "normal", lane=2, x=config.home_x, hp=200)
        state.zombies[zombie.entity_id] = zombie
        events = resolve_home_entry(state, zombie, config)
        self.assertFalse(state.game_over)
        self.assertFalse(state.lawnmowers[2])
        self.assertNotIn("z1", state.zombies)
        self.assertEqual(
            [event.type for event in events],
            ["lawnmower_triggered", "lawnmower_cleared_lane", "lawnmower_consumed"],
        )

    def test_lawnmower_then_loss_rules(self) -> None:
        config = GameConfig()
        state = initial_state(config)
        state.lawnmowers[2] = False
        zombie = ZombieInstance("z2", "normal", lane=2, x=config.home_x, hp=200)
        state.zombies[zombie.entity_id] = zombie
        events = resolve_home_entry(state, zombie, config)
        self.assertTrue(state.game_over)
        self.assertEqual(state.result, "lost")
        self.assertEqual(events[0].type, "game_lost")

    def test_lawnmower_clears_lane_and_prevents_same_tick_loss(self) -> None:
        config = GameConfig()
        state = initial_state(config)
        first = ZombieInstance("z1", "normal", lane=2, x=config.home_x, hp=200)
        second = ZombieInstance("z2", "normal", lane=2, x=config.home_x, hp=200)
        behind = ZombieInstance("z3", "conehead", lane=2, x=config.home_x + 3, hp=640)
        other_lane = ZombieInstance("z4", "normal", lane=3, x=config.home_x, hp=200)
        state.zombies[first.entity_id] = first
        state.zombies[second.entity_id] = second
        state.zombies[behind.entity_id] = behind
        state.zombies[other_lane.entity_id] = other_lane
        first_events = resolve_home_entry(state, first, config)
        second_events = resolve_home_entry(state, second, config)
        self.assertEqual(first_events[0].type, "lawnmower_triggered")
        self.assertEqual(first_events[1].type, "lawnmower_cleared_lane")
        self.assertEqual(set(first_events[1].payload["cleared_zombie_ids"]), {"z1", "z2", "z3"})
        self.assertEqual(second_events, [])
        self.assertFalse(state.game_over)
        self.assertNotIn("z1", state.zombies)
        self.assertNotIn("z2", state.zombies)
        self.assertNotIn("z3", state.zombies)
        self.assertIn("z4", state.zombies)

    def test_pending_imitator_occupies_cell(self) -> None:
        state = initial_state()
        imitator = PendingImitator("i1", lane=4, col=3, hp=300, planted_tick=0, reveal_tick=30)
        event = place_pending_imitator(state, imitator)
        self.assertEqual(state.grid[(4, 3)], "i1")
        self.assertIn("i1", state.pending_imitators)
        self.assertEqual(event.type, "imitator_planted")

    def test_pending_imitator_rejects_out_of_bounds_cell(self) -> None:
        state = initial_state()
        imitator = PendingImitator("bad", lane=99, col=99, hp=300, planted_tick=0, reveal_tick=30)
        with self.assertRaises(ValueError):
            place_pending_imitator(state, imitator)

    def test_reveal_cancelled_if_pending_imitator_eaten(self) -> None:
        state = initial_state()
        imitator = PendingImitator("i1", lane=4, col=3, hp=300, planted_tick=0, reveal_tick=30)
        place_pending_imitator(state, imitator)
        state.scheduled_events.append({"type": "imitator_reveal", "entity_id": "i1"})
        event = destroy_pending_imitator(state, "i1", tick=12)
        self.assertIsNone(state.grid[(4, 3)])
        self.assertNotIn("i1", state.pending_imitators)
        self.assertEqual(state.scheduled_events, [])
        self.assertEqual(event.type, "imitator_destroyed_before_reveal")
        self.assertTrue(event.payload["reveal_cancelled"])

    def test_rng_rejects_invalid_weights(self) -> None:
        rng = ReplayRng("seed")
        with self.assertRaises(ValueError):
            rng.roll("reveal", "bad_weights", ["a", "b"], {"a": 0, "b": 0})
        with self.assertRaises(ValueError):
            rng.roll("reveal", "negative_weights", ["a", "b"], {"a": -1, "b": 2})

    def test_replay_log_exact_match(self) -> None:
        first = self._deterministic_event_log("seed-replay")
        second = self._deterministic_event_log("seed-replay")
        first_json = json.dumps(to_jsonable(first), sort_keys=True)
        second_json = json.dumps(to_jsonable(second), sort_keys=True)
        self.assertEqual(first_json, second_json)

    def _deterministic_event_log(self, seed: str) -> list[Event]:
        rng = ReplayRng(seed)
        selected = rng.roll(
            "lane",
            "spawn_lane",
            ["lane_1", "lane_2", "lane_3"],
            {"lane_1": 1, "lane_2": 1, "lane_3": 1},
            tick=1,
        )
        return [
            Event(
                "evt_spawn",
                1,
                "wave_spawn",
                "zombie_spawned",
                "normal",
                {"lane": selected},
            )
        ]


if __name__ == "__main__":
    unittest.main()
