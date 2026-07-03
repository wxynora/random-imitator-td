from __future__ import annotations

from math import ceil

from .config import GameConfig


def real_seconds_to_decision_delay_ticks(real_elapsed_seconds: float, config: GameConfig) -> int:
    if real_elapsed_seconds <= 0:
        return 0
    game_seconds = real_elapsed_seconds * config.decision_time_scale
    raw_ticks = ceil(game_seconds / config.tick_seconds)
    return min(raw_ticks, config.max_decision_delay_ticks, config.max_fast_forward_ticks)
