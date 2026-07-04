from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

from .game.cards import ALL_IMITATOR_CARD_LOADOUT, FOG_CARD_LOADOUT, RECOMMENDED_CARD_LOADOUT, ROOF_CARD_LOADOUT
from .game.config import GameConfig
from .game.contracts import ContractError
from .game.engine import GameEngine
from .game.events import Event
from .game.models import (
    AirdropInstance,
    BossEventInstance,
    GameState,
    PendingImitator,
    PlantInstance,
    ZombieInstance,
    to_jsonable,
)
from .game.player_view import CARD_COMMANDS, PLANT_NAMES, build_card_selection_view, parse_player_text_action_plan
from .game.presets import ALL_IMITATOR_LEVEL, FOG_LEVEL, ROOF_LEVEL, build_wave_schedule, config_for_level, is_all_imitator_level
from .game.randomizer import ReplayRng


SAVE_VERSION = 1
DEFAULT_SAVE_PATH = Path(os.environ.get("RANDOM_IMITATOR_TD_SAVE", Path.cwd() / "random_imitator_td_save.json"))
DEFAULT_RECORDS_PATH = Path(os.environ.get("RANDOM_IMITATOR_TD_RECORDS", Path.cwd() / "random_imitator_td_records.json"))
DEFAULT_SEED = "RITD-001"
DEFAULT_CARD_LOADOUT: tuple[str, ...] = RECOMMENDED_CARD_LOADOUT
SPECIAL_LEVEL_ALIASES = {"special", "all_imitator", "imitator_only", "特殊", "特殊关", "特殊关卡", "全模仿者"}
ENDLESS_RECORD_ID = "all_imitator_endless"
ANTI_ADDICTION_PAUSE_EVERY_TURNS = 5
ANTI_ADDICTION_PAUSE_PREFIX = "防沉迷暂停"
ANTI_ADDICTION_PENDING_KEY = "anti_addiction_pause_pending_turn"
ALIASES = {
    "new": "new_game",
    "restart": "new_game",
    "reset": "new_game",
    "重开": "new_game",
    "新游戏": "new_game",
    "状态": "status",
    "帮助": "help",
    "卡槽": "cards",
    "选卡": "cards",
    "选": "cards",
    "选择": "cards",
    "观察": "look",
    "棋盘": "look",
    "看": "look",
    "打开": "look",
    "继续": "look",
    "open": "look",
    "resume": "look",
    "复盘": "note",
    "笔记": "note",
}


def cmd(text: str) -> str:
    session = _load_or_create_session()
    records = _load_records()
    raw_text = text.strip()
    parts = [raw_text] if _looks_like_gameplay_command(raw_text) else [part.strip() for part in raw_text.replace("\n", ";").split(";") if part.strip()]
    if not parts:
        output = _current_view(session, records)
        _save_records(records)
        return output

    outputs: list[str] = []
    for part in parts[:12]:
        output = _route_command(session, part, records)
        outputs.append(output)
        if output.startswith(ANTI_ADDICTION_PAUSE_PREFIX):
            break

    _save_session(session)
    _save_records(records)
    return "\n\n".join(output for output in outputs if output).strip()


def _route_command(session: dict[str, Any], part: str, records: dict[str, Any]) -> str:
    words = shlex.split(part)
    if not words:
        return _current_view(session, records)
    command = ALIASES.get(words[0].lower(), words[0].lower())
    args = words[1:]

    if command in {"help", "h"}:
        return _help_text()
    if command in {"status", "s"}:
        return _status_text(session)
    if command in {"look", "l"}:
        return _current_view(session, records)
    if command in {"new_game", "newgame"}:
        return _new_game(session, args, records)
    if command in {"cards", "loadout"}:
        if _session_game_over(session):
            _reset_finished_session(session, records)
        return _set_cards(session, args, records)
    if command in {"note", "notes"}:
        return _set_note(session, args)
    if command in {"recap"}:
        return _recap(session, records)

    if _session_game_over(session):
        return _reset_finished_session(session, records)
    engine = _engine_from_session(session)
    if engine is None:
        return _setup_text(session, records=records)
    pause_text = _consume_anti_addiction_pause(session, engine)
    if pause_text:
        return pause_text
    observation = _action_observation(engine)
    try:
        plan = parse_player_text_action_plan(
            part,
            observation=observation,
            action_plan_id=f"cmd_{session.get('turn', 0) + 1}",
        )
        result = engine.apply_action_plan(plan, observation_id=observation["observation_id"])
    except (ContractError, ValueError) as exc:
        return f"动作未执行: {exc}\n\n{observation['player_view']['text']}\n{_state_json(engine)}"
    session["turn"] = int(session.get("turn", 0)) + 1
    record_updated = _maybe_update_endless_record(records, engine)
    _store_engine(session, engine)
    output = _board_output(records, engine, result["observation"], record_updated=record_updated)
    _mark_anti_addiction_pause_if_due(session, int(session.get("turn", 0)), engine)
    return output


