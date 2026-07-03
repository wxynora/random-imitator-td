from __future__ import annotations

from typing import Any

from .config import GameConfig, SCHEMA_VERSION


class ContractError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


ALLOWED_TOP_LEVEL_ACTION_PLAN_FIELDS = {
    "schema_version",
    "observation_id",
    "action_plan_id",
    "interrupt_policy",
    "actions",
}
ALLOWED_ACTIONS = {"plant_imitator", "plant_card", "shovel_plant", "wait", "end_game"}
ALLOWED_INTERRUPT_POLICIES = {
    "interrupt_on_emergency",
    "continue_unless_game_over",
    "stop_on_any_failure",
    "skip_optional_failure",
}
ALLOWED_ACTION_FIELDS = {
    "plant_imitator": {"action", "lane", "col", "slot_id", "optional"},
    "plant_card": {"action", "lane", "col", "slot_id", "optional"},
    "shovel_plant": {"action", "lane", "col", "optional"},
    "wait": {"action", "max_wait_ticks"},
    "end_game": {"action", "reason"},
}
CELL_ACTIONS = {"plant_imitator", "plant_card", "shovel_plant"}
PLANT_ACTIONS = {"plant_imitator", "plant_card"}
OBSERVATION_REQUIRED_FIELDS = {
    "schema_version",
    "observation_id",
    "tick",
    "sun",
    "advance_summary",
    "events",
    "lanes",
    "valid_actions",
    "action_constraints",
    "game_status",
}
ACTION_RESULT_REQUIRED_FIELDS = {
    "schema_version",
    "action_plan_id",
    "accepted",
    "executed_actions",
    "failed_actions",
    "advance_summary",
    "events",
    "need_next_decision",
    "observation",
}


def minimal_observation(
    *,
    observation_id: str = "obs_1",
    tick: int = 0,
    sun: int = 150,
    advance_summary: dict[str, Any] | None = None,
    game_status: str = "running",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": observation_id,
        "tick": tick,
        "sun": sun,
        "advance_summary": dict(advance_summary or {}),
        "reason": [],
        "events": [],
        "lanes": [],
        "valid_actions": ["plant_imitator", "wait", "end_game"],
        "action_constraints": {},
        "game_status": game_status,
    }


def validate_observation(observation: dict[str, Any]) -> None:
    missing = OBSERVATION_REQUIRED_FIELDS - observation.keys()
    if missing:
        raise ContractError(f"missing_observation_fields:{sorted(missing)}")
    if observation["schema_version"] != SCHEMA_VERSION:
        raise ContractError("schema_version_mismatch")


