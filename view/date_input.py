"""A small POSIX line editor for fixed-format dates; ordinary input elsewhere."""

import os
import select
import shutil
import sys
from typing import Tuple


class DateBuffer:
    """Keep editable digits separate from their automatically displayed separators."""

    def __init__(self, mode: str = "datetime") -> None:
        self.text = ""
        self.cursor = 0
        self.separators = ({2: ":"} if mode == "time" else
                           {4: "-", 6: "-", **({8: " ", 10: ":"} if mode == "datetime" else {})})

    def display(self) -> Tuple[str, int]:
        """Return visible text and cursor column, adding separators for digit input."""
        if not (self.text.isascii() and self.text.isdecimal()):
            return self.text, self.cursor
        shown = "".join(char + self.separators.get(index, "")
                        for index, char in enumerate(self.text, 1))
        cursor = self.cursor + sum(position <= self.cursor for position in self.separators)
        return shown, cursor

    def feed(self, key: str) -> None:
        """Apply a character or editing key; moving across a separator skips it."""
        if key == "LEFT":
            self.cursor = max(0, self.cursor - 1)
        elif key == "RIGHT":
            self.cursor = min(len(self.text), self.cursor + 1)
        elif key == "HOME":
            self.cursor = 0
        elif key == "END":
            self.cursor = len(self.text)
        elif key == "BACKSPACE":
            if self.cursor:
                self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
        elif key == "DELETE":
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        elif key == "CLEAR":
            self.text, self.cursor = "", 0
        elif key == "KILL_END":
            self.text = self.text[:self.cursor]
        elif len(key) == 1 and key.isascii() and key.isprintable():
            if self.text.isdecimal() and not key.isdecimal():
                if key == self.separators.get(self.cursor):
                    return  # An explicitly typed separator is already visible.
                if key != " ":
                    self.text, self.cursor = self.display()
            self.text = self.text[:self.cursor] + key + self.text[self.cursor:]
            self.cursor += 1

    def paste(self, text: str) -> None:
        """Insert pasted text as one value; pasted newlines never submit the form."""
        text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        # Keep formatted/space-separated pasted dates intact for the normal parser.
        if text.isascii() and text.isdecimal():
            for char in text:
                self.feed(char)
        else:
            self.text, self.cursor = self.display()
            text = "".join(char for char in text if char.isascii() and char.isprintable())
            self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
            self.cursor += len(text)


def _key(fd: int) -> str:
    """Read one byte or one ANSI key sequence; a lone Escape does not block."""
    value = os.read(fd, 1)
    if not value:
        raise EOFError
    if value == b"\x1b":
        while len(value) < 16 and select.select([fd], [], [], 0.05)[0]:
            part = os.read(fd, 1)
            if not part:
                break
            if part in (b"\x03", b"\x04") or (len(value) == 1 and part not in (b"[", b"O")):
                return part.decode("ascii", errors="ignore")
            value += part
            if len(value) >= 3 and (part == b"~" or part.isalpha()):
                break
    return value.decode("ascii", errors="ignore")


def read_date_line(prompt: str, mode: str = "datetime") -> str:
    """Read with live separators on POSIX TTYs, restoring settings on every exit.

    Other platforms and redirected streams use input(). Raises EOFError or
    KeyboardInterrupt just like input(). Validation belongs to terminal_view.
    """
    if (os.name != "posix" or not sys.stdin.isatty() or not sys.stdout.isatty()
            or os.environ.get("TERM") == "dumb"):
        return input(prompt)

    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    buffer = DateBuffer(mode)
    keys = {"\x7f": "BACKSPACE", "\b": "BACKSPACE", "\x1b[D": "LEFT",
            "\x1b[C": "RIGHT", "\x1b[3~": "DELETE", "\x1b[H": "HOME",
            "\x1b[F": "END", "\x1bOH": "HOME", "\x1bOF": "END",
            "\x01": "HOME", "\x05": "END", "\x15": "CLEAR", "\x0b": "KILL_END"}
    try:
        tty.setraw(fd, termios.TCSANOW)
        sys.stdout.write("\x1b[?2004h")
        while True:
            value, cursor = buffer.display()
            line, column = prompt + value, len(prompt) + cursor
            columns = shutil.get_terminal_size().columns or 80
            width = max(2, columns - 1)
            start = max(0, column - width + 1)
            visible = line[start:start + width]
            back = len(visible) - (column - start)
            sys.stdout.write("\r\x1b[2K" + visible + (f"\x1b[{back}D" if back else ""))
            sys.stdout.flush()
            key = _key(fd)
            if key in ("\r", "\n"):
                sys.stdout.write("\r\n")
                return value.strip()
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x04":
                if not buffer.text:
                    sys.stdout.write("\r\n")
                    raise EOFError
                buffer.feed("DELETE")
            elif key == "\x1b[200~":
                pasted = bytearray()
                while not pasted.endswith(b"\x1b[201~"):
                    char = os.read(fd, 1)
                    if not char:
                        raise EOFError
                    if char == b"\x03":
                        raise KeyboardInterrupt
                    pasted.extend(char)
                buffer.paste(pasted[:-6].decode("utf-8", errors="replace"))
            else:
                buffer.feed(keys.get(key, key))
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
