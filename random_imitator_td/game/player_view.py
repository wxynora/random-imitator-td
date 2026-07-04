from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
from typing import Any

from .cards import RECOMMENDED_CARD_LOADOUT, build_card_catalog
from . import plant_behaviors, zombie_behaviors
from .config import GameConfig, SCHEMA_VERSION
from .models import GameState, PlantDef, PlantInstance, ZombieDef, ZombieInstance
from .presets import is_all_imitator_level


PENDING_IMITATOR_SYMBOL = "模"
ROOF_POT_STATUS = "roof_pot"

PLANT_NAMES: dict[str, str] = {
    "imitator": "模仿者",
    "peashooter": "豌豆射手",
    "sunflower": "向日葵",
    "wallnut": "坚果墙",
    "cherry_bomb": "樱桃炸弹",
    "potato_mine": "土豆雷",
    "snow_pea": "寒冰射手",
    "repeater": "双发射手",
    "split_pea": "双向射手",
    "squash": "窝瓜",
    "lily_pad": "睡莲",
    "puff_shroom": "小喷菇",
    "grave_buster": "墓碑吞噬者",
    "flower_pot": "花盆",
    "coffee_bean": "咖啡豆",
    "sea_shroom": "海蘑菇",
    "plantern": "路灯花",
    "scaredy_shroom": "胆小菇",
    "threepeater": "三线射手",
    "chomper": "大嘴花",
    "fume_shroom": "大喷菇",
    "cactus": "仙人掌",
    "starfruit": "杨桃",
    "spikeweed": "地刺",
    "tallnut": "高坚果",
    "pumpkin": "南瓜头",
    "magnet_shroom": "磁力菇",
    "umbrella_leaf": "叶子保护伞",
    "cattail": "猫尾草",
    "blover": "三叶草",
    "jalapeno": "火爆辣椒",
    "ice_shroom": "寒冰菇",
    "doom_shroom": "毁灭菇",
}

PLANT_SYMBOLS: dict[str, str] = {
    "peashooter": "豌",
    "sunflower": "向",
    "wallnut": "坚",
    "cherry_bomb": "樱",
    "potato_mine": "土",
    "snow_pea": "冰豌",
    "repeater": "双",
    "split_pea": "裂",
    "squash": "窝",
    "lily_pad": "睡莲",
    "puff_shroom": "小",
    "grave_buster": "墓",
    "flower_pot": "盆",
    "coffee_bean": "咖",
    "sea_shroom": "海",
    "plantern": "灯",
    "scaredy_shroom": "怯",
    "threepeater": "三",
    "chomper": "食",
    "fume_shroom": "烟",
    "cactus": "仙",
    "starfruit": "星",
    "spikeweed": "刺",
    "tallnut": "高",
    "pumpkin": "南",
    "magnet_shroom": "磁",
    "umbrella_leaf": "伞",
    "cattail": "猫",
    "blover": "三叶",
    "jalapeno": "辣",
    "ice_shroom": "冰菇",
    "doom_shroom": "毁",
}

ZOMBIE_NAMES: dict[str, str] = {
    "normal": "普通僵尸",
    "flag": "旗帜僵尸",
    "conehead": "路障僵尸",
    "buckethead": "铁桶僵尸",
    "pole_vaulting": "撑杆僵尸",
    "newspaper": "读报僵尸",
    "jack_in_the_box": "小丑僵尸",
    "football": "橄榄球僵尸",
    "gargantuar": "巨人僵尸",
    "imp": "小鬼僵尸",
    "screen_door": "铁门僵尸",
    "dancing": "舞王僵尸",
    "backup_dancer": "伴舞僵尸",
    "dolphin_rider": "海豚骑士僵尸",
    "snorkel": "潜水僵尸",
    "ducky_tube": "鸭子救生圈僵尸",
    "miner": "矿工僵尸",
    "bungee": "蹦极僵尸",
    "ladder": "梯子僵尸",
    "pogo": "跳跳僵尸",
    "balloon": "气球僵尸",
    "catapult": "投石车僵尸",
    "zomboni": "雪橇车僵尸",
}

ZOMBIE_SYMBOLS: dict[str, str] = {
    "normal": "普",
    "flag": "旗",
    "conehead": "路",
    "buckethead": "桶",
    "pole_vaulting": "撑",
    "newspaper": "报",
    "jack_in_the_box": "丑",
    "football": "球",
    "gargantuar": "巨",
    "imp": "小",
    "screen_door": "门",
    "dancing": "舞",
    "backup_dancer": "伴",
    "dolphin_rider": "豚",
    "snorkel": "潜",
    "ducky_tube": "鸭",
    "miner": "矿",
    "bungee": "蹦",
    "ladder": "梯",
    "pogo": "跳",
    "balloon": "气",
    "catapult": "投",
    "zomboni": "车",
}