def _action_observation(engine: GameEngine) -> dict[str, Any]:
    return engine.build_observation(
        reason=["before_player_action"],
        events=[],
        advance_summary={
            "from_tick": engine.state.tick,
            "to_tick": engine.state.tick,
            "advanced_ticks": 0,
            "stop_reason": "before_player_action",
        },
    )


def _looks_like_gameplay_command(text: str) -> bool:
    if not text.strip():
        return False
    try:
        words = shlex.split(text.strip().replace("\n", " ", 1))
    except ValueError:
        return False
    if not words:
        return False
    command = ALIASES.get(words[0].lower(), words[0].lower())
    return command not in {
        "help",
        "h",
        "status",
        "s",
        "look",
        "l",
        "new_game",
        "newgame",
        "cards",
        "loadout",
        "note",
        "notes",
        "recap",
    }


def _new_game(session: dict[str, Any], args: list[str], records: dict[str, Any]) -> str:
    options = _parse_options(args)
    level = _level_option(options, default=int(session.get("level", 1)))
    seed = str(options.get("seed") or session.get("seed") or DEFAULT_SEED)
    enable_airdrops = is_all_imitator_level(level) and _airdrop_option(options)
    player_notes = _player_notes_from_session(session)
    session.clear()
    session.update(
        {
            "version": SAVE_VERSION,
            "turn": 0,
            "level": level,
            "seed": seed,
            "card_loadout": [],
            "chaos_airdrop": enable_airdrops,
        }
    )
    loadout = _default_loadout_for_level(level) if is_all_imitator_level(level) else _loadout_from_options(options, level=level)
    if loadout is None:
        if player_notes:
            session["player_notes"] = player_notes
        return _setup_text(session, prefix=f"新游戏: lv{level} seed={seed}\n请先编辑卡槽。", records=records)
    engine = _new_engine(level=level, seed=seed, card_loadout=loadout, enable_airdrops=enable_airdrops)
    if player_notes:
        engine.set_player_notes(player_notes)
    session["card_loadout"] = list(loadout)
    _store_engine(session, engine)
    observation = engine.run_until_decision()
    start_line = f"新游戏: lv{level} seed={seed} 卡槽={_loadout_text(loadout)}"
    header_lines = [start_line]
    if is_all_imitator_level(level):
        header_lines[0] += f" 混沌={_chaos_option_text(enable_airdrops)}"
        header_lines.append(_chaos_mode_description(enable_airdrops))
    header_text = "\n".join(header_lines)
    return f"{header_text}\n\n{_board_output(records, engine, observation)}"


def _set_cards(session: dict[str, Any], args: list[str], records: dict[str, Any]) -> str:
    level = int(session.get("level", 1))
    if not args:
        return _card_selection_text(level)
    if len(args) == 1 and args[0].strip().lower() in {"默认", "default", "recommended"}:
        loadout = _default_loadout_for_level(level)
        invalid: list[str] = []
    else:
        loadout = _default_loadout_for_level(level) if is_all_imitator_level(level) else tuple(_card_id(arg) for arg in args)
        invalid = [arg for arg, card_id in zip(args, loadout) if card_id is None]
    if invalid:
        return f"未知卡牌: {', '.join(invalid)}\n\n{_card_selection_text(level)}"
    clean_loadout = tuple(card_id for card_id in loadout if card_id is not None)
    seed = str(session.get("seed") or DEFAULT_SEED)
    enable_airdrops = bool(session.get("chaos_airdrop")) and is_all_imitator_level(level)
    player_notes = _player_notes_from_session(session)
    engine = _new_engine(level=level, seed=seed, card_loadout=clean_loadout, enable_airdrops=enable_airdrops)
    if player_notes:
        engine.set_player_notes(player_notes)
    session["turn"] = 0
    session.pop(ANTI_ADDICTION_PENDING_KEY, None)
    session["card_loadout"] = list(clean_loadout)
    _store_engine(session, engine)
    observation = engine.run_until_decision()
    return f"卡槽已设置: {_loadout_text(clean_loadout)}\n\n{_board_output(records, engine, observation)}"


