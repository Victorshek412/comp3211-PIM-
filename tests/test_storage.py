"""Unit tests for model.storage (Part D)."""
import json
import tempfile
import unittest
from pathlib import Path

from model.record_manager import RecordManager
from model.storage import load_records, save_records


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.dir = Path(self._dir.name)
        self.m = RecordManager()
        self.m.create("note", {"text": "héllo 你好"})
        self.m.create("task", {"description": "t", "deadline": "2026-11-20 20:00"})

    def test_save_then_load_restores_records_and_ids(self):  # US10, US11
        path = self.dir / "a.pim"
        save_records(self.m, path)
        other = RecordManager()
        load_records(other, path)
        self.assertEqual(other.list_records(), self.m.list_records())
        self.assertEqual(other.create("note", {"text": "x"}), 3)

    def test_file_is_utf8_json_and_no_temp_files_left(self):
        """Saved file is UTF-8 JSON with the next_id, and no temporary file remains."""
        path = self.dir / "a.pim"
        save_records(self.m, path)
        self.assertIn("你好", path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["next_id"], 3)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["a.pim"])

    def test_empty_collection_can_be_saved_and_loaded(self):
        """An empty collection saves, and loading it replaces existing records with none."""
        empty = RecordManager()
        path = self.dir / "empty.pim"
        save_records(empty, path)
        self.m.replace_snapshot({"next_id": 1, "records": []})
        self.m.create("note", {"text": "x"})
        load_records(self.m, path)
        self.assertEqual(self.m.list_records(), [])

    def test_extension_must_be_pim(self):
        """Saving or loading a name not ending in .pim raises ValueError."""
        for name in ("a.txt", "a", "a.pim.bak"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    save_records(self.m, self.dir / name)
                with self.assertRaises(ValueError):
                    load_records(self.m, self.dir / name)

    def test_extension_check_ignores_case(self):
        """A.PIM is accepted and its records load back unchanged."""
        save_records(self.m, self.dir / "A.PIM")
        other = RecordManager()
        load_records(other, self.dir / "A.PIM")
        self.assertEqual(other.list_records(), self.m.list_records())

    def test_failed_load_keeps_current_records(self):  # existing data stays safe
        before = self.m.list_records()
        contents = {"missing.pim": None, "broken.pim": "{not json", "empty.pim": "",
                    "list.pim": "[1, 2]", "badrec.pim": '{"next_id": 2, "records": [{"id": 1}]}',
                    "deep.pim": "[" * 100000, "latin.pim": b"\xff\xfe\x00"}
        for name, text in contents.items():
            path = self.dir / name
            if isinstance(text, bytes):
                path.write_bytes(text)
            elif text is not None:
                path.write_text(text, encoding="utf-8")
            with self.subTest(name=name):
                with self.assertRaises((OSError, ValueError)):
                    load_records(self.m, path)
                self.assertEqual(self.m.list_records(), before)

    def test_save_overwrites_existing_file(self):
        """Saving over an existing file replaces its contents with the current records."""
        path = self.dir / "a.pim"
        path.write_text("old", encoding="utf-8")
        save_records(self.m, path)
        other = RecordManager()
        load_records(other, path)
        self.assertEqual(other.list_records(), self.m.list_records())

    def test_failed_save_leaves_original_and_no_temp_file(self):
        """A failure while writing keeps the original file and leaves no temporary file."""
        path = self.dir / "a.pim"
        save_records(self.m, path)
        original = path.read_text(encoding="utf-8")
        self.m.snapshot = lambda: {"next_id": 9, "records": [object()]}  # not JSON-serialisable
        with self.assertRaises(TypeError):
            save_records(self.m, path)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["a.pim"])


if __name__ == "__main__":
    unittest.main()
