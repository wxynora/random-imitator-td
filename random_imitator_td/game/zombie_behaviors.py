from __future__ import annotations

from typing import Final

from .models import ZombieDef, ZombieInstance


SPECIAL_FLAG_WAVE: Final = "flag_wave"
SPECIAL_POLE_VAULTING: Final = "pole_vaulting"
SPECIAL_NEWSPAPER_RAGE: Final = "newspaper_rage"
SPECIAL_JACK_IN_THE_BOX: Final = "jack_in_the_box"
SPECIAL_FOOTBALL_ARMOR: Final = "football_armor"
SPECIAL_GARGANTUAR: Final = "gargantuar"
SPECIAL_IMP: Final = "imp"
SPECIAL_SCREEN_DOOR: Final = "screen_door"
SPECIAL_DANCING: Final = "dancing_summoner"
SPECIAL_BACKUP_DANCER: Final = "backup_dancer"
SPECIAL_DOLPHIN_RIDER: Final = "dolphin_rider"
SPECIAL_SNORKEL: Final = "snorkel"
SPECIAL_DUCKY_TUBE: Final = "ducky_tube"
SPECIAL_MINER: Final = "miner_backline"
SPECIAL_BUNGEE: Final = "bungee_steal"
SPECIAL_LADDER: Final = "ladder"
SPECIAL_POGO: Final = "pogo"
SPECIAL_BALLOON: Final = "balloon"
SPECIAL_CATAPULT: Final = "catapult"
SPECIAL_ZOMBONI: Final = "zomboni_crush"

NORMAL_WALK_SPEED: Final = 0.10
POLE_VAULTING_FAST_WALK_SPEED: Final = 0.18
POLE_VAULTING_SPENT_WALK_SPEED: Final = NORMAL_WALK_SPEED
POLE_VAULTING_SPENT_STATUS: Final = "pole_vault_spent"
POLE_VAULT_LANDING_OFFSET: Final = 1.0
DOLPHIN_JUMP_SPENT_STATUS: Final = "dolphin_jump_spent"
DOLPHIN_RIDER_FAST_WALK_SPEED: Final = 0.18
DOLPHIN_RIDER_SPENT_WALK_SPEED: Final = NORMAL_WALK_SPEED
DOLPHIN_JUMP_LANDING_OFFSET: Final = 1.0
POGO_LANDING_OFFSET: Final = 1.0
POGO_STICK_REMOVED_STATUS: Final = "pogo_stick_removed"

NEWSPAPER_RAGE_HP_THRESHOLD: Final = 200
NEWSPAPER_RAGE_WALK_SPEED: Final = 0.24

JACK_IN_THE_BOX_FUSE_TICKS: Final = 30
JACK_IN_THE_BOX_LANE_RADIUS: Final = 1
JACK_IN_THE_BOX_X_RADIUS: Final = 1.5

GARGANTUAR_SMASH_DAMAGE: Final = 1800
GARGANTUAR_IMP_THROW_RATIO: Final = 0.5
GARGANTUAR_IMP_THROWN_STATUS: Final = "imp_thrown"
NEWSPAPER_RAGED_STATUS: Final = "newspaper_raged"
SLOWED_STATUS: Final = "slowed"
SLOWED_WALK_MULTIPLIER: Final = 0.5
DANCING_SUMMON_TICKS: Final = 30
DANCING_SUMMONED_STATUS: Final = "backup_summoned"
BUNGEE_STEAL_TICKS: Final = 10
BUNGEE_STOLEN_STATUS: Final = "bungee_resolved"
BALLOON_POPPED_STATUS: Final = "balloon_popped"
METAL_REMOVED_STATUS: Final = "metal_removed"
CATAPULT_ATTACK_INTERVAL_TICKS: Final = 40
CATAPULT_DAMAGE: Final = 80
FROZEN_STATUS_PREFIX: Final = "frozen_until_"


def status_tags(zombie: ZombieInstance) -> frozenset[str]:
    return frozenset(tag.strip() for tag in zombie.status.replace("|", ",").split(",") if tag.strip())


def has_status_tag(zombie: ZombieInstance, tag: str) -> bool:
    return tag in status_tags(zombie)


def add_status_tag(zombie: ZombieInstance, tag: str) -> None:
    tags = set(status_tags(zombie))
    tags.discard("walking")
    tags.add(tag)
    zombie.status = ",".join(sorted(tags)) if tags else "walking"


def has_special(zombie_def: ZombieDef, special: str) -> bool:
    return zombie_def.special == special


