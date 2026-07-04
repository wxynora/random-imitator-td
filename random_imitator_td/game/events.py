from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import PHASE_ORDER


EVENT_TYPES: frozenset[str] = frozenset(
    {
        "observation_created",
        "action_plan_received",
        "action_delay_charged",
        "action_started",
        "action_succeeded",
        "action_failed",
        "action_plan_completed",
        "action_plan_interrupted",
        "wait_started",
        "cooldown_wait_started",
        "cooldown_ready",
        "fast_forward_started",
        "fast_forward_stopped",
        "imitator_planted",
        "imitator_damaged",
        "imitator_blocked_zombie",
        "imitator_destroyed_before_reveal",
        "imitator_revealed",
        "reveal_spawned_plant",
        "reveal_spawned_zombie",
        "reveal_spawned_boss_event",
        "reveal_triggered_event",
        "reveal_bad_draw",
        "reveal_rescue_draw",
        "plant_created",
        "plant_card_played",
        "plant_card_planted",
        "plant_destroyed",
        "plant_shoveled",
        "imitator_shoveled",
        "plant_attack_fired",
        "projectile_spawned",
        "projectile_hit",
        "plant_triggered",
        "plant_produced_sun",
        "plant_status_changed",
        "roof_pot_absorbed_hit",
        "roof_tile_slipped",
        "airdrop_dropped",
        "airdrop_opened",
        "airdrop_cleared",
        "airdrop_expired",
        "plant_damaged_by_zombie",
        "plant_eaten",
        "wave_warning",
        "wave_started",
        "zombie_spawned",
        "zombie_spawned_by_special",
        "zombie_moved",
        "pole_vaulted",
        "dolphin_jumped",
        "pogo_jumped",
        "jack_in_the_box_exploded",
        "bungee_stole_plant",
        "bungee_blocked_by_umbrella",
        "catapult_launched_basketball",
        "catapult_blocked_by_umbrella",
        "zombie_entered_danger_zone",
        "zombie_started_eating",
        "zombie_bite",
        "zombie_status_changed",
        "boss_event_action",
        "boss_event_ended",
        "zombie_damaged",
        "zombie_died",
        "zombie_reached_home",
        "lawnmower_triggered",
        "lawnmower_hit_zombie",
        "lawnmower_cleared_lane",
        "lawnmower_consumed",
        "game_won",
        "game_lost",
        "game_ended_by_player",
        "run_ended",
    }
)

SEVERITIES: frozenset[str] = frozenset({"info", "normal", "strong", "emergency"})


@dataclass
class Event:
    event_id: str
    tick: int
    phase: str
    type: str
    severity: str
    payload: dict[str, Any]
    source_id: str | None = None
    cause_event_ids: list[str] | None = None
    visible_to_ai: bool = True

    def __post_init__(self) -> None:
        if self.phase not in PHASE_ORDER:
            raise ValueError(f"unknown phase: {self.phase}")
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {self.type}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown event severity: {self.severity}")


def phase_index(phase: str) -> int:
    try:
        return PHASE_ORDER.index(phase)
    except ValueError as exc:
        raise ValueError(f"unknown phase: {phase}") from exc


def event_sort_key(event: Event) -> tuple[int, int, str, str]:
    return (event.tick, phase_index(event.phase), event.severity, event.event_id)
