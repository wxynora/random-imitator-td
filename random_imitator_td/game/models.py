from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from .config import GameConfig


@dataclass(frozen=True)
class PlantDef:
    id: str
    hp: int
    attack_interval_ticks: int | None
    damage: int | None
    range_type: str
    special: str | None = None


@dataclass(frozen=True)
class ZombieDef:
    id: str
    hp: int
    walk_speed: float
    bite_dps: int
    budget_cost: int
    special: str | None = None


@dataclass(frozen=True)
class RevealResultDef:
    id: str
    category: str
    kind: str
    payload: dict[str, Any]
    weight: int
    min_level: int = 1


@dataclass
class PendingImitator:
    entity_id: str
    lane: int
    col: int
    hp: int
    planted_tick: int
    reveal_tick: int
    blocking: bool = True


@dataclass
class PlantInstance:
    entity_id: str
    plant_id: str
    lane: int
    col: int
    hp: int
    next_attack_tick: int | None = None
    status: str = "active"
    planted_tick: int = 0


@dataclass
class ZombieInstance:
    entity_id: str
    zombie_id: str
    lane: int
    x: float
    hp: int
    spawned_tick: int | None = None
    status: str = "walking"
    target_entity_id: str | None = None


@dataclass
class BossEventInstance:
    entity_id: str
    boss_id: str
    started_tick: int
    end_tick: int
    next_action_tick: int
    hp: int
    action_interval_ticks: int = 40
    actions_taken: int = 0
    status: str = "active"


@dataclass
class GameState:
    tick: int
    sun: int
    level: int
    grid: dict[tuple[int, int], str | None]
    plants: dict[str, PlantInstance]
    pending_imitators: dict[str, PendingImitator]
    zombies: dict[str, ZombieInstance]
    boss_events: dict[str, BossEventInstance]
    cooldowns: dict[str, int]
    lawnmowers: dict[int, bool]
    wave_state: dict[str, Any]
    scheduled_events: list[dict[str, Any]]
    game_over: bool = False
    result: str | None = None


def empty_grid(config: GameConfig) -> dict[tuple[int, int], str | None]:
    return {(lane, col): None for lane in config.lanes_range() for col in config.cols_range()}


def initial_state(config: GameConfig | None = None, *, level: int = 1) -> GameState:
    config = config or GameConfig()
    card_slot_count = min(config.card_slot_count, config.max_card_slot_count)
    card_ids = list(config.card_loadout[:card_slot_count])
    card_ids.extend(["imitator"] * (card_slot_count - len(card_ids)))
    card_counters: dict[str, int] = {}
    cooldowns: dict[str, int] = {}
    for card_id in card_ids:
        card_counters[card_id] = card_counters.get(card_id, 0) + 1
        cooldowns[f"{card_id}_{card_counters[card_id]}"] = 0
    return GameState(
        tick=0,
        sun=config.initial_sun,
        level=level,
        grid=empty_grid(config),
        plants={},
        pending_imitators={},
        zombies={},
        boss_events={},
        cooldowns=cooldowns,
        lawnmowers={lane: True for lane in config.lanes_range()},
        wave_state={"completed": False},
        scheduled_events=[],
    )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, tuple):
                json_key = ",".join(str(part) for part in key)
            else:
                json_key = str(key)
            result[json_key] = to_jsonable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
