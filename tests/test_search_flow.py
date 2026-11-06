"""Selections in these tests use the numbered, plain-terminal menus."""

from contextlib import redirect_stdout
from io import StringIO
import unittest
import os
from unittest.mock import patch

from model.demo import DemoModel, DemoServices
from search_flow import build_condition
from terminal_view import Cancelled


class SearchFlowTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, PIM_PLAIN="1"))

    def build(self, *answers):
        output = StringIO()
        with redirect_stdout(output), patch("sys.stdin", StringIO("\n".join(answers) + "\n")):
            try:
                condition = build_condition()
            except EOFError:
                self.fail(f"Search requested another answer:\n{output.getvalue()}")
        return condition, output.getvalue()

    def test_quick_task_search_keeps_alternatives_inside_the_type_filter(self):
        records = DemoModel()
        stamp = "2026-11-05 09:05"
        records.create("task", {"description": "Submit final report", "deadline": stamp})
        records.create("task", {"description": "Revise for exam", "deadline": stamp})
        records.create("event", {"description": "Exam", "start": stamp, "alarm": stamp})
        records.create("task", {"description": "Buy milk", "deadline": stamp})

        condition, output = self.build("2", "Final report | Exam")
        self.assertEqual(condition, ("and", ("type", "task"),
                                     ("or", ("contains", "description", "Final report"),
                                            ("contains", "description", "Exam"))))
        matches = DemoServices(records).search(condition)
        self.assertEqual([record["id"] for record in matches], [1, 2])
        self.assertIn('Searching tasks for "Final report" OR "Exam".', output)

    def test_quick_scopes_cover_each_text_field_and_exclude_times(self):
        records = DemoModel()
        stamp = "2026-11-05 09:05"
        records.create("note", {"text": "Room 2026"})
        records.create("task", {"description": "Buy milk", "deadline": stamp})
        records.create("event", {"description": "Year 2026", "start": stamp, "alarm": stamp})
        records.create("contact", {"name": "Team 2026", "address": "Home", "mobile": "1"})
        records.create("contact", {"name": "Pat", "address": "2026 Main St", "mobile": "2"})
        records.create("contact", {"name": "Jo", "address": "Office", "mobile": "5552026"})
        for scope, expected in (("1", [1, 3, 4, 5, 6]), ("2", []), ("3", [1]),
                                ("4", [3]), ("5", [4, 5, 6])):
            with self.subTest(scope=scope):
                condition, _ = self.build(scope, "2026")
                matches = DemoServices(records).search(condition)
                self.assertEqual([record["id"] for record in matches], expected)

        for scope, expected in (("1", [1, 2, 3, 4, 5, 6]), ("2", [2]), ("3", [1]),
                                ("4", [3]), ("5", [4, 5, 6])):
            with self.subTest(blank_in_scope=scope):
                condition, _ = self.build(scope, "")
                matches = DemoServices(records).search(condition)
                self.assertEqual([record["id"] for record in matches], expected)

    def test_quick_search_retries_empty_alternatives(self):
        for invalid in ("|exam", "exam|", "report | | exam"):
            with self.subTest(invalid=invalid):
                condition, output = self.build("3", invalid, "Final  draft")
                self.assertEqual(condition, ("and", ("type", "note"),
                                             ("contains", "text", "Final  draft")))
                self.assertIn("empty", output.lower())

    def test_cancel_quick_scope_or_keywords(self):
        for answers in (("/cancel",), ("2", "/cancel")):
            with self.subTest(answers=answers), self.assertRaises(Cancelled):
                self.build(*answers)

    def test_advanced_record_type_search(self):
        for option, kind in enumerate(("note", "task", "event", "contact"), 1):
            with self.subTest(kind=kind):
                condition, output = self.build("6", "1", str(option), "1")
                self.assertEqual(condition, ("type", kind))
                self.assertIn(f"type is {kind}", output.lower())

    def test_text_fields_keep_the_search_string_literal(self):
        for option, field in enumerate(("text", "description", "name", "address", "mobile"), 1):
            with self.subTest(field=field):
                condition, _ = self.build("6", "2", str(option), "A | (OR) B", "1")
                self.assertEqual(condition, ("contains", field, "A | (OR) B"))

    def test_time_fields_and_comparisons_use_the_canonical_value(self):
        for field_choice, field in enumerate(("deadline", "start", "alarm"), 1):
            for op_choice, operator in enumerate(("<", "=", ">"), 1):
                with self.subTest(field=field, operator=operator):
                    condition, _ = self.build("6", "3", str(field_choice), str(op_choice),
                                              "2026 11 5", "9 5", "1")
                    self.assertEqual(condition, ("time", field, operator, "2026-11-05 09:05"))

    def test_grouped_or_is_on_the_right_side_of_and(self):
        condition, output = self.build(
            "6",                            # Advanced filters
            "1", "2",                       # Type is Task
            "2", "4",                       # AND a new group
            "2", "2", "report",             # Description contains "report"
            "3", "2", "2", "exam",          # OR Description contains "exam"
            "1", "1",                       # Finish group, then run
        )
        self.assertEqual(condition, ("and", ("type", "task"),
                                     ("or", ("contains", "description", "report"),
                                            ("contains", "description", "exam"))))
        self.assertIn('Type is Task AND (Description contains "report" OR '
                      'Description contains "exam")', output)

    def test_not_applies_to_the_entire_current_condition(self):
        condition, _ = self.build("6", "1", "1", "3", "1", "4", "4", "1")
        self.assertEqual(condition, ("not", ("or", ("type", "note"), ("type", "contact"))))

    def test_cancel_inside_group_aborts_whole_search(self):
        with self.assertRaises(Cancelled):
            self.build("6", "1", "2", "2", "4", "2", "2", "/cancel")
