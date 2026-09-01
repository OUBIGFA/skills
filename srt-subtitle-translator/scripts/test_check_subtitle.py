# -*- coding: utf-8 -*-
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("check_subtitle.py")
SPEC = importlib.util.spec_from_file_location("check_subtitle", SCRIPT_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class MinimalChinesePunctuationTests(unittest.TestCase):
    def check_warnings(self, text):
        content = "1\n00:00:00,000 --> 00:00:04,000\n%s\n" % text
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.srt"
            path.write_text(content, encoding="utf-8")
            profile = CHECKER.LANG_PROFILES["zh"]
            cfg = {
                "lang": "zh",
                "max_cps": profile["max_cps"],
                "max_width": profile["max_width"],
                "counting": profile["counting"],
                "final_punct": profile["final_punct"],
                "ban_exclamation": profile.get("ban_exclamation", True),
                "spacing": profile["spacing"],
                "strict": False,
                "min_duration": CHECKER.DEFAULTS["min_duration"],
                "max_duration": CHECKER.DEFAULTS["max_duration"],
                "max_lines": CHECKER.DEFAULTS["max_lines"],
                "min_split_piece": CHECKER.DEFAULTS["min_split_piece"],
            }
            _, errors, warnings, _ = CHECKER.check(
                str(path), None, "srt", None, cfg
            )
        self.assertEqual([], errors)
        return warnings

    def test_warns_for_semicolon_that_needs_manual_review(self):
        warnings = self.check_warnings("先选择对象；再打开面板")
        self.assertTrue(any("internal '；'" in warning for warning in warnings))

    def test_allows_genuine_colon(self):
        warnings = self.check_warnings("原因很简单：需要更多几何体")
        self.assertFalse(any("internal" in warning for warning in warnings))

    def test_allows_comma_and_dunhao(self):
        warnings = self.check_warnings("先选择对象，再打开面板、确认设置")
        self.assertFalse(any("internal" in warning or "exclamation" in warning for warning in warnings))

    def test_allows_question_mark(self):
        warnings = self.check_warnings("这样可以吗？")
        self.assertFalse(any("internal" in warning or "exclamation" in warning for warning in warnings))

    def test_allows_terminal_question_mark(self):
        warnings = self.check_warnings("这样可以吗？")
        self.assertFalse(any("line ends" in warning for warning in warnings))

    def test_warns_for_terminal_exclamation_mark(self):
        warnings = self.check_warnings("设置完成！")
        self.assertTrue(any("exclamation mark" in warning or "line ends with '！'" in warning for warning in warnings))

    def test_warns_for_internal_exclamation_mark(self):
        warnings = self.check_warnings("注意！先选择对象")
        self.assertTrue(any("exclamation mark" in warning for warning in warnings))

    def test_warns_for_halfwidth_exclamation_mark(self):
        warnings = self.check_warnings("注意! 先选择对象")
        self.assertTrue(any("exclamation mark" in warning for warning in warnings))

    def test_warns_for_internal_period_that_splits_sentences(self):
        period_warnings = self.check_warnings("先选择对象。然后打开面板")
        self.assertTrue(any("internal '。'" in warning for warning in period_warnings))

    def test_does_not_warn_for_speaker_label(self):
        label_warnings = self.check_warnings("John：请打开面板")
        self.assertFalse(any("internal" in warning for warning in label_warnings))

    def test_warns_for_dangling_tail_word_before_continuation(self):
        content = (
            "1\n00:00:00,000 --> 00:00:02,000\n做一只完全动态的鸟会很有趣 看看\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\n能做些什么\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.srt"
            path.write_text(content, encoding="utf-8")
            profile = CHECKER.LANG_PROFILES["zh"]
            cfg = {
                "lang": "zh",
                "max_cps": profile["max_cps"],
                "max_width": profile["max_width"],
                "counting": profile["counting"],
                "final_punct": profile["final_punct"],
                "ban_exclamation": profile.get("ban_exclamation", True),
                "spacing": profile["spacing"],
                "strict": False,
                "min_duration": CHECKER.DEFAULTS["min_duration"],
                "max_duration": CHECKER.DEFAULTS["max_duration"],
                "max_lines": CHECKER.DEFAULTS["max_lines"],
                "min_split_piece": CHECKER.DEFAULTS["min_split_piece"],
            }
            _, errors, warnings, _ = CHECKER.check(
                str(path), None, "srt", None, cfg
            )
        self.assertEqual([], errors)
        self.assertTrue(any("thought-unit boundary broken — ends on dangling" in w for w in warnings))

    def test_warns_for_dangling_head_particle_stranded(self):
        content = (
            "1\n00:00:00,000 --> 00:00:02,000\n这是一个非常重要\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\n的设置项目\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.srt"
            path.write_text(content, encoding="utf-8")
            profile = CHECKER.LANG_PROFILES["zh"]
            cfg = {
                "lang": "zh",
                "max_cps": profile["max_cps"],
                "max_width": profile["max_width"],
                "counting": profile["counting"],
                "final_punct": profile["final_punct"],
                "ban_exclamation": profile.get("ban_exclamation", True),
                "spacing": profile["spacing"],
                "strict": False,
                "min_duration": CHECKER.DEFAULTS["min_duration"],
                "max_duration": CHECKER.DEFAULTS["max_duration"],
                "max_lines": CHECKER.DEFAULTS["max_lines"],
                "min_split_piece": CHECKER.DEFAULTS["min_split_piece"],
            }
            _, errors, warnings, _ = CHECKER.check(
                str(path), None, "srt", None, cfg
            )
        self.assertEqual([], errors)
        self.assertTrue(any("thought-unit boundary broken — starts with stranded particle '的'" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
