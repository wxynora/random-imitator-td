from __future__ import annotations

from dataclasses import dataclass, replace

from .config import GameConfig


CENTER_LANE_ORDER = (3, 2, 4, 1, 5)
EDGE_MIX_LANE_ORDER = (2, 4, 3, 1, 5)
ALL_IMITATOR_LEVEL = 6
POOL_LEVEL = 3
POOL_WATER_LANES = (2, 4)
FOG_LEVEL = 4
FOG_START_COL = 6
ROOF_LEVEL = 5


@dataclass(frozen=True)
class WavePhase:
    start_tick: int
    duration_ticks: int
    zombies: tuple[str, ...]
    lanes: tuple[int, ...] = CENTER_LANE_ORDER


def config_for_level(level: int, config: GameConfig | None = None) -> GameConfig:
    base_config = config or GameConfig()
    if is_all_imitator_level(level):
        return replace(base_config, is_day=True, water_lanes=(), fog_start_col=None, is_roof=False, is_endless=True)
    if level == POOL_LEVEL:
        return replace(base_config, is_day=True, water_lanes=POOL_WATER_LANES, fog_start_col=None, is_roof=False)
    if level == FOG_LEVEL:
        return replace(base_config, is_day=False, water_lanes=(), fog_start_col=FOG_START_COL, is_roof=False)
    if level == ROOF_LEVEL:
        return replace(base_config, is_day=True, water_lanes=(), fog_start_col=None, is_roof=True)
    return replace(base_config, is_day=(level != 2), water_lanes=(), fog_start_col=None, is_roof=False, is_endless=False)


def is_all_imitator_level(level: int) -> bool:
    return level == ALL_IMITATOR_LEVEL


def build_wave_schedule(level: int) -> list[tuple[int, str, int]]:
    if level <= 1:
        return _schedule_from_phases(
            (
                WavePhase(110, 120, ("normal", "normal")),
                WavePhase(310, 80, ("normal", "conehead")),
                WavePhase(560, 140, ("normal", "buckethead")),
            )
        )
    if level == 2:
        return _schedule_from_phases(
            (
                WavePhase(100, 150, ("normal", "normal", "conehead"), EDGE_MIX_LANE_ORDER),
                WavePhase(300, 90, ("normal", "conehead", "buckethead")),
                WavePhase(
                    610,
                    160,
                    ("normal", "conehead", "buckethead", "pole_vaulting", "conehead"),
                ),
            )
        )
    if level == 3:
        return _schedule_from_phases(
            (
                WavePhase(90, 150, ("normal", "ducky_tube", "conehead"), (3, 2, 5)),
                WavePhase(280, 120, ("normal", "snorkel", "buckethead", "dolphin_rider"), (1, 2, 3, 4)),
                WavePhase(
                    520,
                    150,
                    ("conehead", "ducky_tube", "buckethead", "snorkel", "pole_vaulting"),
                    (1, 2, 3, 4, 5),
                ),
                WavePhase(
                    800,
                    180,
                    (
                        "conehead",
                        "dolphin_rider",
                        "buckethead",
                        "snorkel",
                        "screen_door",
                        "dancing",
                    ),
                    (1, 2, 3, 4, 5, 2),
                ),
            )
        )
    if level == 4:
        return _schedule_from_phases(
            (
                WavePhase(100, 220, ("normal", "normal", "conehead", "pole_vaulting", "newspaper"), EDGE_MIX_LANE_ORDER),
                WavePhase(390, 180, ("conehead", "buckethead", "screen_door", "newspaper", "buckethead")),
                WavePhase(650, 170, ("normal", "pole_vaulting", "buckethead", "jack_in_the_box", "dancing", "screen_door"), EDGE_MIX_LANE_ORDER),
                WavePhase(900, 160, ("conehead", "buckethead", "football", "ladder", "pogo", "buckethead")),
                WavePhase(1160, 180, ("normal", "buckethead", "football", "catapult", "dancing", "jack_in_the_box"), EDGE_MIX_LANE_ORDER),
            )
        )
    if level == 5:
        return _schedule_from_phases(
            (
                WavePhase(80, 180, ("normal", "conehead", "newspaper", "ladder", "buckethead"), EDGE_MIX_LANE_ORDER),
                WavePhase(310, 160, ("conehead", "buckethead", "bungee", "screen_door", "catapult", "newspaper")),
                WavePhase(540, 170, ("normal", "jack_in_the_box", "dancing", "ladder", "football", "buckethead"), EDGE_MIX_LANE_ORDER),
                WavePhase(800, 170, ("conehead", "buckethead", "pogo", "balloon", "catapult", "football", "zomboni")),
                WavePhase(1080, 190, ("normal", "buckethead", "jack_in_the_box", "dancing", "catapult", "football", "gargantuar"), EDGE_MIX_LANE_ORDER),
            )
        )
    if is_all_imitator_level(level):
        return []
    return build_wave_schedule(5)


def _schedule_from_phases(phases: tuple[WavePhase, ...]) -> list[tuple[int, str, int]]:
    schedule: list[tuple[int, str, int]] = []
    for phase in phases:
        if not phase.zombies:
            continue
        if len(phase.zombies) == 1:
            ticks = (phase.start_tick,)
        else:
            step = max(1, phase.duration_ticks // (len(phase.zombies) - 1))
            ticks = tuple(phase.start_tick + min(phase.duration_ticks, index * step) for index in range(len(phase.zombies)))
        schedule.extend(
            (tick, zombie_id, phase.lanes[index % len(phase.lanes)])
            for index, (tick, zombie_id) in enumerate(zip(ticks, phase.zombies))
        )
    return sorted(schedule, key=lambda item: (item[0], item[2], item[1]))
