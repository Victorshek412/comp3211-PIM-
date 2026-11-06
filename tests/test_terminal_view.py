import io
import os
import select
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import terminal_keys
import terminal_view as view


class PromptTests(unittest.TestCase):
    def session(self, lines):
        self.enterContext(patch("sys.stdin", io.StringIO(lines)))
        return self.enterContext(redirect_stdout(io.StringIO()))

    def test_ask_preserves_spaces_and_cancels_on_a_whole_line(self):
        self.session("  /cancel trip  \n  /cancel  \n")
        self.assertEqual(view.ask("> "), "  /cancel trip  ")
        with self.assertRaises(view.Cancelled):
            view.ask("> ")

    def test_plain_record_menu_uses_stable_ids_and_sanitizes_labels(self):
        output = self.session("2\n37\nnext\n")
        self.assertEqual(view.choose("Records", [(12, "Same"), (37, "Same\x1b[2J\n")]), 37)
        self.assertIn("#37", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())
        self.assertEqual(view.ask("> "), "next")

    def test_plain_field_menu_returns_key_for_the_option_number(self):
        self.session("3\n2\nnext\n")
        self.assertEqual(view.choose("Fields", [("text", "Text"), ("due", "Deadline")]), "due")
        self.assertEqual(view.ask("> "), "next")

    def test_explicit_plain_mode_works_on_a_tty(self):
        output = self.session("2\n")
        self.enterContext(patch.object(output, "isatty", return_value=True))
        self.enterContext(patch.object(sys.stdin, "isatty", return_value=True))
        self.enterContext(patch.dict(os.environ, {"PIM_PLAIN": "1", "TERM": "xterm"}))
        self.assertEqual(view.choose("Fields", [("text", "Text"), ("due", "Deadline")]), "due")
        self.assertNotIn("\x1b", output.getvalue())

    def test_plain_palette_filters_labels_then_accepts_a_listed_number(self):
        output = self.session("unknown\nrecord\n2\n")
        actions = [("open", "Open a record"), ("quit", "Leave"), ("make", "New record")]
        self.assertEqual(view.command_palette(actions), "make")
        self.assertIn("No matching", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

    def test_plain_menus_offer_back_without_changing_option_numbers(self):
        for action, args, answer in [
            (view.choose, ("Fields", [("name", "Name")]), "0"),
            (view.choose, ("Fields", [("name", "Name")]), "/back"),
            (view.confirm, ("Delete?",), "0"),
            (view.confirm, ("Delete?",), "/back"),
            (view.command_palette, ([("edit", "Edit record")],), "0"),
            (view.command_palette, ([("edit", "Edit record")],), "/back"),
        ]:
            with self.subTest(action=action.__name__), patch("sys.stdin", io.StringIO(answer + "\n")):
                with redirect_stdout(io.StringIO()) as output, self.assertRaises(view.Back):
                    action(*args)
                self.assertIn("Back", output.getvalue())

    def test_confirmation_requires_a_single_y_or_n(self):
        output = self.session("\nyes\nN\n y \n")
        self.assertFalse(view.confirm("Delete?"))
        self.assertTrue(view.confirm("Delete?"))
        self.assertEqual(output.getvalue().count("Please type Y or N."), 1)

    def test_text_reprompts_for_empty_input_and_preserves_phone_prefix(self):
        self.session("  \n+852 00123456\n")
        self.assertEqual(view.read_text("Mobile"), "+852 00123456")

    def test_note_preserves_paragraphs_and_rejects_a_blank_note(self):
        output = self.session("  \n/done\nFirst\n\n  Second  \n/done\n")
        self.assertEqual(view.read_note(), "First\n\n  Second  ")
        self.assertIn("/cancel", output.getvalue())
        self.assertIn("/done", output.getvalue())

    def test_blank_required_inputs_repeat_prompts_quietly(self):
        output = self.session("\n1\n\nAlex\n\n2026 9 5\n\n9 5\n")
        self.assertEqual(view.choose("Fields", [("name", "Name")]), "name")
        self.assertEqual(view.read_text("Name"), "Alex")
        self.assertEqual(view.read_datetime("Alarm"), "2026-09-05 09:05")
        transcript = output.getvalue()
        for prompt in ("Enter a listed option number", "Name: ", "Alarm date", "Alarm time"):
            self.assertEqual(transcript.count(prompt), 2, transcript)
        for error in ("Please enter", "cannot be blank", "Invalid entry"):
            self.assertNotIn(error, transcript)

    def test_due_date_offers_a_way_back(self):
        output = self.session("/cancel\n")
        with self.assertRaises(view.Cancelled):
            view.read_datetime("Due")
        self.assertIn("/cancel", output.getvalue())

    def test_date_and_time_retry_only_the_incorrect_part(self):
        self.session("2023 2 29\n2024 2 29\n24 00\nwrong\n9 5\n")
        self.assertEqual(view.read_datetime("Due"), "2024-02-29 09:05")

    def test_each_prompt_propagates_cancellation(self):
        for action, args, lines in [
            (view.choose, ("Fields", [("a", "A")]), "/cancel\n"),
            (view.confirm, ("Delete?",), "/cancel\n"),
            (view.read_note, (), "discard this\n/cancel\n"),
            (view.read_datetime, ("Due",), "2024 2 29\n/cancel\n"),
        ]:
            with self.subTest(action=action.__name__), patch("sys.stdin", io.StringIO(lines)):
                with redirect_stdout(io.StringIO()), self.assertRaises(view.Cancelled):
                    action(*args)

    def test_windows_console_keys(self):
        keys = iter(["\x00", "H", "\xe0", "P", "\r", "\x1b", "\xe0", "M"])
        console = SimpleNamespace(getwch=keys.__next__)
        with patch.dict(sys.modules, {"msvcrt": console}):
            self.assertEqual([terminal_keys._windows_key() for _ in range(5)],
                             ["up", "down", "enter", "escape", "right"])


@unittest.skipUnless(os.name == "posix", "requires a POSIX pseudo-terminal")
class ArrowMenuTests(unittest.TestCase):
    def run_menu(self, keys, title="Arrow test", width=80, height=24, ready=b"Two",
                 confirmation=False, action=None):
        import termios

        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        original = termios.tcgetattr(slave)
        action = action or ("view.confirm('Delete?')" if confirmation else
                  f"view.choose({title!r}, [(12, 'One'), (37, 'Two')])")
        script = (
            "import terminal_view as view\n"
            "try:\n"
            f" print('RESULT', {action})\n"
            "except view.Back:\n"
            " print('BACK')\n"
            "except (view.Cancelled, KeyboardInterrupt):\n"
            " print('CANCELLED')\n"
        )
        env = {**os.environ, "TERM": "xterm", "PIM_PLAIN": "0",
               "COLUMNS": str(width), "LINES": str(height)}
        with subprocess.Popen(
            [sys.executable, "-c", script], stdin=slave, stdout=slave,
            stderr=subprocess.STDOUT, env=env, cwd=Path(__file__).resolve().parents[1],
        ) as child:
            try:
                output = bytearray()
                deadline = time.monotonic() + 5
                while ready not in output:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                        self.fail(f"Menu failed to appear: {output!r}")
                    output.extend(os.read(master, 4096))
                os.write(master, keys)
                # Keep draining redraws while libedit restores the pseudo-terminal.
                while child.poll() is None:
                    if time.monotonic() >= deadline:
                        self.fail(f"Menu did not finish: {output!r}")
                    if select.select([master], [], [], 0.05)[0]:
                        output.extend(os.read(master, 4096))
                while select.select([master], [], [], 0)[0]:
                    output.extend(os.read(master, 4096))
            finally:
                child.kill()
        self.assertEqual(child.returncode, 0, output)
        restored = termios.tcgetattr(slave)
        # macOS sets the kernel's PENDIN state when canonical input resumes.
        pending = getattr(termios, "PENDIN", 0)
        restored[3] &= ~pending
        original[3] &= ~pending
        self.assertEqual(restored, original)
        return output

    def test_arrows_and_enter_select_the_pointed_record(self):
        output = self.run_menu(b"\x1b[B\x1b[A\x1b[B\r")
        self.assertIn(b"RESULT 37", output)
        row = b"> #37  Two"
        self.assertIn(b"\x1b[7m" + row.ljust(79) + b"\x1b[0m", output)

    def test_short_menus_redraw_inline_and_select_a_typed_id(self):
        output = self.run_menu(b"37\r")
        self.assertIn(b"RESULT 37", output)
        for screen_switch in (b"\x1b[?1049h", b"\x1b[H", b"\x1b[2J"):
            self.assertNotIn(screen_switch, output)

    def test_menu_is_erased_after_selection_or_back(self):
        for keys, result in [(b"37\r", b"RESULT 37"), (b"0\r", b"BACK"),
                             (b"\x1b", b"BACK"), (b"\x03", b"CANCELLED")]:
            with self.subTest(keys=keys):
                output = self.run_menu(keys)
                self.assertIn(b"0  Back", output)
                self.assertEqual(output.rsplit(b"\x1b[J", 1)[1], result + b"\r\n")

    def test_back_remains_visible_and_selectable_after_filtering(self):
        action = "view.command_palette([('edit', 'Edit record'), ('exit', 'Exit')])"
        output = self.run_menu(b"zzz\x1b[B\r", action=action, ready=b"Exit")
        self.assertIn(b"No matching commands.", output)
        self.assertIn(b"> Back", output)
        self.assertEqual(output.rsplit(b"\x1b[J", 1)[1], b"BACK\r\n")

    def test_confirmation_back_row_and_hotkey(self):
        for keys in (b"0\r", b"\x1b[B\x1b[B\x1b[B\r"):
            with self.subTest(keys=keys):
                output = self.run_menu(keys, confirmation=True, ready=b"Yes")
                self.assertIn(b"Back", output)
                self.assertEqual(output.rsplit(b"\x1b[J", 1)[1], b"BACK\r\n")

    def test_unknown_number_cannot_submit_the_previous_selection(self):
        output = self.run_menu(b"9\r\x7f37\r")
        self.assertIn(b"RESULT 37", output)

    def test_number_selects_an_option_outside_the_visible_rows(self):
        action = "view.choose('Fields', [(f'field{i}', f'Field {i}') for i in range(1, 30)])"
        output = self.run_menu(b"24\r", action=action, height=5, ready=b"Field 1")
        self.assertIn(b"> 24  Field 24", output)
        self.assertIn(b"RESULT field24", output)

    def test_palette_filters_as_you_type_and_arrows_select_within_matches(self):
        action = "view.command_palette([('edit', 'Change'), ('exit', 'Leave'), ('add', 'Create')])"
        output = self.run_menu(b"Ez\r\x7fx\r", action=action, ready=b"Create")
        self.assertIn(b"No matching", output)
        self.assertIn(b"RESULT exit", output)
        output = self.run_menu(b"e\x1b[B\r", action=action, ready=b"Create")
        self.assertIn(b"RESULT exit", output)
        self.assertIn(b"BACK", self.run_menu(b"\x1b", action=action, ready=b"Create"))

    def test_long_filter_can_be_edited_on_a_narrow_screen(self):
        action = "view.command_palette([('view', 'View record'), ('exit', 'Exit')])"
        keys = b"x" * 50 + b"\x7f" * 50 + b"exit\r"
        output = self.run_menu(keys, action=action, width=32, height=5, ready=b"View record")
        self.assertIn(b"RESULT exit", output)
        self.assertNotIn(b"Enter a command, number", output)
        self.assertNotIn(b"view  View record", output)

    def test_arrow_confirmation_needs_a_deliberate_answer(self):
        cases = ((b"\r\r\x1b[B\r", b"False"), (b"\x1b[B\x1b[B\r", b"True"),
                 (b"y\r", b"True"), (b"n\r", b"False"))
        for keys, expected in cases:
            with self.subTest(keys=keys):
                output = self.run_menu(keys, confirmation=True, ready=b"Yes")
                self.assertIn(b"RESULT " + expected, output)
        self.assertIn(b"BACK", self.run_menu(b"\x1b", confirmation=True, ready=b"Yes"))

    def test_escape_goes_back_and_restores_terminal_settings(self):
        self.assertIn(b"BACK", self.run_menu(b"\x1b"))

    def test_long_condition_wraps_above_the_selected_option(self):
        title = ('Current condition: (Type is Task AND (Description contains "report" '
                 'OR Description contains "exam"))')
        output = self.run_menu(b"\x1b[B\r", title, height=5, ready=b"One")
        self.assertIn(b'"exam"))', output)
        self.assertIn(b"> #37", output)
        self.assertIn(b"RESULT 37", output)

    def test_tiny_screen_uses_plain_menu_so_the_entire_prompt_is_available(self):
        output = self.run_menu(b"37\r", "Current condition with Title with details",
                               width=12, height=3, ready=b": ")
        self.assertIn(b"Title with details", output)
        self.assertIn(b"RESULT 37", output)
