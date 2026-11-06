import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MAIN = Path(__file__).resolve().parents[1] / "main.py"


def session(directory, *lines):
    result = subprocess.run(
        [sys.executable, str(MAIN)], cwd=directory, input="\n".join(lines) + "\n",
        text=True, capture_output=True, timeout=10, env={**os.environ, "PIM_PLAIN": "1"},
    )
    if result.returncode:
        raise AssertionError(f"CLI exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


class TerminalJourneys(unittest.TestCase):
    def test_direct_search_opens_only_match_and_save_on_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            output = session(folder, "add note", "Final Report", "/done",
                             "search Final Report", "exit", "2", "report copy")
            self.assertIn('Searching all records for "Final Report".', output)
            self.assertNotIn("Select a record", output)
            self.assertIn("To change this note, type edit 1.", output)
            reopened = session(folder, "load", "report copy", "view 1", "exit")
            self.assertIn("Text: Final Report", reopened)

    def test_cancel_or_failed_save_on_exit_keeps_work(self):
        with tempfile.TemporaryDirectory() as folder:
            output = session(folder, "add note", "Keep me", "/done",
                             "exit", "2", "/cancel",
                             "exit", "2", "missing/folder/file",
                             "view 1", "exit", "2", "kept")
            self.assertIn("Text: Keep me", output)
            self.assertTrue(Path(folder, "kept.pim").exists())

    def test_excessively_nested_file_keeps_unsaved_session_open(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "damaged.pim").write_text("[" * 10000 + "0" + "]" * 10000)
            output = session(folder,
                "add note", "Keep this note", "/done",
                "load", "damaged", "Y", "view 1", "exit", "1",
                "save", "recovered", "exit")
            self.assertIn("Your current records are unchanged.", output)
            self.assertIn("Text: Keep this note", output)
            self.assertIn("Session kept open.", output)
            reopened = session(folder, "load", "recovered", "view 1", "exit")
            self.assertIn("Text: Keep this note", reopened)

    def test_search_and_update_one_of_two_then_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            output = session(folder,
                "add task", "Submit report", "2026 11 16", "9 5",
                "add task", "Submit report", "2026 11 16", "9 5",
                "search", "2", "report | exam", "2",
                "edit 2", "2", "2026 11 17", "10 30",
                "save", "demo with spaces", "exit")
            self.assertIn("To change this task, type edit 2.", output)
            self.assertIn("Updated task #2.", output)
            self.assertTrue((Path(folder) / "demo with spaces.pim").is_file())
            reopened = session(folder, "load", "demo with spaces", "view all", "exit")
            self.assertRegex(reopened, r"(?s)#1  Task.*?Deadline: 2026-11-16 09:05.*?"
                                       r"#2  Task.*?Deadline: 2026-11-17 10:30")

    def test_cancel_failed_load_and_overwrite_preserve_data(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "broken.pim").write_text("{", encoding="utf-8")
            output = session(folder,
                "add note", "original", "", "second line", "/done", "save", "original",
                "edit 1", "1", "changed", "/done", "save", "original", "N",
                "load", "broken", "Y", "view 1", "exit", "1",
                "load", "original", "Y", "view 1", "exit")
            self.assertIn("Save cancelled.", output)
            self.assertIn("Your current records are unchanged.", output)
            self.assertIn("Text: changed", output)
            self.assertIn("Type save to keep your changes.", output)
            self.assertIn("Text: original\n\nsecond line", output)

    def test_event_contact_empty_search_and_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            output = session(folder,
                "search", "add event", "Demo", "2026 11 20", "19 0", "2026 11 19", "18 0",
                "add contact", "Alex", "Flat A, 5 Main Road", "+852 01234567",
                "search", "3", "",
                "view 2", "delete 2", "oops", "y", "view 2", "exit", "3")
            for text in ("No records yet.", "Alarm time: 2026-11-19 18:00",
                         "+852 01234567", "No matches.", "Please type Y or N.",
                         "Deleted contact #2.", "No record with ID 2."):
                self.assertIn(text, output)