PLANT_TRAITS: dict[str, str] = {
    "peashooter": "向本行前方发射豌豆。",
    "sunflower": "按间隔产生阳光。",
    "wallnut": "高耐久阻挡植物。",
    "cherry_bomb": "出现后引爆附近区域。",
    "potato_mine": "种下一段时间后武装，触碰后爆炸。",
    "snow_pea": "向本行前方攻击，并附带减速效果。",
    "repeater": "向本行前方连续发射两颗豌豆。",
    "split_pea": "可向前后两个方向攻击。",
    "squash": "会压向附近僵尸，触发后消失。",
    "lily_pad": "水面平台植物；作为占格植物参与阻挡。",
    "puff_shroom": "短距离攻击蘑菇；白天默认睡觉。",
    "grave_buster": "用于吞墓碑；当前无墓碑层时主要作为占格结果。",
    "flower_pot": "屋顶平台植物；作为占格植物参与阻挡。",
    "coffee_bean": "唤醒目标格的沉睡蘑菇，不进入模仿者随机池。",
    "sea_shroom": "水路短距离攻击蘑菇；白天默认睡觉。",
    "plantern": "用于驱散迷雾，揭开附近视野。",
    "scaredy_shroom": "可远程攻击；白天睡觉，近处有僵尸时会停止攻击。",
    "threepeater": "向本行和相邻两行前方攻击。",
    "chomper": "吞掉近处僵尸后需要较长时间恢复。",
    "fume_shroom": "短中距离穿透攻击蘑菇；白天默认睡觉。",
    "cactus": "可攻击前方，并能命中气球僵尸。",
    "starfruit": "向多个方向发射星星。",
    "spikeweed": "地面伤害植物，不阻挡僵尸；可扎破车辆类僵尸。",
    "tallnut": "高耐久阻挡植物，可挡住部分跳跃。",
    "pumpkin": "保护壳类阻挡；当前实现按高耐久阻挡处理。",
    "magnet_shroom": "吸走部分金属装备；白天默认睡觉。",
    "umbrella_leaf": "可拦截部分从天而降或投掷类效果。",
    "cattail": "全场追踪攻击，可命中气球僵尸。",
    "blover": "出现后吹走空中气球僵尸。",
    "jalapeno": "出现后攻击整条路。",
    "ice_shroom": "出现后冻结全场僵尸；白天默认睡觉。",
    "doom_shroom": "出现后大范围爆炸；白天默认睡觉。",
}

ZOMBIE_TRAITS: dict[str, str] = {
    "normal": "基础僵尸，普通速度和血量。",
    "flag": "接近普通僵尸，主要用于僵尸潮标记。",
    "conehead": "带路障防具，血量高于普通僵尸。",
    "buckethead": "带铁桶防具，耐久很高。",
    "pole_vaulting": "第一次遇到普通阻挡会跳过，之后降速。",
    "newspaper": "报纸破损后暴怒，移动速度会变快。",
    "jack_in_the_box": "小丑盒倒计时爆炸，摧毁附近单位。",
    "football": "移动快且耐久高。",
    "gargantuar": "会砸掉阻挡物，半血后丢出小鬼。",
    "imp": "血量低，移动较快。",
    "screen_door": "门板提供高耐久。",
    "dancing": "存活一段时间后召唤伴舞到相邻行。",
    "backup_dancer": "通常由舞王召唤出现。",
    "dolphin_rider": "首次遇到普通阻挡会跳过一格，之后降速。",
    "snorkel": "潜水僵尸；水下隐藏层未细化，按普通推进单位处理。",
    "ducky_tube": "鸭子圈僵尸；水路单位，按普通推进单位处理。",
    "miner": "矿工僵尸；当前地下绕后未细化，按较快特殊僵尸处理。",
    "bungee": "短暂停留后偷走同一路附近植物并离场。",
    "ladder": "血量较高；当前梯子放置状态未细化。",
    "pogo": "会跳过普通阻挡；高坚果可挡跳，磁力菇可移除跳杆。",
    "balloon": "空中时无视阻挡；被对空命中后落地。",
    "catapult": "周期性攻击本行后排植物，同时缓慢推进。",
    "zomboni": "高耐久车辆，近身会高伤害压碎阻挡。",
}

CARD_COMMANDS: dict[str, str] = {name: plant_id for plant_id, name in PLANT_NAMES.items()}
CARD_COMMANDS.update(
    {
        "咖啡": "coffee_bean",
        "豌豆": "peashooter",
        "坚果": "wallnut",
        "土豆": "potato_mine",
        "寒冰": "snow_pea",
        "双发": "repeater",
        "小喷菇": "puff_shroom",
        "大喷菇": "fume_shroom",
    }
)


