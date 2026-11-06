import io
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from line_input import read_line


class InputFallbackTests(unittest.TestCase):
    def test_redirected_input_returns_raw_line_and_propagates_eof(self):
        with patch("sys.stdin", io.StringIO("  keep spaces  \n")), patch("sys.stdout", io.StringIO()):
            self.assertEqual(read_line("field> "), "  keep spaces  ")
            with self.assertRaises(EOFError):
                read_line("field> ")

    def test_injected_input_receives_the_prompt_even_in_terminal(self):
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            with patch("builtins.input", side_effect=lambda prompt: prompt):
                self.assertEqual(read_line("pim> ", command=True), "pim> ")

    def test_unavailable_keyboard_falls_back_to_line_input(self):
        with patch("sys.stdin", io.StringIO("kept\n")), patch("sys.stdout", io.StringIO()):
            with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
                self.assertEqual(read_line("field> "), "kept")

    def test_plain_empty_input_keeps_default_and_nonempty_input_replaces_it(self):
        with patch("sys.stdin", io.StringIO("\nnew\n")), patch("sys.stdout", io.StringIO()):
            self.assertEqual(read_line("field> ", default="old"), "old")
            self.assertEqual(read_line("field> ", default="old"), "new")


@unittest.skipUnless(os.name == "posix", "requires a POSIX pseudo-terminal")
class TerminalEditingTests(unittest.TestCase):
    def run_prompt(self, expression, keys):
        import termios

        script = f"""
from line_input import read_line
try:
    result = read_line({expression})
    print("RESULT", repr(result), flush=True)
except BaseException as error:
    print("RESULT", type(error).__name__, flush=True)
print("END OUTPUT", flush=True)
"""
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        original = termios.tcgetattr(slave)
        env = {**os.environ, "TERM": "xterm", "PIM_PLAIN": "1", "COLUMNS": "30"}
        with subprocess.Popen(
            [sys.executable, "-c", script], stdin=slave, stdout=slave, stderr=slave,
            env=env, cwd=Path(__file__).resolve().parents[1],
        ) as child:
            output = bytearray()
            try:
                for marker in (b"field> ", b"END OUTPUT"):
                    deadline = time.monotonic() + 5
                    while marker not in output:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                            self.fail(f"Timed out waiting for {marker!r}: {output!r}")
                        output.extend(os.read(master, 4096))
                    if marker == b"field> ":
                        os.write(master, keys)
                child.wait(timeout=5)
            finally:
                child.kill()
        restored = termios.tcgetattr(slave)
        pending = getattr(termios, "PENDIN", 0)
        restored[3] &= ~pending
        original[3] &= ~pending
        self.assertEqual(restored, original)
        return bytes(output).split(b"RESULT ", 1)[1].splitlines()[0].decode()

    def test_escape_leaves_partial_text_immediately_and_restores_terminal(self):
        self.assertEqual(self.run_prompt("'field> '", b"unfinished\x1b"), "Back")

    def test_default_text_can_be_edited_with_home_delete_end_and_backspace(self):
        result = self.run_prompt("'field> ', default='old title'",
                                 b"\x1b[H\x1b[3~\x1b[3~\x1b[3~new\x1b[F\x7f!\r")
        self.assertEqual(result, "'new titl!'")

    def test_interrupt_and_eof_restore_terminal(self):
        for key, expected in ((b"\x03", "KeyboardInterrupt"), (b"\x04", "EOFError")):
            with self.subTest(key=key):
                self.assertEqual(self.run_prompt("'field> '", key), expected)

    def test_commands_recall_and_fields_edit_privately_in_plain_mode(self):
        import termios

        script = """
import json, readline
from line_input import read_line
readline.add_history("unrelated shell history")
answers = []
for i, command in enumerate([True, False, True, True, False, True]):
    answers.append(read_line(f"[{i}]> ", command=command))
external = [readline.get_history_item(i + 1) for i in range(readline.get_current_history_length())]
print("RESULT", json.dumps([answers, external]), flush=True)
print("END OUTPUT", flush=True)
"""
        secret = "私人 note " + "x" * 90
        keys = [
            b"add task\r",
            b"\x1b[A" + secret.encode() + b"\x1b[D\x1b[D!\x1b[C?\r",
            b"\x1b[A 2\r",
            b"draft\x1b[A\x1b[A\x1b[B\x1b[B\r",
            b"\x1b[A\r",
            b"\x1b[A\x1b[A\r",
        ]
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        original = termios.tcgetattr(slave)
        env = {**os.environ, "TERM": "xterm", "PIM_PLAIN": "1"}
        with subprocess.Popen(
            [sys.executable, "-c", script], stdin=slave, stdout=slave, stderr=slave,
            env=env, cwd=Path(__file__).resolve().parents[1],
        ) as child:
            try:
                def read_until(marker):
                    output = bytearray()
                    deadline = time.monotonic() + 5
                    while marker not in output:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not select.select([master], [], [], remaining)[0]:
                            self.fail(f"Timed out waiting for {marker!r}: {output!r}")
                        output.extend(os.read(master, 4096))
                    return bytes(output)

                for i, entry in enumerate(keys):
                    read_until(f"[{i}]> ".encode())
                    os.write(master, entry)
                result = read_until(b"END OUTPUT")
                child.wait(timeout=5)
            finally:
                child.kill()
        answers, external = json.loads(result.split(b"RESULT ", 1)[1].splitlines()[0])
        self.assertEqual(answers, ["add task", secret[:-2] + "!x?x", "add task 2",
                                   "draft", "", "add task 2"])
        self.assertEqual(external, ["unrelated shell history"])
        restored = termios.tcgetattr(slave)
        pending = getattr(termios, "PENDIN", 0)
        restored[3] &= ~pending
        original[3] &= ~pending
        self.assertEqual(restored, original)
