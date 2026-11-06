import io
import os
import re
import unittest
from contextlib import nullcontext, redirect_stdout
from datetime import date
from unittest.mock import patch

from date_fields import read_date_fields
from terminal_keys import Back, Cancelled
from terminal_view import read_datetime


class DateFieldTests(unittest.TestCase):
    def enter(self, keys):
        output = io.StringIO()
        with redirect_stdout(output):
            result = read_date_fields("Due", iter(keys).__next__)
        visible = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output.getvalue())
        return result, visible

    def test_mask_is_visible_before_typing_and_separators_work(self):
        for value in ("2026 9 5", "2026-09-05"):
            with self.subTest(value=value):
                result, out = self.enter([*value, "enter"])
                self.assertIn("Due date: YYYY-MM-DD", out)
                self.assertIn("Due date: 2026-09-05", out)
                self.assertEqual(result, date(2026, 9, 5))

    def test_empty_enter_and_editing_an_earlier_field(self):
        result, out = self.enter(["enter", "enter", *"2026 8 51", "backspace",
                                  "left", "9", "right", "enter"])
        self.assertNotIn("Invalid", out)
        self.assertEqual(result, date(2026, 9, 5))

    def test_digit_limits_and_letters_keep_date_slots_fixed_width(self):
        result, out = self.enter([*"202699x９ 123y 055z", "enter"])
        self.assertEqual(result, date(2026, 12, 5))
        rows = [row.split("\n")[0] for row in out.split("\r") if row.startswith("Due date: ")]
        self.assertTrue(all(len(row.removeprefix("Due date: ")) == 10 for row in rows))

    def test_single_digits_show_leading_zero_without_advancing_fields(self):
        result, out = self.enter([*"2026 9", "backspace", *"12 5", "enter"])
        self.assertEqual(result, date(2026, 12, 5))
        self.assertIn("Due date: 2026-09-DD", out)
        self.assertIn("Due date: 2026-01-DD", out)
        self.assertIn("Due date: 2026-12-05", out)

    def test_unknown_slash_command_preserves_date_fields(self):
        result, out = self.enter([*"2026 9 5/other", "enter", "enter"])
        self.assertEqual(result, date(2026, 9, 5))
        self.assertIn("Unknown command", out)

    def test_slash_command_backspace_returns_to_date_editing(self):
        result, out = self.enter([*"2026 9 5/", "backspace", "backspace", "7", "enter"])
        self.assertEqual(result, date(2026, 9, 7))

    def test_escape_and_back_command_return_to_previous_step(self):
        for keys in ([*"2026 ", "escape"], [*"2026 9 5/back", "enter"]):
            with self.subTest(keys=keys), self.assertRaises(Back):
                self.enter(keys)

    def test_date_back_propagates_to_calling_form(self):
        with patch("sys.stdin", io.StringIO("/back\n")), redirect_stdout(io.StringIO()):
            with self.assertRaises(Back):
                read_datetime("Due")

    def test_escape_at_time_reopens_populated_date(self):
        keys = iter([*"2026 9 7", "enter", "right", *"10", "enter"])
        responses = iter([Back(), "09:05"])

        def ask_time(prompt):
            answer = next(responses)
            if isinstance(answer, Back):
                raise answer
            return answer

        with (patch("terminal_view.interactive_terminal", return_value=True),
              patch("terminal_view.keyboard", side_effect=lambda: nullcontext(keys.__next__)),
              patch("terminal_view.ask", side_effect=ask_time), redirect_stdout(io.StringIO())):
            self.assertEqual(read_datetime("Due"), "2026-10-07 09:05")

    def test_invalid_day_can_be_replaced_without_retyping_month_or_year(self):
        for value, reason, expected in (("2026 9 31", "September has 30 days", date(2026, 9, 28)),
                                        ("2024 2 30", "February has 29 days", date(2024, 2, 28))):
            with self.subTest(value=value):
                result, out = self.enter([*value, "enter", *"28", "enter", "escape"])
                self.assertEqual(result, expected)
                self.assertIn(reason, out)

    def test_errors_select_first_invalid_field_and_preserve_good_day(self):
        result, out = self.enter([*"0000 13 7", "enter", *"2024", "enter", *"2", "enter",
                                  "escape"])
        self.assertEqual(result, date(2024, 2, 7))

    def test_tty_back_reopens_populated_date_and_allows_month_edit(self):
        keys = iter([*"2026 9 7", "enter", "right", *"10", "enter", "escape"])
        output = io.StringIO()
        with (patch("terminal_view.interactive_terminal", return_value=True),
              patch.dict(os.environ, PIM_PLAIN="1"),
              patch("terminal_view.keyboard", side_effect=lambda: nullcontext(keys.__next__)),
              patch("sys.stdin", io.StringIO("/back\n09:05\n")), redirect_stdout(output)):
            self.assertEqual(read_datetime("Due"), "2026-10-07 09:05")
        self.assertIn("/back", output.getvalue())

    def test_plain_back_shows_previous_date_and_can_keep_or_change_it(self):
        for replacement, expected in (("", "2026-09-07"), ("2024 2 29", "2024-02-29")):
            with self.subTest(replacement=replacement):
                output = io.StringIO()
                data = f"2026 9 7\n/back\n{replacement}\n09:05\n"
                with patch("sys.stdin", io.StringIO(data)), redirect_stdout(output):
                    self.assertEqual(read_datetime("Due"), expected + " 09:05")
                self.assertIn("2026-09-07", output.getvalue())

    def test_plain_invalid_date_allows_slot_repair_or_full_replacement(self):
        for replacement, expected in (("30", "2026-09-30"), ("2024 2 29", "2024-02-29")):
            with self.subTest(replacement=replacement):
                output = io.StringIO()
                data = f"2026 9 31\n{replacement}\n09:05\n"
                with patch("sys.stdin", io.StringIO(data)), redirect_stdout(output):
                    self.assertEqual(read_datetime("Due"), expected + " 09:05")
                self.assertIn("September has 30 days", output.getvalue())

    def test_plain_incomplete_date_requests_full_replacement(self):
        output = io.StringIO()
        data = "nonsense\n2026 9 30\n09:05\n"
        with patch("sys.stdin", io.StringIO(data)), redirect_stdout(output):
            self.assertEqual(read_datetime("Due"), "2026-09-30 09:05")
        self.assertIn("full date", output.getvalue())

    def test_plain_correction_prompt_does_not_echo_terminal_control_sequences(self):
        data = "2026 9 \x1b[2J\n30\n09:05\n"
        with patch("sys.stdin", io.StringIO(data)), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(read_datetime("Due"), "2026-09-30 09:05")
        self.assertNotIn("\x1b", output.getvalue())

    def test_can_cancel_from_reopened_year_with_other_fields_populated(self):
        keys = iter([*"2026 9 7", "enter", *"/cancel", "enter"])
        with (patch("terminal_view.interactive_terminal", return_value=True),
              patch.dict(os.environ, PIM_PLAIN="0"),
              patch("terminal_view.keyboard", side_effect=lambda: nullcontext(keys.__next__)),
              patch("sys.stdin", io.StringIO("/back\n")), redirect_stdout(io.StringIO()),
              self.assertRaises(Cancelled)):
            read_datetime("Due")

    def test_typed_cancel_from_partial_date(self):
        for keys in ([*"2026 /cancel", "enter"], [*"2026 /cancel", "left", "enter"]):
            with self.subTest(keys=keys), self.assertRaises(Cancelled):
                self.enter(keys)

    @unittest.skipUnless(os.name == "posix", "POSIX escape sequence input")
    def test_pasted_date_ignores_terminal_paste_markers(self):
        from terminal_keys import _posix_key

        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        os.write(writer, b"\x1b[200~2026-9-5\x1b[201~\r")
        os.close(writer)
        with redirect_stdout(io.StringIO()):
            result = read_date_fields("Due", lambda: _posix_key(reader))
        self.assertEqual(result, date(2026, 9, 5))
