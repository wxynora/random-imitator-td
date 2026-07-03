from __future__ import annotations

from dataclasses import dataclass, replace

from .config import GameConfig


CENTER_LANE_ORDER = (3, 2, 4, 1, 5)
EDGE_MIX_LANE_ORDER = (2, 4, 3, 1, 5)


@dataclass(frozen=True)
class WavePhase:
    start_tick: int
    duration_ticks: int
    zombies: tuple[str, ...]
    lanes: tuple[int, ...] = CENTER_LANE_ORDER


def config_for_level(level: int, config: GameConfig | None = None) -> GameConfig:
    base_config = config or GameConfig()
    return replace(base_config, is_day=(level != 2))


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
                WavePhase(90, 150, ("normal", "conehead", "normal"), EDGE_MIX_LANE_ORDER),
                WavePhase(280, 100, ("normal", "conehead", "buckethead", "pole_vaulting")),
                WavePhase(
                    520,
                    140,
                    ("normal", "conehead", "buckethead", "newspaper", "conehead"),
                ),
                WavePhase(
                    800,
                    180,
                    (
                        "normal",
                        "conehead",
                        "buckethead",
                        "pole_vaulting",
                        "newspaper",
                        "screen_door",
                    ),
                    EDGE_MIX_LANE_ORDER,
                ),
            )
        )
    if level <= 4:
        return [
            (70, "normal", 3),
            (130, "conehead", 2),
            (190, "pole_vaulting", 4),
            (250, "newspaper", 3),
            (320, "buckethead", 5),
        ]
    if level <= 5:
        return [
            (70, "normal", 3),
            (130, "conehead", 2),
            (190, "pole_vaulting", 4),
            (250, "newspaper", 3),
            (320, "buckethead", 5),
            (390, "jack_in_the_box", 2),
        ]
    return [
        (70, "normal", 3),
        (130, "conehead", 2),
        (190, "pole_vaulting", 4),
        (250, "newspaper", 3),
        (320, "buckethead", 5),
        (390, "jack_in_the_box", 2),
        (480, "football", 4),
        (620, "gargantuar", 3),
    ]


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
