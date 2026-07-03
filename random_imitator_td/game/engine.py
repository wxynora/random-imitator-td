from __future__ import annotations

from typing import Any

from random_imitator_td.data.plants import PLANTS
from random_imitator_td.data.reveal_pools import P2_REVEAL_RESULTS
from random_imitator_td.data.zombies import ZOMBIES

from .cards import build_card_catalog, card_cooldown_ticks, card_cost
from .config import GameConfig
from .contracts import action_failed_result, minimal_observation, normalize_action_plan
from .events import Event
from .experience import build_player_experience, build_round_record, build_run_recap as make_run_recap
from .models import BossEventInstance, GameState, PendingImitator, PlantInstance, RevealResultDef, ZombieInstance, initial_state
from .player_view import build_player_view
from . import plant_behaviors, zombie_behaviors
from .randomizer import ReplayRng
from .timing import real_seconds_to_decision_delay_ticks


EARLY_REVEAL_RELIEF_MAX_LEVEL = 2
EARLY_REVEAL_RELIEF_UNTIL_TICK = 500
EARLY_REVEAL_PRESSURE_WEIGHT_CAPS = {
    "chaos_pole_vaulting_zombie": 3,
    "chaos_football_zombie": 1,
}

def cell_block_threshold(col: int) -> float:
    return col + 0.5


def zombie_can_bite_cell(zombie: ZombieInstance, lane: int, col: int) -> bool:
    return zombie.lane == lane and col - 0.5 <= zombie.x <= cell_block_threshold(col)


def reveal_zombie_flavor_text(zombie_id: str) -> str:
    texts = {
        "normal": "模仿者这次站到了僵尸队。",
        "flag": "模仿者举起了旗子，队列里多了一位。",
        "conehead": "模仿者把路障戴上了，方向也一起换了。",
        "buckethead": "这次长出来的是铁桶，不是花盆。",
        "pole_vaulting": "模仿者带着撑杆落地，起跑线有点靠前。",
        "newspaper": "模仿者展开报纸，把读者本人也带来了。",
        "jack_in_the_box": "盒子打开了，里面不是礼物。",
        "football": "模仿者穿上球衣，比赛突然开始。",
        "gargantuar": "模仿者这次模仿得有点用力，巨人登场。",
        "imp": "模仿者变小了，但站到了另一边。",
        "screen_door": "门板倒是有了，拿门板的也来了。",
        "dancing": "模仿者放了段音乐，舞王跟着进场。",
        "backup_dancer": "伴舞到位，舞台方向略有偏差。",
        "dolphin_rider": "模仿者带着海豚上岸，路线很自信。",
        "snorkel": "模仿者浮出水面，冒出来的是潜水僵尸。",
        "ducky_tube": "模仿者套上鸭子圈，普通路也要假装有水。",
        "miner": "模仿者往地下找了找，挖出来一位矿工。",
        "bungee": "模仿者从天而降，绳子也带来了。",
        "ladder": "模仿者带来一架梯子，也带来拿梯子的。",
        "pogo": "模仿者弹了一下，跳跳僵尸落位。",
        "balloon": "模仿者升空了一下，气球僵尸落位。",
        "catapult": "模仿者推来一台投石车，场面开始工程化。",
        "zomboni": "模仿者发动了冰车，地面准备被认真路过。",
    }
    return texts.get(zombie_id, "模仿者这次站到了僵尸队。")


def reveal_boss_flavor_text(boss_id: str) -> str:
    if boss_id == "zomboss":
        return "模仿者把场面叫大了，僵王博士也来签到。"
    return "模仿者把场面叫大了，首领事件开始。"


def place_pending_imitator(state: GameState, imitator: PendingImitator) -> Event:
    cell = (imitator.lane, imitator.col)
    if cell not in state.grid:
        raise ValueError("target_out_of_bounds")
    if state.grid.get(cell) is not None:
        raise ValueError("target_cell_no_longer_empty")
    state.grid[cell] = imitator.entity_id
    state.pending_imitators[imitator.entity_id] = imitator
    return Event(
        event_id=f"evt_{state.tick}_imitator_planted_{imitator.entity_id}",
        tick=state.tick,
        phase="scheduled_actions",
        type="imitator_planted",
        severity="normal",
        payload={"lane": imitator.lane, "col": imitator.col},
        source_id=imitator.entity_id,
    )


def destroy_pending_imitator(
    state: GameState,
    entity_id: str,
    *,
    tick: int | None = None,
    reason: str = "eaten_by_zombie",
) -> Event:
    imitator = state.pending_imitators.pop(entity_id)
    state.grid[(imitator.lane, imitator.col)] = None
    state.scheduled_events = [
        event
        for event in state.scheduled_events
        if event.get("entity_id") != entity_id and event.get("source_id") != entity_id
    ]
    return Event(
        event_id=f"evt_{tick if tick is not None else state.tick}_imitator_destroyed_{entity_id}",
        tick=tick if tick is not None else state.tick,
        phase="zombie_bite",
        type="imitator_destroyed_before_reveal",
        severity="strong",
        payload={
            "lane": imitator.lane,
            "col": imitator.col,
            "reason": reason,
            "reveal_cancelled": True,
        },
        source_id=entity_id,
    )


def resolve_home_entry(
    state: GameState,
    zombie: ZombieInstance,
    config: GameConfig | None = None,
) -> list[Event]:
    config = config or GameConfig()
    if state.game_over:
        return []
    if zombie.entity_id not in state.zombies:
        return []
    if zombie.x > config.home_x:
        return []

    if state.lawnmowers.get(zombie.lane, False):
        state.lawnmowers[zombie.lane] = False
        cleared_zombie_ids = [
            zombie_id
            for zombie_id, lane_zombie in state.zombies.items()
            if lane_zombie.lane == zombie.lane
        ]
        for zombie_id in cleared_zombie_ids:
            state.zombies.pop(zombie_id, None)
        return [
            Event(
                event_id=f"evt_{state.tick}_lawnmower_triggered_{zombie.lane}",
                tick=state.tick,
                phase="lawnmower_home",
                type="lawnmower_triggered",
                severity="emergency",
                payload={"lane": zombie.lane, "zombie_id": zombie.entity_id},
                source_id=zombie.entity_id,
            ),
            Event(
                event_id=f"evt_{state.tick}_lawnmower_cleared_lane_{zombie.lane}",
                tick=state.tick,
                phase="lawnmower_home",
                type="lawnmower_cleared_lane",
                severity="strong",
                payload={"lane": zombie.lane, "cleared_zombie_ids": cleared_zombie_ids},
                source_id=zombie.entity_id,
            ),
            Event(
                event_id=f"evt_{state.tick}_lawnmower_consumed_{zombie.lane}",
                tick=state.tick,
                phase="lawnmower_home",
                type="lawnmower_consumed",
                severity="strong",
                payload={"lane": zombie.lane},
                source_id=zombie.entity_id,
            ),
        ]

    state.game_over = True
    state.result = "lost"
    return [
        Event(
            event_id=f"evt_{state.tick}_game_lost_{zombie.entity_id}",
            tick=state.tick,
            phase="win_loss",
            type="game_lost",
            severity="emergency",
            payload={"lane": zombie.lane, "zombie_id": zombie.entity_id},
            source_id=zombie.entity_id,
        )
    ]