def effective_walk_speed(zombie_def: ZombieDef, zombie: ZombieInstance | None = None) -> float:
    speed = zombie_def.walk_speed
    if has_special(zombie_def, SPECIAL_NEWSPAPER_RAGE) and zombie is not None:
        if is_newspaper_enraged(zombie_def, zombie):
            speed = NEWSPAPER_RAGE_WALK_SPEED
    if has_special(zombie_def, SPECIAL_POLE_VAULTING) and zombie is not None:
        if not has_pole_vault_available(zombie_def, zombie):
            speed = POLE_VAULTING_SPENT_WALK_SPEED
    if has_special(zombie_def, SPECIAL_DOLPHIN_RIDER) and zombie is not None:
        if not has_dolphin_jump_available(zombie_def, zombie):
            speed = DOLPHIN_RIDER_SPENT_WALK_SPEED
    if has_special(zombie_def, SPECIAL_BALLOON) and zombie is not None:
        if not is_balloon_airborne(zombie_def, zombie):
            speed = NORMAL_WALK_SPEED
    if zombie is not None and has_status_tag(zombie, SLOWED_STATUS):
        speed *= SLOWED_WALK_MULTIPLIER
    return speed


def newspaper_rage_hp_threshold(zombie_def: ZombieDef) -> int | None:
    if not has_special(zombie_def, SPECIAL_NEWSPAPER_RAGE):
        return None
    return NEWSPAPER_RAGE_HP_THRESHOLD