def _set_note(session: dict[str, Any], args: list[str]) -> str:
    note = " ".join(args).strip()
    engine = _engine_from_session(session)
    if note:
        existing_notes = _player_notes_from_session(session)
        if engine is None:
            engine = _new_engine(level=int(session.get("level", 1)), seed=str(session.get("seed") or DEFAULT_SEED), card_loadout=tuple(session.get("card_loadout") or ()))
            if existing_notes:
                engine.set_player_notes(existing_notes)
        notes = [{"memory_id": "player_note_1", "note": note, "source_round_id": "manual", "updated_tick": engine.state.tick}]
        engine.set_player_notes(notes)
        _store_engine(session, engine)
        return f"复盘已记录: {note}\n{_state_json(engine)}"
    notes = _player_notes_from_session(session)
    if not notes:
        if engine is None:
            return "暂无复盘记录。"
        return f"暂无复盘记录。\n{_state_json(engine)}"
    return "\n".join(f"- {item.get('note', '')}" for item in notes)


def _recap(session: dict[str, Any], records: dict[str, Any]) -> str:
    engine = _engine_from_session(session)
    recap = engine.build_run_recap()
    lines = [
        "本局统计:",
        f"- 结果: {recap.get('result')}",
        f"- tick: {recap.get('final_tick')}",
        f"- 系统波次: {recap.get('system_waves_spawned', 0)}",
        f"- 空投: 掉落{recap.get('airdrops_spawned', 0)} / 开启{recap.get('airdrops_opened', 0)} / 清除{recap.get('airdrops_cleared', 0)}",
        f"- 回合: {len(engine.player_round_history)}",
    ]
    record_text = _endless_record_text(records, engine)
    if record_text:
        lines.append(record_text)
    if "reveal_category_counts" in recap:
        lines.append(f"- 开奖: {recap['reveal_category_counts']}")
    return "\n".join(lines) + "\n" + _state_json(engine)


def _current_view(session: dict[str, Any], records: dict[str, Any]) -> str:
    if _session_game_over(session):
        return _reset_finished_session(session, records)
    engine = _engine_from_session(session)
    if engine is None:
        return _setup_text(session, records=records)
    observation = engine.run_until_decision()
    record_updated = _maybe_update_endless_record(records, engine)
    _store_engine(session, engine)
    _save_session(session)
    return _board_output(records, engine, observation, record_updated=record_updated)


def _status_text(session: dict[str, Any]) -> str:
    engine = _engine_from_session(session)
    if engine is None:
        return _setup_text(session)
    return _state_json(engine)


def _help_text() -> str:
    return "\n".join(
        [
            "随机模仿者文字塔防",
            "",
            "命令:",
            "  new_game level=1 seed=demo",
            "  new_game level=特殊",
            "  new_game mode=特殊 chaos=off",
            "  new_game mode=特殊 chaos=airdrop",
            "  cards 默认",
            "  cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜",
            "  种 模仿者 3-4; 种 向日葵 2-3",
            "  开空投 3-5",
            "  等待 200",
            "  铲 3-4",
            "  等待",
            "  结束本局",
            "  note 第一局自己的复盘",
            "  recap / look / 打开 / 继续 / status / help",
        ]
    )


def _anti_addiction_pause_text(turn: int, engine: GameEngine) -> str:
    if turn <= 0 or turn % ANTI_ADDICTION_PAUSE_EVERY_TURNS != 0:
        return ""
    if engine.state.game_over:
        return ""
    return f"{ANTI_ADDICTION_PAUSE_PREFIX}: 由于防沉迷机制，已完成第{turn}回合后暂时中止游戏回合；状态已保存，下次用同一存档继续。"


