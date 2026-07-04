from __future__ import annotations

from collections import Counter
from typing import Any

from .events import Event
from .models import GameState


DEFAULT_EXPERIENCE_LIMIT = 5
DEFAULT_ROUND_HISTORY_LIMIT = 8


def build_player_experience(
    *,
    round_history: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    level: int,
    mode: str = "random_imitator",
    note_limit: int = DEFAULT_EXPERIENCE_LIMIT,
    round_limit: int = DEFAULT_ROUND_HISTORY_LIMIT,
) -> dict[str, Any]:
    return {
        "recent_rounds": round_history[-round_limit:],
        "notes": select_player_notes(notes, level=level, mode=mode, limit=note_limit),
    }


def select_player_notes(
    notes: list[dict[str, Any]],
    *,
    level: int,
    mode: str = "random_imitator",
    limit: int = DEFAULT_EXPERIENCE_LIMIT,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for note in notes:
        if not note.get("enabled", True):
            continue
        scope = note.get("scope", {})
        if scope.get("mode", mode) != mode:
            continue
        scoped_level = scope.get("level")
        if scoped_level is not None and scoped_level != level:
            continue
        selected.append(compact_player_note(note, fallback_index=len(selected) + 1))
        if len(selected) >= limit:
            break
    return selected


def compact_player_note(note: dict[str, Any], *, fallback_index: int = 1) -> dict[str, Any]:
    return {
        "memory_id": note.get("memory_id", f"player_note_{fallback_index}"),
        "note": note.get("player_note") or note.get("note", ""),
        "source_run_id": note.get("source_run_id"),
        "source_round_id": note.get("source_round_id"),
        "updated_tick": note.get("updated_tick"),
    }


def make_player_note(
    *,
    player_note: str,
    level: int,
    mode: str = "random_imitator",
    memory_id: str | None = None,
    source_run_id: str | None = None,
    source_round_id: str | None = None,
    updated_tick: int | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    if not player_note.strip():
        raise ValueError("player_note_required")
    return {
        "memory_id": memory_id or f"player_note_{level}_{mode}_1",
        "scope": {"level": level, "mode": mode},
        "player_note": player_note.strip(),
        "source_run_id": source_run_id,
        "source_round_id": source_round_id,
        "updated_tick": updated_tick,
        "enabled": enabled,
    }


def update_player_note(
    notes: list[dict[str, Any]],
    *,
    memory_id: str,
    player_note: str,
    updated_tick: int | None = None,
) -> list[dict[str, Any]]:
    if not player_note.strip():
        raise ValueError("player_note_required")
    updated: list[dict[str, Any]] = []
    found = False
    for note in notes:
        if note.get("memory_id") != memory_id:
            updated.append(note)
            continue
        replacement = dict(note)
        replacement["player_note"] = player_note.strip()
        replacement["updated_tick"] = updated_tick
        updated.append(replacement)
        found = True
    if not found:
        raise KeyError(memory_id)
    return updated


def build_round_record(
    *,
    round_id: str,
    observation_id: str,
    action_plan_id: str,
    from_tick: int,
    to_tick: int,
    real_elapsed_seconds: float,
    actions: list[dict[str, Any]],
    executed_actions: list[dict[str, Any]],
    failed_actions: list[dict[str, Any]],
    visible_events: list[dict[str, Any]],
    stop_reason: str = "action_plan_completed",
) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "observation_id": observation_id,
        "action_plan_id": action_plan_id,
        "from_tick": from_tick,
        "to_tick": to_tick,
        "advanced_ticks": to_tick - from_tick,
        "stop_reason": stop_reason,
        "actions": [_compact_action(action) for action in actions],
        "executed_actions": [_compact_action(action) for action in executed_actions],
        "failed_actions": failed_actions,
        "result_events": _compact_visible_events(visible_events),
    }


def _compact_action(action: dict[str, Any]) -> dict[str, Any]:
    keys = ("action", "lane", "col", "slot_id", "card_id", "action_index", "max_wait_ticks", "reason")
    return {key: action[key] for key in keys if key in action}


def _compact_visible_events(events: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    important_types = {
        "imitator_planted",
        "imitator_revealed",
        "reveal_spawned_plant",
        "reveal_spawned_zombie",
        "reveal_spawned_boss_event",
        "plant_attack_fired",
        "zombie_died",
        "plant_triggered",
        "plant_produced_sun",
        "plant_damaged_by_zombie",
        "plant_eaten",
        "plant_shoveled",
        "imitator_shoveled",
        "imitator_damaged",
        "imitator_destroyed_before_reveal",
        "zombie_spawned",
        "zombie_spawned_by_special",
        "jack_in_the_box_exploded",
        "bungee_blocked_by_umbrella",
        "catapult_blocked_by_umbrella",
        "pogo_jumped",
        "lawnmower_triggered",
        "lawnmower_cleared_lane",
        "game_lost",
        "game_won",
        "game_ended_by_player",
        "action_failed",
    }
    compacted: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") not in important_types:
            continue
        compacted.append(
            {
                key: value
                for key, value in event.items()
                if key
                in {
                    "tick",
                    "type",
                    "lane",
                    "col",
                    "result",
                    "category",
                    "kind",
                    "plant_id",
                    "plant_type",
                    "zombie_id",
                    "zombie_type",
                    "imitator_id",
                    "target_plant_id",
                    "target_plant_type",
                    "action",
                    "reason",
                    "effect",
                    "delay_ticks",
                    "damage",
                    "status",
                    "amount",
                    "source",
                    "hp",
                    "killed_by",
                    "shot_index",
                    "shot_lane",
                    "pierce_index",
                    "effects",
                    "destroyed_plants",
                    "destroyed_imitators",
                    "cleared_zombie_ids",
                    "flavor_text",
                    "reveal_cancelled",
                    "reveal_tick",
                    "restart_level",
                }
            }
        )
    return compacted[-limit:]


def build_run_recap(
    *,
    run_id: str,
    state: GameState,
    event_log: list[Event],
    mode: str = "random_imitator",
    max_key_events: int = 10,
) -> dict[str, Any]:
    loss_events = [event for event in event_log if event.type == "game_lost"]
    reveal_events = [event for event in event_log if event.type == "imitator_revealed"]
    reveal_categories = Counter(event.payload.get("category") for event in reveal_events)
    reveal_results = Counter(event.payload.get("result") for event in reveal_events)
    return {
        "run_id": run_id,
        "mode": mode,
        "level": state.level,
        "result": state.result or ("game_over" if state.game_over else "running"),
        "final_tick": state.tick,
        "system_waves_spawned": int(state.wave_state.get("spawned_count", 0) or 0),
        "airdrops_spawned": int(state.wave_state.get("airdrops_spawned", 0) or 0),
        "airdrops_opened": int(state.wave_state.get("airdrops_opened", 0) or 0),
        "airdrops_cleared": int(state.wave_state.get("airdrops_cleared", 0) or 0),
        "loss_lane": loss_events[-1].payload.get("lane") if loss_events else None,
        "lawnmowers_used": sum(1 for used in state.lawnmowers.values() if not used),
        "reveal_categories": dict(sorted((key, value) for key, value in reveal_categories.items() if key)),
        "top_reveals": dict(reveal_results.most_common(8)),
        "key_events": _key_event_lines(event_log, max_key_events=max_key_events),
    }


def _key_event_lines(event_log: list[Event], *, max_key_events: int) -> list[str]:
    important_types = {
        "imitator_revealed",
        "reveal_spawned_plant",
        "reveal_spawned_zombie",
        "reveal_spawned_boss_event",
        "zombie_spawned",
        "zombie_spawned_by_special",
        "plant_triggered",
        "plant_eaten",
        "imitator_destroyed_before_reveal",
        "lawnmower_triggered",
        "lawnmower_cleared_lane",
        "game_lost",
        "game_won",
        "game_ended_by_player",
    }
    lines = [_event_line(event) for event in event_log if event.type in important_types]
    return lines[-max_key_events:]


def _event_line(event: Event) -> str:
    payload = event.payload
    if event.type == "imitator_revealed":
        return (
            f"tick {event.tick}: lane {payload.get('lane')} col {payload.get('col')} "
            f"imitator -> {payload.get('result')} ({payload.get('kind')})"
        )
    if event.type == "reveal_spawned_zombie":
        return f"tick {event.tick}: lane {payload.get('lane')} spawned {payload.get('zombie_type')} from reveal"
    if event.type == "reveal_spawned_plant":
        return f"tick {event.tick}: lane {payload.get('lane')} col {payload.get('col')} spawned {payload.get('plant_id')}"
    if event.type == "reveal_spawned_boss_event":
        return f"tick {event.tick}: boss event {payload.get('boss_id')} started"
    if event.type == "zombie_spawned":
        return f"tick {event.tick}: lane {payload.get('lane')} wave spawned {payload.get('zombie_type')}"
    if event.type == "zombie_spawned_by_special":
        return f"tick {event.tick}: lane {payload.get('lane')} special spawned {payload.get('zombie_type')}"
    if event.type == "plant_triggered":
        return f"tick {event.tick}: {payload.get('plant_id') or payload.get('plant_type')} triggered"
    if event.type == "plant_eaten":
        return f"tick {event.tick}: lane {payload.get('lane')} col {payload.get('col')} plant eaten"
    if event.type == "imitator_destroyed_before_reveal":
        return f"tick {event.tick}: lane {payload.get('lane')} col {payload.get('col')} imitator destroyed before reveal"
    if event.type == "lawnmower_triggered":
        return f"tick {event.tick}: lane {payload.get('lane')} lawnmower triggered"
    if event.type == "lawnmower_cleared_lane":
        return f"tick {event.tick}: lane {payload.get('lane')} lawnmower cleared lane"
    if event.type == "game_lost":
        return f"tick {event.tick}: lane {payload.get('lane')} zombie reached home, game lost"
    if event.type == "game_won":
        return f"tick {event.tick}: game won"
    if event.type == "game_ended_by_player":
        return f"tick {event.tick}: player ended run, restart at level {payload.get('restart_level')}"
    return f"tick {event.tick}: {event.type}"