def is_newspaper_enraged(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    threshold = newspaper_rage_hp_threshold(zombie_def)
    return threshold is not None and zombie.hp <= threshold


def has_pole_vault_available(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    return has_special(zombie_def, SPECIAL_POLE_VAULTING) and not has_status_tag(zombie, POLE_VAULTING_SPENT_STATUS)


def can_pole_vault_over(zombie_def: ZombieDef, zombie: ZombieInstance, lane: int, col: int) -> bool:
    return has_pole_vault_available(zombie_def, zombie) and zombie_overlaps_cell(zombie, lane, col)


def pole_vault_landing_x(col: int, *, home_x: float = 0.0) -> float:
    return max(home_x, float(col) - POLE_VAULT_LANDING_OFFSET)


def has_dolphin_jump_available(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    return has_special(zombie_def, SPECIAL_DOLPHIN_RIDER) and not has_status_tag(zombie, DOLPHIN_JUMP_SPENT_STATUS)


def can_dolphin_jump_over(zombie_def: ZombieDef, zombie: ZombieInstance, lane: int, col: int) -> bool:
    return has_dolphin_jump_available(zombie_def, zombie) and zombie_overlaps_cell(zombie, lane, col)


def dolphin_jump_landing_x(col: int, *, home_x: float = 0.0) -> float:
    return max(home_x, float(col) - DOLPHIN_JUMP_LANDING_OFFSET)


def has_pogo_jump_available(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    return has_special(zombie_def, SPECIAL_POGO) and not has_status_tag(zombie, POGO_STICK_REMOVED_STATUS)


def can_pogo_jump_over(
    zombie_def: ZombieDef,
    zombie: ZombieInstance,
    lane: int,
    col: int,
    *,
    blocked_by_tallnut: bool = False,
) -> bool:
    return (
        has_pogo_jump_available(zombie_def, zombie)
        and not blocked_by_tallnut
        and zombie_overlaps_cell(zombie, lane, col)
    )


def pogo_landing_x(col: int, *, home_x: float = 0.0) -> float:
    return max(home_x, float(col) - POGO_LANDING_OFFSET)


def is_balloon_airborne(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    return has_special(zombie_def, SPECIAL_BALLOON) and not has_status_tag(zombie, BALLOON_POPPED_STATUS)


def pop_balloon(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    if not is_balloon_airborne(zombie_def, zombie):
        return False
    add_status_tag(zombie, BALLOON_POPPED_STATUS)
    return True


def jack_in_the_box_fuse_ticks(zombie_def: ZombieDef) -> int | None:
    if not has_special(zombie_def, SPECIAL_JACK_IN_THE_BOX):
        return None
    return JACK_IN_THE_BOX_FUSE_TICKS


def jack_in_the_box_explosion_radius(zombie_def: ZombieDef) -> tuple[int, float] | None:
    if not has_special(zombie_def, SPECIAL_JACK_IN_THE_BOX):
        return None
    return (JACK_IN_THE_BOX_LANE_RADIUS, JACK_IN_THE_BOX_X_RADIUS)


def cell_in_jack_in_the_box_explosion(
    zombie_def: ZombieDef,
    *,
    center_lane: int,
    center_x: float,
    target_lane: int,
    target_col: int,
) -> bool:
    return target_in_jack_in_the_box_explosion(
        zombie_def,
        center_lane=center_lane,
        center_x=center_x,
        target_lane=target_lane,
        target_x=float(target_col),
    )


def target_in_jack_in_the_box_explosion(
    zombie_def: ZombieDef,
    *,
    center_lane: int,
    center_x: float,
    target_lane: int,
    target_x: float,
) -> bool:
    radius = jack_in_the_box_explosion_radius(zombie_def)
    if radius is None:
        return False
    lane_radius, x_radius = radius
    return abs(target_lane - center_lane) <= lane_radius and abs(target_x - center_x) <= x_radius


def gargantuar_imp_throw_threshold(zombie_def: ZombieDef) -> int | None:
    if not has_special(zombie_def, SPECIAL_GARGANTUAR):
        return None
    return int(zombie_def.hp * GARGANTUAR_IMP_THROW_RATIO)


def should_gargantuar_throw_imp(zombie_def: ZombieDef, zombie: ZombieInstance) -> bool:
    threshold = gargantuar_imp_throw_threshold(zombie_def)
    return threshold is not None and zombie.hp <= threshold and not has_status_tag(zombie, GARGANTUAR_IMP_THROWN_STATUS)


def gargantuar_smash_damage(zombie_def: ZombieDef) -> int | None:
    if not has_special(zombie_def, SPECIAL_GARGANTUAR):
        return None
    return GARGANTUAR_SMASH_DAMAGE


def gargantuar_can_smash(zombie_def: ZombieDef, zombie: ZombieInstance, lane: int, col: int) -> bool:
    return has_special(zombie_def, SPECIAL_GARGANTUAR) and zombie_overlaps_cell(zombie, lane, col)


def should_dancing_summon(zombie_def: ZombieDef, zombie: ZombieInstance, *, current_tick: int) -> bool:
    return (
        has_special(zombie_def, SPECIAL_DANCING)
        and zombie.spawned_tick is not None
        and current_tick - zombie.spawned_tick >= DANCING_SUMMON_TICKS
        and not has_status_tag(zombie, DANCING_SUMMONED_STATUS)
    )


def should_bungee_steal(zombie_def: ZombieDef, zombie: ZombieInstance, *, current_tick: int) -> bool:
    return (
        has_special(zombie_def, SPECIAL_BUNGEE)
        and zombie.spawned_tick is not None
        and current_tick - zombie.spawned_tick >= BUNGEE_STEAL_TICKS
        and not has_status_tag(zombie, BUNGEE_STOLEN_STATUS)
    )


def should_catapult_attack(zombie_def: ZombieDef, zombie: ZombieInstance, *, current_tick: int) -> bool:
    return (
        has_special(zombie_def, SPECIAL_CATAPULT)
        and zombie.spawned_tick is not None
        and current_tick > zombie.spawned_tick
        and (current_tick - zombie.spawned_tick) % CATAPULT_ATTACK_INTERVAL_TICKS == 0
    )


def add_frozen_status(zombie: ZombieInstance, *, until_tick: int) -> None:
    tags = {tag for tag in status_tags(zombie) if not tag.startswith(FROZEN_STATUS_PREFIX)}
    tags.add(f"{FROZEN_STATUS_PREFIX}{until_tick}")
    zombie.status = ",".join(sorted(tags)) if tags else "walking"


def frozen_until_tick(zombie: ZombieInstance) -> int | None:
    until_ticks: list[int] = []
    for tag in status_tags(zombie):
        if not tag.startswith(FROZEN_STATUS_PREFIX):
            continue
        try:
            until_ticks.append(int(tag.removeprefix(FROZEN_STATUS_PREFIX)))
        except ValueError:
            continue
    return max(until_ticks, default=None)


def is_frozen(zombie: ZombieInstance, *, current_tick: int) -> bool:
    until_tick = frozen_until_tick(zombie)
    return until_tick is not None and current_tick < until_tick


def clear_expired_frozen_status(zombie: ZombieInstance, *, current_tick: int) -> bool:
    tags = set(status_tags(zombie))
    kept_tags: set[str] = set()
    changed = False
    for tag in tags:
        if not tag.startswith(FROZEN_STATUS_PREFIX):
            kept_tags.add(tag)
            continue
        try:
            until_tick = int(tag.removeprefix(FROZEN_STATUS_PREFIX))
        except ValueError:
            changed = True
            continue
        if current_tick < until_tick:
            kept_tags.add(tag)
        else:
            changed = True
    if changed:
        zombie.status = ",".join(sorted(kept_tags)) if kept_tags else "walking"
    return changed


def zombie_overlaps_cell(zombie: ZombieInstance, lane: int, col: int) -> bool:
    return zombie.lane == lane and float(col) - 0.5 <= zombie.x <= float(col) + 0.5