def _mark_anti_addiction_pause_if_due(session: dict[str, Any], turn: int, engine: GameEngine) -> None:
    if _anti_addiction_pause_text(turn, engine):
        session[ANTI_ADDICTION_PENDING_KEY] = turn


def _consume_anti_addiction_pause(session: dict[str, Any], engine: GameEngine) -> str:
    raw_turn = session.get(ANTI_ADDICTION_PENDING_KEY)
    try:
        turn = int(raw_turn)
    except Exception:
        session.pop(ANTI_ADDICTION_PENDING_KEY, None)
        return ""
    pause_text = _anti_addiction_pause_text(turn, engine)
    session.pop(ANTI_ADDICTION_PENDING_KEY, None)
    return pause_text


def _load_or_create_session() -> dict[str, Any]:
    if DEFAULT_SAVE_PATH.exists():
        with DEFAULT_SAVE_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    session = _fresh_session()
    _save_session(session)
    return session


def _fresh_session() -> dict[str, Any]:
    return {"version": SAVE_VERSION, "turn": 0, "level": 1, "seed": DEFAULT_SEED, "card_loadout": list(DEFAULT_CARD_LOADOUT)}


def _player_notes_from_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    notes = session.get("player_notes")
    session_notes = list(notes) if isinstance(notes, list) else []
    engine = _engine_from_session(session)
    if engine is not None and engine.player_notes:
        return list(engine.player_notes)
    return session_notes


def _session_game_over(session: dict[str, Any]) -> bool:
    engine = _engine_from_session(session)
    return bool(engine and engine.state.game_over)


def _reset_finished_session(session: dict[str, Any], records: dict[str, Any]) -> str:
    engine = _engine_from_session(session)
    player_notes = _player_notes_from_session(session)
    if engine is not None:
        _maybe_update_endless_record(records, engine)
    next_level = 1
    seed = DEFAULT_SEED
    prefix = "上一局已结束，已准备新局。\n请先编辑卡槽。"
    if engine is not None and engine.state.result == "won" and not engine.config.is_endless:
        next_level = engine.state.level + 1
        seed = engine.rng.seed
        prefix = f"上一关已通关，已准备 lv{next_level}。\n请先编辑卡槽。"
    session.clear()
    session.update(_fresh_session())
    session["level"] = next_level
    session["seed"] = seed
    if player_notes:
        session["player_notes"] = player_notes
    return _setup_text(session, prefix=prefix, records=records)


def _save_session(session: dict[str, Any]) -> None:
    DEFAULT_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_SAVE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(session, handle, ensure_ascii=False, indent=2)


def _load_records() -> dict[str, Any]:
    if not DEFAULT_RECORDS_PATH.exists():
        return {"version": 1}
    try:
        with DEFAULT_RECORDS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"version": 1}
    return payload if isinstance(payload, dict) else {"version": 1}


def _save_records(records: dict[str, Any]) -> None:
    DEFAULT_RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(records)
    payload.setdefault("version", 1)
    with DEFAULT_RECORDS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _board_output(
    records: dict[str, Any],
    engine: GameEngine,
    observation: dict[str, Any],
    *,
    record_updated: bool = False,
) -> str:
    lines = [observation["player_view"]["text"]]
    record_text = _endless_record_text(records, engine, record_updated=record_updated)
    if record_text:
        lines.append(record_text)
    lines.append(_state_json(engine))
    return "\n".join(lines)


def _maybe_update_endless_record(records: dict[str, Any], engine: GameEngine) -> bool:
    if not engine.config.is_endless or not engine.state.game_over:
        return False
    candidate = _endless_score(engine)
    record_id = _endless_record_id(engine)
    current = records.get(record_id)
    if isinstance(current, dict) and not _is_better_endless_score(candidate, current):
        return False
    records[record_id] = candidate
    records["version"] = 1
    return True


def _endless_score(engine: GameEngine) -> dict[str, Any]:
    return {
        "waves": int(engine.state.wave_state.get("spawned_count", 0) or 0),
        "tick": engine.state.tick,
        "turns": len(engine.player_round_history),
        "seed": engine.rng.seed,
        "variant": _endless_variant(engine),
        "result": engine.state.result or ("game_over" if engine.state.game_over else "running"),
    }


