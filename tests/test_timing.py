from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td.game.config import GameConfig, SCHEMA_VERSION
from random_imitator_td.game.engine import GameEngine
from random_imitator_td.game.timing import real_seconds_to_decision_delay_ticks


class ImitatorPvzTimingTests(unittest.TestCase):
    def test_real_seconds_are_soft_mapped_to_game_ticks(self) -> None:
        config = GameConfig()
        cases = {
            0: 0,
            1: 1,
            4.5: 3,
            5: 4,
            15: 10,
            45: 30,
            90: 60,
            180: 60,
        }
        for real_seconds, expected_ticks in cases.items():
            with self.subTest(real_seconds=real_seconds):
                self.assertEqual(real_seconds_to_decision_delay_ticks(real_seconds, config), expected_ticks)

    def test_time_mapping_uses_ceil_for_fractional_ticks(self) -> None:
        config = GameConfig()
        self.assertEqual(real_seconds_to_decision_delay_ticks(4.01, config), 3)
        self.assertEqual(real_seconds_to_decision_delay_ticks(44.1, config), 30)

    def test_action_plan_uses_soft_time_mapping(self) -> None:
        engine = GameEngine(wave_schedule=[(9999, "normal", 3)])
        observation = engine.run_until_decision()
        plan = {
            "schema_version": SCHEMA_VERSION,
            "observation_id": observation["observation_id"],
            "action_plan_id": "plan_time",
            "interrupt_policy": "interrupt_on_emergency",
            "actions": [{"action": "plant_imitator", "lane": 3, "col": 3}],
        }
        result = engine.apply_action_plan(
            plan,
            observation_id=observation["observation_id"],
            real_elapsed_seconds=45,
        )
        self.assertEqual(result["advance_summary"]["from_tick"], 0)
        self.assertEqual(result["advance_summary"]["to_tick"], 33)
        self.assertEqual(result["advance_summary"]["advanced_ticks"], 33)
        self.assertNotIn("action_delay_charged", [event["type"] for event in result["events"]])
        self.assertEqual(
            [event for event in engine.event_log if event.type == "action_delay_charged"][0].payload["delay_ticks"],
            30,
        )


if __name__ == "__main__":
    unittest.main()
