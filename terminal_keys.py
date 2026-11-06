"""Shared keyboard handling for terminal menus and date fields."""

import os
import select
import sys
from contextlib import contextmanager


class Cancelled(Exception):
    """The user cancelled the current action."""


class Back(Exception):
    """The user requested the previous field or screen."""


def interactive_terminal():
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def _posix_key(fd):
    def read_byte():
        value = os.read(fd, 1)
        if value in (b"", b"\x04"):
            raise EOFError
        if value == b"\x03":
            raise KeyboardInterrupt
        return value

    key = read_byte()
    if key in (b"\r", b"\n"):
        return "enter"
    if key == b"\x1b":
        if not select.select([fd], [], [], 0.10)[0]:
            return "escape"
        if read_byte() in (b"[", b"O"):
            # Consume the whole sequence, including paste markers such as ESC [ 200 ~.
            sequence = b""
            while select.select([fd], [], [], 0.10)[0]:
                final = read_byte()
                sequence += final
                if b"@" <= final <= b"~":
                    if final == b"~":
                        return {b"1~": "home", b"7~": "home", b"4~": "end",
                                b"8~": "end", b"3~": "delete"}.get(sequence)
                    return {b"A": "up", b"B": "down", b"C": "right", b"D": "left",
                            b"H": "home", b"F": "end"}.get(final)
        return None
    if key in (b"\x7f", b"\x08"):
        return "backspace"
    if key == b"\t":
        return "tab"
    if key == b"\x01":
        return "home"
    if key == b"\x05":
        return "end"
    length = 4 if key[0] >= 0xF0 else 3 if key[0] >= 0xE0 else 2 if key[0] >= 0xC0 else 1
    for _ in range(length - 1):
        key += read_byte()
    return key.decode("utf-8", errors="replace")


def _windows_key():
    import msvcrt

    key = msvcrt.getwch()
    if key in ("\x00", "\xe0"):
        return {"H": "up", "P": "down", "K": "left", "M": "right",
                "G": "home", "O": "end", "S": "delete"}.get(msvcrt.getwch())
    if key == "\x03":
        raise KeyboardInterrupt
    if key == "\x1a":
        raise EOFError
    if 0xD800 <= ord(key) <= 0xDBFF:
        key = (key + msvcrt.getwch()).encode("utf-16", errors="surrogatepass").decode("utf-16")
    return {"\r": "enter", "\x1b": "escape", "\b": "backspace", "\t": "tab",
            "\x01": "home", "\x05": "end"}.get(key, key)


@contextmanager
def keyboard():
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        console = ctypes.windll.kernel32
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
        mode = wintypes.DWORD()
        if not console.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError("Console mode unavailable")
        # Enable virtual-terminal screen updates on Windows console hosts.
        if not console.SetConsoleMode(handle, mode.value | 0x0004):
            raise OSError("Console cannot redraw menus")
        try:
            yield _windows_key
        finally:
            console.SetConsoleMode(handle, mode)
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        try:
            original = termios.tcgetattr(fd)
            tty.setcbreak(fd, termios.TCSANOW)
            mode = termios.tcgetattr(fd)
            mode[3] &= ~termios.ISIG
            termios.tcsetattr(fd, termios.TCSANOW, mode)
        except termios.error as error:
            raise OSError("Keyboard mode unavailable") from error
        try:
            yield lambda: _posix_key(fd)
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, original)