def _is_better_endless_score(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        int(candidate.get("waves", 0) or 0),
        int(candidate.get("tick", 0) or 0),
        int(candidate.get("turns", 0) or 0),
    ) > (
        int(current.get("waves", 0) or 0),
        int(current.get("tick", 0) or 0),
        int(current.get("turns", 0) or 0),
    )


def _endless_record_text(
    records: dict[str, Any],
    engine: GameEngine | None = None,
    *,
    record_updated: bool = False,
) -> str:
    lines: list[str] = []
    record_id = _endless_record_id(engine) if engine is not None else ENDLESS_RECORD_ID
    variant_label = f"({_endless_variant_label(engine)})" if engine is not None and engine.config.is_endless else ""
    if engine is not None and engine.config.is_endless:
        current = _endless_score(engine)
        lines.append(
            f"无尽本局{variant_label}: 系统波次{current['waves']} | tick {current['tick']} | 回合{current['turns']}"
        )
    record = records.get(record_id)
    if isinstance(record, dict):
        label = "新纪录" if record_updated else "最佳"
        lines.append(
            f"无尽纪录{variant_label}: {label} 系统波次{int(record.get('waves', 0) or 0)} | "
            f"tick {int(record.get('tick', 0) or 0)} | 回合{int(record.get('turns', 0) or 0)} | "
            f"seed={record.get('seed', DEFAULT_SEED)}"
        )
    elif engine is not None and engine.config.is_endless:
        lines.append("无尽纪录: 暂无")
    return "\n".join(lines)


def _endless_variant(engine: GameEngine) -> str:
    return "airdrop" if engine.config.enable_airdrops else "plain"


def _endless_variant_label(engine: GameEngine) -> str:
    return "空投" if engine.config.enable_airdrops else "普通"


def _endless_record_id(engine: GameEngine) -> str:
    variant = _endless_variant(engine)
    if variant == "plain":
        return ENDLESS_RECORD_ID
    return f"{ENDLESS_RECORD_ID}:{variant}"


def _new_engine(*, level: int, seed: str, card_loadout: tuple[str, ...], enable_airdrops: bool = False) -> GameEngine:
    if is_all_imitator_level(level):
        card_loadout = ALL_IMITATOR_CARD_LOADOUT
    config = config_for_level(
        level,
        GameConfig(
            card_loadout=card_loadout,
            card_slot_count=max(6, len(card_loadout)),
            enable_airdrops=enable_airdrops and is_all_imitator_level(level),
        ),
    )
    mode = "all_imitator_endless" if is_all_imitator_level(level) else "random_imitator"
    engine = GameEngine(config=config, seed=seed, wave_schedule=build_wave_schedule(level), run_id=f"cmd-lv{level}-{seed}", mode=mode)
    engine.state.level = level
    return engine


def _store_engine(session: dict[str, Any], engine: GameEngine) -> None:
    session["level"] = engine.state.level
    session["seed"] = engine.rng.seed
    session["engine"] = _engine_to_json(engine)


def _engine_from_session(session: dict[str, Any]) -> GameEngine | None:
    payload = session.get("engine")
    if isinstance(payload, dict):
        return _engine_from_json(payload)
    return None


def _setup_text(session: dict[str, Any], *, prefix: str | None = None, records: dict[str, Any] | None = None) -> str:
    level = int(session.get("level", 1))
    seed = str(session.get("seed") or "RITD-001")
    lines = []
    if prefix:
        lines.append(prefix)
    else:
        lines.append(f"新局准备中: lv{level} seed={seed}")
        lines.append("请先编辑卡槽。")
    lines.append("")
    lines.append("模式: 默认普通；特殊无尽用 new_game mode=特殊 chaos=off|airdrop（固定六个模仿者）。")
    if is_all_imitator_level(level):
        lines.append("特殊关卡: 固定六个模仿者，无尽模式；chaos=off 为普通无尽，chaos=airdrop 为空投混沌。")
        lines.append("混沌模式: 会新增空投箱；空投占格但不拦僵尸，可主动打开，僵尸经过也会打开，里面是强力植物或僵尸。")
        record_text = _endless_record_text(records or {})
        if record_text:
            lines.append(record_text)
        lines.append("格式: cards 默认")
    else:
        lines.append("格式: cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜")
        lines.append("提示: 模仿者越多，随机味越足。")
    lines.append("")
    lines.append(_card_selection_text(level))
    return "\n".join(lines)


