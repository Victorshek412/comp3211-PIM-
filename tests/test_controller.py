import io
import unittest
import os
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from controller import Controller
from terminal_view import Cancelled


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, PIM_PLAIN="1"))
        self.records = Mock()
        self.search = Mock()
        self.storage = Mock()
        self.cli = Controller(self.records, self.search, self.storage)
        self.task = dict(id=37, type="task", description="Report", deadline="2026-11-16 09:05")
        self.records.get.return_value = self.task
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))

    def test_add_uses_returned_id_and_validated_time(self):
        with patch("builtins.input", side_effect=["Report", "2026 11 16", "9 5"]):
            self.records.create.return_value = 37
            self.cli.execute("add task")
        self.records.create.assert_called_once_with("task", {
            "description": "Report", "deadline": "2026-11-16 09:05"})
        self.assertIn("Created task #37", self.output.getvalue())
        self.assertIn("2026-11-16 09:05", self.output.getvalue())
        self.assertTrue(self.cli.dirty)

    def test_cancel_add_never_calls_model(self):
        with patch("builtins.input", side_effect=["Report", "/cancel"]):
            with self.assertRaises(Cancelled):
                self.cli.execute("add task")
        self.records.create.assert_not_called()
        self.assertFalse(self.cli.dirty)

    def test_select_field_edits_only_that_field_on_original_id(self):
        with patch("builtins.input", side_effect=["2", "2026 11 17", "10 0"]):
            self.cli.execute("edit 37")
        self.records.update.assert_called_once_with(37, "deadline", "2026-11-17 10:00")
        self.assertTrue(self.cli.dirty)

    def test_delete_requires_yes(self):
        with patch("builtins.input", side_effect=["", "N"]):
            self.cli.execute("delete 37")
        self.records.delete.assert_not_called()
        self.assertFalse(self.cli.dirty)

    def test_single_match_opens_without_prompting_for_an_id(self):
        condition = ("contains", "description", "Report")
        self.records.list_records.return_value = [self.task]
        self.search.return_value = [self.task]
        with patch("controller.build_condition", return_value=condition):
            with patch("builtins.input", side_effect=AssertionError("Unexpected ID prompt")):
                self.cli.execute("search")
        self.search.assert_called_once_with(condition)
        self.assertIn("edit 37", self.output.getvalue())

    def test_palette_dispatches_to_existing_edit_flow(self):
        with patch("controller.command_palette", return_value="edit") as palette:
            with patch.object(self.cli, "target", return_value=self.task):
                with patch.object(self.cli, "edit") as edit:
                    self.cli.execute("?")
        self.assertIn(("edit", "Edit record"), palette.call_args.args[0])
        edit.assert_called_once_with(self.task)

    def test_failed_load_preserves_dirty_flag(self):
        self.cli.dirty = True
        self.storage.load.side_effect = ValueError("bad content")
        with patch("builtins.input", side_effect=["bad file", "Y"]):
            self.cli.execute("load")
        self.storage.load.assert_called_once()
        self.assertTrue(self.cli.dirty)
        self.assertIn("Your current records are unchanged.", self.output.getvalue())

    def test_decline_discard_on_exit(self):
        self.cli.dirty = True
        with patch("builtins.input", return_value="1"):
            self.assertTrue(self.cli.execute("exit"))
        self.assertTrue(self.cli.dirty)

    def test_view_all_outputs_all_fields_in_id_order(self):
        note = dict(id=5, type="note", text="first\nsecond")
        self.records.list_records.return_value = [self.task, note]
        self.cli.execute("view all")
        output = self.output.getvalue()
        self.assertLess(output.index("#5"), output.index("#37"))
        for value in ("first", "second", "Report", "2026-11-16 09:05"):
            self.assertIn(value, output)
