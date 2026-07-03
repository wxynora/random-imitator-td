from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import statistics
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.game.config import GameConfig, SCHEMA_VERSION
from random_imitator_td.game.engine import GameEngine
from random_imitator_td.game.presets import build_wave_schedule, config_for_level


PLACEMENT_COL_PRIORITY = (3, 4, 2, 5, 1, 6, 7, 8, 9)


@dataclass
class SimulationResult:
    seed: str
    level: int
    delay_profile: str
    result: str
    final_tick: int
    decisions: int
    planted: int
    failed_actions: int
    lawnmowers_used: int
    min_home_eta_ticks: int | None
    event_counts: dict[str, int]
    reveal_counts: dict[str, int]
    reveal_category_counts: dict[str, int]
    reveal_zombie_counts: dict[str, int]


class PressureScriptedPlayer:
    def __init__(self) -> None:
        self._plan_index = 0

    def decide(self, observation: dict) -> dict:
        self._plan_index += 1
        constraints = observation.get("action_constraints", {})
        imitator_cost = constraints.get("imitator_cost", 0)
        ready_slots = [
            slot
            for slot in constraints.get("card_slots", [])
            if slot.get("card_id") == "imitator" and slot.get("ready")
        ]
        sun = observation.get("sun", 0)

        if imitator_cost <= 0:
            max_plants = min(3, len(ready_slots))
        else:
            max_plants = min(3, len(ready_slots), sun // imitator_cost)
        actions = [
            {"action": "plant_imitator", "lane": lane, "col": col, "slot_id": ready_slots[index]["slot_id"]}
            for index, (lane, col) in enumerate(self._choose_cells(observation.get("lanes", []), max_plants))
        ]
        if not actions:
            actions = [{"action": "wait", "max_wait_ticks": 80}]

        return {
            "schema_version": SCHEMA_VERSION,
            "observation_id": observation["observation_id"],
            "action_plan_id": f"sim_plan_{self._plan_index}_{observation['observation_id']}",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": actions,
        }

    def _choose_cells(self, lanes: list[dict], max_count: int) -> list[tuple[int, int]]:
        if max_count <= 0:
            return []
        chosen: list[tuple[int, int]] = []
        sorted_lanes = sorted(
            lanes,
            key=lambda lane: (
                lane.get("home_eta_ticks") is None,
                lane.get("home_eta_ticks") if lane.get("home_eta_ticks") is not None else 99999,
                -lane.get("danger", 0),
                -lane.get("zombie_hp_total", 0),
            ),
        )
        fallback_lanes = sorted(lanes, key=lambda lane: abs(lane["lane"] - 3))
        for lane_info in sorted_lanes + fallback_lanes:
            open_cells = set(lane_info.get("open_cells", []))
            for col in PLACEMENT_COL_PRIORITY:
                cell = (lane_info["lane"], col)
                if col in open_cells and cell not in chosen:
                    chosen.append(cell)
                    if len(chosen) >= max_count:
                        return chosen
        return chosen


def real_elapsed_for_profile(profile: str, decision_index: int) -> float:
    if profile == "none":
        return 0
    if profile == "fast":
        return 5
    if profile == "tool_45":
        return 45
    if profile == "mixed":
        sequence = (45, 12, 30, 5, 60, 18)
        return sequence[decision_index % len(sequence)]
    if profile == "slow":
        return 90
    raise ValueError(f"unknown delay profile: {profile}")


def run_one(
    *,
    seed: str,
    level: int,
    delay_profile: str,
    max_decisions: int,
    max_ticks: int,
    config: GameConfig,
) -> SimulationResult:
    level_config = config_for_level(level, config)
    engine = GameEngine(config=level_config, seed=seed, wave_schedule=build_wave_schedule(level))
    engine.state.level = level
    player = PressureScriptedPlayer()
    observation = engine.run_until_decision()

    decisions = 0
    planted = 0
    failed_actions = 0
    min_home_eta: int | None = None

    while not engine.state.game_over and decisions < max_decisions and engine.state.tick < max_ticks:
        min_home_eta = min_eta_from_observation(observation, current=min_home_eta)
        plan = player.decide(observation)
        real_elapsed = real_elapsed_for_profile(delay_profile, decisions)
        result = engine.apply_action_plan(
            plan,
            observation_id=observation["observation_id"],
            real_elapsed_seconds=real_elapsed,
        )
        decisions += 1
        planted += sum(1 for action in result["executed_actions"] if action["action"] == "plant_imitator")
        failed_actions += len(result["failed_actions"])
        observation = result["observation"]

    if not engine.state.game_over and engine.state.tick < max_ticks:
        engine.advance_until(max_ticks=max_ticks - engine.state.tick)
    min_home_eta = min_eta_from_observation(engine.build_observation(
        reason=["simulation_summary"],
        events=[],
        advance_summary={
            "from_tick": engine.state.tick,
            "to_tick": engine.state.tick,
            "advanced_ticks": 0,
            "stop_reason": "simulation_summary",
        },
    ), current=min_home_eta)

    event_counts = Counter(event.type for event in engine.event_log)
    reveal_counts = Counter(
        event.payload.get("result")
        for event in engine.event_log
        if event.type == "imitator_revealed"
    )
    reveal_category_counts = Counter(
        event.payload.get("category")
        for event in engine.event_log
        if event.type == "imitator_revealed"
    )
    reveal_zombie_counts = Counter(
        event.payload.get("zombie_type")
        for event in engine.event_log
        if event.type == "reveal_spawned_zombie"
    )

    return SimulationResult(
        seed=seed,
        level=level,
        delay_profile=delay_profile,
        result=engine.state.result or ("timeout" if not engine.state.game_over else "game_over"),
        final_tick=engine.state.tick,
        decisions=decisions,
        planted=planted,
        failed_actions=failed_actions,
        lawnmowers_used=sum(1 for used in engine.state.lawnmowers.values() if not used),
        min_home_eta_ticks=min_home_eta,
        event_counts=dict(sorted(event_counts.items())),
        reveal_counts=dict(sorted((key, value) for key, value in reveal_counts.items() if key)),
        reveal_category_counts=dict(sorted((key, value) for key, value in reveal_category_counts.items() if key)),
        reveal_zombie_counts=dict(sorted((key, value) for key, value in reveal_zombie_counts.items() if key)),
    )


def min_eta_from_observation(observation: dict, *, current: int | None) -> int | None:
    values = [
        lane.get("home_eta_ticks")
        for lane in observation.get("lanes", [])
        if lane.get("home_eta_ticks") is not None
    ]
    if not values:
        return current
    candidate = min(values)
    return candidate if current is None else min(current, candidate)


def summarize(results: Iterable[SimulationResult]) -> dict:
    rows = list(results)
    result_counts = Counter(row.result for row in rows)
    aggregate_events: Counter[str] = Counter()
    aggregate_reveals: Counter[str] = Counter()
    aggregate_categories: Counter[str] = Counter()
    aggregate_reveal_zombies: Counter[str] = Counter()
    for row in rows:
        aggregate_events.update(row.event_counts)
        aggregate_reveals.update(row.reveal_counts)
        aggregate_categories.update(row.reveal_category_counts)
        aggregate_reveal_zombies.update(row.reveal_zombie_counts)

    return {
        "runs": len(rows),
        "results": dict(sorted(result_counts.items())),
        "avg_final_tick": round(statistics.mean(row.final_tick for row in rows), 1) if rows else 0,
        "avg_decisions": round(statistics.mean(row.decisions for row in rows), 1) if rows else 0,
        "avg_planted": round(statistics.mean(row.planted for row in rows), 1) if rows else 0,
        "avg_lawnmowers_used": round(statistics.mean(row.lawnmowers_used for row in rows), 2) if rows else 0,
        "min_home_eta_ticks": min((row.min_home_eta_ticks for row in rows if row.min_home_eta_ticks is not None), default=None),
        "event_counts": dict(sorted(aggregate_events.items())),
        "reveal_category_counts": dict(sorted(aggregate_categories.items())),
        "top_reveals": dict(aggregate_reveals.most_common(12)),
        "reveal_zombie_counts": dict(sorted(aggregate_reveal_zombies.items())),
    }


def parse_csv_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--levels", default="1,4")
    parser.add_argument("--delay-profiles", default="none,tool_45")
    parser.add_argument("--max-decisions", type=int, default=80)
    parser.add_argument("--max-ticks", type=int, default=3000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = GameConfig()
    all_results: list[SimulationResult] = []
    groups: dict[str, list[SimulationResult]] = {}
    for level in parse_csv_ints(args.levels):
        for profile in [item.strip() for item in args.delay_profiles.split(",") if item.strip()]:
            key = f"level_{level}/{profile}"
            groups[key] = []
            for index in range(args.seeds):
                result = run_one(
                    seed=f"sim-L{level}-{profile}-{index}",
                    level=level,
                    delay_profile=profile,
                    max_decisions=args.max_decisions,
                    max_ticks=args.max_ticks,
                    config=config,
                )
                groups[key].append(result)
                all_results.append(result)

    payload = {
        "config": {
            "tick_seconds": config.tick_seconds,
            "decision_time_scale": config.decision_time_scale,
            "max_decision_delay_ticks": config.max_decision_delay_ticks,
        },
        "levels": {
            str(level): {
                "is_day": config_for_level(level, config).is_day,
                "wave_count": len(build_wave_schedule(level)),
                "last_wave_tick": max((tick for tick, _, _ in build_wave_schedule(level)), default=None),
            }
            for level in parse_csv_ints(args.levels)
        },
        "groups": {key: summarize(rows) for key, rows in groups.items()},
        "runs": [asdict(row) for row in all_results],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human_summary(payload)
    return 0


def print_human_summary(payload: dict) -> None:
    print("config:", json.dumps(payload["config"], sort_keys=True))
    print("levels:", json.dumps(payload["levels"], ensure_ascii=False, sort_keys=True))
    for key, summary in payload["groups"].items():
        print(f"\n[{key}]")
        print(
            "runs={runs} results={results} avg_tick={avg_final_tick} "
            "avg_decisions={avg_decisions} avg_planted={avg_planted} "
            "avg_mowers={avg_lawnmowers_used} min_eta={min_home_eta_ticks}".format(**summary)
        )
        print("reveal_categories=", summary["reveal_category_counts"])
        print("reveal_zombies=", summary["reveal_zombie_counts"])
        interesting = {
            key: summary["event_counts"].get(key, 0)
            for key in (
                "game_won",
                "game_lost",
                "lawnmower_triggered",
                "imitator_revealed",
                "reveal_spawned_zombie",
                "plant_triggered",
                "pole_vaulted",
                "jack_in_the_box_exploded",
                "zombie_spawned_by_special",
                "zombie_status_changed",
            )
        }
        print("events=", interesting)


if __name__ == "__main__":
    raise SystemExit(main())