def build_player_view(
    *,
    state: GameState,
    config: GameConfig,
    plant_defs: dict[str, PlantDef],
    zombie_defs: dict[str, ZombieDef],
    events: list[dict[str, Any]],
    valid_actions: list[str],
    card_slots: list[dict[str, Any]],
    previously_seen_unit_ids: set[str] | frozenset[str],
    card_costs: dict[str, int] | None = None,
    wave_progress: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    current_unit_ids = _current_unit_ids(state, events)
    new_unit_ids = sorted(unit_id for unit_id in current_unit_ids if unit_id not in previously_seen_unit_ids)
    new_unit_traits = [_unit_trait(unit_id, plant_defs=plant_defs, zombie_defs=zombie_defs) for unit_id in new_unit_ids]
    if is_all_imitator_level(state.level):
        stage_label = "全模仿者·空投" if config.enable_airdrops else "全模仿者"
    elif config.water_lanes:
        stage_label = "泳池"
    elif config.fog_start_col is not None:
        stage_label = "迷雾夜间"
    elif config.is_roof:
        stage_label = "屋顶"
    else:
        stage_label = "白天" if config.is_day else "夜间"
    lines = [
        f"Lv{state.level} 场地:{stage_label} tick {state.tick}",
        f"资源: 阳光{state.sun} | 推车:{_lawnmower_line(state, config)}",
        f"系统波次: {_wave_progress_line(wave_progress)}",
    ]
    if config.water_lanes:
        lines.append("地形: 水路" + ",".join(str(lane) for lane in config.water_lanes))
    if config.fog_start_col is not None:
        lines.append(f"地形: 迷雾{config.fog_start_col}-{config.cols}列，路灯花可揭开附近视野")
    if config.is_roof:
        lines.append("地形: 屋顶，花盆可作为平台并提供一次缓冲；瓦片会按tick滑落")
    if config.enable_airdrops:
        lines.append("空投: " + _airdrop_progress_line(state, config))

    event_lines = _event_lines(events)
    if event_lines:
        lines.extend(["", "事件:"])
        lines.extend(f"- {line}" for line in event_lines)

    boss_lines = _boss_lines(state)
    if boss_lines:
        lines.extend(["", "Boss:"])
        lines.extend(f"- {line}" for line in boss_lines)

    if new_unit_traits:
        lines.extend(["", "新单位:"])
        lines.extend(
            f"- {item['symbol']} {item['name']}: {item['trait']}"
            for item in new_unit_traits
        )

    lines.extend(["", "列: " + " ".join(str(col) for col in config.cols_range())])
    for lane in config.lanes_range():
        lane_label = f"{lane}水" if config.is_water_lane(lane) else str(lane)
        lines.append(f"{lane_label}: " + " ".join(_lane_cells(state, config, plant_defs, zombie_defs, lane)))

    alert_lines = _alert_lines_from_observation_events(events)
    if alert_lines:
        lines.extend(["", "提示:"])
        lines.extend(f"- {line}" for line in alert_lines)

    lines.extend(
        [
            "",
            "卡槽: " + _ready_cards_line(card_slots, card_costs or {}, current_sun=state.sun),
            "动作: " + _actions_line(valid_actions),
        ]
    )
    lines.append("动作格式: 种 模仿者 3-4; 种 豌豆射手 2-3; 种 咖啡豆 2-3; 开空投 3-5; 铲 4-5; 等待; 结束本局")
    rules = "规则: 咖啡豆会唤醒目标格的沉睡蘑菇；铲子只移除植物/未开奖模仿者，同格有僵尸也只铲植物；动作失败会中断后续动作，已发生的推进保留"
    if config.is_roof:
        rules += "；种到花盆上的植物/模仿者带一次花盆缓冲"
    if config.enable_airdrops:
        rules += "；空投占格但不阻拦僵尸，僵尸经过会打开，炸弹清除不开奖"
    lines.append(rules)

    return (
        {
            "format": "board_text_v1",
            "text": "\n".join(lines),
            "new_unit_traits": new_unit_traits,
            "legend": {
                "empty": "空",
                "pending_imitator": PENDING_IMITATOR_SYMBOL,
                "eating_suffix": "咬",
            },
        },
        current_unit_ids,
    )


def build_card_selection_view(
    config: GameConfig,
    *,
    recommended_loadout: tuple[str, ...] = RECOMMENDED_CARD_LOADOUT,
) -> dict[str, Any]:
    catalog = build_card_catalog(config)
    cards = ", ".join(
        f"{_card_name(str(card['card_id']))}({card['cost']})"
        for card in catalog
    )
    recommended = " ".join(_card_name(card_id) for card_id in recommended_loadout)
    return {
        "format": "card_selection_text_v1",
        "text": (
            f"开局选卡: 槽位{config.card_slot_count}/{config.max_card_slot_count}，可重复选择\n"
            f"默认卡组: {recommended}\n"
            f"候选卡: {cards}"
        ),
        "card_catalog": catalog,
        "recommended_loadout": list(recommended_loadout),
    }


def parse_player_text_action_plan(
    text: str,
    *,
    observation: dict[str, Any],
    action_plan_id: str | None = None,
    interrupt_policy: str = "interrupt_on_emergency",
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for raw_line in re.split(r"[\n;；]+", text):
        line = raw_line.strip()
        if not line:
            continue
        normalized = re.sub(r"\s+", " ", line)
        wait_match = re.match(r"^(?:等待|wait|等)(?:\s+(\d+))?$", normalized, re.I)
        if wait_match:
            actions.append({"action": "wait", "max_wait_ticks": int(wait_match.group(1) or 80)})
            continue
        if normalized in {"结束", "结束本局", "重开", "放弃", "end_game"}:
            actions.append({"action": "end_game"})
            continue

        airdrop_match = re.match(r"^(?:开空投|打开空投|开箱|open_airdrop)\s*(\d+)\s*[-,， ]\s*(\d+)$", normalized, re.I)
        if airdrop_match:
            lane, col = _lane_col_from_match(airdrop_match)
            actions.append({"action": "open_airdrop", "lane": lane, "col": col})
            continue

        shovel_match = re.match(r"^(?:铲|铲除|shovel)\s*(\d+)\s*[-,， ]\s*(\d+)$", normalized, re.I)
        if shovel_match:
            lane, col = _lane_col_from_match(shovel_match)
            actions.append({"action": "shovel_plant", "lane": lane, "col": col})
            continue

        plant_match = re.match(r"^(?:种|种植|plant)\s*([^\d ]+)\s*(\d+)\s*[-,， ]\s*(\d+)$", normalized, re.I)
        if plant_match:
            card_name = plant_match.group(1).strip()
            lane, col = _lane_col_from_match(plant_match)
            if card_name in {"模仿者", "模", "imitator"}:
                actions.append({"action": "plant_imitator", "lane": lane, "col": col})
                continue
            card_id = CARD_COMMANDS.get(card_name)
            if card_id is not None:
                action: dict[str, Any] = {"action": "plant_card", "lane": lane, "col": col}
                slot_id = _first_slot_for_card(observation, card_id)
                if slot_id is not None:
                    action["slot_id"] = slot_id
                actions.append(action)
                continue
        raise ValueError(f"unknown_player_command:{line}")

    if not actions:
        raise ValueError("empty_player_command")

    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": observation["observation_id"],
        "action_plan_id": action_plan_id or f"plan_{observation['observation_id']}_player_text",
        "interrupt_policy": interrupt_policy,
        "actions": actions,
    }


def _lane_col_from_match(match: re.Match[str]) -> tuple[int, int]:
    return int(match.group(match.lastindex - 1)), int(match.group(match.lastindex))


def _first_slot_for_card(observation: dict[str, Any], card_id: str) -> str | None:
    slots = observation.get("action_constraints", {}).get("card_slots", [])
    for slot in slots:
        if slot.get("card_id") == card_id and slot.get("ready"):
            return slot.get("slot_id")
    for slot in slots:
        if slot.get("card_id") == card_id:
            return slot.get("slot_id")
    return None


def _current_unit_ids(state: GameState, events: list[dict[str, Any]]) -> set[str]:
    unit_ids = {f"plant:{plant.plant_id}" for plant in state.plants.values()}
    unit_ids.update(f"zombie:{zombie.zombie_id}" for zombie in state.zombies.values())
    unit_ids.update(f"boss:{boss.boss_id}" for boss in state.boss_events.values())
    for event in events:
        plant_id = event.get("plant_id") or event.get("plant_type")
        if isinstance(plant_id, str) and plant_id and not plant_id.startswith("p"):
            unit_ids.add(f"plant:{plant_id}")
        zombie_id = event.get("zombie_type")
        if isinstance(zombie_id, str) and zombie_id:
            unit_ids.add(f"zombie:{zombie_id}")
        boss_id = event.get("boss_id")
        if isinstance(boss_id, str) and boss_id:
            unit_ids.add(f"boss:{boss_id}")
    return unit_ids


def _unit_trait(
    unit_id: str,
    *,
    plant_defs: dict[str, PlantDef],
    zombie_defs: dict[str, ZombieDef],
) -> dict[str, str]:
    kind, _, raw_id = unit_id.partition(":")
    if kind == "plant":
        return {
            "id": raw_id,
            "kind": "plant",
            "name": PLANT_NAMES.get(raw_id, raw_id),
            "symbol": PLANT_SYMBOLS.get(raw_id, raw_id[:1]),
            "trait": PLANT_TRAITS.get(raw_id, _plant_trait_from_def(raw_id, plant_defs.get(raw_id))),
        }
    if kind == "zombie":
        return {
            "id": raw_id,
            "kind": "zombie",
            "name": ZOMBIE_NAMES.get(raw_id, raw_id),
            "symbol": ZOMBIE_SYMBOLS.get(raw_id, raw_id[:1]),
            "trait": ZOMBIE_TRAITS.get(raw_id, _zombie_trait_from_def(raw_id, zombie_defs.get(raw_id))),
        }
    return {
        "id": raw_id,
        "kind": "boss",
        "name": "僵王博士" if raw_id == "zomboss" else raw_id,
        "symbol": "王",
        "trait": "作为持续事件存在，会按间隔召唤或破坏格子。",
    }


def _plant_trait_from_def(plant_id: str, plant_def: PlantDef | None) -> str:
    if plant_def is None:
        return "植物特性以本局规则表为准。"
    if plant_behaviors.is_day_sleeper(plant_def):
        return "蘑菇类植物，白天默认睡觉。"
    if plant_def.attack_interval_ticks is not None:
        return "按攻击间隔对范围内僵尸造成伤害。"
    return "非直接攻击植物。"


def _zombie_trait_from_def(zombie_id: str, zombie_def: ZombieDef | None) -> str:
    if zombie_def is None:
        return "僵尸特性以本局规则表为准。"
    if zombie_def.special:
        return "特殊僵尸，行为按本局规则表结算。"
    return "普通推进型僵尸。"


def _lawnmower_line(state: GameState, config: GameConfig) -> str:
    available = [str(lane) for lane in config.lanes_range() if state.lawnmowers.get(lane, False)]
    return ",".join(available) if available else "无"


def _wave_progress_line(wave_progress: dict[str, Any] | None) -> str:
    if not wave_progress:
        return "未知"
    if wave_progress.get("endless"):
        spawned = wave_progress.get("spawned", 0)
        next_wave = wave_progress.get("next")
        if isinstance(next_wave, dict):
            tick = next_wave.get("tick")
            in_ticks = next_wave.get("in_ticks")
            if isinstance(tick, int) and isinstance(in_ticks, int):
                return f"无尽，已出现{spawned}只，下一波 tick {tick}(约{in_ticks}ticks后)"
        return f"无尽，已出现{spawned}只"
    total = wave_progress.get("total", 0)
    spawned = wave_progress.get("spawned", 0)
    if not isinstance(total, int) or total <= 0:
        return "无"
    if wave_progress.get("completed"):
        return f"{spawned}/{total}，已结束；新增僵尸来自模仿者或特殊事件"
    next_wave = wave_progress.get("next")
    if isinstance(next_wave, dict):
        lane = next_wave.get("lane")
        tick = next_wave.get("tick")
        in_ticks = next_wave.get("in_ticks")
        zombie_type = next_wave.get("zombie_type")
        zombie_name = ZOMBIE_NAMES.get(str(zombie_type), str(zombie_type))
        if isinstance(lane, int) and isinstance(tick, int) and isinstance(in_ticks, int):
            return f"{spawned}/{total}，下一只 tick {tick}(约{in_ticks}ticks后): {lane}路{zombie_name}"
    return f"{spawned}/{total}"


def _airdrop_progress_line(state: GameState, config: GameConfig) -> str:
    if state.airdrops:
        items = [
            f"{airdrop.lane}-{airdrop.col}(约{max(0, airdrop.expires_tick - state.tick)}ticks后飞走)"
            for airdrop in sorted(state.airdrops.values(), key=lambda item: (item.lane, item.col, item.entity_id))
        ]
        return "场上 " + "，".join(items)
    next_tick = int(state.wave_state.get("next_airdrop_tick", config.airdrop_start_tick) or config.airdrop_start_tick)
    return f"预告 tick {next_tick}(约{max(0, next_tick - state.tick)}ticks后可能掉落)"


def _lane_cells(
    state: GameState,
    config: GameConfig,
    plant_defs: dict[str, PlantDef],
    zombie_defs: dict[str, ZombieDef],
    lane: int,
) -> list[str]:
    fog_revealed = _fog_revealed_cells(state, config, plant_defs)
    zombies_by_col: dict[int, list[ZombieInstance]] = defaultdict(list)
    for zombie in state.zombies.values():
        if zombie.lane != lane:
            continue
        zombies_by_col[_zombie_col(zombie, config)].append(zombie)

    cells: list[str] = []
    for col in config.cols_range():
        entity_id = state.grid.get((lane, col))
        plant_symbol: str | None = None
        if entity_id in state.pending_imitators:
            imitator = state.pending_imitators[entity_id]
            plant_symbol = _with_roof_pot_symbol(PENDING_IMITATOR_SYMBOL, imitator.status)
        elif entity_id in state.plants:
            plant = state.plants[entity_id]
            plant_symbol = _plant_symbol(plant, plant_defs, current_tick=state.tick, is_day=config.is_day)
        elif entity_id in state.airdrops:
            plant_symbol = "箱"

        cell_zombies = zombies_by_col.get(col, [])
        fogged = _is_fogged_cell(config, lane, col, fog_revealed)
        zombie_symbol = "雾" if fogged and cell_zombies else _zombie_stack_symbol(cell_zombies, zombie_defs)
        if fogged and not plant_symbol and not cell_zombies:
            cells.append("雾")
            continue
        if plant_symbol and zombie_symbol:
            suffix = "咬" if any(zombie.target_entity_id == entity_id for zombie in cell_zombies) else ""
            cells.append(f"{plant_symbol}+{zombie_symbol}{suffix}")
        elif plant_symbol:
            cells.append(plant_symbol)
        elif zombie_symbol:
            cells.append(zombie_symbol)
        else:
            cells.append("空")
    return cells


def _fog_revealed_cells(
    state: GameState,
    config: GameConfig,
    plant_defs: dict[str, PlantDef],
) -> set[tuple[int, int]]:
    if config.fog_start_col is None:
        return set()
    revealed: set[tuple[int, int]] = set()
    radius = max(0, config.fog_reveal_radius)
    for plant in state.plants.values():
        plant_def = plant_defs.get(plant.plant_id)
        if plant_def is None or not plant_behaviors.has_special(plant_def, "fog_reveal"):
            continue
        for lane in range(max(1, plant.lane - radius), min(config.lanes, plant.lane + radius) + 1):
            for col in range(max(1, plant.col - radius), min(config.cols, plant.col + radius) + 1):
                revealed.add((lane, col))
    return revealed


def _is_fogged_cell(
    config: GameConfig,
    lane: int,
    col: int,
    revealed: set[tuple[int, int]],
) -> bool:
    return config.is_fog_col(col) and (lane, col) not in revealed


def _zombie_col(zombie: ZombieInstance, config: GameConfig) -> int:
    return min(config.cols, max(1, math.floor(zombie.x + 0.5)))


def _plant_symbol(
    plant: PlantInstance,
    plant_defs: dict[str, PlantDef],
    *,
    current_tick: int,
    is_day: bool,
) -> str:
    symbol = PLANT_SYMBOLS.get(plant.plant_id, plant.plant_id[:1])
    plant_def = plant_defs.get(plant.plant_id)
    if plant.plant_id == "potato_mine" and plant_def is not None:
        if not plant_behaviors.is_potato_mine_armed(
            plant_def,
            planted_tick=plant.planted_tick,
            current_tick=current_tick,
        ):
            return _with_roof_pot_symbol("土待", plant.status)
    if plant_def is not None and plant_behaviors.is_plant_sleeping(plant_def, is_day=is_day, plant=plant):
        return _with_roof_pot_symbol(f"{symbol}睡", plant.status)
    return _with_roof_pot_symbol(symbol, plant.status)


def _with_roof_pot_symbol(symbol: str, status: str) -> str:
    if _has_status_tag(status, ROOF_POT_STATUS):
        return f"盆{symbol}"
    return symbol


def _has_status_tag(status: str, tag: str) -> bool:
    return tag in {item for item in status.split(",") if item}


def _zombie_stack_symbol(zombies: list[ZombieInstance], zombie_defs: dict[str, ZombieDef]) -> str | None:
    if not zombies:
        return None
    symbols = [_zombie_symbol(zombie, zombie_defs) for zombie in sorted(zombies, key=lambda item: (item.x, item.entity_id))]
    counts = Counter(symbols)
    if len(counts) == 1:
        symbol, count = next(iter(counts.items()))
        return _stack_count_symbol(symbol, count)
    return "+".join(_stack_count_symbol(symbol, count) for symbol, count in counts.items())


def _stack_count_symbol(symbol: str, count: int) -> str:
    return symbol if count == 1 else f"{symbol}x{count}"


def _zombie_symbol(zombie: ZombieInstance, zombie_defs: dict[str, ZombieDef]) -> str:
    symbol = ZOMBIE_SYMBOLS.get(zombie.zombie_id, zombie.zombie_id[:1])
    zombie_def = zombie_defs.get(zombie.zombie_id)
    if zombie_def is not None and zombie_behaviors.is_balloon_airborne(zombie_def, zombie):
        return symbol
    return symbol


PLAYER_ACTION_EVENT_TYPES = {
    "action_failed",
    "game_ended_by_player",
    "imitator_planted",
    "imitator_shoveled",
    "plant_card_planted",
    "plant_card_played",
    "plant_shoveled",
    "airdrop_opened",
}


def _event_lines(events: list[dict[str, Any]], *, limit: int = 8) -> list[str]:
    entries: list[tuple[int, str, str | None]] = []
    for index, event in enumerate(events):
        line = _event_line(event)
        if line:
            event_type = event.get("type")
            entries.append((index, line, str(event_type) if event_type is not None else None))
    if len(entries) <= limit:
        return [line for _, line, _ in entries]

    selected_indexes = {
        index
        for index, _, event_type in entries
        if event_type in PLAYER_ACTION_EVENT_TYPES
    }
    remaining_slots = max(0, limit - len(selected_indexes))
    if remaining_slots:
        for index, _, _ in entries[-remaining_slots:]:
            selected_indexes.add(index)
    if len(selected_indexes) > limit:
        selected_indexes = set(sorted(selected_indexes)[-limit:])
    return [line for index, line, _ in entries if index in selected_indexes]


def _event_line(event: dict[str, Any]) -> str | None:
    event_type = event.get("type")
    lane = event.get("lane")
    col = event.get("col")
    if event_type == "imitator_planted":
        return f"{lane}路{col}列种下模仿者{_roof_pot_buffer_suffix(event)}"
    if event_type == "imitator_revealed":
        kind = event.get("kind")
        if kind == "plant":
            return f"{lane}路{col}列模仿者开奖成植物"
        if kind == "spawn_zombie":
            return f"{lane}路{col}列模仿者开奖成僵尸"
        if kind == "boss_event":
            return f"{lane}路{col}列模仿者开奖成首领事件"
        if kind == "blank":
            return f"{lane}路{col}列模仿者开奖为空"
        return f"{lane}路{col}列模仿者开奖"
    if event_type == "reveal_spawned_plant":
        return f"{lane}路{col}列变成{PLANT_NAMES.get(str(event.get('plant_id')), event.get('plant_id'))}{_roof_pot_buffer_suffix(event)}"
    if event_type == "plant_card_planted":
        return f"{lane}路{col}列种下{PLANT_NAMES.get(str(event.get('plant_id')), event.get('plant_id'))}{_roof_pot_buffer_suffix(event)}"
    if event_type == "plant_card_played":
        suffix = "（消耗花盆）" if event.get("roof_pot") else ""
        return f"{lane}路{col}列使用{PLANT_NAMES.get(str(event.get('card_id')), event.get('card_id'))}{suffix}"
    if event_type == "airdrop_dropped":
        return f"{lane}路{col}列落下空投箱"
    if event_type == "airdrop_opened":
        if event.get("flavor_text"):
            return str(event["flavor_text"])
        return f"{lane}路{col}列空投打开"
    if event_type == "airdrop_cleared":
        return f"{lane}路{col}列空投被炸弹清除"
    if event_type == "airdrop_expired":
        if event.get("flavor_text"):
            return str(event["flavor_text"])
        if lane is None or col is None:
            return "空投飞走了"
        return f"{lane}路{col}列空投飞走"
    if event_type == "plant_triggered":
        display_lane = event.get("lane", event.get("plant_lane"))
        display_col = event.get("col", event.get("plant_col"))
        plant_ref = event.get("plant_type") or event.get("plant_id")
        plant_name = PLANT_NAMES.get(str(plant_ref), str(plant_ref))
        counts: list[str] = []
        killed = event.get("killed_zombies")
        damaged = event.get("damaged_zombies")
        frozen = event.get("frozen_zombies")
        if isinstance(killed, list) and killed:
            counts.append(f"消灭{len(killed)}只")
        if isinstance(damaged, list) and damaged:
            counts.append(f"影响{len(damaged)}只")
        if isinstance(frozen, list) and frozen:
            counts.append(f"冻结{len(frozen)}只")
        suffix = f"（{'，'.join(counts)}）" if counts else ""
        position = f"{display_lane}路{display_col}列" if display_lane is not None and display_col is not None else ""
        return f"{position}{plant_name}触发{suffix}"
    if event_type == "reveal_spawned_zombie":
        if event.get("flavor_text"):
            return f"{lane}路{_x_to_text(event.get('x'))}开奖: {event['flavor_text']}"
        return f"{lane}路{_x_to_text(event.get('x'))}出现{ZOMBIE_NAMES.get(str(event.get('zombie_type')), event.get('zombie_type'))}"
    if event_type == "zombie_spawned":
        return f"{lane}路右侧出现{ZOMBIE_NAMES.get(str(event.get('zombie_type')), event.get('zombie_type'))}"
    if event_type == "zombie_spawned_by_special":
        return f"{lane}路出现{ZOMBIE_NAMES.get(str(event.get('zombie_type')), event.get('zombie_type'))}"
    if event_type == "plant_shoveled":
        return f"{lane}路{col}列铲掉{PLANT_NAMES.get(str(event.get('plant_type')), event.get('plant_type'))}"
    if event_type == "imitator_shoveled":
        return f"{lane}路{col}列铲掉未开奖模仿者"
    if event_type == "imitator_destroyed_before_reveal":
        return f"{lane}路{col}列未开奖模仿者被吃掉"
    if event_type == "plant_eaten":
        return f"{lane}路{col}列植物被吃掉"
    if event_type == "roof_pot_absorbed_hit":
        return f"{lane}路{col}列花盆缓冲挡下{_roof_pot_reason_text(str(event.get('reason')))}"
    if event_type == "roof_tile_slipped":
        return _roof_tile_line(event)
    if event_type == "zombie_died":
        zombie_type = event.get("zombie_type")
        prefix = ""
        if isinstance(lane, int):
            prefix = f"{lane}路"
            if event.get("x") is not None:
                prefix += f"{_x_to_text(event.get('x'))}"
        if prefix:
            prefix += " "
        if isinstance(zombie_type, str):
            return f"{prefix}{ZOMBIE_NAMES.get(zombie_type, zombie_type)}被消灭"
        return f"{prefix}僵尸被消灭"
    if event_type == "lawnmower_triggered":
        return f"{lane}路推车触发"
    if event_type == "jack_in_the_box_exploded":
        destroyed_plants = len(event.get("destroyed_plants") or [])
        destroyed_imitators = len(event.get("destroyed_imitators") or [])
        destroyed_parts: list[str] = []
        if destroyed_plants:
            destroyed_parts.append(f"{destroyed_plants}个植物")
        if destroyed_imitators:
            destroyed_parts.append(f"{destroyed_imitators}个未开奖模仿者")
        suffix = f"，摧毁{'和'.join(destroyed_parts)}" if destroyed_parts else ""
        return f"{lane}路小丑盒爆炸{suffix}"
    if event_type == "game_lost":
        return f"{lane}路僵尸进屋，本局失败"
    if event_type == "game_won":
        return "本局通关"
    if event_type == "game_ended_by_player":
        return "玩家主动结束本局，下局从 lv1 开始"
    if event_type == "reveal_spawned_boss_event":
        if event.get("flavor_text"):
            return f"开奖: {event['flavor_text']}"
        return f"{event.get('boss_id')} 事件开始"
    if event_type == "boss_event_action":
        return f"{event.get('boss_id', 'boss')} 执行动作: {event.get('action')}"
    if event_type == "boss_event_ended":
        return f"{event.get('boss_id', 'boss')} 事件结束"
    if event_type == "action_failed":
        return f"动作失败(后续未执行): {_failure_reason_text(str(event.get('reason')), event)}"
    if event.get("flavor_text"):
        return str(event["flavor_text"])
    return None


def _roof_pot_buffer_suffix(event: dict[str, Any]) -> str:
    return "（花盆缓冲）" if event.get("roof_pot") else ""


def _roof_pot_reason_text(reason: str) -> str:
    texts = {
        "zombie_bite": "一次啃咬",
        "bungee": "蹦极偷取",
        "catapult": "投石车攻击",
        "roof_tile": "瓦片滑落",
    }
    return texts.get(reason, reason)


def _roof_tile_line(event: dict[str, Any]) -> str:
    lane = event.get("lane")
    col = event.get("col")
    target_kind = event.get("target_kind")
    if target_kind == "empty":
        return f"屋顶瓦片滑落: {lane}路{col}列砸空"
    if event.get("absorbed_by_roof_pot"):
        return f"屋顶瓦片滑落: {lane}路{col}列花盆缓冲挡下"
    target_name = _event_target_display_name(event)
    suffix = ""
    if event.get("destroyed"):
        suffix = "，目标被摧毁"
        if target_kind == "zombie":
            suffix = "，目标被消灭"
        elif target_kind == "pending_imitator":
            suffix = "，开奖取消"
    return f"屋顶瓦片滑落: {lane}路{col}列砸中{target_name}{suffix}"


def _event_target_display_name(event: dict[str, Any]) -> str:
    target_kind = event.get("target_kind")
    target_type = event.get("target_type")
    if target_kind == "zombie":
        return str(ZOMBIE_NAMES.get(str(target_type), target_type))
    if target_kind == "plant":
        return str(PLANT_NAMES.get(str(target_type), target_type))
    if target_kind == "pending_imitator":
        return "未开奖模仿者"
    return "目标"


def _x_to_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1f}列"
    return "未知位置"


