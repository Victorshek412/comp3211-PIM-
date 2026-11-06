import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model.demo import DemoModel, DemoServices


class DemoModelTests(unittest.TestCase):
    def setUp(self):
        self.model = DemoModel()
        self.services = DemoServices(self.model)

    def task(self, description="Report", deadline="2026-11-20 20:00"):
        return self.model.create("task", {"description": description, "deadline": deadline})

    def test_same_name_tasks_can_be_changed_and_deleted_independently(self):
        first = self.task()
        second = self.task()
        self.assertNotEqual(first, second)
        self.model.update(second, "deadline", "2026-12-01 10:05")
        self.assertEqual(self.model.get(first)["deadline"], "2026-11-20 20:00")
        self.assertEqual(self.model.get(second)["deadline"], "2026-12-01 10:05")
        self.model.delete(first)
        with self.assertRaises(KeyError):
            self.model.get(first)
        self.assertEqual(self.model.list_records(), [self.model.get(second)])

    def test_field_validation_preserves_existing_records_and_id_counter(self):
        record_id = self.task()
        for fields in (
            {"description": "No deadline"},
            {"description": "   ", "deadline": "2026-11-20 20:00"},
            {"description": "Invalid day", "deadline": "2026-02-29 00:00"},
            {"description": "Noncanonical", "deadline": "2026-11-20T20:00"},
            {"description": "Extra", "deadline": "2026-11-20 20:00", "id": 12},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.model.create("task", fields)
        for field, value in (("deadline", "bad"), ("id", "2"), ("start", "unexpected")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.model.update(record_id, field, value)
        self.assertEqual(self.model.get(record_id)["deadline"], "2026-11-20 20:00")
        self.assertEqual(self.task(), record_id + 1)

    def test_nested_search_returns_matching_records_and_distinguishes_field_types(self):
        report = self.task("Report")
        exam = self.task("EXAM")
        self.task("Other")
        event = self.model.create("event", {"description": "Exam", "start": "2026-11-05 10:00",
                                            "alarm": "2026-11-05 10:05"})
        condition = ("and", ("type", "task"), ("or", ("contains", "description", "REPORT"),
                                                   ("contains", "description", "exam")))
        self.assertEqual(self.services.search(condition), [self.model.get(report), self.model.get(exam)])
        self.assertEqual(self.services.search(("not", ("type", "task"))), [self.model.get(event)])
        for operator, time in (("<", "2026-11-05 10:01"), ("=", "2026-11-05 10:00"),
                               (">", "2026-11-05 09:59")):
            self.assertEqual(self.services.search(("time", "start", operator, time)), [self.model.get(event)])
        self.assertEqual(self.services.search(("time", "start", "<", "2026-11-05 10:00")), [])

    def test_round_trip_preserves_text_phone_ids_and_next_id_after_deletion(self):
        note = self.model.create("note", {"text": "第一段\n\n second paragraph "})
        contact = self.model.create("contact", {"name": "A", "address": "Hong Kong", "mobile": "00123"})
        deleted = self.task()
        self.model.delete(deleted)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "my records.pim")
            self.services.save(path)
            restored = DemoModel()
            DemoServices(restored).load(path)
        self.assertEqual(restored.get(note)["text"], "第一段\n\n second paragraph ")
        self.assertEqual(restored.get(contact)["mobile"], "00123")
        self.assertEqual(restored.create("note", {"text": "Next"}), deleted + 1)

    def test_failed_load_preserves_records_and_next_id(self):
        first = self.task()
        self.model.delete(self.task())
        original = self.model.get(first)
        for data in (
            "broken json", "[]", '{"records":[]}',
            json.dumps({"next_id": 3, "records": [original, original]}),
            json.dumps({"next_id": 1, "records": [original]}),
            json.dumps({"next_id": True, "records": []}),
            json.dumps({"next_id": 4, "records": [original, {"id": 2, "type": "note"}]}),
        ):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as folder:
                path = Path(folder, "bad.pim")
                path.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.services.load(path)
                self.assertEqual(self.model.list_records(), [original])
        self.assertEqual(self.task(), first + 2)

    def test_failed_save_keeps_previous_file_and_cleans_up_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "original.pim")
            self.task("First")
            self.services.save(path)
            previous = path.read_bytes()
            self.task("Second")
            with patch("os.replace", side_effect=OSError("replace failed")), self.assertRaises(OSError):
                self.services.save(path)
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_services_use_an_independently_supplied_record_manager(self):
        class TeamRecords:
            def __init__(self, state):
                self.state = state

            def list_records(self):
                return self.state["records"]

            def snapshot(self):
                return self.state

            def replace_snapshot(self, data):
                self.state = data

        record = {"id": 37, "type": "note", "text": "Example"}
        original = {"next_id": 42, "records": [record]}
        records = TeamRecords(original)
        services = DemoServices(records)
        self.assertEqual(services.search(("contains", "text", "EXAMPLE")), [record])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "team.pim")
            services.save(path)
            records.replace_snapshot({"next_id": 1, "records": []})
            self.assertEqual(services.search(("type", "note")), [])
            services.load(path)
        self.assertEqual(records.snapshot(), original)

    def test_model_owns_its_records_after_snapshot_replacement(self):
        state = {"next_id": 7, "records": [{"id": 3, "type": "note", "text": "Original"}]}
        self.model.replace_snapshot(state)
        state["records"][0]["text"] = "External mutation"
        self.model.snapshot()["records"][0]["text"] = "Changed copy"
        self.assertEqual(self.model.get(3)["text"], "Original")
        self.assertEqual(self.task(), 7)

    def test_deeply_nested_json_is_a_load_error_and_keeps_records(self):
        record_id = self.task()
        depth = 10000
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "damaged.pim")
            path.write_text("[" * depth + "0" + "]" * depth)
            with self.assertRaises(ValueError):
                self.services.load(path)
        self.assertEqual(self.model.get(record_id)["description"], "Report")
