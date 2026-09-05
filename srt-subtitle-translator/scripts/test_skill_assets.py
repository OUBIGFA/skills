# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillAssetTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
