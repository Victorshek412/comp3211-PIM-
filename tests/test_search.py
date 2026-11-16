"""Unit tests for model.search (Part B)."""
import unittest

from model.record_manager import RecordManager
from model.search import search_records, validate_condition


def ids(rows):
    return [r["id"] for r in rows]


class SearchTests(unittest.TestCase):
    def setUp(self):
        m = RecordManager()
        m.create("note", {"text": "Buy Milk and eggs"})                                   # 1
        m.create("task", {"description": "Submit report", "deadline": "2026-11-20 20:00"})  # 2
        m.create("event", {"description": "Report meeting", "start_time": "2026-11-18 09:00",
                           "alarm": "2026-11-18 08:30"})                                  # 3
        m.create("contact", {"name": "Alice Chan", "address": "PolyU", "mobile": "91234567"})  # 4
        self.rows = m.list_records()

    def run_search(self, cond):
        return ids(search_records(self.rows, cond))

    def test_type(self):  # search by record type
        self.assertEqual(self.run_search(("type", "task")), [2])

    def test_contains_case_insensitive(self):  # text match ignores case
        self.assertEqual(self.run_search(("contains", "text", "MILK")), [1])

    def test_contains_description_spans_types(self):  # description exists in task and event
        self.assertEqual(self.run_search(("contains", "description", "report")), [2, 3])

    def test_contains_missing_field_is_false(self):  # field not in record -> no match
        self.assertEqual(self.run_search(("contains", "mobile", "9")), [4])

    def test_time_before_after_equal(self):  # < > = on a time field
        self.assertEqual(self.run_search(("time", "start_time", "<", "2026-11-19 00:00")), [3])
        self.assertEqual(self.run_search(("time", "deadline", ">", "2026-11-19 00:00")), [2])
        self.assertEqual(self.run_search(("time", "alarm", "=", "2026-11-18 08:30")), [3])
        self.assertEqual(self.run_search(("time", "alarm", "=", "2026-11-18 08:31")), [])

    def test_and_or_not(self):  # logical connectors
        report = ("contains", "description", "report")
        self.assertEqual(self.run_search(("and", ("type", "task"), report)), [2])
        self.assertEqual(self.run_search(("or", ("type", "note"), ("type", "contact"))), [1, 4])
        self.assertEqual(self.run_search(("not", report)), [1, 4])

    def test_no_match_returns_empty_list(self):
        """A search with no hits returns an empty list."""
        self.assertEqual(self.run_search(("contains", "text", "zzz")), [])

    def test_invalid_conditions_raise(self):  # malformed input is rejected, not ignored
        bad = [None, (), ("type", "memo"), ("contains", "deadline", "x"),
               ("time", "start_time", "~", "2026-01-01 00:00"),
               ("time", "start_time", "<", "2026-13-01 00:00"),
               ("and", ("type", "note")), ("not",), ("xor", ("type", "note"), ("type", "task"))]
        for cond in bad:
            with self.subTest(cond=cond):
                with self.assertRaises(ValueError):
                    validate_condition(cond)
                with self.assertRaises(ValueError):
                    search_records(self.rows, cond)

    def test_search_time_must_use_the_same_format_as_records(self):
        """A search time is validated exactly like a record time (YYYY-MM-DD HH:MM)."""
        for loose in ("2026-1-5 9:5", "2026-11-20", "2026-11-20T20:00", " 2026-11-20 20:00"):
            with self.subTest(time=loose), self.assertRaises(ValueError):
                validate_condition(("time", "deadline", "<", loose))


if __name__ == "__main__":
    unittest.main()
