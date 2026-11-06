"""English prompts and keyboard menus for the PIM terminal."""

import os
import shutil
import textwrap
import unicodedata
from datetime import datetime

from date_fields import read_date_fields, read_plain_date
from line_input import read_line
from terminal_keys import Back, Cancelled, interactive_terminal, keyboard


def ask(prompt: str, *, command=False, default="") -> str:
    line = read_line(prompt, command=command, default=default)
    if line.strip().lower() == "/cancel":
        raise Cancelled
    if line.strip().lower() == "/back":
        raise Back
    return line


def _safe_line(text):
    return "".join(char if char.isprintable() else " " for char in text)


def _char_limit(text, columns):
    # Reserve two screen cells per character on lines containing wide glyphs.
    if any(unicodedata.east_asian_width(ch) in ("W", "F") for ch in text):
        return max(1, columns // 2)
    return columns


def _menu_row(label, selected, columns):
    row = ("> " if selected else "  ") + label
    row = row[:_char_limit(row, columns)]
    if selected:
        cells = sum(0 if unicodedata.combining(c) else
                    2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                    for c in row)
        row = "\x1b[7m" + row + " " * max(0, columns - cells) + "\x1b[0m"
    return row


def _menu_lines(title, hints, typed, labels, matches, selected):
    width, height = shutil.get_terminal_size()
    columns = max(1, width - 1)
    lines = textwrap.wrap(title, _char_limit(title, columns))
    if typed:
        available = max(1, columns - len(hints))
        lines.append((hints + typed[-_char_limit(typed, available):])[:columns])
    else:
        lines.extend(textwrap.wrap(hints, columns))
    visible = height - len(lines) - 1  # Keep Back visible below scrolling options.
    if visible < 1:
        return []  # The complete prompt is still available in plain mode.
    start = max(0, min(selected or 0, len(matches) - 2) - visible + 1)
    for position in range(start, min(start + visible, len(matches) - 1)):
        lines.append(_menu_row(labels[matches[position]], position == selected, columns))
    if len(matches) == 1:
        lines.append("No matching commands."[:columns])
    lines.append(_menu_row(labels[-1], selected == len(matches) - 1, columns))
    return lines


def _matching_labels(labels, query):
    needle = query.casefold()
    return [index for index, label in enumerate(labels) if needle in label.casefold()]


def _arrow_menu(title, labels, *, numbers=(), confirmation=False, palette=False):
    back = len(labels)
    labels = [*labels, "0  Back" if numbers or confirmation else "Back"]
    if numbers:
        numbers = [*numbers, "0"]
    selected = None if confirmation else 0
    matches = range(len(labels))
    typed = ""
    previous_lines = 0
    with keyboard() as read_key:
        try:
            while True:
                hints = "Up/Down or type a number, Enter to select, Esc to go back."
                if confirmation:
                    hints = "Y/N/0 or arrows, then Enter. Esc to go back."
                elif palette:
                    hints = "Filter: "
                elif typed:
                    hints = "Number: "
                lines = _menu_lines(title, hints, typed, labels, matches, selected)
                if not lines:
                    return None
                # Redraw only the menu, starting at its first line in the transcript.
                rewind = f"\x1b[{previous_lines - 1}A" if previous_lines > 1 else ""
                prefix = "\r" + rewind + "\x1b[J" if previous_lines else ""
                print(prefix + "\n".join(lines), end="", flush=True)
                previous_lines = len(lines)
                key = read_key()
                if key == "escape":
                    raise Back
                if key == "enter" and matches and selected is not None:
                    if matches[selected] == back:
                        raise Back
                    return matches[selected]
                if key in ("up", "down"):
                    if not palette:
                        typed = ""
                    if selected is None:
                        selected = 0 if matches else None
                    elif key == "up":
                        selected = max(0, selected - 1)
                    else:
                        selected = min(len(matches) - 1, selected + 1)
                elif confirmation and key in ("y", "Y", "n", "N"):
                    selected = 1 if key.lower() == "y" else 0
                elif confirmation and key == "0":
                    selected = back
                elif palette or numbers:
                    if key == "backspace":
                        typed = typed[:-1]
                    elif key and len(key) == 1 and (key.isprintable() if palette else key in "0123456789"):
                        typed += key
                    else:
                        continue
                    if palette:
                        matches = _matching_labels(labels[:-1], typed)
                        selected = 0 if matches else None
                        matches.append(back)
                    elif typed:
                        selected = numbers.index(typed) if typed in numbers else None
                    else:
                        selected = 0
        finally:
            if previous_lines:
                rewind = f"\x1b[{previous_lines - 1}A" if previous_lines > 1 else ""
                print("\r" + rewind + "\x1b[J", end="", flush=True)


def _choose_with_keys(title, labels, **mode):
    if os.environ.get("PIM_PLAIN") != "1" and interactive_terminal():
        try:
            return _arrow_menu(title, labels, **mode)
        except (ImportError, OSError):
            pass  # Some IDEs report a TTY without providing a console keyboard.
    return None


def choose(title, options):
    """Return a selected key. Integer keys are the stable IDs shown to the user."""
    if not options:
        raise ValueError("A menu needs at least one option")
    title = _safe_line(title)
    records = isinstance(options[0][0], int)
    numbers = [str(key if records else i) for i, (key, _) in enumerate(options, 1)]
    prefix = "#" if records else ""
    labels = [f"{prefix}{number}  {_safe_line(label)}"
              for number, (_, label) in zip(numbers, options)]
    index = _choose_with_keys(title, labels, numbers=numbers)
    if index is not None:
        return options[index][0]
    print(title, *labels, "0  Back", sep="\n")
    what = "ID" if records else "option number"
    while True:
        answer = ask(f"Enter a listed {what}, 0 to go back or /cancel: ").strip()
        if answer == "0":
            raise Back
        if answer in numbers:
            return options[numbers.index(answer)][0]
        if answer:
            print(f"Please enter a listed {what}.")


def command_palette(options):
    """Choose a command by filtering its name or description."""
    if not options:
        raise ValueError("A command palette needs at least one command")
    labels = [_safe_line(label if command.casefold() in label.casefold() else f"{command}  {label}")
              for command, label in options]
    index = _choose_with_keys("Commands — type to filter, Up/Down, Enter or Esc",
                              labels, palette=True)
    if index is not None:
        return options[index][0]

    matches = range(len(options))
    while True:
        for number, index in enumerate(matches, 1):
            print(f"{number}  {labels[index]}")
        print("0  Back")
        answer = ask("Enter a command, number, search text, 0 to go back or /cancel: ").strip()
        if answer == "0":
            raise Back
        for number, index in enumerate(matches, 1):
            if answer == str(number):
                return options[index][0]
        for command, _ in options:
            if command.casefold() == answer.casefold():
                return command
        matches = _matching_labels(labels, answer)
        if len(matches) == 1:
            return options[matches[0]][0]
        if not matches:
            print("No matching commands. Try another search.")


def confirm(prompt: str) -> bool:
    index = _choose_with_keys(_safe_line(prompt), ["No", "Yes"], confirmation=True)
    if index is not None:
        return index == 1
    while True:
        answer = ask(f"{prompt} [Y/N/0 (Back)] ").strip().lower()
        if answer == "0":
            raise Back
        if answer in ("y", "n"):
            return answer == "y"
        if answer:
            print("Please type Y or N.")


def read_steps(steps):
    """Collect a short form, retaining accepted values when moving back."""
    values = []
    index = 0
    while index < len(steps):
        try:
            value = steps[index](values)
        except Back:
            if index == 0:
                raise
            index -= 1
            continue
        if index == len(values):
            values.append(value)
        elif values[index] != value:
            values[index:] = [value]
        index += 1
    return values


def read_text(label: str, default="") -> str:
    while True:
        value = ask(f"{label}: ", default=default).strip()
        if value:
            return value


def read_note() -> str:
    print("Enter your note. Use /done on its own line to finish, or /cancel to discard.")
    lines = []
    while True:
        line = ask("")
        if line.strip() == "/done":
            body = "\n".join(lines)
            if body.strip():
                return body
            print("A note cannot be blank. Enter your note and finish with /done.")
            lines.clear()
        else:
            lines.append(line)


def _read_time(label):
    prompt = f"{label} time (HH:MM or hour minute, /back to edit date, /cancel): "
    while True:
        value = ask(prompt).strip()
        if not value:
            continue
        for pattern in ("%H:%M", "%H %M"):
            try:
                return datetime.strptime(value, pattern).time()
            except ValueError:
                continue
        print("Invalid entry. Try 09:05, /back to edit the date, or /cancel to return.")


def _read_day(label, previous):
    if interactive_terminal():
        try:
            with keyboard() as read_key:
                return read_date_fields(label, read_key, previous)
        except (ImportError, OSError):
            pass
    return read_plain_date(label, ask, previous)


def read_datetime(label: str) -> str:
    day = None
    while True:
        day = _read_day(label, day)
        try:
            clock = _read_time(label)
        except Back:
            continue
        return f"{day.isoformat()} {clock.isoformat(timespec='minutes')}"