def _engine_to_json(engine: GameEngine) -> dict[str, Any]:
    return {
        "config": to_jsonable(engine.config),
        "state": to_jsonable(engine.state),
        "rng": engine.rng.snapshot(),
        "wave_schedule": [list(item) for item in engine.wave_schedule],
        "event_log": [to_jsonable(event) for event in engine.event_log],
        "entity_counter": engine._entity_counter,
        "event_counter": engine._event_counter,
        "observation_counter": engine._observation_counter,
        "round_counter": engine._round_counter,
        "mode": engine.mode,
        "run_id": engine.run_id,
        "player_notes": to_jsonable(engine.player_notes),
        "player_round_history": to_jsonable(engine.player_round_history),
        "player_view_seen_unit_ids": sorted(engine._player_view_seen_unit_ids),
    }


def _engine_from_json(payload: dict[str, Any]) -> GameEngine:
    config = _config_from_json(payload["config"])
    engine = GameEngine(
        config=config,
        seed=payload.get("rng", {}).get("seed", "RITD-001"),
        wave_schedule=[tuple(item) for item in payload.get("wave_schedule", [])],
        player_notes=list(payload.get("player_notes", [])),
        player_round_history=list(payload.get("player_round_history", [])),
        mode=str(payload.get("mode", "random_imitator")),
        run_id=str(payload.get("run_id", "cmd-run")),
    )
    engine.state = _state_from_json(payload["state"])
    engine.rng = ReplayRng.from_snapshot(payload.get("rng", {}))
    engine.event_log = [_event_from_json(item) for item in payload.get("event_log", [])]
    engine._entity_counter = int(payload.get("entity_counter", 0))
    engine._event_counter = int(payload.get("event_counter", 0))
    engine._observation_counter = int(payload.get("observation_counter", 0))
    engine._round_counter = int(payload.get("round_counter", len(engine.player_round_history)))
    engine._player_view_seen_unit_ids = set(payload.get("player_view_seen_unit_ids", []))
    return engine


def _config_from_json(payload: dict[str, Any]) -> GameConfig:
    data = dict(payload)
    if "card_loadout" in data:
        data["card_loadout"] = tuple(data["card_loadout"])
    if "water_lanes" in data:
        data["water_lanes"] = tuple(data["water_lanes"])
    return GameConfig(**data)


def _state_from_json(payload: dict[str, Any]) -> GameState:
    return GameState(
        tick=int(payload["tick"]),
        sun=int(payload["sun"]),
        level=int(payload["level"]),
        grid={_cell_key(key): value for key, value in payload["grid"].items()},
        plants={key: PlantInstance(**value) for key, value in payload.get("plants", {}).items()},
        pending_imitators={key: PendingImitator(**value) for key, value in payload.get("pending_imitators", {}).items()},
        zombies={key: ZombieInstance(**value) for key, value in payload.get("zombies", {}).items()},
        boss_events={key: BossEventInstance(**value) for key, value in payload.get("boss_events", {}).items()},
        airdrops={key: AirdropInstance(**value) for key, value in payload.get("airdrops", {}).items()},
        cooldowns=dict(payload.get("cooldowns", {})),
        lawnmowers={int(key): bool(value) for key, value in payload.get("lawnmowers", {}).items()},
        wave_state=dict(payload.get("wave_state", {})),
        scheduled_events=list(payload.get("scheduled_events", [])),
        game_over=bool(payload.get("game_over", False)),
        result=payload.get("result"),
    )


def _event_from_json(payload: dict[str, Any]) -> Event:
    return Event(
        event_id=str(payload["event_id"]),
        tick=int(payload["tick"]),
        phase=str(payload["phase"]),
        type=str(payload["type"]),
        severity=str(payload["severity"]),
        payload=dict(payload.get("payload", {})),
        source_id=payload.get("source_id"),
        cause_event_ids=payload.get("cause_event_ids"),
        visible_to_ai=bool(payload.get("visible_to_ai", True)),
    )


