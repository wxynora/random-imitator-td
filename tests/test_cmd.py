from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from random_imitator_td import engine as cmd_engine


class ImitatorPvzCmdTests(unittest.TestCase):
    def test_cmd_requires_card_setup_before_play(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            start = cmd_engine.cmd("new_game level=1 seed=setup-test")
            blocked = cmd_engine.cmd("种 模仿者 3-3")

            self.assertIn("请先编辑卡槽", start)
            self.assertIn("提示: 模仿者越多，随机味越足。", start)
            self.assertIn("请先编辑卡槽", blocked)

    def test_cmd_starts_game_sets_cards_and_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            start = cmd_engine.cmd("new_game level=1 seed=cmd-test cards=模仿者 模仿者 向日葵 窝瓜")
            action = cmd_engine.cmd("种 模仿者 3-3; 种 向日葵 2-3")
            status = cmd_engine.cmd("status")

            self.assertIn("新游戏: lv1 seed=cmd-test", start)
            self.assertIn("资源: 阳光", start)
            self.assertIn("3路3列种下模仿者", action)
            self.assertIn('"level": 1', status)
            self.assertTrue(cmd_engine.DEFAULT_SAVE_PATH.exists())

            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            restored = cmd_engine._engine_from_session(payload)
            self.assertEqual(restored.rng.seed, "cmd-test")
            self.assertGreater(restored.state.tick, 0)
            self.assertIsNotNone(restored.state.grid[(3, 3)])

    def test_cmd_reports_card_selection_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            output = cmd_engine.cmd("cards")

            self.assertIn("槽位6/10", output)
            self.assertIn("模仿者(0)", output)


if __name__ == "__main__":
    unittest.main()
