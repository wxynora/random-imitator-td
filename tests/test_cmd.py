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

    def test_cmd_emits_anti_addiction_pause_every_five_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            cmd_engine.cmd("new_game level=1 seed=pause-test cards=模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜")
            for _ in range(5):
                output = cmd_engine.cmd("等待 1")
                self.assertNotIn(cmd_engine.ANTI_ADDICTION_PAUSE_PREFIX, output)

            output = cmd_engine.cmd("等待 1")

            self.assertIn(cmd_engine.ANTI_ADDICTION_PAUSE_PREFIX, output)
            self.assertIn("已完成第5回合", output)
            self.assertIn("暂时中止游戏回合", output)
            self.assertNotIn("资源: 阳光", output)

            output = cmd_engine.cmd("等待 1")

            self.assertNotIn(cmd_engine.ANTI_ADDICTION_PAUSE_PREFIX, output)
            self.assertIn("资源: 阳光", output)

    def test_cmd_open_prefers_existing_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            cmd_engine.cmd("new_game level=1 seed=resume-test cards=模仿者 模仿者 向日葵 窝瓜")
            cmd_engine.cmd("等待 1")

            output = cmd_engine.cmd("打开")

            self.assertIn("资源: 阳光", output)
            self.assertIn('"seed"', cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            self.assertNotIn("请先编辑卡槽", output)

    def test_finished_game_resets_on_next_open_but_keeps_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            cmd_engine.cmd("new_game level=1 seed=finished-test cards=模仿者 模仿者 向日葵 窝瓜")
            note_output = cmd_engine.cmd("note 多带模仿者")
            end_output = cmd_engine.cmd("结束本局")
            open_output = cmd_engine.cmd("打开")
            notes_output = cmd_engine.cmd("note")

            self.assertIn("复盘已记录", note_output)
            self.assertIn("玩家主动结束本局", end_output)
            self.assertIn("上一局已结束，已准备新局。", open_output)
            self.assertIn("请先编辑卡槽", open_output)
            self.assertIn("多带模仿者", notes_output)

    def test_won_game_advances_to_next_level_on_next_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            cmd_engine.cmd("new_game level=1 seed=won-next-level cards=模仿者 模仿者 向日葵 窝瓜")
            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            engine = cmd_engine._engine_from_session(payload)
            self.assertIsNotNone(engine)
            engine.state.game_over = True
            engine.state.result = "won"
            cmd_engine._store_engine(payload, engine)
            cmd_engine._save_session(payload)

            open_output = cmd_engine.cmd("打开")
            cards_output = cmd_engine.cmd("cards 模仿者 模仿者 模仿者 模仿者 向日葵 窝瓜")

            self.assertIn("上一关已通关，已准备 lv2。", open_output)
            self.assertIn("请先编辑卡槽", open_output)
            self.assertIn("Lv2 场地:夜间", cards_output)


if __name__ == "__main__":
    unittest.main()