def _cell_key(value: str) -> tuple[int, int]:
    lane, col = value.split(",", 1)
    return int(lane), int(col)


def _parse_options(args: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    loose_cards: list[str] = []
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            options[key.strip().lower()] = value.strip()
        elif arg.strip().lower() in SPECIAL_LEVEL_ALIASES:
            options["level"] = arg.strip()
        else:
            loose_cards.append(arg)
    if loose_cards:
        cards = [str(options["cards"])] if options.get("cards") else []
        cards.extend(loose_cards)
        options["cards"] = " ".join(cards)
    mode = options.get("mode") or options.get("模式")
    if isinstance(mode, str) and mode.strip().lower() in SPECIAL_LEVEL_ALIASES:
        options["level"] = mode.strip()
    return options


def _airdrop_option(options: dict[str, Any]) -> bool:
    raw_values = [
        options.get("chaos"),
        options.get("mod"),
        options.get("modifier"),
        options.get("混沌"),
        options.get("模式词条"),
    ]
    enabled_values = {"airdrop", "airdrops", "on", "true", "yes", "1", "空投", "开", "开启"}
    return any(isinstance(value, str) and value.strip().lower() in enabled_values for value in raw_values)


def _chaos_option_text(enable_airdrops: bool) -> str:
    return "airdrop" if enable_airdrops else "off"


def _chaos_mode_description(enable_airdrops: bool) -> str:
    if enable_airdrops:
        return "混沌模式: 新增空投箱；空投占格但不拦僵尸，可主动打开，僵尸经过也会打开，里面是强力植物或僵尸。"
    return "混沌模式: 关闭，普通全模仿者无尽。"


def _int_option(options: dict[str, Any], key: str, *, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(options.get(key, default)))
    except (TypeError, ValueError):
        return default


def _level_option(options: dict[str, Any], *, default: int) -> int:
    raw_level = options.get("level")
    if isinstance(raw_level, str) and raw_level.strip().lower() in SPECIAL_LEVEL_ALIASES:
        return ALL_IMITATOR_LEVEL
    return _int_option(options, "level", default=default, minimum=1)


def _default_loadout_for_level(level: int) -> tuple[str, ...]:
    if is_all_imitator_level(level):
        return ALL_IMITATOR_CARD_LOADOUT
    if level == FOG_LEVEL:
        return FOG_CARD_LOADOUT
    if level == ROOF_LEVEL:
        return ROOF_CARD_LOADOUT
    return DEFAULT_CARD_LOADOUT


def _card_selection_text(level: int) -> str:
    return build_card_selection_view(
        GameConfig(card_slot_count=6, max_card_slot_count=10),
        recommended_loadout=_default_loadout_for_level(level),
    )["text"]


def _loadout_from_options(options: dict[str, Any], *, level: int) -> tuple[str, ...] | None:
    raw_cards = options.get("cards") or options.get("loadout")
    if not raw_cards:
        return None
    if str(raw_cards).strip().lower() in {"默认", "default", "recommended"}:
        return _default_loadout_for_level(level)
    cards = [item for item in str(raw_cards).replace(",", " ").replace("，", " ").split() if item]
    loadout = tuple(_card_id(item) for item in cards)
    if any(item is None for item in loadout):
        return None
    return tuple(item for item in loadout if item is not None)


def _card_id(name: str) -> str | None:
    normalized = name.strip()
    if not normalized:
        return None
    if normalized in {"imitator", "模仿者", "模"}:
        return "imitator"
    if normalized in CARD_COMMANDS:
        return CARD_COMMANDS[normalized]
    if normalized in PLANT_NAMES:
        return normalized
    return None


def _loadout_text(loadout: tuple[str, ...]) -> str:
    if not loadout:
        return "未设置"
    return ",".join(PLANT_NAMES.get(card_id, "模仿者" if card_id == "imitator" else card_id) for card_id in loadout)


def _state_json(engine: GameEngine) -> str:
    return (
        f'{{"level": {engine.state.level}, "tick": {engine.state.tick}, "sun": {engine.state.sun}, '
        f'"result": "{engine.state.result or "running"}", "turns": {engine._round_counter}}}'
    )
