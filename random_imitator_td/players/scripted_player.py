from __future__ import annotations

from dataclasses import dataclass, field

from random_imitator_td.game.config import SCHEMA_VERSION


@dataclass
class ScriptedPlayer:
    placements: list[tuple[int, int]] = field(
        default_factory=lambda: [(3, 3), (2, 3), (4, 3), (3, 4), (1, 3), (5, 3)]
    )
    _index: int = 0

    def decide(self, observation: dict) -> dict:
        actions: list[dict] = []
        constraints = observation.get("action_constraints", {})
        imitator_cost = constraints.get("imitator_cost", 0)
        ready_slots = [
            slot
            for slot in constraints.get("card_slots", [])
            if slot.get("card_id") == "imitator" and slot.get("ready")
        ]
        sun = observation.get("sun", 0)
        open_cells_by_lane = {
            lane["lane"]: set(lane.get("open_cells", []))
            for lane in observation.get("lanes", [])
        }

        if imitator_cost <= 0:
            max_plants = min(3, len(ready_slots))
        else:
            max_plants = min(3, len(ready_slots), sun // imitator_cost)
        while self._index < len(self.placements) and len(actions) < max_plants:
            lane, col = self.placements[self._index]
            self._index += 1
            if col not in open_cells_by_lane.get(lane, set()):
                continue
            slot_id = ready_slots[len(actions)]["slot_id"]
            actions.append({"action": "plant_imitator", "lane": lane, "col": col, "slot_id": slot_id})
            open_cells_by_lane[lane].remove(col)
            sun -= imitator_cost

        if not actions:
            actions.append({"action": "wait", "max_wait_ticks": 80})

        return {
            "schema_version": SCHEMA_VERSION,
            "observation_id": observation["observation_id"],
            "action_plan_id": f"plan_{observation['observation_id']}",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": actions,
        }
