# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillAssetTests(unittest.TestCase):
    def test_skill_routes_controlled_expression_reference(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference = ROOT / "references" / "asd-ste100-subtitles.md"
        self.assertTrue(reference.exists())
        self.assertIn("ASD-STE100", skill)
        self.assertIn("asd-ste100-subtitles.md", skill)
        self.assertIn("删去无意义填充词", skill)
        self.assertIn("保留信息载荷", skill)
        reference_text = reference.read_text(encoding="utf-8")
        self.assertIn("Information pass", reference_text)
        self.assertIn("Economy pass", reference_text)
        self.assertIn("negation", reference_text)
        self.assertIn("do not force", reference_text)

    def test_eval_manifest_covers_controlled_subtitle_pressure_cases(self):
        manifest = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        ids = {item["id"] for item in manifest["evals"]}
        self.assertIn(33, ids)
        self.assertIn(34, ids)
        prompts = "\n".join(item["prompt"] for item in manifest["evals"] if item["id"] in {33, 34})
        self.assertIn("口水词", prompts)
        self.assertIn("否定", prompts)

    def test_eval_manifest_is_valid_and_fixture_paths_exist(self):
        manifest = json.loads((ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual("srt-subtitle-translator", manifest["skill_name"])
        self.assertGreaterEqual(len(manifest["evals"]), 30)
        missing = [
            (item["id"], path)
            for item in manifest["evals"]
            for path in item.get("files", [])
            if not (ROOT / path).exists()
        ]
        self.assertEqual([], missing)

    def test_language_profile_file_is_valid_json(self):
        profiles = json.loads(
            (ROOT / "config" / "language_profiles.json").read_text(encoding="utf-8")
        )
        self.assertIn("default", profiles)
        self.assertGreaterEqual(len(profiles), 10)

    def test_skill_routes_simultaneous_interpreting_order(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        style_common = (ROOT / "references" / "style-common.md").read_text(encoding="utf-8")
        style_zh = (ROOT / "references" / "style-zh.md").read_text(encoding="utf-8")
        self.assertIn("同声传译式展开语序", skill)
        self.assertIn("Simultaneous interpreting clause order", style_common)
        self.assertIn("中文同声传译式展开语序", style_zh)

    def test_skill_routes_terminology_locking_and_slash_ban(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        style_common = (ROOT / "references" / "style-common.md").read_text(encoding="utf-8")
        style_zh = (ROOT / "references" / "style-zh.md").read_text(encoding="utf-8")
        self.assertIn("LOCKED", skill)
        self.assertIn("preferred", skill)
        self.assertIn("slash-separated alternatives", skill)
        self.assertIn("LOCKED (刚性锁定)", style_common)
        self.assertIn("preferred (柔性偏好)", style_common)
        self.assertIn("Single final rendering mandate", style_common)
        self.assertIn("严禁输出斜杠备选译法", style_zh)

    def test_skill_routes_asr_repair_boundaries(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        seg = (ROOT / "references" / "segmentation.md").read_text(encoding="utf-8")
        style_common = (ROOT / "references" / "style-common.md").read_text(encoding="utf-8")
        self.assertIn("division of ASR repair", skill)
        self.assertIn("ASR repair boundaries", seg)
        self.assertIn("physiological breaths", seg)
        self.assertIn("Boundaries of ASR repair", style_common)

    def test_skill_routes_display_units_budget(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        reading_load = (ROOT / "references" / "reading-load.md").read_text(encoding="utf-8")
        seg = (ROOT / "references" / "segmentation.md").read_text(encoding="utf-8")
        self.assertIn("Display Units", skill)
        self.assertIn("行级显示单元预算", reading_load)
        self.assertIn("Soft Budget", reading_load)
        self.assertIn("Hard Budget", reading_load)
        self.assertIn("Line-level Display Unit Budget", seg)


if __name__ == "__main__":
    unittest.main()
