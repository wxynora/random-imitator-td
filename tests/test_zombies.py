from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.data.zombies import ZOMBIES
from random_imitator_td.game.models import ZombieInstance
from random_imitator_td.game.zombie_behaviors import (
    BALLOON_POPPED_STATUS,
    BUNGEE_STEAL_TICKS,
    CATAPULT_ATTACK_INTERVAL_TICKS,
    DANCING_SUMMON_TICKS,
    DANCING_SUMMONED_STATUS,
    DOLPHIN_JUMP_SPENT_STATUS,
    DOLPHIN_RIDER_SPENT_WALK_SPEED,
    GARGANTUAR_SMASH_DAMAGE,
    JACK_IN_THE_BOX_FUSE_TICKS,
    NEWSPAPER_RAGE_HP_THRESHOLD,
    NEWSPAPER_RAGE_WALK_SPEED,
    POLE_VAULTING_SPENT_STATUS,
    POLE_VAULTING_SPENT_WALK_SPEED,
    POGO_STICK_REMOVED_STATUS,
    add_frozen_status,
    can_dolphin_jump_over,
    can_pogo_jump_over,
    can_pole_vault_over,
    cell_in_jack_in_the_box_explosion,
    clear_expired_frozen_status,
    effective_walk_speed,
    frozen_until_tick,
    gargantuar_imp_throw_threshold,
    gargantuar_smash_damage,
    is_balloon_airborne,
    is_frozen,
    is_newspaper_enraged,
    jack_in_the_box_fuse_ticks,
    pop_balloon,
    pogo_landing_x,
    pole_vault_landing_x,
    should_gargantuar_throw_imp,
    should_bungee_steal,
    should_catapult_attack,
    should_dancing_summon,
)


