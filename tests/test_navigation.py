import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from controller import Controller
from model.demo import DemoModel, DemoServices


class NavigationTests(unittest.TestCase):
    def run_command(self, command, answers):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO("\n".join(answers) + "\n")), redirect_stdout(output):
            result = self.cli.execute(command)
        return result, output.getvalue()

    def setUp(self):
        self.enterContext(patch.dict(os.environ, PIM_PLAIN="1"))
        self.records = DemoModel()
        self.services = DemoServices(self.records)
        self.cli = Controller(self.records, self.services.search, self.services)

    def test_back_from_description_reopens_edit_field_menu(self):
        self.records.create("task", {"description": "Report", "deadline": "2026-09-05 09:05"})
        _, output = self.run_command("edit 1", ["1", "/back", "2", "2026 9 6", "9:05"])
        self.assertEqual(output.count("choose one field"), 2)
        self.assertEqual(self.records.get(1)["description"], "Report")
        self.assertEqual(self.records.get(1)["deadline"], "2026-09-06 09:05")

    def test_add_back_to_description_keeps_previous_value(self):
        self.run_command("add task", ["Report", "/back", "", "2026 9 5", "9:05"])
        self.assertEqual(self.records.get(1)["description"], "Report")

    def test_edit_back_reopens_record_picker(self):
        self.records.create("note", {"text": "One"})
        self.records.create("note", {"text": "Two"})
        self.run_command("edit", ["1", "/back", "2", "1", "Changed", "/done"])
        self.assertEqual(self.records.get(1)["text"], "One")
        self.assertEqual(self.records.get(2)["text"], "Changed")

    def test_palette_back_from_command_returns_to_palette(self):
        _, output = self.run_command("?", ["add", "add task", "/back", "help"])
        self.assertIn("Commands", output)
        self.assertEqual(self.records.list_records(), [])

    def test_search_back_from_keywords_returns_to_scopes(self):
        self.records.create("note", {"text": "Report"})
        _, output = self.run_command("search", ["2", "/back", "3", "Report"])
        self.assertIn("Note", output)

    def test_advanced_search_back_moves_one_prompt(self):
        from search_flow import build_condition
        answers = ["6", "2", "2", "/back", "1", "Report", "1"]
        with patch("sys.stdin", io.StringIO("\n".join(answers) + "\n")), redirect_stdout(io.StringIO()):
            result = build_condition()
        self.assertEqual(result, ("contains", "text", "Report"))
