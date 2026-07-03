from __future__ import annotations

from random_imitator_td.game import zombie_behaviors
from random_imitator_td.game.models import ZombieDef


ZOMBIES: dict[str, ZombieDef] = {
    "normal": ZombieDef("normal", 200, 0.10, 100, 1),
    "conehead": ZombieDef("conehead", 640, 0.10, 100, 3),
    "buckethead": ZombieDef("buckethead", 1370, 0.10, 100, 6),
    "flag": ZombieDef("flag", 200, 0.12, 100, 1, zombie_behaviors.SPECIAL_FLAG_WAVE),
    "pole_vaulting": ZombieDef(
        "pole_vaulting",
        340,
        zombie_behaviors.POLE_VAULTING_FAST_WALK_SPEED,
        100,
        4,
        zombie_behaviors.SPECIAL_POLE_VAULTING,
    ),
    "newspaper": ZombieDef("newspaper", 420, 0.08, 100, 4, zombie_behaviors.SPECIAL_NEWSPAPER_RAGE),
    "jack_in_the_box": ZombieDef(
        "jack_in_the_box",
        500,
        0.12,
        100,
        7,
        zombie_behaviors.SPECIAL_JACK_IN_THE_BOX,
    ),
    "football": ZombieDef("football", 1670, 0.20, 100, 9, zombie_behaviors.SPECIAL_FOOTBALL_ARMOR),
    "gargantuar": ZombieDef("gargantuar", 3000, 0.05, 300, 16, zombie_behaviors.SPECIAL_GARGANTUAR),
    "imp": ZombieDef("imp", 200, 0.14, 100, 2, zombie_behaviors.SPECIAL_IMP),
    "screen_door": ZombieDef("screen_door", 1100, 0.10, 100, 5, zombie_behaviors.SPECIAL_SCREEN_DOOR),
    "dancing": ZombieDef("dancing", 500, 0.10, 100, 6, zombie_behaviors.SPECIAL_DANCING),
    "backup_dancer": ZombieDef("backup_dancer", 270, 0.10, 100, 2, zombie_behaviors.SPECIAL_BACKUP_DANCER),
    "dolphin_rider": ZombieDef(
        "dolphin_rider",
        500,
        zombie_behaviors.DOLPHIN_RIDER_FAST_WALK_SPEED,
        100,
        6,
        zombie_behaviors.SPECIAL_DOLPHIN_RIDER,
    ),
    "snorkel": ZombieDef("snorkel", 200, 0.10, 100, 3, zombie_behaviors.SPECIAL_SNORKEL),
    "ducky_tube": ZombieDef("ducky_tube", 200, 0.10, 100, 2, zombie_behaviors.SPECIAL_DUCKY_TUBE),
    "miner": ZombieDef("miner", 420, 0.12, 100, 7, zombie_behaviors.SPECIAL_MINER),
    "bungee": ZombieDef("bungee", 450, 0.00, 0, 7, zombie_behaviors.SPECIAL_BUNGEE),
    "ladder": ZombieDef("ladder", 1000, 0.10, 100, 6, zombie_behaviors.SPECIAL_LADDER),
    "pogo": ZombieDef("pogo", 500, 0.12, 100, 7, zombie_behaviors.SPECIAL_POGO),
    "balloon": ZombieDef("balloon", 290, 0.14, 100, 6, zombie_behaviors.SPECIAL_BALLOON),
    "catapult": ZombieDef("catapult", 850, 0.05, 100, 9, zombie_behaviors.SPECIAL_CATAPULT),
    "zomboni": ZombieDef("zomboni", 1350, 0.08, 3000, 10, zombie_behaviors.SPECIAL_ZOMBONI),
}