def _coerce_intish(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


def _positive_index(value: Any) -> int | None:
    value = _coerce_intish(value)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _card_hint(action: dict[str, Any], config: GameConfig) -> str | None:
    known_card_ids = {"imitator", "coffee_bean", *config.card_loadout}
    for field in ("card_id", "card"):
        value = action.get(field)
        if isinstance(value, str):
            value = value.strip()
            if value in known_card_ids:
                return value
    return None


def _normalize_slot_id(value: Any, *, action_type: str, card_hint: str | None) -> Any:
    if value is None:
        return None
    slot_index = _positive_index(value)
    if slot_index is not None:
        if action_type == "plant_imitator":
            return f"imitator_{slot_index}"
        if card_hint is not None:
            return f"{card_hint}_{slot_index}"
        return str(slot_index)
    if isinstance(value, str):
        value = value.strip()
        if value in {"imitator", "coffee_bean"}:
            return None
        return value
    return value


def _normalize_action(action: Any, config: GameConfig) -> Any:
    if not isinstance(action, dict):
        return action
    normalized = dict(action)
    action_type = normalized.get("action")
    if action_type not in CELL_ACTIONS:
        return normalized

    if "lane" not in normalized and "row" in normalized:
        normalized["lane"] = normalized["row"]
    normalized.pop("row", None)

    for field in ("lane", "col"):
        if field in normalized:
            normalized[field] = _coerce_intish(normalized[field])

    if action_type in PLANT_ACTIONS:
        has_slot_id = "slot_id" in normalized
        slot_candidate = normalized.get("slot_id") if has_slot_id else None
        if slot_candidate is None:
            if "card" in normalized:
                slot_candidate = normalized["card"]
            elif "card_id" in normalized:
                slot_candidate = normalized["card_id"]

        normalized_slot_id = _normalize_slot_id(
            slot_candidate,
            action_type=action_type,
            card_hint=_card_hint(normalized, config),
        )
        if normalized_slot_id is not None:
            normalized["slot_id"] = normalized_slot_id
        elif not has_slot_id:
            normalized.pop("slot_id", None)

        normalized.pop("card", None)
        normalized.pop("card_id", None)
    return normalized


def normalize_action_plan(
    action_plan: dict[str, Any],
    *,
    config: GameConfig | None = None,
    observation_id: str | None = None,
) -> dict[str, Any]:
    config = config or GameConfig()
    if not isinstance(action_plan, dict):
        raise ContractError("action_not_legal")
    normalized = dict(action_plan)
    actions = normalized.get("actions")
    if isinstance(actions, list):
        normalized["actions"] = [_normalize_action(action, config) for action in actions]
    validate_action_plan(normalized, config=config, observation_id=observation_id)
    return normalized


def validate_action_plan(
    action_plan: dict[str, Any],
    *,
    config: GameConfig | None = None,
    observation_id: str | None = None,
) -> None:
    config = config or GameConfig()
    unknown = set(action_plan) - ALLOWED_TOP_LEVEL_ACTION_PLAN_FIELDS
    if unknown:
        raise ContractError("action_not_legal")
    if action_plan.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("schema_version_mismatch")
    for field in ("observation_id", "action_plan_id", "interrupt_policy", "actions"):
        if field not in action_plan:
            raise ContractError("action_not_legal")
    if observation_id is not None and action_plan["observation_id"] != observation_id:
        raise ContractError("observation_id_mismatch")
    if action_plan["interrupt_policy"] not in ALLOWED_INTERRUPT_POLICIES:
        raise ContractError("action_not_legal")
    actions = action_plan["actions"]
    if not isinstance(actions, list) or not actions:
        raise ContractError("action_not_legal")
    if any(not isinstance(action, dict) for action in actions):
        raise ContractError("action_not_legal")
    wait_indexes = [index for index, action in enumerate(actions) if action.get("action") == "wait"]
    if wait_indexes and wait_indexes != [len(actions) - 1]:
        raise ContractError("action_not_legal")
    end_game_indexes = [index for index, action in enumerate(actions) if action.get("action") == "end_game"]
    if end_game_indexes and (end_game_indexes != [0] or len(actions) != 1):
        raise ContractError("action_not_legal")
    for action in actions:
        action_type = action.get("action")
        if action_type not in ALLOWED_ACTIONS:
            raise ContractError("action_not_legal")
        if set(action) - ALLOWED_ACTION_FIELDS[action_type]:
            raise ContractError("action_not_legal")
        if action_type in CELL_ACTIONS and not {"lane", "col"} <= action.keys():
            raise ContractError("action_not_legal")
        if action_type in CELL_ACTIONS:
            lane = action["lane"]
            col = action["col"]
            if not isinstance(lane, int) or not isinstance(col, int):
                raise ContractError("action_not_legal")
            if not config.is_valid_cell(lane, col):
                raise ContractError("action_not_legal")
        if action_type in PLANT_ACTIONS:
            slot_id = action.get("slot_id")
            if slot_id is not None and not isinstance(slot_id, str):
                raise ContractError("action_not_legal")
        if action_type == "wait":
            if "max_wait_ticks" in action:
                max_wait_ticks = action["max_wait_ticks"]
                if not isinstance(max_wait_ticks, int) or max_wait_ticks <= 0:
                    raise ContractError("action_not_legal")
        if action_type == "end_game" and "reason" in action and not isinstance(action["reason"], str):
            raise ContractError("action_not_legal")


def action_failed_result(
    *,
    action_plan_id: str,
    action_index: int,
    action: str,
    reason: str,
    observation: dict[str, Any] | None = None,
    advance_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "action_plan_id": action_plan_id,
        "accepted": True,
        "executed_actions": [],
        "failed_actions": [
            {"action_index": action_index, "action": action, "reason": reason}
        ],
        "advance_summary": dict(advance_summary or {}),
        "events": [{"type": "action_failed", "reason": reason}],
        "need_next_decision": True,
        "observation": observation or {},
    }
    validate_action_result(result)
    return result


def validate_action_result(action_result: dict[str, Any]) -> None:
    missing = ACTION_RESULT_REQUIRED_FIELDS - action_result.keys()
    if missing:
        raise ContractError(f"missing_action_result_fields:{sorted(missing)}")
    if action_result["schema_version"] != SCHEMA_VERSION:
        raise ContractError("schema_version_mismatch")
