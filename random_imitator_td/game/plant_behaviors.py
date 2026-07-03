from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import PlantDef, PlantInstance, ZombieInstance


POTATO_MINE_ARM_TICKS = 150
POTATO_MINE_TRIGGER_DISTANCE_CELLS = 0.5
PUFF_SHROOM_RANGE_CELLS = 3.0
FUME_SHROOM_RANGE_CELLS = 4.0
SCAREDY_SHROOM_FEAR_DISTANCE_CELLS = 1.5
SQUASH_TRIGGER_DISTANCE_CELLS = 1.5
DOOM_SHROOM_LANE_RADIUS = 2
DOOM_SHROOM_X_RADIUS = 2.5
STARFRUIT_DIAGONAL_TOLERANCE = 0.5


@dataclass(frozen=True)
class AttackProfile:
    shots: int
    damage_per_shot: int
    range_type: str
    effects: tuple[str, ...] = ()

    @property
    def total_damage(self) -> int:
        return self.shots * self.damage_per_shot


def special_tags(plant_def: PlantDef) -> frozenset[str]:
    if plant_def.special is None:
        return frozenset()
    normalized = plant_def.special.replace("|", ",").replace(" ", ",")
    return frozenset(tag.strip() for tag in normalized.split(",") if tag.strip())


def has_special(plant_def: PlantDef, tag: str) -> bool:
    return tag in special_tags(plant_def)


def attack_profile(plant_def: PlantDef) -> AttackProfile | None:
    if plant_def.damage is None or plant_def.attack_interval_ticks is None:
        return None

    effects: list[str] = []
    if has_special(plant_def, "slow_projectile"):
        effects.append("slow")

    return AttackProfile(
        shots=3 if has_special(plant_def, "three_lane_shot") else (2 if has_special(plant_def, "double_shot") else 1),
        damage_per_shot=plant_def.damage,
        range_type=plant_def.range_type,
        effects=tuple(effects),
    )


def is_day_sleeper(plant_def: PlantDef) -> bool:
    return has_special(plant_def, "day_sleeper")


def plant_status_tags(plant: PlantInstance) -> frozenset[str]:
    return frozenset(tag.strip() for tag in plant.status.split(",") if tag.strip())


def is_plant_sleeping(plant_def: PlantDef, *, is_day: bool, plant: PlantInstance | None = None) -> bool:
    if plant is not None and "awake" in plant_status_tags(plant):
        return False
    return is_day and is_day_sleeper(plant_def)


def is_attack_tick_ready(plant: PlantInstance, *, current_tick: int) -> bool:
    return plant.next_attack_tick is not None and current_tick >= plant.next_attack_tick


def target_in_attack_range(plant: PlantInstance, plant_def: PlantDef, zombie: ZombieInstance) -> bool:
    forward_distance = zombie.x - plant.col
    if plant_def.range_type == "area_3x3":
        return abs(zombie.lane - plant.lane) <= 1 and abs(forward_distance) <= 1
    if plant_def.range_type == "three_lanes_forward":
        return abs(zombie.lane - plant.lane) <= 1 and forward_distance >= 0
    if plant_def.range_type == "full_board":
        return True
    if plant_def.range_type == "area_large":
        return abs(zombie.lane - plant.lane) <= DOOM_SHROOM_LANE_RADIUS and abs(forward_distance) <= DOOM_SHROOM_X_RADIUS
    if plant_def.range_type == "star_five_way":
        if zombie.lane == plant.lane:
            return True
        lane_delta = abs(zombie.lane - plant.lane)
        return abs(abs(forward_distance) - lane_delta) <= STARFRUIT_DIAGONAL_TOLERANCE

    if zombie.lane != plant.lane:
        return False

    if plant_def.range_type == "lane_forward":
        return forward_distance >= 0
    if plant_def.range_type == "lane_both":
        return True
    if plant_def.range_type == "lane_forward_short":
        return 0 <= forward_distance <= PUFF_SHROOM_RANGE_CELLS
    if plant_def.range_type == "lane_forward_pierce":
        return 0 <= forward_distance <= FUME_SHROOM_RANGE_CELLS
    if plant_def.range_type == "full_lane":
        return forward_distance >= 0
    if plant_def.range_type == "cell":
        return abs(forward_distance) <= POTATO_MINE_TRIGGER_DISTANCE_CELLS
    if plant_def.range_type == "ground_cell":
        return -0.5 <= forward_distance <= 0.5
    if plant_def.range_type == "near_cell":
        return -0.5 <= forward_distance <= SQUASH_TRIGGER_DISTANCE_CELLS
    return False


def zombies_in_attack_range(
    plant: PlantInstance,
    plant_def: PlantDef,
    zombies: Iterable[ZombieInstance],
) -> tuple[ZombieInstance, ...]:
    return tuple(zombie for zombie in zombies if target_in_attack_range(plant, plant_def, zombie))


def nearest_attack_target(
    plant: PlantInstance,
    plant_def: PlantDef,
    zombies: Iterable[ZombieInstance],
) -> ZombieInstance | None:
    candidates = zombies_in_attack_range(plant, plant_def, zombies)
    if not candidates:
        return None
    return min(candidates, key=lambda zombie: (abs(zombie.x - plant.col), zombie.x))


def is_scaredy_shroom_scared(plant: PlantInstance, plant_def: PlantDef, zombies: Iterable[ZombieInstance]) -> bool:
    if not has_special(plant_def, "scared_when_near"):
        return False
    return any(
        zombie.lane == plant.lane and abs(zombie.x - plant.col) <= SCAREDY_SHROOM_FEAR_DISTANCE_CELLS
        for zombie in zombies
    )


def can_plant_attack(
    plant: PlantInstance,
    plant_def: PlantDef,
    zombies: Iterable[ZombieInstance],
    *,
    current_tick: int,
    is_day: bool = False,
) -> bool:
    cached_zombies = tuple(zombies)
    return (
        "active" in plant_status_tags(plant)
        and attack_profile(plant_def) is not None
        and is_attack_tick_ready(plant, current_tick=current_tick)
        and not is_plant_sleeping(plant_def, is_day=is_day, plant=plant)
        and not is_scaredy_shroom_scared(plant, plant_def, cached_zombies)
        and nearest_attack_target(plant, plant_def, cached_zombies) is not None
    )


def potato_mine_arm_ticks(plant_def: PlantDef) -> int:
    for tag in special_tags(plant_def):
        if tag.startswith("armed_after_"):
            return int(tag.removeprefix("armed_after_"))
    return POTATO_MINE_ARM_TICKS


def is_potato_mine_armed(plant_def: PlantDef, *, planted_tick: int, current_tick: int) -> bool:
    return current_tick - planted_tick >= potato_mine_arm_ticks(plant_def)


def potato_mine_trigger_target(
    plant: PlantInstance,
    plant_def: PlantDef,
    zombies: Iterable[ZombieInstance],
    *,
    planted_tick: int,
    current_tick: int,
) -> ZombieInstance | None:
    if not is_potato_mine_armed(plant_def, planted_tick=planted_tick, current_tick=current_tick):
        return None
    return nearest_attack_target(plant, plant_def, zombies)


def squash_trigger_target(
    plant: PlantInstance,
    plant_def: PlantDef,
    zombies: Iterable[ZombieInstance],
) -> ZombieInstance | None:
    if not has_special(plant_def, "instant_squash"):
        return None
    return nearest_attack_target(plant, plant_def, zombies)