class ImitatorPvzZombieTests(unittest.TestCase):
    def test_implemented_zombie_defs_are_registered(self) -> None:
        self.assertEqual(
            set(ZOMBIES),
            {
                "normal",
                "conehead",
                "buckethead",
                "flag",
                "pole_vaulting",
                "newspaper",
                "jack_in_the_box",
                "football",
                "gargantuar",
                "imp",
                "screen_door",
                "dancing",
                "backup_dancer",
                "dolphin_rider",
                "snorkel",
                "ducky_tube",
                "miner",
                "bungee",
                "ladder",
                "pogo",
                "balloon",
                "catapult",
                "zomboni",
            },
        )
        self.assertEqual(ZOMBIES["normal"].hp, 200)
        self.assertEqual(ZOMBIES["conehead"].budget_cost, 3)
        self.assertEqual(ZOMBIES["buckethead"].budget_cost, 6)

    def test_new_zombie_budget_costs_and_speeds(self) -> None:
        expectations = {
            "flag": (1, 0.12),
            "pole_vaulting": (4, 0.18),
            "newspaper": (4, 0.08),
            "jack_in_the_box": (7, 0.12),
            "football": (9, 0.20),
            "gargantuar": (16, 0.05),
            "imp": (2, 0.14),
            "screen_door": (5, 0.10),
            "dancing": (6, 0.10),
            "backup_dancer": (2, 0.10),
            "dolphin_rider": (6, 0.18),
            "snorkel": (3, 0.10),
            "ducky_tube": (2, 0.10),
            "miner": (7, 0.12),
            "bungee": (7, 0.00),
            "ladder": (6, 0.10),
            "pogo": (7, 0.12),
            "balloon": (6, 0.14),
            "catapult": (9, 0.05),
            "zomboni": (10, 0.08),
        }
        for zombie_id, (budget_cost, walk_speed) in expectations.items():
            with self.subTest(zombie_id=zombie_id):
                self.assertEqual(ZOMBIES[zombie_id].budget_cost, budget_cost)
                self.assertEqual(ZOMBIES[zombie_id].walk_speed, walk_speed)
                self.assertIsNotNone(ZOMBIES[zombie_id].special)

    def test_newspaper_rages_below_threshold(self) -> None:
        zombie_def = ZOMBIES["newspaper"]
        calm = ZombieInstance("z1", "newspaper", lane=3, x=5.0, hp=NEWSPAPER_RAGE_HP_THRESHOLD + 1)
        enraged = ZombieInstance("z2", "newspaper", lane=3, x=5.0, hp=NEWSPAPER_RAGE_HP_THRESHOLD)

        self.assertFalse(is_newspaper_enraged(zombie_def, calm))
        self.assertTrue(is_newspaper_enraged(zombie_def, enraged))
        self.assertEqual(effective_walk_speed(zombie_def, calm), zombie_def.walk_speed)
        self.assertEqual(effective_walk_speed(zombie_def, enraged), NEWSPAPER_RAGE_WALK_SPEED)

    def test_pole_vaulting_jump_conditions(self) -> None:
        zombie_def = ZOMBIES["pole_vaulting"]
        ready = ZombieInstance("z1", "pole_vaulting", lane=2, x=4.5, hp=zombie_def.hp)
        spent = ZombieInstance(
            "z2",
            "pole_vaulting",
            lane=2,
            x=4.5,
            hp=zombie_def.hp,
            status=POLE_VAULTING_SPENT_STATUS,
        )

        self.assertTrue(can_pole_vault_over(zombie_def, ready, lane=2, col=4))
        self.assertFalse(can_pole_vault_over(zombie_def, ready, lane=1, col=4))
        self.assertFalse(can_pole_vault_over(zombie_def, spent, lane=2, col=4))
        self.assertEqual(effective_walk_speed(zombie_def, spent), POLE_VAULTING_SPENT_WALK_SPEED)
        self.assertEqual(pole_vault_landing_x(4), 3.0)

    def test_pogo_jump_conditions(self) -> None:
        zombie_def = ZOMBIES["pogo"]
        ready = ZombieInstance("z1", "pogo", lane=2, x=4.5, hp=zombie_def.hp)
        removed = ZombieInstance(
            "z2",
            "pogo",
            lane=2,
            x=4.5,
            hp=zombie_def.hp,
            status=POGO_STICK_REMOVED_STATUS,
        )

        self.assertTrue(can_pogo_jump_over(zombie_def, ready, lane=2, col=4))
        self.assertFalse(can_pogo_jump_over(zombie_def, ready, lane=2, col=4, blocked_by_tallnut=True))
        self.assertFalse(can_pogo_jump_over(zombie_def, removed, lane=2, col=4))
        self.assertEqual(pogo_landing_x(4), 3.0)

    def test_second_batch_status_helpers(self) -> None:
        dolphin_def = ZOMBIES["dolphin_rider"]
        dolphin = ZombieInstance("z1", "dolphin_rider", lane=2, x=4.5, hp=dolphin_def.hp)
        spent_dolphin = ZombieInstance(
            "z2",
            "dolphin_rider",
            lane=2,
            x=4.5,
            hp=dolphin_def.hp,
            status=DOLPHIN_JUMP_SPENT_STATUS,
        )
        balloon_def = ZOMBIES["balloon"]
        balloon = ZombieInstance("z3", "balloon", lane=3, x=5.0, hp=balloon_def.hp)

        self.assertTrue(can_dolphin_jump_over(dolphin_def, dolphin, lane=2, col=4))
        self.assertFalse(can_dolphin_jump_over(dolphin_def, spent_dolphin, lane=2, col=4))
        self.assertEqual(effective_walk_speed(dolphin_def, spent_dolphin), DOLPHIN_RIDER_SPENT_WALK_SPEED)
        self.assertTrue(is_balloon_airborne(balloon_def, balloon))
        self.assertTrue(pop_balloon(balloon_def, balloon))
        self.assertIn(BALLOON_POPPED_STATUS, balloon.status)
        self.assertFalse(is_balloon_airborne(balloon_def, balloon))

    def test_second_batch_scheduled_special_helpers(self) -> None:
        dancing = ZombieInstance("z1", "dancing", lane=3, x=5.0, hp=500, spawned_tick=0)
        summoned = ZombieInstance(
            "z2",
            "dancing",
            lane=3,
            x=5.0,
            hp=500,
            spawned_tick=0,
            status=DANCING_SUMMONED_STATUS,
        )
        bungee = ZombieInstance("z3", "bungee", lane=3, x=5.0, hp=450, spawned_tick=0)
        catapult = ZombieInstance("z4", "catapult", lane=3, x=8.0, hp=850, spawned_tick=0)

        self.assertFalse(should_dancing_summon(ZOMBIES["dancing"], dancing, current_tick=DANCING_SUMMON_TICKS - 1))
        self.assertTrue(should_dancing_summon(ZOMBIES["dancing"], dancing, current_tick=DANCING_SUMMON_TICKS))
        self.assertFalse(should_dancing_summon(ZOMBIES["dancing"], summoned, current_tick=DANCING_SUMMON_TICKS))
        self.assertTrue(should_bungee_steal(ZOMBIES["bungee"], bungee, current_tick=BUNGEE_STEAL_TICKS))
        self.assertFalse(should_catapult_attack(ZOMBIES["catapult"], catapult, current_tick=1))
        self.assertTrue(
            should_catapult_attack(
                ZOMBIES["catapult"],
                catapult,
                current_tick=CATAPULT_ATTACK_INTERVAL_TICKS,
            )
        )

    def test_freeze_status_expires(self) -> None:
        zombie = ZombieInstance("z1", "normal", lane=3, x=5.0, hp=200)
        add_frozen_status(zombie, until_tick=10)

        self.assertEqual(frozen_until_tick(zombie), 10)
        self.assertTrue(is_frozen(zombie, current_tick=9))
        self.assertFalse(is_frozen(zombie, current_tick=10))
        self.assertTrue(clear_expired_frozen_status(zombie, current_tick=10))
        self.assertEqual(zombie.status, "walking")

    def test_jack_in_the_box_explosion_range(self) -> None:
        zombie_def = ZOMBIES["jack_in_the_box"]

        self.assertEqual(jack_in_the_box_fuse_ticks(zombie_def), JACK_IN_THE_BOX_FUSE_TICKS)
        self.assertTrue(
            cell_in_jack_in_the_box_explosion(
                zombie_def,
                center_lane=3,
                center_x=4.5,
                target_lane=2,
                target_col=5,
            )
        )
        self.assertFalse(
            cell_in_jack_in_the_box_explosion(
                zombie_def,
                center_lane=3,
                center_x=4.5,
                target_lane=5,
                target_col=5,
            )
        )
        self.assertFalse(
            cell_in_jack_in_the_box_explosion(
                zombie_def,
                center_lane=3,
                center_x=4.5,
                target_lane=3,
                target_col=7,
            )
        )

    def test_gargantuar_half_health_imp_throw_threshold(self) -> None:
        zombie_def = ZOMBIES["gargantuar"]
        just_above_half = ZombieInstance("z1", "gargantuar", lane=4, x=6.0, hp=1501)
        half_health = ZombieInstance("z2", "gargantuar", lane=4, x=6.0, hp=1500)
        already_thrown = ZombieInstance("z3", "gargantuar", lane=4, x=6.0, hp=1200, status="imp_thrown")

        self.assertEqual(gargantuar_imp_throw_threshold(zombie_def), zombie_def.hp // 2)
        self.assertFalse(should_gargantuar_throw_imp(zombie_def, just_above_half))
        self.assertTrue(should_gargantuar_throw_imp(zombie_def, half_health))
        self.assertFalse(should_gargantuar_throw_imp(zombie_def, already_thrown))
        self.assertEqual(gargantuar_smash_damage(zombie_def), GARGANTUAR_SMASH_DAMAGE)


if __name__ == "__main__":
    unittest.main()
