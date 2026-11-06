"""Edit terminal text with Escape navigation and private command history."""

import shutil
import sys
import unicodedata
from contextlib import ExitStack
from types import BuiltinFunctionType

from terminal_keys import Back, keyboard


_commands = []


def _width(text):
    return sum(0 if unicodedata.combining(char) else
               2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
               for char in text)


def read_line(prompt: str, *, command: bool = False, default: str = "") -> str:
    """Edit one line, keeping history only for command prompts."""
    if not isinstance(input, BuiltinFunctionType) or not sys.stdin.isatty() or not sys.stdout.isatty():
        return input(prompt) or default

    line, cursor, start = default, len(default), 0
    history = len(_commands)
    draft = default

    def redraw():
        nonlocal start
        columns = max(2, shutil.get_terminal_size().columns or 80)
        label = prompt
        while label and _width(label) > columns - 2:
            label = label[1:]
        available = columns - _width(label) - 1
        start = min(start, cursor)
        while _width(line[start:cursor]) >= available:
            start += 1
        end = start
        while end < len(line) and _width(line[start:end + 1]) <= available:
            end += 1
        position = _width(label) + _width(line[start:cursor])
        sys.stdout.write("\r\x1b[2K" + label + line[start:end] + "\r")
        if position:
            sys.stdout.write(f"\x1b[{position}C")
        sys.stdout.flush()

    with ExitStack() as stack:
        try:
            read_key = stack.enter_context(keyboard())
        except OSError:
            return input(prompt) or default
        try:
            while True:
                redraw()
                key = read_key()
                if key == "enter":
                    if command and line.strip():
                        _commands.append(line)
                    return line
                if key == "escape":
                    raise Back
                if key == "left":
                    cursor = max(0, cursor - 1)
                elif key == "right":
                    cursor = min(len(line), cursor + 1)
                elif key == "home":
                    cursor = 0
                elif key == "end":
                    cursor = len(line)
                elif key == "backspace" and cursor:
                    line = line[:cursor - 1] + line[cursor:]
                    cursor -= 1
                elif key == "delete":
                    line = line[:cursor] + line[cursor + 1:]
                elif command and key in ("up", "down"):
                    if history == len(_commands):
                        draft = line
                    history = max(0, min(len(_commands), history + (-1 if key == "up" else 1)))
                    line = draft if history == len(_commands) else _commands[history]
                    cursor, start = len(line), 0
                elif key and len(key) == 1 and key.isprintable():
                    line = line[:cursor] + key + line[cursor:]
                    cursor += 1
        finally:
            print(flush=True)
