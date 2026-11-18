"""Loaded text must remain data, including when it appears in an edit prompt."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MAIN = Path(__file__).resolve().parents[1] / "main.py"


class TerminalSafetyTests(unittest.TestCase):
    def test_edit_prompt_does_not_emit_loaded_control_characters(self):
        """Opening an edit form must not execute terminal escapes or change the stored name."""
        name = "Alice\x1b[2J\x07\n香港"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pim"
            saved = Path(directory) / "saved.pim"
            data = {"next_id": 2, "records": [{"id": 1, "type": "contact",
                    "name": name, "address": "Hong Kong", "mobile": "12345678"}]}
            source.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MAIN)], cwd=directory,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                input="load source\nedit #1\n1\n\nsave saved\nexit\n",
                capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertNotIn("\x1b", result.stdout)
            self.assertNotIn("\x07", result.stdout)
            self.assertIn("Value unchanged.", result.stdout)
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8")), data)

    def test_edit_accepts_unicode_text_and_saves_it(self):
        """Prompt sanitising must not alter the user's replacement text."""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(MAIN)], cwd=directory,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                input="add contact\nAlice\nHong Kong\n12345678\n"
                      "edit #1\n1\n陳小明\nsave saved\nexit\n",
                capture_output=True, text=True, encoding="utf-8", timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((Path(directory) / "saved.pim").read_text(encoding="utf-8"))
            self.assertEqual(data["records"][0]["name"], "陳小明")
