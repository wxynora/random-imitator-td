from __future__ import annotations

from dataclasses import dataclass


PHASE_ORDER: tuple[str, ...] = (
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
)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GameConfig:
    lanes: int = 5
    cols: int = 9
    home_x: float = 0.0
    spawn_x: float = 10.0
    tick_seconds: float = 0.1
    is_day: bool = True
    initial_sun: int = 150
    imitator_cost: int = 0
    coffee_bean_cost: int = 75
    card_slot_count: int = 6
    max_card_slot_count: int = 10
    card_loadout: tuple[str, ...] = ()
    reveal_delay_ticks: int = 30
    plant_action_ticks: int = 3
    shovel_action_ticks: int = 1
    imitator_slot_cooldown_ticks: int = 20
    coffee_bean_slot_cooldown_ticks: int = 80
    decision_time_scale: float = 1 / 15
    max_decision_delay_ticks: int = 60
    max_fast_forward_ticks: int = 600
    max_action_wait_ticks: int = 80
    first_wave_start_tick: int = 100
    auto_collect_sun: bool = False
    sky_sun_amount: int = 25
    sky_sun_interval_ticks: int = 100
    sunflower_sun_amount: int = 25
    sunflower_interval_ticks: int = 240

    def lanes_range(self) -> range:
        return range(1, self.lanes + 1)

    def cols_range(self) -> range:
        return range(1, self.cols + 1)

    def is_valid_lane(self, lane: int) -> bool:
        return 1 <= lane <= self.lanes

    def is_valid_col(self, col: int) -> bool:
        return 1 <= col <= self.cols

    def is_valid_cell(self, lane: int, col: int) -> bool:
        return self.is_valid_lane(lane) and self.is_valid_col(col)
