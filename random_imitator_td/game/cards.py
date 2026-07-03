from __future__ import annotations

from typing import Any

from .config import GameConfig


DIRECT_CARD_COSTS = {
    "sunflower": 50,
    "peashooter": 100,
    "wallnut": 50,
    "potato_mine": 25,
    "cherry_bomb": 150,
    "snow_pea": 175,
    "repeater": 200,
    "puff_shroom": 25,
    "fume_shroom": 75,
    "squash": 50,
}

DIRECT_CARD_COOLDOWN_TICKS = {
    "sunflower": 80,
    "peashooter": 80,
    "wallnut": 300,
    "potato_mine": 300,
    "cherry_bomb": 500,
    "snow_pea": 80,
    "repeater": 80,
    "puff_shroom": 80,
    "fume_shroom": 80,
    "squash": 300,
}

CARD_CATALOG_ORDER = (
    "imitator",
    "coffee_bean",
    "sunflower",
    "peashooter",
    "wallnut",
    "potato_mine",
    "cherry_bomb",
    "snow_pea",
    "repeater",
    "puff_shroom",
    "fume_shroom",
    "squash",
)

RECOMMENDED_CARD_LOADOUT = ("imitator", "imitator", "imitator", "imitator", "sunflower", "squash")


def card_cost(card_id: str, config: GameConfig) -> int:
    if card_id == "imitator":
        return config.imitator_cost
    if card_id == "coffee_bean":
        return config.coffee_bean_cost
    if card_id in DIRECT_CARD_COSTS:
        return DIRECT_CARD_COSTS[card_id]
    return 0


def card_cooldown_ticks(card_id: str, config: GameConfig) -> int:
    if card_id == "imitator":
        return config.imitator_slot_cooldown_ticks
    if card_id == "coffee_bean":
        return config.coffee_bean_slot_cooldown_ticks
    if card_id in DIRECT_CARD_COOLDOWN_TICKS:
        return DIRECT_CARD_COOLDOWN_TICKS[card_id]
    return config.imitator_slot_cooldown_ticks


def build_card_catalog(config: GameConfig) -> list[dict[str, Any]]:
    return [
        {
            "card_id": card_id,
            "cost": card_cost(card_id, config),
            "cooldown_ticks": card_cooldown_ticks(card_id, config),
            "repeatable": True,
        }
        for card_id in CARD_CATALOG_ORDER
    ]