def _boss_lines(state: GameState) -> list[str]:
    lines: list[str] = []
    for boss in sorted(state.boss_events.values(), key=lambda item: item.entity_id):
        remaining = max(0, boss.end_tick - state.tick)
        next_action = max(0, boss.next_action_tick - state.tick)
        name = "僵王博士" if boss.boss_id == "zomboss" else boss.boss_id
        lines.append(f"{name} 剩余{remaining}ticks，下次动作约{next_action}ticks后，已动作{boss.actions_taken}次")
    return lines


def _failure_reason_text(reason: str, event: dict[str, Any] | None = None) -> str:
    if reason == "target_cell_no_longer_empty":
        occupied_text = _occupied_cell_failure_text(event or {})
        if occupied_text:
            return occupied_text
    texts = {
        "target_cell_empty": "该格没有可铲植物或未开奖模仿者",
        "target_not_shovelable": "该格目标不能被铲子移除",
        "target_airdrop_missing": "该格没有空投箱",
        "target_cell_no_longer_empty": "目标格已经被占用",
        "no_card_slot_ready": "没有可用卡槽",
        "cooldown_not_ready": "卡槽冷却未好",
        "not_enough_sun": "阳光不足",
        "water_lane_requires_imitator_or_water_plant": "水路只能直种模仿者或水路植物",
        "requires_water_lane": "该植物只能直种在水路",
        "action_not_legal": "动作格式不合法",
        "observation_id_mismatch": "该观察已经过期",
        "game_already_over": "本局已经结束",
    }
    return texts.get(reason, reason)


