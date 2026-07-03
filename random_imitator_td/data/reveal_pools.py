from __future__ import annotations

from random_imitator_td.game.models import RevealResultDef


def _plant(result_id: str, category: str, plant_id: str, weight: int) -> RevealResultDef:
    return RevealResultDef(result_id, category, "plant", {"plant_id": plant_id}, weight)


def _zombie(result_id: str, zombie_id: str, weight: int) -> RevealResultDef:
    return RevealResultDef(result_id, "chaos", "spawn_zombie", {"zombie_id": zombie_id}, weight)


P2_REVEAL_RESULTS: dict[str, RevealResultDef] = {
    result.id: result
    for result in (
        _plant("good_peashooter", "good", "peashooter", 15),
        _plant("good_sunflower", "good", "sunflower", 10),
        _plant("good_wallnut", "good", "wallnut", 10),
        _plant("good_potato_mine", "good", "potato_mine", 8),
        _plant("rare_snow_pea", "rare_good", "snow_pea", 6),
        _plant("rare_repeater", "rare_good", "repeater", 5),
        _plant("good_split_pea", "good", "split_pea", 3),
        _plant("rare_cherry_bomb", "rare_good", "cherry_bomb", 4),
        _plant("rare_squash", "rare_good", "squash", 4),
        _plant("rare_threepeater", "rare_good", "threepeater", 5),
        _plant("rare_chomper", "rare_good", "chomper", 5),
        _plant("rare_cactus", "rare_good", "cactus", 3),
        _plant("rare_starfruit", "rare_good", "starfruit", 3),
        _plant("rare_spikeweed", "rare_good", "spikeweed", 3),
        _plant("rare_tallnut", "rare_good", "tallnut", 3),
        _plant("rare_pumpkin", "rare_good", "pumpkin", 3),
        _plant("rare_umbrella_leaf", "rare_good", "umbrella_leaf", 2),
        _plant("rare_cattail", "rare_good", "cattail", 2),
        _plant("rare_blover", "rare_good", "blover", 2),
        _plant("rare_jalapeno", "rare_good", "jalapeno", 4),
        _plant("bad_lily_pad", "bad", "lily_pad", 5),
        _plant("bad_puff_shroom", "bad", "puff_shroom", 6),
        _plant("bad_grave_buster", "bad", "grave_buster", 5),
        _plant("bad_flower_pot", "bad", "flower_pot", 5),
        _plant("bad_sea_shroom", "bad", "sea_shroom", 3),
        _plant("bad_plantern", "bad", "plantern", 2),
        _plant("bad_scaredy_shroom", "bad", "scaredy_shroom", 6),
        _plant("bad_fume_shroom", "bad", "fume_shroom", 4),
        _plant("bad_magnet_shroom", "bad", "magnet_shroom", 3),
        _plant("bad_ice_shroom", "bad", "ice_shroom", 3),
        _plant("bad_doom_shroom", "bad", "doom_shroom", 2),
        _zombie("chaos_normal_zombie", "normal", 18),
        _zombie("chaos_conehead_zombie", "conehead", 14),
        _zombie("chaos_buckethead_zombie", "buckethead", 9),
        _zombie("chaos_pole_vaulting_zombie", "pole_vaulting", 7),
        _zombie("chaos_newspaper_zombie", "newspaper", 7),
        _zombie("chaos_screen_door_zombie", "screen_door", 5),
        _zombie("chaos_jack_in_the_box_zombie", "jack_in_the_box", 4),
        _zombie("chaos_football_zombie", "football", 3),
        _zombie("chaos_gargantuar_zombie", "gargantuar", 1),
        _zombie("chaos_dancing_zombie", "dancing", 3),
        _zombie("chaos_ducky_tube_zombie", "ducky_tube", 4),
        _zombie("chaos_snorkel_zombie", "snorkel", 3),
        _zombie("chaos_dolphin_rider_zombie", "dolphin_rider", 3),
        _zombie("chaos_miner_zombie", "miner", 3),
        _zombie("chaos_bungee_zombie", "bungee", 2),
        _zombie("chaos_ladder_zombie", "ladder", 3),
        _zombie("chaos_pogo_zombie", "pogo", 3),
        _zombie("chaos_balloon_zombie", "balloon", 2),
        _zombie("chaos_catapult_zombie", "catapult", 2),
        _zombie("chaos_zomboni_zombie", "zomboni", 1),
        RevealResultDef(
            "chaos_zomboss",
            "chaos",
            "boss_event",
            {
                "boss_id": "zomboss",
                "duration_ticks": 600,
                "action_interval_ticks": 60,
                "first_action_delay_ticks": 90,
            },
            3,
        ),
    )
}
