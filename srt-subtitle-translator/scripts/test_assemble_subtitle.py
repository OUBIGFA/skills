# -*- coding: utf-8 -*-
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("assemble_subtitle.py")


class AssembleSubtitleTests(unittest.TestCase):
    def run_assemble(self, extension, parts):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            part_paths = []
            for index, content in enumerate(parts, 1):
                path = root / (f"part{index}.{extension}")
                path.write_text(content, encoding="utf-8")
                part_paths.append(str(path))
            output = root / (f"out.{extension}")
            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), str(output), *part_paths],
                text=True,
                encoding="utf-8",
                capture_output=True,
            )
            output_text = output.read_text(encoding="utf-8") if output.exists() else ""
            return result, output_text

    def test_assembles_srt_parts_without_losing_blocks(self):
        result, output_text = self.run_assemble(
            "srt",
            [
                "1\n00:00:00,000 --> 00:00:01,000\n第一块\n\n",
                "2\n00:00:01,000 --> 00:00:02,000\n第二块\n\n",
            ],
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "1\n00:00:00,000 --> 00:00:01,000\n第一块\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n第二块\n\n",
            output_text,
        )

    def test_assembles_vtt_with_one_header(self):
        result, output_text = self.run_assemble(
            "vtt",
            [
                "WEBVTT\n\n00:00.000 --> 00:01.000\n第一块\n\n",
                "WEBVTT\n\n00:01.000 --> 00:02.000\n第二块\n\n",
            ],
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, output_text.count("WEBVTT"))
        self.assertIn("第二块", output_text)


if __name__ == "__main__":
    unittest.main()
