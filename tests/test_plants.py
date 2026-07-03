from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.data.plants import PLANTS
from random_imitator_td.game.models import PlantInstance, ZombieInstance
from random_imitator_td.game.plant_behaviors import (
    FUME_SHROOM_RANGE_CELLS,
    POTATO_MINE_ARM_TICKS,
    PUFF_SHROOM_RANGE_CELLS,
    attack_profile,
    can_plant_attack,
    is_plant_sleeping,
    is_potato_mine_armed,
    potato_mine_trigger_target,
    squash_trigger_target,
    target_in_attack_range,
)


class ImitatorPvzPlantTests(unittest.TestCase):
    def test_implemented_plants_are_registered(self) -> None:
        expected = {
            "peashooter",
            "sunflower",
            "wallnut",
            "cherry_bomb",
            "potato_mine",
            "snow_pea",
            "repeater",
            "split_pea",
            "squash",
            "lily_pad",
            "puff_shroom",
            "grave_buster",
            "flower_pot",
            "coffee_bean",
            "sea_shroom",
            "plantern",
            "scaredy_shroom",
            "threepeater",
            "chomper",
            "fume_shroom",
            "cactus",
            "starfruit",
            "spikeweed",
            "tallnut",
            "pumpkin",
            "magnet_shroom",
            "umbrella_leaf",
            "cattail",
            "blover",
            "jalapeno",
            "ice_shroom",
            "doom_shroom",
        }
        self.assertEqual(set(PLANTS), expected)
        for key, plant_def in PLANTS.items():
            self.assertEqual(plant_def.id, key)

    def test_new_plant_data_uses_existing_fields(self) -> None:
        self.assertEqual(PLANTS["potato_mine"].range_type, "cell")
        self.assertEqual(PLANTS["potato_mine"].special, f"armed_after_{POTATO_MINE_ARM_TICKS}")
        self.assertEqual(PLANTS["snow_pea"].special, "slow_projectile")
        self.assertEqual(PLANTS["repeater"].special, "double_shot")
        self.assertEqual(PLANTS["split_pea"].range_type, "lane_both")
        self.assertEqual(PLANTS["squash"].range_type, "near_cell")
        self.assertEqual(PLANTS["lily_pad"].special, "water_platform")
        self.assertEqual(PLANTS["puff_shroom"].range_type, "lane_forward_short")
        self.assertEqual(PLANTS["grave_buster"].special, "grave_buster")
        self.assertEqual(PLANTS["flower_pot"].special, "roof_platform")
        self.assertEqual(PLANTS["coffee_bean"].special, "wake_sleeping_mushroom")
        self.assertIn("water_plant", PLANTS["sea_shroom"].special or "")
        self.assertEqual(PLANTS["plantern"].special, "fog_reveal")
        self.assertIn("scared_when_near", PLANTS["scaredy_shroom"].special or "")
        self.assertEqual(PLANTS["threepeater"].range_type, "three_lanes_forward")
        self.assertIn("starts_ready", PLANTS["chomper"].special or "")
        self.assertEqual(PLANTS["fume_shroom"].range_type, "lane_forward_pierce")
        self.assertIn("anti_air", PLANTS["cactus"].special or "")
        self.assertEqual(PLANTS["starfruit"].range_type, "star_five_way")
        self.assertIn("non_blocking", PLANTS["spikeweed"].special or "")
        self.assertIn("tall_blocker", PLANTS["tallnut"].special or "")
        self.assertIn("pumpkin_shell", PLANTS["pumpkin"].special or "")
        self.assertIn("magnet", PLANTS["magnet_shroom"].special or "")
        self.assertIn("umbrella_protect", PLANTS["umbrella_leaf"].special or "")
        self.assertIn("homing", PLANTS["cattail"].special or "")
        self.assertIn("instant_blover", PLANTS["blover"].special or "")
        self.assertIn("instant_jalapeno", PLANTS["jalapeno"].special or "")
        self.assertIn("instant_freeze", PLANTS["ice_shroom"].special or "")
        self.assertIn("instant_doom", PLANTS["doom_shroom"].special or "")

    def test_attack_profiles_cover_single_double_and_slow_shots(self) -> None:
        peashooter = attack_profile(PLANTS["peashooter"])
        snow_pea = attack_profile(PLANTS["snow_pea"])
        repeater = attack_profile(PLANTS["repeater"])

        self.assertIsNotNone(peashooter)
        self.assertIsNotNone(snow_pea)
        self.assertIsNotNone(repeater)
        assert peashooter is not None
        assert snow_pea is not None
        assert repeater is not None

        self.assertEqual(peashooter.shots, 1)
        self.assertEqual(peashooter.total_damage, 20)
        self.assertEqual(snow_pea.effects, ("slow",))
        self.assertEqual(repeater.shots, 2)
        self.assertEqual(repeater.total_damage, 40)
        self.assertIsNone(attack_profile(PLANTS["wallnut"]))
        self.assertIsNone(attack_profile(PLANTS["magnet_shroom"]))

        threepeater = attack_profile(PLANTS["threepeater"])
        fume_shroom = attack_profile(PLANTS["fume_shroom"])
        cattail = attack_profile(PLANTS["cattail"])
        self.assertIsNotNone(threepeater)
        self.assertIsNotNone(fume_shroom)
        self.assertIsNotNone(cattail)
        assert threepeater is not None
        assert fume_shroom is not None
        assert cattail is not None
        self.assertEqual(threepeater.shots, 3)
        self.assertEqual(threepeater.total_damage, 60)
        self.assertEqual(fume_shroom.range_type, "lane_forward_pierce")
        self.assertEqual(cattail.shots, 2)
        self.assertEqual(cattail.range_type, "full_board")

    def test_puff_shroom_has_short_forward_range(self) -> None:
        plant = PlantInstance("p1", "puff_shroom", lane=3, col=4, hp=300, next_attack_tick=10)
        in_range = ZombieInstance("z1", "normal", lane=3, x=4 + PUFF_SHROOM_RANGE_CELLS, hp=200)
        too_far = ZombieInstance("z2", "normal", lane=3, x=4 + PUFF_SHROOM_RANGE_CELLS + 0.1, hp=200)
        wrong_lane = ZombieInstance("z3", "normal", lane=2, x=5, hp=200)

        self.assertTrue(target_in_attack_range(plant, PLANTS["puff_shroom"], in_range))
        self.assertFalse(target_in_attack_range(plant, PLANTS["puff_shroom"], too_far))
        self.assertFalse(target_in_attack_range(plant, PLANTS["puff_shroom"], wrong_lane))
        self.assertTrue(can_plant_attack(plant, PLANTS["puff_shroom"], [in_range], current_tick=10, is_day=False))
        self.assertFalse(can_plant_attack(plant, PLANTS["puff_shroom"], [in_range], current_tick=10, is_day=True))

    def test_fume_and_threepeater_ranges(self) -> None:
        fume = PlantInstance("p1", "fume_shroom", lane=3, col=4, hp=300, next_attack_tick=10, status="active,awake")
        near = ZombieInstance("z1", "normal", lane=3, x=4 + FUME_SHROOM_RANGE_CELLS, hp=200)
        far = ZombieInstance("z2", "normal", lane=3, x=4 + FUME_SHROOM_RANGE_CELLS + 0.1, hp=200)
        three = PlantInstance("p2", "threepeater", lane=3, col=4, hp=300, next_attack_tick=10)
        upper_lane = ZombieInstance("z3", "normal", lane=2, x=5, hp=200)
        too_far_lane = ZombieInstance("z4", "normal", lane=1, x=5, hp=200)

        self.assertTrue(target_in_attack_range(fume, PLANTS["fume_shroom"], near))
        self.assertFalse(target_in_attack_range(fume, PLANTS["fume_shroom"], far))
        self.assertTrue(target_in_attack_range(three, PLANTS["threepeater"], upper_lane))
        self.assertFalse(target_in_attack_range(three, PLANTS["threepeater"], too_far_lane))

    def test_split_pea_starfruit_and_spikeweed_ranges(self) -> None:
        split = PlantInstance("p1", "split_pea", lane=3, col=4, hp=300, next_attack_tick=10)
        behind = ZombieInstance("z1", "normal", lane=3, x=2.0, hp=200)
        wrong_lane = ZombieInstance("z2", "normal", lane=2, x=2.0, hp=200)
        star = PlantInstance("p2", "starfruit", lane=3, col=4, hp=300, next_attack_tick=10)
        diagonal = ZombieInstance("z3", "normal", lane=4, x=5.0, hp=200)
        off_diagonal = ZombieInstance("z4", "normal", lane=5, x=5.0, hp=200)
        spike = PlantInstance("p3", "spikeweed", lane=3, col=4, hp=300, next_attack_tick=10)
        on_spike = ZombieInstance("z5", "normal", lane=3, x=4.4, hp=200)
        past_spike = ZombieInstance("z6", "normal", lane=3, x=4.6, hp=200)

        self.assertTrue(target_in_attack_range(split, PLANTS["split_pea"], behind))
        self.assertFalse(target_in_attack_range(split, PLANTS["split_pea"], wrong_lane))
        self.assertTrue(target_in_attack_range(star, PLANTS["starfruit"], diagonal))
        self.assertFalse(target_in_attack_range(star, PLANTS["starfruit"], off_diagonal))
        self.assertTrue(target_in_attack_range(spike, PLANTS["spikeweed"], on_spike))
        self.assertFalse(target_in_attack_range(spike, PLANTS["spikeweed"], past_spike))

    def test_shrooms_sleep_during_day(self) -> None:
        self.assertTrue(is_plant_sleeping(PLANTS["puff_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["scaredy_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["fume_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["sea_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["magnet_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["ice_shroom"], is_day=True))
        self.assertTrue(is_plant_sleeping(PLANTS["doom_shroom"], is_day=True))
        self.assertFalse(is_plant_sleeping(PLANTS["snow_pea"], is_day=True))
        self.assertFalse(is_plant_sleeping(PLANTS["puff_shroom"], is_day=False))
        awakened = PlantInstance("p_awake", "puff_shroom", lane=3, col=4, hp=300, status="active,awake")
        self.assertFalse(is_plant_sleeping(PLANTS["puff_shroom"], is_day=True, plant=awakened))

    def test_scaredy_shroom_stops_attacking_when_zombie_is_near(self) -> None:
        plant = PlantInstance("p1", "scaredy_shroom", lane=3, col=4, hp=300, next_attack_tick=10)
        near = ZombieInstance("z_near", "normal", lane=3, x=5.4, hp=200)
        far = ZombieInstance("z_far", "normal", lane=3, x=6.0, hp=200)

        self.assertFalse(can_plant_attack(plant, PLANTS["scaredy_shroom"], [near], current_tick=10, is_day=False))
        self.assertTrue(can_plant_attack(plant, PLANTS["scaredy_shroom"], [far], current_tick=10, is_day=False))

    def test_potato_mine_arms_after_prepare_time(self) -> None:
        plant_def = PLANTS["potato_mine"]
        self.assertFalse(is_potato_mine_armed(plant_def, planted_tick=5, current_tick=5 + POTATO_MINE_ARM_TICKS - 1))
        self.assertTrue(is_potato_mine_armed(plant_def, planted_tick=5, current_tick=5 + POTATO_MINE_ARM_TICKS))

        plant = PlantInstance("p1", "potato_mine", lane=3, col=4, hp=300)
        zombie = ZombieInstance("z1", "normal", lane=3, x=4.4, hp=200)
        self.assertIsNone(
            potato_mine_trigger_target(
                plant,
                plant_def,
                [zombie],
                planted_tick=5,
                current_tick=5 + POTATO_MINE_ARM_TICKS - 1,
            )
        )
        self.assertEqual(
            potato_mine_trigger_target(
                plant,
                plant_def,
                [zombie],
                planted_tick=5,
                current_tick=5 + POTATO_MINE_ARM_TICKS,
            ),
            zombie,
        )

    def test_squash_triggers_on_nearby_zombie(self) -> None:
        plant = PlantInstance("p1", "squash", lane=3, col=4, hp=300)
        close = ZombieInstance("z_close", "normal", lane=3, x=5.4, hp=200)
        too_far = ZombieInstance("z_far", "normal", lane=3, x=5.6, hp=200)
        wrong_lane = ZombieInstance("z_wrong", "normal", lane=2, x=4.5, hp=200)

        self.assertEqual(squash_trigger_target(plant, PLANTS["squash"], [close]), close)
        self.assertIsNone(squash_trigger_target(plant, PLANTS["squash"], [too_far, wrong_lane]))


if __name__ == "__main__":
    unittest.main()