def _occupied_cell_failure_text(event: dict[str, Any]) -> str | None:
    lane = event.get("lane")
    col = event.get("col")
    occupants = event.get("occupants")
    if not isinstance(lane, int) or not isinstance(col, int):
        return None
    if not isinstance(occupants, list):
        return f"{lane}路{col}列已经被占用"
    occupant_names = [_occupant_name(item) for item in occupants if isinstance(item, dict)]
    occupant_names = [name for name in occupant_names if name]
    if occupant_names:
        return f"{lane}路{col}列已有{'、'.join(occupant_names)}"
    return f"{lane}路{col}列已经被占用"


def _occupant_name(occupant: dict[str, Any]) -> str | None:
    kind = occupant.get("kind")
    if kind == "pending_imitator":
        return "模仿者"
    if kind == "plant":
        plant_id = occupant.get("plant_id")
        if isinstance(plant_id, str):
            return PLANT_NAMES.get(plant_id, plant_id)
        return "植物"
    if kind == "airdrop":
        return "空投箱"
    if kind == "unknown":
        return "已有单位"
    return None


def _alert_lines_from_observation_events(events: list[dict[str, Any]]) -> list[str]:
    # Reserved for event-level warnings. Lane alerts already stay in raw observation.
    return []


def _ready_cards_line(
    card_slots: list[dict[str, Any]],
    card_costs: dict[str, int],
    *,
    current_sun: int,
) -> str:
    parts: list[str] = []
    ready_counts = Counter(slot.get("card_id") for slot in card_slots if slot.get("ready"))
    if ready_counts.get("imitator", 0):
        parts.append(_card_count_with_cost("模仿者", ready_counts.get("imitator", 0), card_costs.get("imitator"), current_sun=current_sun))
    for card_id, count in sorted(ready_counts.items()):
        if card_id in {None, "imitator"}:
            continue
        parts.append(_card_count_with_cost(_card_name(str(card_id)), count, card_costs.get(str(card_id)), current_sun=current_sun))
    return ", ".join(parts) if parts else "无"


def _actions_line(valid_actions: list[str]) -> str:
    parts: list[str] = []
    if "plant_imitator" in valid_actions or "plant_card" in valid_actions:
        parts.append("种植")
    if "shovel_plant" in valid_actions:
        parts.append("铲子")
    if "open_airdrop" in valid_actions:
        parts.append("开空投")
    if "wait" in valid_actions:
        parts.append("等待")
    if "end_game" in valid_actions:
        parts.append("结束本局")
    return ", ".join(parts) if parts else "无"


def _card_count_with_cost(name: str, count: int, cost: int | None, *, current_sun: int) -> str:
    if cost is None:
        return f"{name}x{count}"
    suffix = "/阳光不足" if cost > current_sun else ""
    return f"{name}x{count}({cost}{suffix})"


def _card_name(card_id: str) -> str:
    return PLANT_NAMES.get(card_id, card_id)
