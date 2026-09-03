# -*- coding: utf-8 -*-
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("check_subtitle.py")
SPEC = importlib.util.spec_from_file_location("check_subtitle", SCRIPT_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def make_cfg(lang="zh", **overrides):
    """The cfg dict main() builds, so tests exercise the same defaults as the CLI."""
    profile = CHECKER.LANG_PROFILES.get(lang, CHECKER.LANG_PROFILES["default"])
    cfg = {
        "lang": lang,
        "max_cps": profile["max_cps"],
        "max_width": profile["max_width"],
        "counting": profile["counting"],
        "final_punct": profile["final_punct"],
        "ban_exclamation": profile.get("ban_exclamation", False),
        "spacing": profile["spacing"],
        "strict": False,
        "min_duration": CHECKER.DEFAULTS["min_duration"],
        "max_duration": CHECKER.DEFAULTS["max_duration"],
        "max_lines": CHECKER.DEFAULTS["max_lines"],
        "min_split_piece": CHECKER.DEFAULTS["min_split_piece"],
        "min_span_cost": CHECKER.FIDELITY["min_span_cost"],
        "min_spans": CHECKER.FIDELITY["min_spans"],
        "pad_factor": CHECKER.FIDELITY["pad_factor"],
        "drop_factor": CHECKER.FIDELITY["drop_factor"],
        "max_reports": CHECKER.FIDELITY["max_reports"],
    }
    cfg.update(overrides)
    return cfg


def run_check(output, source=None, lang="zh", **overrides):
    """Write the given SRT text(s) to a temp dir and run the checker on them."""
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.srt"
        out_path.write_text(output, encoding="utf-8")
        src_path = None
        if source is not None:
            src_path = Path(tmp) / "in.srt"
            src_path.write_text(source, encoding="utf-8")
        return CHECKER.check(
            str(out_path),
            str(src_path) if src_path else None,
            "srt",
            "srt" if src_path else None,
            make_cfg(lang, **overrides),
        )


def srt(*blocks):
    """Build SRT text from (start_seconds, end_seconds, text) tuples."""
    def stamp(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

    return "\n".join(
        "%d\n%s --> %s\n%s\n" % (i + 1, stamp(a), stamp(b), text)
        for i, (a, b, text) in enumerate(blocks)
    )


class MinimalChinesePunctuationTests(unittest.TestCase):
    def check_warnings(self, text):
        _, errors, warnings, _ = run_check(srt((0.0, 4.0, text)))
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
        _, errors, warnings, _ = run_check(srt(
            (0.0, 2.0, "做一只完全动态的鸟会很有趣 看看"),
            (2.0, 4.0, "能做些什么"),
        ))
        self.assertEqual([], errors)
        self.assertTrue(any("thought-unit boundary broken — ends on dangling" in w for w in warnings))

    def test_warns_for_dangling_head_particle_stranded(self):
        _, errors, warnings, _ = run_check(srt(
            (0.0, 2.0, "这是一个非常重要"),
            (2.0, 4.0, "的设置项目"),
        ))
        self.assertEqual([], errors)
        self.assertTrue(any(
            "thought-unit boundary broken — starts with stranded particle '的'" in w
            for w in warnings
        ))


class LengthFidelityTests(unittest.TestCase):
    """Padding and dropped payload leave the timeline intact, so they need their own check."""

    # Ten separated speech spans; each source line is ~40 raw Latin chars (cost ~20)
    # and each lean translation is ~10 full-width chars, so the file's norm is ~0.5.
    SOURCE_LINES = [
        "move the object up a little bit right now",
        "then add a bevel to the top edge here",
        "set the roughness value down to twenty",
        "drag the light closer to the model now",
        "open the material manager on the right",
        "select every polygon on the front face",
        "turn the substep count up to sixteen ok",
        "check the render preview window again",
        "delete the extra edge loop near the top",
        "save the project before you continue on",
    ]
    LEAN_LINES = [
        "把对象往上挪一点",
        "给上边加个倒角",
        "粗糙度降到 20",
        "把灯光往模型挪近",
        "打开右边材质管理器",
        "选中正面所有多边形",
        "子步调到 16",
        "再看看渲染预览窗",
        "删掉顶部多余循环边",
        "继续之前先保存工程",
    ]

    def build(self, out_lines):
        """One 4s span per line, separated by 1s of real silence."""
        blocks = lambda lines: srt(*[
            (i * 5.0, i * 5.0 + 4.0, text) for i, text in enumerate(lines)
        ])
        return blocks(out_lines), blocks(self.SOURCE_LINES)

    def run_fidelity(self, out_lines):
        output, source = self.build(out_lines)
        _, errors, warnings, notes = run_check(output, source)
        self.assertEqual([], errors)
        return warnings, notes

    def test_lean_translation_raises_no_fidelity_warning(self):
        warnings, notes = self.run_fidelity(self.LEAN_LINES)
        self.assertFalse([w for w in warnings if "padding" in w or "dropped payload" in w],
                         "a uniformly lean file must not be flagged")
        self.assertTrue(any("length fidelity: median" in n for n in notes))

    def test_padded_span_is_flagged(self):
        lines = list(self.LEAN_LINES)
        lines[3] = "接下来我们需要把这个灯光稍微向着模型的方向移动得更近一些就可以了"
        warnings, _ = self.run_fidelity(lines)
        padded = [w for w in warnings if "check for padding" in w]
        self.assertEqual(1, len(padded), "exactly the padded span should be flagged: %s" % warnings)
        self.assertIn("00:00:15,000", padded[0])

    def test_dropped_span_is_flagged(self):
        lines = list(self.LEAN_LINES)
        lines[6] = "调一下"
        warnings, _ = self.run_fidelity(lines)
        dropped = [w for w in warnings if "check for dropped payload" in w]
        self.assertEqual(1, len(dropped), "exactly the gutted span should be flagged: %s" % warnings)
        self.assertIn("00:00:30,000", dropped[0])

    def test_short_file_is_not_judged(self):
        """Below min_spans there is no reliable median, so the check stays silent."""
        out = srt((0.0, 4.0, "接下来我们需要把这个灯光稍微向着模型的方向移动得更近一些"))
        src = srt((0.0, 4.0, "move the light closer"))
        _, errors, warnings, notes = run_check(out, src)
        self.assertEqual([], errors)
        self.assertFalse([w for w in warnings if "check for padding" in w])
        self.assertFalse([n for n in notes if "length fidelity" in n])

    def test_bilingual_output_shifts_the_norm_not_the_verdict(self):
        """Every span doubles in length, so the median absorbs it and nothing is flagged."""
        lines = ["%s / %s" % (zh, en)
                 for zh, en in zip(self.LEAN_LINES, self.SOURCE_LINES)]
        warnings, _ = self.run_fidelity(lines)
        self.assertFalse([w for w in warnings if "check for padding" in w],
                         "uniform doubling is a house style, not a fidelity defect")


if __name__ == "__main__":
    unittest.main()
