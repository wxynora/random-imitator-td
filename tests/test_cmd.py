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
    def setUp(self) -> None:
        self._old_records_path = cmd_engine.DEFAULT_RECORDS_PATH
        self._records_tmpdir = tempfile.TemporaryDirectory()
        cmd_engine.DEFAULT_RECORDS_PATH = Path(self._records_tmpdir.name) / "records.json"

    def tearDown(self) -> None:
        cmd_engine.DEFAULT_RECORDS_PATH = self._old_records_path
        self._records_tmpdir.cleanup()

    def test_cmd_requires_card_setup_before_play(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            start = cmd_engine.cmd("new_game level=1 seed=setup-test")
            blocked = cmd_engine.cmd("种 模仿者 3-3")

            self.assertIn("请先编辑卡槽", start)
            self.assertIn("模式: 默认普通；特殊无尽用 new_game mode=特殊 chaos=off|airdrop（固定六个模仿者）。", start)
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

    def test_cmd_can_start_six_imitator_endless_special_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            output = cmd_engine.cmd("new_game mode=特殊 seed=six-imitator-special")
            status = cmd_engine.cmd("status")

            self.assertIn("新游戏: lv6 seed=six-imitator-special", output)
            self.assertIn("混沌=off", output)
            self.assertIn("混沌模式: 关闭，普通全模仿者无尽。", output)
            self.assertIn("Lv6 场地:全模仿者", output)
            self.assertIn("卡槽: 模仿者x6(0)", output)
            self.assertIn("无尽本局(普通): 系统波次0", output)
            self.assertIn("系统波次: 无尽，已出现0只", output)
            self.assertIn('"level": 6', status)
            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            restored = cmd_engine._engine_from_session(payload)
            self.assertEqual(tuple(restored.config.card_loadout), ("imitator",) * 6)
            self.assertTrue(restored.config.is_endless)
            self.assertEqual(len(restored.state.cooldowns), 6)

    def test_special_endless_record_is_separate_from_current_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"
            cmd_engine.DEFAULT_RECORDS_PATH = Path(tmpdir) / "records.json"

            cmd_engine.cmd("new_game mode=特殊 seed=endless-record-test")
            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            engine = cmd_engine._engine_from_session(payload)
            self.assertIsNotNone(engine)
            engine.state.wave_state["spawned_count"] = 12
            engine.state.tick = 900
            engine.state.game_over = True
            engine.state.result = "lost"
            cmd_engine._store_engine(payload, engine)
            cmd_engine._save_session(payload)

            open_output = cmd_engine.cmd("打开")
            normal_output = cmd_engine.cmd("new_game level=1 seed=normal-after-record")
            special_setup = cmd_engine.cmd("new_game mode=特殊 seed=record-visible")

            self.assertNotIn("无尽纪录", open_output)
            self.assertIn("新游戏: lv1 seed=normal-after-record", normal_output)
            self.assertIn("请先编辑卡槽", normal_output)
            self.assertIn("无尽纪录(普通): 最佳 系统波次12", special_setup)

    def test_cmd_can_start_special_airdrop_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            output = cmd_engine.cmd("new_game mode=特殊 chaos=airdrop seed=airdrop-special")
            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            restored = cmd_engine._engine_from_session(payload)

            self.assertIn("Lv6 场地:全模仿者·空投", output)
            self.assertIn("混沌=airdrop", output)
            self.assertIn("混沌模式: 新增空投箱", output)
            self.assertIn("空投: 预告 tick", output)
            self.assertIn("无尽本局(空投): 系统波次0", output)
            self.assertIsNotNone(restored)
            self.assertTrue(restored.config.enable_airdrops)

    def test_special_airdrop_record_is_separate_from_plain_endless_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"
            cmd_engine.DEFAULT_RECORDS_PATH = Path(tmpdir) / "records.json"

            cmd_engine.cmd("new_game mode=特殊 chaos=airdrop seed=airdrop-record")
            payload = json.loads(cmd_engine.DEFAULT_SAVE_PATH.read_text(encoding="utf-8"))
            engine = cmd_engine._engine_from_session(payload)
            self.assertIsNotNone(engine)
            engine.state.wave_state["spawned_count"] = 7
            engine.state.tick = 700
            engine.state.game_over = True
            engine.state.result = "lost"
            cmd_engine._store_engine(payload, engine)
            cmd_engine._save_session(payload)

            cmd_engine.cmd("打开")
            plain_output = cmd_engine.cmd("new_game mode=特殊 seed=plain-after-airdrop")
            airdrop_output = cmd_engine.cmd("new_game mode=特殊 chaos=airdrop seed=airdrop-visible")
            records = json.loads(cmd_engine.DEFAULT_RECORDS_PATH.read_text(encoding="utf-8"))

            self.assertNotIn("无尽纪录(空投)", plain_output)
            self.assertIn("无尽纪录(空投): 最佳 系统波次7", airdrop_output)
            self.assertNotIn(cmd_engine.ENDLESS_RECORD_ID, records)
            self.assertIn(f"{cmd_engine.ENDLESS_RECORD_ID}:airdrop", records)

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

    def test_cmd_does_not_fast_forward_before_player_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_engine.DEFAULT_SAVE_PATH = Path(tmpdir) / "save.json"

            cmd_engine.cmd("new_game level=1 seed=no-hidden-advance cards=模仿者 模仿者")
            first = cmd_engine.cmd("种 模仿者 3-3")
            second = cmd_engine.cmd("种 模仿者 3-4")

            self.assertIn('"tick": 3', first)
            self.assertIn('"tick": 6', second)
            self.assertIn("3路4列种下模仿者", second)
            self.assertNotIn("3路3列模仿者开奖", second)

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