class GameEngine:
    def __init__(
        self,
        config: GameConfig | None = None,
        *,
        seed: str = "RITD-001",
        reveal_results: dict[str, RevealResultDef] | None = None,
        wave_schedule: list[tuple[int, str, int]] | None = None,
        player_notes: list[dict[str, Any]] | None = None,
        player_round_history: list[dict[str, Any]] | None = None,
        mode: str = "random_imitator",
        run_id: str = "run_001",
    ) -> None:
        self.config = config or GameConfig()
        self.state = initial_state(self.config)
        self.rng = ReplayRng(seed)
        self.plant_defs = PLANTS
        self.zombie_defs = ZOMBIES
        self.reveal_results = reveal_results or P2_REVEAL_RESULTS
        self.wave_schedule = (
            list(wave_schedule)
            if wave_schedule is not None
            else [
                (self.config.first_wave_start_tick, "normal", 3),
                (self.config.first_wave_start_tick + 80, "normal", 2),
                (self.config.first_wave_start_tick + 160, "conehead", 4),
            ]
        )
        self.state.wave_state = {"spawned_count": 0, "total": len(self.wave_schedule), "completed": False}
        self.event_log: list[Event] = []
        self._entity_counter = 0
        self._event_counter = 0
        self._observation_counter = 0
        self.mode = mode
        self.run_id = run_id
        self.player_notes = list(player_notes or [])
        self.player_round_history = list(player_round_history or [])
        self._round_counter = len(self.player_round_history)
        self._player_view_seen_unit_ids: set[str] = set()

    def _next_entity_id(self, prefix: str) -> str:
        occupied_ids = (
            set(self.state.plants)
            | set(self.state.pending_imitators)
            | set(self.state.zombies)
            | set(self.state.boss_events)
        )
        occupied_ids.update(event.source_id for event in self.event_log if event.source_id is not None)
        while True:
            self._entity_counter += 1
            entity_id = f"{prefix}{self._entity_counter}"
            if entity_id not in occupied_ids:
                return entity_id

    def _event(
        self,
        phase: str,
        event_type: str,
        severity: str,
        payload: dict[str, Any],
        *,
        source_id: str | None = None,
        cause_event_ids: list[str] | None = None,
        visible_to_ai: bool = True,
    ) -> Event:
        self._event_counter += 1
        event = Event(
            event_id=f"evt_{self.state.tick}_{self._event_counter}",
            tick=self.state.tick,
            phase=phase,
            type=event_type,
            severity=severity,
            payload=payload,
            source_id=source_id,
            cause_event_ids=cause_event_ids,
            visible_to_ai=visible_to_ai,
        )
        self.event_log.append(event)
        return event

    def run_until_decision(self, *, max_ticks: int | None = None) -> dict[str, Any]:
        if self._observation_counter == 0 and self.state.tick == 0:
            return self.build_observation(
                reason=["initial"],
                events=[],
                advance_summary={"from_tick": 0, "to_tick": 0, "advanced_ticks": 0, "stop_reason": "initial"},
            )
        summary = self.advance_until(max_ticks=max_ticks)
        return self.build_observation(
            reason=[summary["stop_reason"]],
            events=summary["events"],
            advance_summary=summary,
        )

    def advance_until(
        self,
        *,
        max_ticks: int | None = None,
        stop_on_event: bool = True,
    ) -> dict[str, Any]:
        max_ticks = self.config.max_fast_forward_ticks if max_ticks is None else max_ticks
        from_tick = self.state.tick
        collected: list[Event] = []
        stop_reason = "max_fast_forward_ticks"
        for _ in range(max_ticks):
            events = self.step_one_tick()
            collected.extend(events)
            if self.state.game_over:
                stop_reason = self.state.result or "game_over"
                break
            if stop_on_event and self._should_stop_for_events(events):
                stop_reason = "strong_event"
                break
        else:
            stop_reason = "max_fast_forward_ticks"

        return {
            "from_tick": from_tick,
            "to_tick": self.state.tick,
            "advanced_ticks": self.state.tick - from_tick,
            "stop_reason": stop_reason,
            "events": [self._event_to_observation(event) for event in collected if event.visible_to_ai],
        }

    def step_one_tick(self) -> list[Event]:
        if self.state.game_over:
            return []
        self.state.tick += 1
        events: list[Event] = []
        events.extend(self._reveal_due_imitators())
        events.extend(self._plant_status())
        events.extend(self._plant_attack())
        events.extend(self._zombie_status())
        events.extend(self._boss_event_status())
        events.extend(self._zombie_move())
        events.extend(self._zombie_bite())
        events.extend(self._resolve_home_entries())
        events.extend(self._wave_spawn())
        events.extend(self._check_win_loss())
        return events

    def apply_action_plan(
        self,
        action_plan: dict[str, Any],
        *,
        real_elapsed_seconds: float = 0,
        observation_id: str | None = None,
    ) -> dict[str, Any]:
        action_plan = normalize_action_plan(action_plan, config=self.config, observation_id=observation_id)
        start_tick = self.state.tick
        collected: list[Event] = [
            self._event(
                "scheduled_actions",
                "action_plan_received",
                "info",
                {"action_plan_id": action_plan["action_plan_id"]},
            )
        ]
        executed_actions: list[dict[str, Any]] = []
        if len(action_plan["actions"]) == 1 and action_plan["actions"][0]["action"] == "end_game":
            action = action_plan["actions"][0]
            collected.append(self._end_game_by_player(reason=action.get("reason")))
            executed_actions.append({"action_index": 0, **action})
            return self._accepted_action_result(
                action_plan,
                start_tick=start_tick,
                real_elapsed_seconds=real_elapsed_seconds,
                executed_actions=executed_actions,
                failed_actions=[],
                collected=collected,
                stop_reason="ended_by_player",
            )

        if real_elapsed_seconds > 0:
            delay_ticks = real_seconds_to_decision_delay_ticks(real_elapsed_seconds, self.config)
            collected.append(
                self._event(
                    "scheduled_actions",
                    "action_delay_charged",
                    "normal",
                    {
                        "real_elapsed_seconds": real_elapsed_seconds,
                        "decision_time_scale": self.config.decision_time_scale,
                        "delay_ticks": delay_ticks,
                    },
                    visible_to_ai=False,
                )
            )
            collected.extend(self._events_from_summary(self.advance_until(max_ticks=delay_ticks, stop_on_event=False)))
            if self.state.game_over:
                return self._accepted_action_result(
                    action_plan,
                    start_tick=start_tick,
                    real_elapsed_seconds=real_elapsed_seconds,
                    executed_actions=executed_actions,
                    failed_actions=[],
                    collected=collected,
                    stop_reason=f"delay_{self.state.result or 'game_over'}",
                )

        completion_stop_reason = "action_plan_completed"
        for index, action in enumerate(action_plan["actions"]):
            if self.state.game_over:
                completion_stop_reason = self.state.result or "game_over"
                break
            if action["action"] == "wait":
                wait_ticks = action.get("max_wait_ticks", self.config.max_fast_forward_ticks)
                collected.append(self._event("scheduler", "wait_started", "normal", {"max_wait_ticks": wait_ticks}))
                wait_summary = self.advance_until(max_ticks=wait_ticks)
                if wait_summary["stop_reason"] == "max_fast_forward_ticks":
                    completion_stop_reason = "wait_max_wait_ticks"
                else:
                    completion_stop_reason = f"wait_{wait_summary['stop_reason']}"
                collected.extend(self._events_from_summary(wait_summary))
                break

            if action["action"] == "shovel_plant":
                reason = self._shovel_plant(action["lane"], action["col"], collected)
                if reason is not None:
                    return self._failed_action(
                        action_plan,
                        index,
                        action,
                        reason,
                        collected,
                        start_tick=start_tick,
                        real_elapsed_seconds=real_elapsed_seconds,
                        executed_actions=executed_actions,
                    )
                executed_actions.append({"action_index": index, **action})
                collected.extend(self._events_from_summary(self.advance_until(max_ticks=self.config.shovel_action_ticks, stop_on_event=False)))
                if self.state.game_over:
                    completion_stop_reason = f"action_{self.state.result or 'game_over'}"
                    break
                continue

            allowed_card_ids = (
                {"imitator"}
                if action["action"] == "plant_imitator"
                else {
                    self._card_id_for_slot_id(slot_id)
                    for slot_id in self.state.cooldowns
                    if self._card_id_for_slot_id(slot_id) != "imitator"
                }
            )
            slot_id = self._resolve_plant_card_slot(action, allowed_card_ids=allowed_card_ids)
            if slot_id is None:
                return self._failed_action(
                    action_plan,
                    index,
                    action,
                    "no_card_slot_ready",
                    collected,
                    start_tick=start_tick,
                    real_elapsed_seconds=real_elapsed_seconds,
                    executed_actions=executed_actions,
                )

            card_id = self._card_id_for_slot_id(slot_id)
            cooldown_remaining = max(0, self.state.cooldowns.get(slot_id, 0) - self.state.tick)
            if cooldown_remaining:
                if cooldown_remaining > self.config.max_action_wait_ticks:
                    return self._failed_action(
                        action_plan,
                        index,
                        action,
                        "cooldown_not_ready",
                        collected,
                        start_tick=start_tick,
                        real_elapsed_seconds=real_elapsed_seconds,
                        executed_actions=executed_actions,
                    )
                collected.extend(self._events_from_summary(self.advance_until(max_ticks=cooldown_remaining, stop_on_event=False)))
                if self.state.game_over:
                    completion_stop_reason = f"cooldown_{self.state.result or 'game_over'}"
                    break

            reason = self._plant_card(action["lane"], action["col"], collected, slot_id=slot_id, card_id=card_id)
            if reason is not None:
                return self._failed_action(
                    action_plan,
                    index,
                    action,
                    reason,
                    collected,
                    start_tick=start_tick,
                    real_elapsed_seconds=real_elapsed_seconds,
                    executed_actions=executed_actions,
                )
            executed_actions.append({"action_index": index, "slot_id": slot_id, "card_id": card_id, **action})
            collected.extend(self._events_from_summary(self.advance_until(max_ticks=self.config.plant_action_ticks, stop_on_event=False)))
            if self.state.game_over:
                completion_stop_reason = f"action_{self.state.result or 'game_over'}"
                break

        return self._accepted_action_result(
            action_plan,
            start_tick=start_tick,
            real_elapsed_seconds=real_elapsed_seconds,
            executed_actions=executed_actions,
            failed_actions=[],
            collected=collected,
            stop_reason=completion_stop_reason,
        )

    def _accepted_action_result(
        self,
        action_plan: dict[str, Any],
        *,
        start_tick: int,
        real_elapsed_seconds: float,
        executed_actions: list[dict[str, Any]],
        failed_actions: list[dict[str, Any]],
        collected: list[Event],
        stop_reason: str,
    ) -> dict[str, Any]:
        self._record_player_round(
            action_plan,
            start_tick=start_tick,
            real_elapsed_seconds=real_elapsed_seconds,
            executed_actions=executed_actions,
            failed_actions=failed_actions,
            collected=collected,
            stop_reason=stop_reason,
        )
        observation = self.build_observation(
            reason=[stop_reason],
            events=collected,
            advance_summary={
                "from_tick": start_tick,
                "to_tick": self.state.tick,
                "advanced_ticks": self.state.tick - start_tick,
                "stop_reason": stop_reason,
            },
        )
        return {
            "schema_version": action_plan["schema_version"],
            "action_plan_id": action_plan["action_plan_id"],
            "accepted": True,
            "executed_actions": executed_actions,
            "failed_actions": failed_actions,
            "advance_summary": observation["advance_summary"],
            "events": [self._event_to_observation(event) for event in collected if event.visible_to_ai],
            "need_next_decision": not self.state.game_over,
            "observation": observation,
        }

    def build_observation(
        self,
        *,
        reason: list[str],
        events: list[Event] | list[dict[str, Any]],
        advance_summary: dict[str, Any],
    ) -> dict[str, Any]:
        self._observation_counter += 1
        observation = minimal_observation(
            observation_id=f"obs_{self._observation_counter}",
            tick=self.state.tick,
            sun=self.state.sun,
            advance_summary={key: value for key, value in advance_summary.items() if key != "events"},
            game_status=self.state.result or ("game_over" if self.state.game_over else "running"),
        )
        observation["reason"] = reason
        observation["events"] = [
            self._event_to_observation(event) if isinstance(event, Event) else event
            for event in events
        ]
        observation["lanes"] = [self._lane_observation(lane) for lane in self.config.lanes_range()]
        observation["zombie_glossary"] = {
            zombie_id: self._zombie_trait_summary(zombie_id)
            for zombie_id in sorted({zombie.zombie_id for zombie in self.state.zombies.values()})
        }
        observation["boss_events"] = [
            {
                "boss_event_id": boss.entity_id,
                "boss_id": boss.boss_id,
                "started_tick": boss.started_tick,
                "end_tick": boss.end_tick,
                "remaining_ticks": max(0, boss.end_tick - self.state.tick),
                "next_action_tick": boss.next_action_tick,
                "next_action_in_ticks": max(0, boss.next_action_tick - self.state.tick),
                "hp": boss.hp,
                "actions_taken": boss.actions_taken,
                "status": boss.status,
            }
            for boss in sorted(self.state.boss_events.values(), key=lambda item: item.entity_id)
        ]
        card_slots = self._card_slot_observations()
        cooldown_remaining = min((slot["cooldown_remaining_ticks"] for slot in card_slots), default=0)
        card_slot_count = len(card_slots)
        observation["valid_actions"] = []
        if not self.state.game_over:
            observation["valid_actions"] = ["end_game", "wait"]
            if any(slot["card_id"] == "imitator" and slot["ready"] and self.state.sun >= self._card_cost("imitator") for slot in card_slots):
                observation["valid_actions"].insert(0, "plant_imitator")
            if any(slot["card_id"] != "imitator" and slot["ready"] and self.state.sun >= self._card_cost(slot["card_id"]) for slot in card_slots):
                observation["valid_actions"].insert(0, "plant_card")
            if any(entity_id in self.state.plants or entity_id in self.state.pending_imitators for entity_id in self.state.grid.values() if entity_id is not None):
                observation["valid_actions"].insert(0, "shovel_plant")
        observation["action_constraints"] = {
            "imitator_cost": self.config.imitator_cost,
            "card_costs": {
                "imitator": self.config.imitator_cost,
                "coffee_bean": self.config.coffee_bean_cost,
                **{
                    card_id: self._card_cost(card_id)
                    for card_id in sorted({self._card_id_for_slot_id(slot_id) for slot_id in self.state.cooldowns})
                    if card_id != "imitator"
                },
            },
            "imitator_slot_cooldown_ticks": cooldown_remaining,
            "card_slot_count": card_slot_count,
            "max_card_slot_count": self.config.max_card_slot_count,
            "card_slots": card_slots,
            "card_catalog": build_card_catalog(self.config),
            "plant_action_ticks": self.config.plant_action_ticks,
            "shovel_action_ticks": self.config.shovel_action_ticks,
            "max_actions_per_plan": 12,
            "same_observation_single_plan": True,
        }
        observation["player_experience"] = build_player_experience(
            round_history=self.player_round_history,
            notes=self.player_notes,
            level=self.state.level,
            mode=self.mode,
        )
        player_view, seen_unit_ids = build_player_view(
            state=self.state,
            config=self.config,
            plant_defs=self.plant_defs,
            zombie_defs=self.zombie_defs,
            events=observation["events"],
            valid_actions=observation["valid_actions"],
            card_slots=card_slots,
            previously_seen_unit_ids=self._player_view_seen_unit_ids,
            card_costs=observation["action_constraints"]["card_costs"],
        )
        observation["player_view"] = player_view
        self._player_view_seen_unit_ids.update(seen_unit_ids)
        return observation

    def set_player_notes(self, notes: list[dict[str, Any]]) -> None:
        self.player_notes = list(notes)

    def get_player_round_history(self) -> list[dict[str, Any]]:
        return [dict(round_record) for round_record in self.player_round_history]

    def build_run_recap(self) -> dict[str, Any]:
        return make_run_recap(
            run_id=self.run_id,
            state=self.state,
            event_log=self.event_log,
            mode=self.mode,
        )

    def _end_game_by_player(self, *, reason: str | None = None) -> Event:
        self.state.game_over = True
        self.state.result = "ended_by_player"
        payload: dict[str, Any] = {"restart_level": 1}
        if reason:
            payload["reason"] = reason
        return self._event(
            "scheduled_actions",
            "game_ended_by_player",
            "normal",
            payload,
        )

    def _plant_card(self, lane: int, col: int, collected: list[Event], *, slot_id: str, card_id: str) -> str | None:
        if card_id == "imitator":
            return self._plant_imitator(lane, col, collected, slot_id=slot_id)
        if card_id == "coffee_bean":
            return self._plant_coffee_bean(lane, col, collected, slot_id=slot_id)
        if card_id in self.plant_defs:
            return self._plant_direct_card(lane, col, collected, slot_id=slot_id, card_id=card_id)
        return "unsupported_card"

    def _plant_direct_card(self, lane: int, col: int, collected: list[Event], *, slot_id: str, card_id: str) -> str | None:
        if self.state.sun < self._card_cost(card_id):
            return "not_enough_sun"
        if slot_id not in self.state.cooldowns:
            return "card_slot_not_available"
        if self.state.cooldowns[slot_id] > self.state.tick:
            return "cooldown_not_ready"
        if not self.config.is_valid_cell(lane, col):
            return "target_out_of_bounds"
        if self.state.grid[(lane, col)] is not None:
            return "target_cell_no_longer_empty"

        plant_def = self.plant_defs[card_id]
        self.state.sun -= self._card_cost(card_id)
        self.state.cooldowns[slot_id] = self.state.tick + self._card_cooldown_ticks(card_id)
        if self._should_trigger_instant_plant(plant_def):
            trigger_event = self._event(
                "scheduled_actions",
                "plant_card_played",
                "normal",
                {"lane": lane, "col": col, "card_id": card_id, "slot_id": slot_id},
            )
            collected.append(trigger_event)
            collected.extend(self._trigger_instant_plant_id(card_id, lane, col, trigger_event.event_id))
            return None

        entity_id = self._next_entity_id("p")
        plant = PlantInstance(
            entity_id=entity_id,
            plant_id=card_id,
            lane=lane,
            col=col,
            hp=plant_def.hp,
            next_attack_tick=self._initial_next_attack_tick(card_id, plant_def),
            planted_tick=self.state.tick,
        )
        self.state.plants[entity_id] = plant
        self.state.grid[(lane, col)] = entity_id
        collected.append(
            self._event(
                "scheduled_actions",
                "plant_card_planted",
                "normal",
                {"lane": lane, "col": col, "plant_id": card_id, "slot_id": slot_id},
                source_id=entity_id,
            )
        )
        return None

    def _shovel_plant(self, lane: int, col: int, collected: list[Event]) -> str | None:
        if not self.config.is_valid_cell(lane, col):
            return "target_out_of_bounds"
        entity_id = self.state.grid[(lane, col)]
        if entity_id is None:
            return "target_cell_empty"
        if entity_id in self.state.pending_imitators:
            imitator = self.state.pending_imitators.pop(entity_id)
            self.state.grid[(lane, col)] = None
            self.state.scheduled_events = [
                event
                for event in self.state.scheduled_events
                if event.get("entity_id") != entity_id and event.get("source_id") != entity_id
            ]
            collected.append(
                self._event(
                    "scheduled_actions",
                    "imitator_shoveled",
                    "normal",
                    {
                        "lane": lane,
                        "col": col,
                        "imitator_id": entity_id,
                        "reveal_tick": imitator.reveal_tick,
                        "reveal_cancelled": True,
                    },
                    source_id=entity_id,
                )
            )
            return None
        if entity_id in self.state.plants:
            plant = self.state.plants.pop(entity_id)
            self.state.grid[(lane, col)] = None
            collected.append(
                self._event(
                    "scheduled_actions",
                    "plant_shoveled",
                    "normal",
                    {
                        "lane": lane,
                        "col": col,
                        "plant_id": entity_id,
                        "plant_type": plant.plant_id,
                    },
                    source_id=entity_id,
                )
            )
            return None
        return "target_not_shovelable"

    def _plant_imitator(self, lane: int, col: int, collected: list[Event], *, slot_id: str) -> str | None:
        if self.state.sun < self._card_cost("imitator"):
            return "not_enough_sun"
        if slot_id not in self.state.cooldowns:
            return "card_slot_not_available"
        if self.state.cooldowns[slot_id] > self.state.tick:
            return "cooldown_not_ready"
        if not self.config.is_valid_cell(lane, col):
            return "target_out_of_bounds"
        if self.state.grid[(lane, col)] is not None:
            return "target_cell_no_longer_empty"
        entity_id = self._next_entity_id("i")
        imitator = PendingImitator(
            entity_id=entity_id,
            lane=lane,
            col=col,
            hp=300,
            planted_tick=self.state.tick,
            reveal_tick=self.state.tick + self.config.reveal_delay_ticks,
        )
        event = place_pending_imitator(self.state, imitator)
        event.payload["slot_id"] = slot_id
        self.event_log.append(event)
        collected.append(event)
        self.state.sun -= self._card_cost("imitator")
        self.state.cooldowns[slot_id] = self.state.tick + self._card_cooldown_ticks("imitator")
        self.state.scheduled_events.append(
            {"type": "imitator_reveal", "entity_id": entity_id, "tick": imitator.reveal_tick}
        )
        return None

    def _plant_coffee_bean(self, lane: int, col: int, collected: list[Event], *, slot_id: str) -> str | None:
        if self.state.sun < self._card_cost("coffee_bean"):
            return "not_enough_sun"
        if slot_id not in self.state.cooldowns:
            return "card_slot_not_available"
        if self.state.cooldowns[slot_id] > self.state.tick:
            return "cooldown_not_ready"
        if not self.config.is_valid_cell(lane, col):
            return "target_out_of_bounds"

        events = self._trigger_coffee_bean(lane, col, None)
        for event in events:
            event.payload["slot_id"] = slot_id
        collected.extend(events)
        self.state.sun -= self._card_cost("coffee_bean")
        self.state.cooldowns[slot_id] = self.state.tick + self._card_cooldown_ticks("coffee_bean")
        return None

    def _card_slot_observations(self) -> list[dict[str, Any]]:
        return [
            {
                "slot_id": slot_id,
                "card_id": self._card_id_for_slot_id(slot_id),
                "cooldown_remaining_ticks": max(0, ready_tick - self.state.tick),
                "ready": ready_tick <= self.state.tick,
            }
            for slot_id, ready_tick in sorted(self.state.cooldowns.items(), key=lambda item: self._card_slot_sort_key(item[0]))
        ]

    def _resolve_plant_card_slot(self, action: dict[str, Any], *, allowed_card_ids: set[str] | None = None) -> str | None:
        requested_slot = action.get("slot_id")
        if requested_slot is not None:
            if requested_slot not in self.state.cooldowns:
                return None
            if allowed_card_ids is not None and self._card_id_for_slot_id(requested_slot) not in allowed_card_ids:
                return None
            return requested_slot
        candidate_slots = {
            slot_id: ready_tick
            for slot_id, ready_tick in self.state.cooldowns.items()
            if allowed_card_ids is None or self._card_id_for_slot_id(slot_id) in allowed_card_ids
        }
        if not candidate_slots:
            return None
        for slot_id, ready_tick in sorted(candidate_slots.items(), key=lambda item: self._card_slot_sort_key(item[0])):
            if ready_tick <= self.state.tick:
                return slot_id
        return min(candidate_slots, key=lambda slot_id: (candidate_slots[slot_id], self._card_slot_sort_key(slot_id)))

    def _card_id_for_slot_id(self, slot_id: str) -> str:
        prefix, _, suffix = slot_id.rpartition("_")
        return prefix if suffix.isdigit() else slot_id

    def _card_cost(self, card_id: str) -> int:
        return card_cost(card_id, self.config)

    def _card_cooldown_ticks(self, card_id: str) -> int:
        return card_cooldown_ticks(card_id, self.config)

    def _card_slot_sort_key(self, slot_id: str) -> tuple[str, int]:
        prefix, _, suffix = slot_id.rpartition("_")
        if suffix.isdigit():
            return (prefix, int(suffix))
        return (slot_id, 0)

    def _reveal_due_imitators(self) -> list[Event]:
        events: list[Event] = []
        due_ids = [
            entity_id
            for entity_id, imitator in self.state.pending_imitators.items()
            if imitator.reveal_tick <= self.state.tick
        ]
        for entity_id in due_ids:
            imitator = self.state.pending_imitators.pop(entity_id)
            self.state.grid[(imitator.lane, imitator.col)] = None
            self.state.scheduled_events = [
                event for event in self.state.scheduled_events if event.get("entity_id") != entity_id
            ]
            result = self._roll_reveal(imitator)
            reveal_event = self._event(
                "reveal",
                "imitator_revealed",
                "strong",
                {
                    "lane": imitator.lane,
                    "col": imitator.col,
                    "result": result.id,
                    "category": result.category,
                    "kind": result.kind,
                },
                source_id=entity_id,
            )
            events.append(reveal_event)
            if result.kind == "plant":
                events.extend(self._spawn_plant_from_reveal(imitator, result, reveal_event.event_id))
            elif result.kind == "spawn_zombie":
                events.append(self._spawn_zombie(result.payload["zombie_id"], imitator.lane, x=imitator.col + 0.5, source="reveal"))
            elif result.kind == "boss_event":
                events.append(self._spawn_boss_event(result, reveal_event.event_id))
            elif result.kind == "blank":
                events.append(
                    self._event(
                        "reveal",
                        "reveal_triggered_event",
                        "normal",
                        {"lane": imitator.lane, "col": imitator.col, "effect": "blank"},
                        source_id=entity_id,
                        cause_event_ids=[reveal_event.event_id],
                    )
                )
        return events

    def _spawn_boss_event(self, result: RevealResultDef, cause_event_id: str) -> Event:
        entity_id = self._next_entity_id("boss")
        duration_ticks = int(result.payload.get("duration_ticks", 240))
        action_interval_ticks = int(result.payload.get("action_interval_ticks", 40))
        boss = BossEventInstance(
            entity_id=entity_id,
            boss_id=result.payload.get("boss_id", "zomboss"),
            started_tick=self.state.tick,
            end_tick=self.state.tick + duration_ticks,
            next_action_tick=self.state.tick + action_interval_ticks,
            hp=int(result.payload.get("hp", 8000)),
            action_interval_ticks=action_interval_ticks,
        )
        self.state.boss_events[entity_id] = boss
        return self._event(
            "reveal",
            "reveal_spawned_boss_event",
            "emergency",
            {
                "boss_event_id": entity_id,
                "boss_id": boss.boss_id,
                "duration_ticks": duration_ticks,
                "action_interval_ticks": action_interval_ticks,
                "hp": boss.hp,
                "flavor_text": reveal_boss_flavor_text(boss.boss_id),
            },
            source_id=entity_id,
            cause_event_ids=[cause_event_id],
        )

    def _roll_reveal(self, imitator: PendingImitator) -> RevealResultDef:
        pool = list(self.reveal_results)
        weights = {key: result.weight for key, result in self.reveal_results.items()}
        adjusted_weights = self._adjust_reveal_weights(weights)
        selected = self.rng.roll(
            "reveal",
            "imitator_reveal",
            pool,
            weights,
            {
                "lane": imitator.lane,
                "col": imitator.col,
                "level": self.state.level,
                "early_reveal_relief": adjusted_weights != weights,
            },
            adjusted_weights=adjusted_weights,
            tick=self.state.tick,
        )
        return self.reveal_results[selected]

    def _adjust_reveal_weights(self, weights: dict[str, int]) -> dict[str, int]:
        if self.state.level > EARLY_REVEAL_RELIEF_MAX_LEVEL:
            return dict(weights)
        if self.state.tick >= EARLY_REVEAL_RELIEF_UNTIL_TICK:
            return dict(weights)
        adjusted = dict(weights)
        for result_id, cap in EARLY_REVEAL_PRESSURE_WEIGHT_CAPS.items():
            if result_id in adjusted:
                adjusted[result_id] = min(adjusted[result_id], cap)
        return adjusted

    def _spawn_plant_from_reveal(
        self,
        imitator: PendingImitator,
        result: RevealResultDef,
        cause_event_id: str,
    ) -> list[Event]:
        plant_id = result.payload["plant_id"]
        if plant_id == "blank":
            return []
        if plant_id == "coffee_bean":
            return self._trigger_coffee_bean(imitator.lane, imitator.col, cause_event_id)
        plant_def = self.plant_defs[plant_id]
        if self._should_trigger_instant_plant(plant_def):
            return self._trigger_instant_plant_id(plant_id, imitator.lane, imitator.col, cause_event_id)
        entity_id = self._next_entity_id("p")
        plant = PlantInstance(
            entity_id=entity_id,
            plant_id=plant_id,
            lane=imitator.lane,
            col=imitator.col,
            hp=plant_def.hp,
            next_attack_tick=self._initial_next_attack_tick(plant_id, plant_def),
            planted_tick=self.state.tick,
        )
        self.state.plants[entity_id] = plant
        self.state.grid[(plant.lane, plant.col)] = entity_id
        return [
            self._event(
                "reveal",
                "reveal_spawned_plant",
                "strong" if plant_id in {"wallnut", "peashooter"} else "normal",
                {"lane": plant.lane, "col": plant.col, "plant_id": plant_id},
                source_id=entity_id,
                cause_event_ids=[cause_event_id],
            )
        ]

    def _initial_next_attack_tick(self, plant_id: str, plant_def: Any) -> int | None:
        if plant_id == "sunflower":
            return self.state.tick + self.config.sunflower_interval_ticks
        if plant_behaviors.has_special(plant_def, "starts_ready"):
            return self.state.tick
        if plant_def.attack_interval_ticks:
            return self.state.tick + plant_def.attack_interval_ticks
        return None

    def _should_trigger_instant_plant(self, plant_def: Any, plant: PlantInstance | None = None) -> bool:
        return (
            plant_behaviors.has_special(plant_def, "instant_jalapeno")
            or plant_behaviors.has_special(plant_def, "instant_freeze")
            or plant_behaviors.has_special(plant_def, "instant_doom")
            or plant_behaviors.has_special(plant_def, "instant_blover")
            or plant_behaviors.has_special(plant_def, "instant")
        ) and not plant_behaviors.is_plant_sleeping(plant_def, is_day=self.config.is_day, plant=plant)

    def _trigger_instant_plant_id(self, plant_id: str, lane: int, col: int, cause_event_id: str) -> list[Event]:
        if plant_id == "cherry_bomb":
            return self._trigger_cherry_bomb(lane, col, cause_event_id)
        if plant_id == "jalapeno":
            return self._trigger_jalapeno(lane, col, cause_event_id)
        if plant_id == "ice_shroom":
            return self._trigger_ice_shroom(lane, col, cause_event_id)
        if plant_id == "doom_shroom":
            return self._trigger_doom_shroom(lane, col, cause_event_id)
        if plant_id == "blover":
            return self._trigger_blover(lane, col, cause_event_id)
        return []

    def _trigger_coffee_bean(self, lane: int, col: int, cause_event_id: str | None) -> list[Event]:
        cause_event_ids = [cause_event_id] if cause_event_id is not None else None
        entity_id = self.state.grid.get((lane, col))
        target = self.state.plants.get(entity_id) if entity_id is not None else None
        if (
            target is None
            or not plant_behaviors.is_day_sleeper(self.plant_defs[target.plant_id])
            or "awake" in target.status.split(",")
        ):
            return [
                self._event(
                    "plant_status",
                    "plant_triggered",
                    "normal",
                    {
                        "lane": lane,
                        "col": col,
                        "plant_id": "coffee_bean",
                        "effect": "no_sleeping_mushroom_to_wake",
                    },
                    cause_event_ids=cause_event_ids,
                )
            ]

        target.status = ",".join(sorted({tag for tag in target.status.split(",") if tag} | {"awake"}))
        if target.next_attack_tick is None and self.plant_defs[target.plant_id].attack_interval_ticks is not None:
            target.next_attack_tick = self.state.tick
        events = [
            self._event(
                "plant_status",
                "plant_triggered",
                "normal",
                {
                    "lane": lane,
                    "col": col,
                    "plant_id": "coffee_bean",
                    "effect": "woke_sleeping_mushroom",
                    "target_plant_id": target.entity_id,
                    "target_plant_type": target.plant_id,
                },
                cause_event_ids=cause_event_ids,
            ),
            self._event(
                "plant_status",
                "plant_status_changed",
                "normal",
                {"plant_id": target.entity_id, "status": target.status, "reason": "coffee_bean"},
                source_id=target.entity_id,
            ),
        ]
        if self._should_trigger_instant_plant(self.plant_defs[target.plant_id], target):
            events.extend(self._trigger_instant_sleeping_plant(target, target.entity_id))
        return events

    def _trigger_cherry_bomb(self, lane: int, col: int, cause_event_id: str) -> list[Event]:
        killed: list[str] = []
        for zombie_id, zombie in list(self.state.zombies.items()):
            if abs(zombie.lane - lane) <= 1 and abs(zombie.x - col) <= 1.5:
                killed.append(zombie_id)
                del self.state.zombies[zombie_id]
        return [
            self._event(
                "plant_attack",
                "plant_triggered",
                "strong",
                {"lane": lane, "col": col, "plant_id": "cherry_bomb", "killed_zombies": killed},
                cause_event_ids=[cause_event_id],
            )
        ]

    def _trigger_jalapeno(self, lane: int, col: int, cause_event_id: str) -> list[Event]:
        killed: list[str] = []
        damaged: list[str] = []
        for zombie_id, zombie in list(self.state.zombies.items()):
            if zombie.lane != lane:
                continue
            zombie.hp -= self.plant_defs["jalapeno"].damage or 0
            damaged.append(zombie_id)
            if zombie.hp <= 0:
                killed.append(zombie_id)
                del self.state.zombies[zombie_id]
        return [
            self._event(
                "plant_attack",
                "plant_triggered",
                "strong",
                {
                    "lane": lane,
                    "col": col,
                    "plant_id": "jalapeno",
                    "damaged_zombies": damaged,
                    "killed_zombies": killed,
                },
                cause_event_ids=[cause_event_id],
            )
        ]

    def _trigger_ice_shroom(self, lane: int, col: int, cause_event_id: str) -> list[Event]:
        frozen_until = self.state.tick + 40
        frozen: list[str] = []
        for zombie in self.state.zombies.values():
            zombie_behaviors.add_frozen_status(zombie, until_tick=frozen_until)
            frozen.append(zombie.entity_id)
        return [
            self._event(
                "plant_attack",
                "plant_triggered",
                "strong",
                {
                    "lane": lane,
                    "col": col,
                    "plant_id": "ice_shroom",
                    "frozen_zombies": frozen,
                    "frozen_until_tick": frozen_until,
                },
                cause_event_ids=[cause_event_id],
            )
        ]

    def _trigger_doom_shroom(self, lane: int, col: int, cause_event_id: str) -> list[Event]:
        killed: list[str] = []
        damaged: list[str] = []
        damage = self.plant_defs["doom_shroom"].damage or 0
        for zombie_id, zombie in list(self.state.zombies.items()):
            if abs(zombie.lane - lane) > plant_behaviors.DOOM_SHROOM_LANE_RADIUS:
                continue
            if abs(zombie.x - col) > plant_behaviors.DOOM_SHROOM_X_RADIUS:
                continue
            zombie.hp -= damage
            damaged.append(zombie_id)
            if zombie.hp <= 0:
                killed.append(zombie_id)
                del self.state.zombies[zombie_id]
        return [
            self._event(
                "plant_attack",
                "plant_triggered",
                "emergency",
                {
                    "lane": lane,
                    "col": col,
                    "plant_id": "doom_shroom",
                    "damaged_zombies": damaged,
                    "killed_zombies": killed,
                    "crater": "not_implemented",
                },
                cause_event_ids=[cause_event_id],
            )
        ]

    def _trigger_blover(self, lane: int, col: int, cause_event_id: str) -> list[Event]:
        blown_zombies: list[str] = []
        for zombie_id, zombie in list(self.state.zombies.items()):
            zombie_def = self.zombie_defs[zombie.zombie_id]
            if zombie_behaviors.is_balloon_airborne(zombie_def, zombie):
                blown_zombies.append(zombie_id)
                self.state.zombies.pop(zombie_id, None)
        return [
            self._event(
                "plant_attack",
                "plant_triggered",
                "strong",
                {
                    "lane": lane,
                    "col": col,
                    "plant_id": "blover",
                    "effect": "blew_away_airborne_zombies",
                    "killed_zombies": blown_zombies,
                },
                cause_event_ids=[cause_event_id],
            )
        ]

    def _trigger_instant_sleeping_plant(self, plant: PlantInstance, cause_event_id: str) -> list[Event]:
        self.state.plants.pop(plant.entity_id, None)
        self.state.grid[(plant.lane, plant.col)] = None
        return self._trigger_instant_plant_id(plant.plant_id, plant.lane, plant.col, cause_event_id)

    def _plant_status(self) -> list[Event]:
        events: list[Event] = []
        if (
            self.config.auto_collect_sun
            and self.config.sky_sun_interval_ticks > 0
            and self.state.tick % self.config.sky_sun_interval_ticks == 0
        ):
            self.state.sun += self.config.sky_sun_amount
            events.append(
                self._event(
                    "plant_status",
                    "plant_produced_sun",
                    "normal",
                    {"amount": self.config.sky_sun_amount, "source": "sky"},
                )
            )
        for plant in self.state.plants.values():
            if plant.plant_id != "sunflower" or plant.next_attack_tick is None:
                continue
            if self.state.tick >= plant.next_attack_tick:
                self.state.sun += self.config.sunflower_sun_amount
                plant.next_attack_tick += self.config.sunflower_interval_ticks
                events.append(
                    self._event(
                        "plant_status",
                        "plant_produced_sun",
                        "normal",
                        {"amount": self.config.sunflower_sun_amount, "source": plant.entity_id},
                        source_id=plant.entity_id,
                    )
                )
        for plant in list(self.state.plants.values()):
            plant_def = self.plant_defs[plant.plant_id]
            if plant.plant_id == "potato_mine":
                target = plant_behaviors.potato_mine_trigger_target(
                    plant,
                    plant_def,
                    self.state.zombies.values(),
                    planted_tick=plant.planted_tick,
                    current_tick=self.state.tick,
                )
                if target is not None:
                    events.extend(self._trigger_single_use_plant(plant, plant_def, target, "potato_mine_triggered"))
            elif plant.plant_id == "squash":
                target = plant_behaviors.squash_trigger_target(plant, plant_def, self.state.zombies.values())
                if target is not None:
                    events.extend(self._trigger_single_use_plant(plant, plant_def, target, "squash_triggered"))
            elif plant_behaviors.has_special(plant_def, "magnet"):
                if (
                    plant.next_attack_tick is not None
                    and self.state.tick >= plant.next_attack_tick
                    and not plant_behaviors.is_plant_sleeping(
                        plant_def,
                        is_day=self.config.is_day,
                        plant=plant,
                    )
                ):
                    target = self._magnet_target()
                    if target is not None:
                        plant.next_attack_tick += plant_def.attack_interval_ticks or 1
                        events.extend(self._trigger_magnet_shroom(plant, target))
            elif plant_behaviors.has_special(plant_def, "vehicle_spike"):
                target = self._vehicle_spike_target(plant)
                if target is not None:
                    events.extend(self._trigger_spikeweed_vehicle_hit(plant, plant_def, target))
        return events

    def _magnet_target(self) -> ZombieInstance | None:
        metal_zombie_ids = {"buckethead", "screen_door", "football", "ladder", "pogo"}
        candidates = [
            zombie
            for zombie in self.state.zombies.values()
            if zombie.zombie_id in metal_zombie_ids
            and not zombie_behaviors.has_status_tag(zombie, zombie_behaviors.METAL_REMOVED_STATUS)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda zombie: (zombie.x, zombie.entity_id))

    def _trigger_magnet_shroom(self, plant: PlantInstance, target: ZombieInstance) -> list[Event]:
        strip_damage_by_zombie = {
            "buckethead": 770,
            "screen_door": 500,
            "football": 800,
            "ladder": 500,
            "pogo": 0,
        }
        damage = strip_damage_by_zombie.get(target.zombie_id, 0)
        target.hp -= damage
        zombie_behaviors.add_status_tag(target, zombie_behaviors.METAL_REMOVED_STATUS)
        if target.zombie_id == "pogo":
            zombie_behaviors.add_status_tag(target, zombie_behaviors.POGO_STICK_REMOVED_STATUS)
        events = [
            self._event(
                "plant_status",
                "plant_triggered",
                "strong",
                {
                    "plant_id": plant.entity_id,
                    "plant_type": plant.plant_id,
                    "effect": "magnet_removed_metal",
                    "zombie_id": target.entity_id,
                    "zombie_type": target.zombie_id,
                    "damage": damage,
                    "status": target.status,
                },
                source_id=plant.entity_id,
            ),
            self._event(
                "zombie_status",
                "zombie_status_changed",
                "normal",
                {"zombie_id": target.entity_id, "status": target.status, "reason": "magnet_shroom"},
                source_id=target.entity_id,
            ),
        ]
        if target.hp <= 0:
            self.state.zombies.pop(target.entity_id, None)
            events.append(
                self._event(
                    "projectile",
                    "zombie_died",
                    "strong",
                    {"zombie_id": target.entity_id, "killed_by": plant.entity_id},
                    source_id=target.entity_id,
                )
            )
        return events

    def _vehicle_spike_target(self, plant: PlantInstance) -> ZombieInstance | None:
        vehicle_zombie_ids = {"zomboni", "catapult"}
        candidates = [
            zombie
            for zombie in self.state.zombies.values()
            if zombie.zombie_id in vehicle_zombie_ids
            and zombie.lane == plant.lane
            and -0.5 <= zombie.x - plant.col <= 0.5
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda zombie: (abs(zombie.x - plant.col), zombie.entity_id))

    def _trigger_spikeweed_vehicle_hit(
        self,
        plant: PlantInstance,
        plant_def: Any,
        target: ZombieInstance,
    ) -> list[Event]:
        damage = max(plant_def.damage or 0, 1800)
        target.hp -= damage
        self.state.plants.pop(plant.entity_id, None)
        self.state.grid[(plant.lane, plant.col)] = None
        events = [
            self._event(
                "plant_status",
                "plant_triggered",
                "strong",
                {
                    "plant_id": plant.entity_id,
                    "plant_type": plant.plant_id,
                    "trigger_type": "spikeweed_punctured_vehicle",
                    "zombie_id": target.entity_id,
                    "zombie_type": target.zombie_id,
                    "damage": damage,
                },
                source_id=plant.entity_id,
            )
        ]
        if target.hp <= 0:
            self.state.zombies.pop(target.entity_id, None)
            events.append(
                self._event(
                    "projectile",
                    "zombie_died",
                    "strong",
                    {"zombie_id": target.entity_id},
                    source_id=target.entity_id,
                )
            )
        return events

    def _plant_attack(self) -> list[Event]:
        events: list[Event] = []
        for plant in list(self.state.plants.values()):
            plant_def = self.plant_defs[plant.plant_id]
            profile = plant_behaviors.attack_profile(plant_def)
            if profile is None or plant.next_attack_tick is None:
                continue
            if self.state.tick < plant.next_attack_tick:
                continue

            zombies = tuple(self._targetable_zombies_for_plant(plant, plant_def))
            if not plant_behaviors.can_plant_attack(
                plant,
                plant_def,
                zombies,
                current_tick=self.state.tick,
                is_day=self.config.is_day,
            ):
                continue

            plant.next_attack_tick += plant_def.attack_interval_ticks or 1
            if profile.range_type == "three_lanes_forward":
                events.extend(self._threepeater_attack(plant, plant_def, profile))
                continue
            if profile.range_type == "lane_forward_pierce":
                events.extend(self._piercing_lane_attack(plant, plant_def, profile))
                continue

            for shot_index in range(profile.shots):
                target = plant_behaviors.nearest_attack_target(
                    plant,
                    plant_def,
                    zombies,
                )
                if target is None:
                    break
                events.append(
                    self._event(
                        "plant_attack",
                        "plant_attack_fired",
                        "normal",
                        {
                            "plant_id": plant.entity_id,
                            "zombie_id": target.entity_id,
                            "damage": profile.damage_per_shot,
                            "shot_index": shot_index,
                            "effects": list(profile.effects),
                        },
                        source_id=plant.entity_id,
                    )
                )
                events.extend(self._damage_zombie_from_plant(target, profile.damage_per_shot, plant.entity_id))
                if "slow" in profile.effects and not zombie_behaviors.has_status_tag(target, zombie_behaviors.SLOWED_STATUS):
                    zombie_behaviors.add_status_tag(target, zombie_behaviors.SLOWED_STATUS)
                    events.append(
                        self._event(
                            "zombie_status",
                            "zombie_status_changed",
                            "normal",
                            {"zombie_id": target.entity_id, "status": target.status, "reason": "snow_pea_slow"},
                            source_id=target.entity_id,
                        )
                    )
        return events

    def _targetable_zombies_for_plant(self, plant: PlantInstance, plant_def: Any) -> tuple[ZombieInstance, ...]:
        can_hit_airborne = plant_behaviors.has_special(plant_def, "anti_air") or plant_behaviors.has_special(plant_def, "homing")
        targetable: list[ZombieInstance] = []
        for zombie in self.state.zombies.values():
            zombie_def = self.zombie_defs[zombie.zombie_id]
            if zombie_behaviors.is_balloon_airborne(zombie_def, zombie) and not can_hit_airborne:
                continue
            targetable.append(zombie)
        return tuple(targetable)

    def _threepeater_attack(
        self,
        plant: PlantInstance,
        plant_def: Any,
        profile: plant_behaviors.AttackProfile,
    ) -> list[Event]:
        events: list[Event] = []
        for lane in (plant.lane - 1, plant.lane, plant.lane + 1):
            if lane not in self.config.lanes_range():
                continue
            candidates = [
                zombie
                for zombie in self._targetable_zombies_for_plant(plant, plant_def)
                if zombie.lane == lane and plant_behaviors.target_in_attack_range(plant, plant_def, zombie)
            ]
            if not candidates:
                continue
            target = min(candidates, key=lambda zombie: (zombie.x - plant.col, zombie.x))
            events.append(
                self._event(
                    "plant_attack",
                    "plant_attack_fired",
                    "normal",
                    {
                        "plant_id": plant.entity_id,
                        "zombie_id": target.entity_id,
                        "damage": profile.damage_per_shot,
                        "shot_lane": lane,
                        "effects": list(profile.effects),
                    },
                    source_id=plant.entity_id,
                )
            )
            events.extend(self._damage_zombie_from_plant(target, profile.damage_per_shot, plant.entity_id))
        return events

    def _piercing_lane_attack(
        self,
        plant: PlantInstance,
        plant_def: Any,
        profile: plant_behaviors.AttackProfile,
    ) -> list[Event]:
        events: list[Event] = []
        targets = sorted(
            plant_behaviors.zombies_in_attack_range(
                plant,
                plant_def,
                self._targetable_zombies_for_plant(plant, plant_def),
            ),
            key=lambda zombie: zombie.x,
        )
        for pierce_index, target in enumerate(targets):
            events.append(
                self._event(
                    "plant_attack",
                    "plant_attack_fired",
                    "normal",
                    {
                        "plant_id": plant.entity_id,
                        "zombie_id": target.entity_id,
                        "damage": profile.damage_per_shot,
                        "pierce_index": pierce_index,
                        "effects": list(profile.effects),
                    },
                    source_id=plant.entity_id,
                )
            )
            events.extend(self._damage_zombie_from_plant(target, profile.damage_per_shot, plant.entity_id))
        return events

    def _damage_zombie_from_plant(self, target: ZombieInstance, damage: int, plant_entity_id: str) -> list[Event]:
        events: list[Event] = []
        zombie_def = self.zombie_defs[target.zombie_id]
        target.hp -= damage
        if zombie_behaviors.pop_balloon(zombie_def, target):
            events.append(
                self._event(
                    "zombie_status",
                    "zombie_status_changed",
                    "strong",
                    {"zombie_id": target.entity_id, "status": target.status, "reason": "balloon_popped"},
                    source_id=target.entity_id,
                )
            )
        if target.hp <= 0:
            self.state.zombies.pop(target.entity_id, None)
            events.append(
                self._event(
                    "projectile",
                    "zombie_died",
                    "strong",
                    {"zombie_id": target.entity_id, "killed_by": plant_entity_id},
                    source_id=target.entity_id,
                )
            )
        return events

    def _nearest_zombie_ahead(self, plant: PlantInstance) -> ZombieInstance | None:
        candidates = [
            zombie
            for zombie in self.state.zombies.values()
            if zombie.lane == plant.lane and zombie.x >= plant.col
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda zombie: zombie.x)

    def _trigger_single_use_plant(
        self,
        plant: PlantInstance,
        plant_def: Any,
        target: ZombieInstance,
        trigger_type: str,
    ) -> list[Event]:
        events: list[Event] = []
        damage = plant_def.damage or 0
        target.hp -= damage
        self.state.plants.pop(plant.entity_id, None)
        self.state.grid[(plant.lane, plant.col)] = None
        events.append(
            self._event(
                "plant_status",
                "plant_triggered",
                "strong",
                {
                    "plant_id": plant.entity_id,
                    "plant_type": plant.plant_id,
                    "trigger_type": trigger_type,
                    "zombie_id": target.entity_id,
                    "damage": damage,
                },
                source_id=plant.entity_id,
            )
        )
        if target.hp <= 0:
            self.state.zombies.pop(target.entity_id, None)
            events.append(
                self._event(
                    "projectile",
                    "zombie_died",
                    "strong",
                    {"zombie_id": target.entity_id},
                    source_id=target.entity_id,
                )
            )
        return events

    def _zombie_status(self) -> list[Event]:
        events: list[Event] = []
        for zombie in list(self.state.zombies.values()):
            zombie_def = self.zombie_defs[zombie.zombie_id]
            if zombie_behaviors.clear_expired_frozen_status(zombie, current_tick=self.state.tick):
                events.append(
                    self._event(
                        "zombie_status",
                        "zombie_status_changed",
                        "normal",
                        {"zombie_id": zombie.entity_id, "status": zombie.status, "reason": "freeze_expired"},
                        source_id=zombie.entity_id,
                    )
                )
            if zombie_behaviors.is_frozen(zombie, current_tick=self.state.tick):
                continue

            fuse_ticks = zombie_behaviors.jack_in_the_box_fuse_ticks(zombie_def)
            if fuse_ticks is not None and zombie.spawned_tick is not None:
                if self.state.tick - zombie.spawned_tick >= fuse_ticks:
                    events.extend(self._explode_jack_in_the_box(zombie, zombie_def))
                    continue

            if zombie_behaviors.should_bungee_steal(zombie_def, zombie, current_tick=self.state.tick):
                events.extend(self._resolve_bungee_steal(zombie))
                continue

            if zombie_behaviors.should_dancing_summon(zombie_def, zombie, current_tick=self.state.tick):
                events.extend(self._dancing_summon_backup(zombie))

            if zombie_behaviors.should_catapult_attack(zombie_def, zombie, current_tick=self.state.tick):
                catapult_event = self._catapult_attack(zombie)
                if catapult_event is not None:
                    events.append(catapult_event)

            if (
                zombie_behaviors.is_newspaper_enraged(zombie_def, zombie)
                and not zombie_behaviors.has_status_tag(zombie, zombie_behaviors.NEWSPAPER_RAGED_STATUS)
            ):
                zombie_behaviors.add_status_tag(zombie, zombie_behaviors.NEWSPAPER_RAGED_STATUS)
                events.append(
                    self._event(
                        "zombie_status",
                        "zombie_status_changed",
                        "normal",
                        {"zombie_id": zombie.entity_id, "status": zombie.status, "reason": "newspaper_rage"},
                        source_id=zombie.entity_id,
                    )
                )

            if zombie_behaviors.should_gargantuar_throw_imp(zombie_def, zombie):
                zombie_behaviors.add_status_tag(zombie, zombie_behaviors.GARGANTUAR_IMP_THROWN_STATUS)
                imp_x = max(self.config.home_x + 0.5, zombie.x - 3.0)
                events.append(self._spawn_zombie("imp", zombie.lane, x=imp_x, source="special"))
                events.append(
                    self._event(
                        "zombie_status",
                        "zombie_status_changed",
                        "strong",
                        {"zombie_id": zombie.entity_id, "status": zombie.status, "reason": "gargantuar_threw_imp"},
                        source_id=zombie.entity_id,
                    )
                )
        return events

    def _dancing_summon_backup(self, zombie: ZombieInstance) -> list[Event]:
        zombie_behaviors.add_status_tag(zombie, zombie_behaviors.DANCING_SUMMONED_STATUS)
        events: list[Event] = [
            self._event(
                "zombie_status",
                "zombie_status_changed",
                "strong",
                {"zombie_id": zombie.entity_id, "status": zombie.status, "reason": "dancing_summoned_backup"},
                source_id=zombie.entity_id,
            )
        ]
        for lane in (zombie.lane - 1, zombie.lane, zombie.lane + 1):
            if lane not in self.config.lanes_range():
                continue
            events.append(self._spawn_zombie("backup_dancer", lane, x=min(self.config.spawn_x, zombie.x + 0.5), source="special"))
        return events

    def _resolve_bungee_steal(self, zombie: ZombieInstance) -> list[Event]:
        zombie_behaviors.add_status_tag(zombie, zombie_behaviors.BUNGEE_STOLEN_STATUS)
        candidates = [
            plant
            for plant in self.state.plants.values()
            if plant.lane == zombie.lane and abs(plant.col - zombie.x) <= 1.5
        ]
        stolen_entity_id: str | None = None
        stolen_type: str | None = None
        if candidates:
            target = min(candidates, key=lambda plant: (abs(plant.col - zombie.x), plant.entity_id))
            if self._is_protected_by_umbrella(target):
                self.state.zombies.pop(zombie.entity_id, None)
                return [
                    self._event(
                        "zombie_status",
                        "bungee_blocked_by_umbrella",
                        "strong",
                        {
                            "zombie_id": zombie.entity_id,
                            "lane": zombie.lane,
                            "x": zombie.x,
                            "target_plant_id": target.entity_id,
                            "target_plant_type": target.plant_id,
                        },
                        source_id=zombie.entity_id,
                    )
                ]
            stolen_entity_id = target.entity_id
            stolen_type = target.plant_id
            self.state.plants.pop(target.entity_id, None)
            self.state.grid[(target.lane, target.col)] = None
        self.state.zombies.pop(zombie.entity_id, None)
        return [
            self._event(
                "zombie_status",
                "bungee_stole_plant",
                "strong",
                {
                    "zombie_id": zombie.entity_id,
                    "lane": zombie.lane,
                    "x": zombie.x,
                    "stolen_entity_id": stolen_entity_id,
                    "stolen_type": stolen_type,
                },
                source_id=zombie.entity_id,
            )
        ]

    def _catapult_attack(self, zombie: ZombieInstance) -> Event | None:
        candidates = [plant for plant in self.state.plants.values() if plant.lane == zombie.lane]
        if not candidates:
            return None
        target = max(candidates, key=lambda plant: (plant.col, plant.entity_id))
        if self._is_protected_by_umbrella(target):
            return self._event(
                "zombie_status",
                "catapult_blocked_by_umbrella",
                "strong",
                {
                    "zombie_id": zombie.entity_id,
                    "target_plant_id": target.entity_id,
                    "target_plant_type": target.plant_id,
                },
                source_id=zombie.entity_id,
            )
        target.hp -= zombie_behaviors.CATAPULT_DAMAGE
        destroyed = target.hp <= 0
        if destroyed:
            self.state.plants.pop(target.entity_id, None)
            self.state.grid[(target.lane, target.col)] = None
        return self._event(
            "zombie_status",
            "catapult_launched_basketball",
            "strong",
            {
                "zombie_id": zombie.entity_id,
                "target_plant_id": target.entity_id,
                "target_plant_type": target.plant_id,
                "damage": zombie_behaviors.CATAPULT_DAMAGE,
                "target_hp": target.hp,
                "destroyed": destroyed,
            },
            source_id=zombie.entity_id,
        )

    def _is_protected_by_umbrella(self, plant: PlantInstance) -> bool:
        return any(
            protector.plant_id == "umbrella_leaf"
            and abs(protector.lane - plant.lane) <= 1
            and abs(protector.col - plant.col) <= 1
            for protector in self.state.plants.values()
        )

    def _boss_event_status(self) -> list[Event]:
        events: list[Event] = []
        for boss in list(self.state.boss_events.values()):
            if self.state.tick >= boss.end_tick:
                self.state.boss_events.pop(boss.entity_id, None)
                events.append(
                    self._event(
                        "zombie_status",
                        "boss_event_ended",
                        "strong",
                        {"boss_event_id": boss.entity_id, "boss_id": boss.boss_id},
                        source_id=boss.entity_id,
                    )
                )
                continue

            if self.state.tick < boss.next_action_tick:
                continue

            action_index = boss.actions_taken
            boss.actions_taken += 1
            boss.next_action_tick += max(1, boss.action_interval_ticks)
            if action_index % 2 == 0:
                events.extend(self._boss_summon_zombie(boss, action_index))
            else:
                events.append(self._boss_smash_cell(boss, action_index))
        return events

    def _boss_summon_zombie(self, boss: BossEventInstance, action_index: int) -> list[Event]:
        lane = 1 + ((self.state.tick + action_index) % self.config.lanes)
        zombie_cycle = ("normal", "conehead", "newspaper", "buckethead")
        zombie_id = zombie_cycle[action_index % len(zombie_cycle)]
        return [
            self._event(
                "zombie_status",
                "boss_event_action",
                "emergency",
                {
                    "boss_event_id": boss.entity_id,
                    "boss_id": boss.boss_id,
                    "action": "summon_zombie",
                    "lane": lane,
                    "zombie_type": zombie_id,
                },
                source_id=boss.entity_id,
            ),
            self._spawn_zombie(zombie_id, lane, x=self.config.spawn_x, source="special"),
        ]

    def _boss_smash_cell(self, boss: BossEventInstance, action_index: int) -> Event:
        occupied_cells: list[tuple[int, int, str, str]] = []
        for plant_id, plant in self.state.plants.items():
            occupied_cells.append((plant.lane, plant.col, plant_id, "plant"))
        for imitator_id, imitator in self.state.pending_imitators.items():
            occupied_cells.append((imitator.lane, imitator.col, imitator_id, "pending_imitator"))

        if occupied_cells:
            lane, col, entity_id, entity_type = sorted(occupied_cells)[action_index % len(occupied_cells)]
            if entity_type == "plant":
                self.state.plants.pop(entity_id, None)
            else:
                self.state.pending_imitators.pop(entity_id, None)
                self.state.scheduled_events = [
                    event for event in self.state.scheduled_events if event.get("entity_id") != entity_id
                ]
            self.state.grid[(lane, col)] = None
            destroyed_entity_id: str | None = entity_id
            destroyed_type: str | None = entity_type
        else:
            lane = 1 + ((self.state.tick + action_index) % self.config.lanes)
            col = min(self.config.cols, 4 + (action_index % 3))
            destroyed_entity_id = None
            destroyed_type = None

        return self._event(
            "zombie_status",
            "boss_event_action",
            "emergency",
            {
                "boss_event_id": boss.entity_id,
                "boss_id": boss.boss_id,
                "action": "smash_cell",
                "lane": lane,
                "col": col,
                "destroyed_entity_id": destroyed_entity_id,
                "destroyed_type": destroyed_type,
            },
            source_id=boss.entity_id,
        )

    def _explode_jack_in_the_box(self, zombie: ZombieInstance, zombie_def: Any) -> list[Event]:
        destroyed_plants: list[str] = []
        destroyed_imitators: list[str] = []
        events: list[Event] = []

        for plant_id, plant in list(self.state.plants.items()):
            if zombie_behaviors.cell_in_jack_in_the_box_explosion(
                zombie_def,
                center_lane=zombie.lane,
                center_x=zombie.x,
                target_lane=plant.lane,
                target_col=plant.col,
            ):
                destroyed_plants.append(plant_id)
                self.state.plants.pop(plant_id, None)
                self.state.grid[(plant.lane, plant.col)] = None

        for imitator_id, imitator in list(self.state.pending_imitators.items()):
            if zombie_behaviors.cell_in_jack_in_the_box_explosion(
                zombie_def,
                center_lane=zombie.lane,
                center_x=zombie.x,
                target_lane=imitator.lane,
                target_col=imitator.col,
            ):
                destroyed_imitators.append(imitator_id)
                self.state.pending_imitators.pop(imitator_id, None)
                self.state.grid[(imitator.lane, imitator.col)] = None
                self.state.scheduled_events = [
                    event for event in self.state.scheduled_events if event.get("entity_id") != imitator_id
                ]

        self.state.zombies.pop(zombie.entity_id, None)
        events.append(
            self._event(
                "zombie_status",
                "jack_in_the_box_exploded",
                "strong",
                {
                    "zombie_id": zombie.entity_id,
                    "lane": zombie.lane,
                    "x": zombie.x,
                    "destroyed_plants": destroyed_plants,
                    "destroyed_imitators": destroyed_imitators,
                },
                source_id=zombie.entity_id,
            )
        )
        return events

    def _zombie_move(self) -> list[Event]:
        events: list[Event] = []
        for zombie in list(self.state.zombies.values()):
            if zombie.spawned_tick == self.state.tick:
                continue
            zombie_def = self.zombie_defs[zombie.zombie_id]
            if zombie_behaviors.is_frozen(zombie, current_tick=self.state.tick):
                continue
            blocking_cell = self._blocking_cell_for_zombie(zombie)
            if blocking_cell:
                col, target_id = blocking_cell
                blocked_by_tallnut = self._entity_has_plant_special(target_id, "tall_blocker")
                if zombie_behaviors.can_pole_vault_over(zombie_def, zombie, zombie.lane, col):
                    if blocked_by_tallnut:
                        zombie.target_entity_id = target_id
                        continue
                    zombie.x = zombie_behaviors.pole_vault_landing_x(col, home_x=self.config.home_x)
                    zombie_behaviors.add_status_tag(zombie, zombie_behaviors.POLE_VAULTING_SPENT_STATUS)
                    zombie.target_entity_id = None
                    events.append(
                        self._event(
                            "zombie_move",
                            "pole_vaulted",
                            "strong",
                            {"zombie_id": zombie.entity_id, "jumped_col": col, "x": zombie.x},
                            source_id=zombie.entity_id,
                        )
                    )
                    continue
                if zombie_behaviors.can_dolphin_jump_over(zombie_def, zombie, zombie.lane, col):
                    if blocked_by_tallnut:
                        zombie.target_entity_id = target_id
                        continue
                    zombie.x = zombie_behaviors.dolphin_jump_landing_x(col, home_x=self.config.home_x)
                    zombie_behaviors.add_status_tag(zombie, zombie_behaviors.DOLPHIN_JUMP_SPENT_STATUS)
                    zombie.target_entity_id = None
                    events.append(
                        self._event(
                            "zombie_move",
                            "dolphin_jumped",
                            "strong",
                            {"zombie_id": zombie.entity_id, "jumped_col": col, "x": zombie.x},
                            source_id=zombie.entity_id,
                        )
                    )
                    continue
                if zombie_behaviors.can_pogo_jump_over(
                    zombie_def,
                    zombie,
                    zombie.lane,
                    col,
                    blocked_by_tallnut=blocked_by_tallnut,
                ):
                    zombie.x = zombie_behaviors.pogo_landing_x(col, home_x=self.config.home_x)
                    zombie.target_entity_id = None
                    events.append(
                        self._event(
                            "zombie_move",
                            "pogo_jumped",
                            "strong",
                            {"zombie_id": zombie.entity_id, "jumped_col": col, "x": zombie.x},
                            source_id=zombie.entity_id,
                        )
                    )
                    continue
                zombie.target_entity_id = target_id
                continue
            zombie.target_entity_id = None
            zombie.x -= zombie_behaviors.effective_walk_speed(zombie_def, zombie) * self.config.tick_seconds
            events.append(
                self._event(
                    "zombie_move",
                    "zombie_moved",
                    "info",
                    {"zombie_id": zombie.entity_id, "x": zombie.x},
                    source_id=zombie.entity_id,
                    visible_to_ai=False,
                )
            )
        return events

    def _blocking_target_for_zombie(self, zombie: ZombieInstance) -> str | None:
        blocking_cell = self._blocking_cell_for_zombie(zombie)
        if blocking_cell is None:
            return None
        return blocking_cell[1]

    def _blocking_cell_for_zombie(self, zombie: ZombieInstance) -> tuple[int, str] | None:
        zombie_def = self.zombie_defs[zombie.zombie_id]
        if zombie_behaviors.is_balloon_airborne(zombie_def, zombie):
            return None
        for col in sorted(self.config.cols_range(), reverse=True):
            entity_id = self.state.grid.get((zombie.lane, col))
            if entity_id is None:
                continue
            if self._entity_has_plant_special(entity_id, "non_blocking"):
                continue
            if col - 0.5 <= zombie.x <= cell_block_threshold(col):
                return col, entity_id
        return None

    def _entity_has_plant_special(self, entity_id: str, special: str) -> bool:
        plant = self.state.plants.get(entity_id)
        if plant is None:
            return False
        return plant_behaviors.has_special(self.plant_defs[plant.plant_id], special)

    def _zombie_bite(self) -> list[Event]:
        events: list[Event] = []
        for zombie in list(self.state.zombies.values()):
            if zombie.spawned_tick == self.state.tick or zombie.target_entity_id is None:
                continue
            zombie_def = self.zombie_defs[zombie.zombie_id]
            if zombie_behaviors.is_frozen(zombie, current_tick=self.state.tick):
                continue
            smash_damage = zombie_behaviors.gargantuar_smash_damage(zombie_def)
            damage = smash_damage if smash_damage is not None else int(zombie_def.bite_dps * self.config.tick_seconds)
            target_id = zombie.target_entity_id
            if target_id in self.state.pending_imitators:
                imitator = self.state.pending_imitators[target_id]
                imitator.hp -= damage
                events.append(
                    self._event(
                        "zombie_bite",
                        "imitator_damaged",
                        "strong" if smash_damage is not None else "normal",
                        {"imitator_id": target_id, "damage": damage, "hp": imitator.hp},
                        source_id=zombie.entity_id,
                    )
                )
                if imitator.hp <= 0:
                    event = destroy_pending_imitator(self.state, target_id, tick=self.state.tick)
                    self.event_log.append(event)
                    events.append(event)
                    zombie.target_entity_id = None
            elif target_id in self.state.plants:
                plant = self.state.plants[target_id]
                plant.hp -= damage
                events.append(
                    self._event(
                        "zombie_bite",
                        "plant_damaged_by_zombie",
                        "strong" if smash_damage is not None else "normal",
                        {"plant_id": target_id, "damage": damage, "hp": plant.hp},
                        source_id=zombie.entity_id,
                    )
                )
                if plant.hp <= 0:
                    self.state.plants.pop(target_id)
                    self.state.grid[(plant.lane, plant.col)] = None
                    zombie.target_entity_id = None
                    events.append(
                        self._event(
                            "zombie_bite",
                            "plant_eaten",
                            "strong",
                            {"plant_id": target_id, "lane": plant.lane, "col": plant.col},
                            source_id=zombie.entity_id,
                        )
                    )
            else:
                zombie.target_entity_id = None
        return events

    def _resolve_home_entries(self) -> list[Event]:
        events: list[Event] = []
        for zombie in list(self.state.zombies.values()):
            resolved = resolve_home_entry(self.state, zombie, self.config)
            self.event_log.extend(resolved)
            events.extend(resolved)
            if self.state.game_over:
                break
        return events

    def _wave_spawn(self) -> list[Event]:
        events: list[Event] = []
        for tick, zombie_id, lane in self.wave_schedule:
            if tick != self.state.tick:
                continue
            events.append(self._spawn_zombie(zombie_id, lane, x=self.config.spawn_x, source="wave"))
            self.state.wave_state["spawned_count"] += 1
        if (
            self.state.wave_state["total"] > 0
            and self.state.wave_state["spawned_count"] >= self.state.wave_state["total"]
        ):
            self.state.wave_state["completed"] = True
        return events

    def _spawn_zombie(self, zombie_id: str, lane: int, *, x: float, source: str) -> Event:
        zombie_def = self.zombie_defs[zombie_id]
        entity_id = self._next_entity_id("z")
        zombie = ZombieInstance(
            entity_id=entity_id,
            zombie_id=zombie_id,
            lane=lane,
            x=x,
            hp=zombie_def.hp,
            spawned_tick=self.state.tick,
        )
        self.state.zombies[entity_id] = zombie
        if source == "wave":
            phase = "wave_spawn"
            event_type = "zombie_spawned"
        elif source == "special":
            phase = "zombie_status"
            event_type = "zombie_spawned_by_special"
        else:
            phase = "reveal"
            event_type = "reveal_spawned_zombie"
        payload = {"zombie_id": entity_id, "zombie_type": zombie_id, "lane": lane, "x": x, "source": source}
        if source == "reveal":
            payload["flavor_text"] = reveal_zombie_flavor_text(zombie_id)
        return self._event(
            phase,
            event_type,
            "strong",
            payload,
            source_id=entity_id,
        )

    def _check_win_loss(self) -> list[Event]:
        if self.state.game_over:
            return []
        if (
            self.state.wave_state.get("completed")
            and not self.state.zombies
            and not self.state.pending_imitators
            and not self.state.boss_events
            and not self.state.scheduled_events
        ):
            self.state.game_over = True
            self.state.result = "won"
            return [
                self._event(
                    "win_loss",
                    "game_won",
                    "strong",
                    {"tick": self.state.tick},
                )
            ]
        return []

    def _failed_action(
        self,
        action_plan: dict[str, Any],
        index: int,
        action: dict[str, Any],
        reason: str,
        collected: list[Event],
        *,
        start_tick: int,
        real_elapsed_seconds: float = 0,
        executed_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        failure_payload = {
            "action_index": index,
            "action": action["action"],
            "reason": reason,
            **self._action_failure_context(action=action, reason=reason),
        }
        event = self._event(
            "scheduled_actions",
            "action_failed",
            "strong",
            failure_payload,
        )
        collected.append(event)
        failed_actions = [dict(failure_payload)]
        executed_actions = list(executed_actions or [])
        self._record_player_round(
            action_plan,
            start_tick=start_tick,
            real_elapsed_seconds=real_elapsed_seconds,
            executed_actions=executed_actions,
            failed_actions=failed_actions,
            collected=collected,
            stop_reason="action_failed",
        )
        observation = self.build_observation(
            reason=["action_failed"],
            events=collected,
            advance_summary={
                "from_tick": start_tick,
                "to_tick": self.state.tick,
                "advanced_ticks": self.state.tick - start_tick,
                "stop_reason": "action_failed",
            },
        )
        result = action_failed_result(
            action_plan_id=action_plan["action_plan_id"],
            action_index=index,
            action=action["action"],
            reason=reason,
            observation=observation,
            advance_summary=observation["advance_summary"],
        )
        result["executed_actions"] = executed_actions
        result["failed_actions"] = failed_actions
        result["events"] = [self._event_to_observation(item) for item in collected if item.visible_to_ai]
        result["need_next_decision"] = not self.state.game_over
        return result

    def _action_failure_context(self, *, action: dict[str, Any], reason: str) -> dict[str, Any]:
        if reason != "target_cell_no_longer_empty":
            return {}
        lane = action.get("lane")
        col = action.get("col")
        if not isinstance(lane, int) or not isinstance(col, int):
            return {}
        if not self.config.is_valid_cell(lane, col):
            return {}
        return {
            "lane": lane,
            "col": col,
            "occupants": self._cell_occupants(lane, col),
        }

    def _cell_occupants(self, lane: int, col: int) -> list[dict[str, Any]]:
        entity_id = self.state.grid.get((lane, col))
        if entity_id is None:
            return []
        if entity_id in self.state.pending_imitators:
            return [{"kind": "pending_imitator", "entity_id": entity_id}]
        if entity_id in self.state.plants:
            plant = self.state.plants[entity_id]
            return [
                {
                    "kind": "plant",
                    "entity_id": entity_id,
                    "plant_id": plant.plant_id,
                    "status": plant.status,
                }
            ]
        return [{"kind": "unknown", "entity_id": entity_id}]

    def _record_player_round(
        self,
        action_plan: dict[str, Any],
        *,
        start_tick: int,
        real_elapsed_seconds: float,
        executed_actions: list[dict[str, Any]],
        failed_actions: list[dict[str, Any]],
        collected: list[Event],
        stop_reason: str,
    ) -> None:
        self._round_counter += 1
        visible_events = [self._event_to_observation(event) for event in collected if event.visible_to_ai]
        self.player_round_history.append(
            build_round_record(
                round_id=f"round_{self._round_counter}",
                observation_id=action_plan["observation_id"],
                action_plan_id=action_plan["action_plan_id"],
                from_tick=start_tick,
                to_tick=self.state.tick,
                real_elapsed_seconds=real_elapsed_seconds,
                actions=action_plan["actions"],
                executed_actions=executed_actions,
                failed_actions=failed_actions,
                visible_events=visible_events,
                stop_reason=stop_reason,
            )
        )

    def _should_stop_for_events(self, events: list[Event]) -> bool:
        return any(event.severity in {"strong", "emergency"} for event in events)

    def _events_from_summary(self, summary: dict[str, Any]) -> list[Event]:
        event_ids = {event["event_id"] for event in summary["events"] if "event_id" in event}
        return [event for event in self.event_log if event.event_id in event_ids]

    def _event_to_observation(self, event: Event) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "tick": event.tick,
            "phase": event.phase,
            "type": event.type,
            "severity": event.severity,
            **event.payload,
        }

    def _lane_observation(self, lane: int) -> dict[str, Any]:
        lane_zombies = [zombie for zombie in self.state.zombies.values() if zombie.lane == lane]
        closest = min(lane_zombies, key=lambda zombie: zombie.x, default=None)
        closest_speed = (
            zombie_behaviors.effective_walk_speed(self.zombie_defs[closest.zombie_id], closest) * self.config.tick_seconds
            if closest
            else None
        )
        home_eta_ticks = (
            int((closest.x - self.config.home_x) / closest_speed)
            if closest and closest_speed and closest_speed > 0
            else None
        )
        lawnmower_available = self.state.lawnmowers.get(lane, False)
        return {
            "lane": lane,
            "danger": min(1.0, len(lane_zombies) * 0.25),
            "home_eta_ticks": home_eta_ticks,
            "lane_alerts": self._lane_alerts(
                lane=lane,
                home_eta_ticks=home_eta_ticks,
                lawnmower_available=lawnmower_available,
                closest=closest,
            ),
            "closest_zombie": {
                "type": closest.zombie_id,
                "hp": closest.hp,
                "x": closest.x,
            }
            if closest
            else None,
            "zombie_count": len(lane_zombies),
            "zombie_hp_total": sum(zombie.hp for zombie in lane_zombies),
            "plant_summary": [
                f"{self.state.plants[entity_id].plant_id}@{col}"
                if entity_id in self.state.plants
                else f"pending_imitator@{col}"
                for (cell_lane, col), entity_id in sorted(self.state.grid.items())
                if cell_lane == lane and entity_id is not None
            ],
            "pending_imitators": [
                {
                    "col": imitator.col,
                    "hp": imitator.hp,
                    "reveal_in_ticks": max(0, imitator.reveal_tick - self.state.tick),
                    "blocking": imitator.blocking,
                }
                for imitator in self.state.pending_imitators.values()
                if imitator.lane == lane
            ],
            "open_cells": [
                col for col in self.config.cols_range() if self.state.grid[(lane, col)] is None
            ],
            "lawnmower_available": lawnmower_available,
        }

    def _lane_alerts(
        self,
        *,
        lane: int,
        home_eta_ticks: int | None,
        lawnmower_available: bool,
        closest: ZombieInstance | None,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if home_eta_ticks is not None and home_eta_ticks <= 30 and not lawnmower_available and closest is not None:
            alerts.append(
                {
                    "type": "home_entry_edge",
                    "severity": "emergency",
                    "message": f"第{lane}路无推车，最近僵尸约 {home_eta_ticks} ticks 到家。",
                    "home_eta_ticks": home_eta_ticks,
                    "zombie_type": closest.zombie_id,
                }
            )
        if (
            closest is not None
            and not lawnmower_available
            and home_eta_ticks is not None
            and home_eta_ticks <= 240
            and closest.zombie_id in {"pole_vaulting", "pogo", "dolphin_rider"}
        ):
            alerts.append(
                {
                    "type": "jump_over_blockers",
                    "severity": "emergency" if home_eta_ticks <= 60 else "strong",
                    "message": (
                        f"第{lane}路无推车，{closest.zombie_id} 会跳过普通阻挡，"
                        "未开奖模仿者也按普通阻挡处理。"
                    ),
                    "home_eta_ticks": home_eta_ticks,
                    "zombie_type": closest.zombie_id,
                    "affects_pending_imitator": True,
                }
            )
        return alerts

    def _zombie_trait_summary(self, zombie_id: str) -> dict[str, Any]:
        zombie_def = self.zombie_defs[zombie_id]
        notes = {
            "normal": "基础僵尸，普通速度和血量。",
            "flag": "接近普通僵尸，主要用于僵尸潮标记。",
            "conehead": "路障防具，血量高于普通僵尸。",
            "buckethead": "铁桶防具很硬，普通火力处理时间长。",
            "pole_vaulting": "第一次遇到普通阻挡会跳过植物或未开奖模仿者，之后降速。",
            "newspaper": "报纸破损后暴怒，移动速度会变快。",
            "jack_in_the_box": "小丑盒倒计时爆炸，摧毁附近单位。",
            "football": "移动快且很硬，接近防线速度高。",
            "gargantuar": "巨人会砸掉阻挡物，半血后丢小鬼。",
            "imp": "小鬼血少但推进快，可能被巨人丢到后排。",
            "screen_door": "门板提供高耐久，正面推进更难打穿。",
            "dancing": "舞王存活一段时间后会召唤伴舞到相邻行。",
            "backup_dancer": "伴舞僵尸血量较低，通常由舞王召唤出现。",
            "dolphin_rider": "首次遇到普通阻挡会跳过一格，未开奖模仿者也会被跳过，落地后降速。",
            "snorkel": "潜水僵尸；当前场地层未细化水下隐藏，先按普通移动单位处理。",
            "ducky_tube": "鸭子圈僵尸；当前无水路层，先作为普通推进单位处理。",
            "miner": "矿工僵尸；当前地下绕后未细化，先按较快特殊僵尸处理。",
            "bungee": "蹦极僵尸停留短时间后会偷走同一路附近植物并离场。",
            "ladder": "梯子僵尸血量较高；梯子放置状态未细化，当前先作为高血量单位。",
            "pogo": "跳跳僵尸会连续跳过普通阻挡，未开奖模仿者也按普通阻挡处理；高坚果可阻挡跳跃，磁力菇可移除跳杆。",
            "balloon": "空中时无视阻挡；被对空命中后落地。",
            "catapult": "周期性攻击本行后排植物，同时缓慢推进。",
            "zomboni": "高耐久车辆，近身会高伤害压碎阻挡。",
        }
        return {
            "special": zombie_def.special,
            "trait": notes.get(zombie_id, "特殊行为以数据表为准。"),
        }
