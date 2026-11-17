"""Plain-text prompts and menus for the PIM terminal.

Every prompt understands two commands: /back (previous step) and /cancel (stop).
"""

from calendar import month_name, monthrange
from contextlib import contextmanager
from datetime import date, datetime, time
from typing import Any, Callable, Iterator, List, Optional, Sequence, Tuple

from view.date_input import read_date_line

try:  # Gives Up-arrow command history and line editing on Linux and macOS.
    import readline  # noqa: F401
except ImportError:  # Windows has no readline module; input() still works there.
    pass


class Cancelled(Exception):
    """The user typed /cancel (or pressed Ctrl+C) to stop the current action."""


class Back(Exception):
    """The user asked to go back one step (typed /back or chose 0)."""


RULE = "-" * 24


@contextmanager
def section(title: str) -> Iterator[None]:
    """Frame an action and close its rule even when input is interrupted."""
    print(f"\n{_safe_line(title)}\n{RULE}")
    try:
        yield
    except Cancelled as error:
        message = (f"{title[4:].capitalize()} creation cancelled."
                   if title.startswith("New ") else f"{title} cancelled.")
        raise Cancelled(message) from error
    except KeyboardInterrupt:
        print()
        raise
    finally:
        print(RULE)


def _safe_line(text: str) -> str:
    """Replace control characters so saved data can never move the cursor or recolour the screen."""
    return "".join(char if char.isprintable() else " " for char in text)


def ask(prompt: str, *, default: str = "", date_mode: str = "") -> str:
    """Show a prompt and return the line typed, or default if the line is empty.

    Raises:
        Cancelled: the user typed /cancel.
        Back: the user typed /back.
        EOFError: the input ended (for example Ctrl+D).
    """
    prompt = _safe_line(prompt)
    line = read_date_line(prompt, date_mode) if date_mode else input(prompt)
    command = line.strip().lower()
    if command == "/cancel":
        raise Cancelled
    if command == "/back":
        raise Back
    return line or default


def choose(title: str, options: Sequence[Tuple[Any, str]]) -> Any:
    """Show a numbered menu and return the key of the chosen option.

    Integer keys are record IDs: the menu then lists and asks for the IDs themselves.

    Raises:
        ValueError: options is empty.
        Back: the user chose 0.
        Cancelled: the user typed /cancel.
    """
    if not options:
        raise ValueError("A menu needs at least one option")
    records = isinstance(options[0][0], int)
    numbers = [str(key if records else index) for index, (key, _) in enumerate(options, 1)]
    labels = [f"{'#' + number + '  ' if records else number + '. '}{_safe_line(label)}"
              for number, (_, label) in zip(numbers, options)]
    if title:
        print(_safe_line(title))
    print(*labels, "0. Back", sep="\n")
    prompt = "Record: " if records else ("Field: " if not title else "Choice: ")
    while True:
        answer = ask(prompt).strip()
        if records and answer.startswith("#"):
            answer = answer[1:]
        if answer == "0":
            raise Back
        if answer in numbers:
            return options[numbers.index(answer)][0]
        if answer:
            print("Please enter a number from the list.")


def confirm(prompt: str) -> bool:
    """Ask a yes/no question on one line. Enter alone means No, so nothing is lost by accident.

    Raises:
        Cancelled, Back: the user typed /cancel or /back.
    """
    while True:
        answer = ask(f"{prompt} [y/N] ").strip().lower()
        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes"):
            return True
        print("Please type Y or N.")


def pick(prompt: str, options: Sequence[Tuple[str, str]]) -> str:
    """Ask for one of a few choices on one line.

    options is [(letter, word), ...]; the letter or the whole word is accepted, in any case.
    Returns the word of the chosen option.

    Raises:
        Cancelled, Back: the user typed /cancel or /back.
    """
    letters = [letter.upper() for letter, _ in options]
    hint = ", ".join(letters[:-1]) + " or " + letters[-1]
    while True:
        answer = ask(prompt).strip().lower()
        for letter, word in options:
            if answer in (letter, word):
                return word
        print(f"Please type {hint}.")


def read_steps(steps: Sequence[Callable[[List[Any]], Any]],
               values: Optional[Sequence[Any]] = None, start: int = 0) -> List[Any]:
    """Run a short form: each step receives the answers so far and returns its answer.

    /back (a Back raised by a step) returns to the previous step with earlier answers kept.
    Pass values (earlier answers) and start to reopen a form at one step.

    Raises:
        Back: the user went back from the first step.
        Cancelled: the user typed /cancel.
    """
    answers = list(values or [])
    index = start
    while index < len(steps):
        try:
            value = steps[index](answers)
        except Back:
            if index == 0:
                raise
            index -= 1
            continue
        if index == len(answers):
            answers.append(value)
        elif answers[index] != value:
            answers[index:] = [value]
        index += 1
    return answers


def read_text(label: str, default: str = "") -> str:
    """Ask for a non-empty line of text; with a default, Enter keeps it.

    Raises:
        Cancelled, Back: the user typed /cancel or /back.
    """
    shown = f"{label} [{default}]" if default else label
    while True:
        value = ask(f"{shown}: ", default=default).strip()
        if value:
            return value


def read_note() -> str:
    """Read lines until /done; blank lines and backslashes are ordinary content.

    Raises:
        Cancelled, Back: the user typed /cancel or /back.
    """
    print("Enter = new line; /done = finish")
    lines: List[str] = []
    while True:
        line = ask("> ")
        if line.strip().lower() == "/done":
            body = "\n".join(lines).strip()
            if body:
                return body
            print("A note cannot be blank.")
            lines.clear()
        else:
            lines.append(line)


def _date_error(fields: Sequence[str]) -> Optional[Tuple[int, str]]:
    """Return (index of the wrong field, message) for year/month/day text, or None if valid."""
    year, month, day = fields
    if not (len(year) == 4 and year.isascii() and year.isdecimal() and int(year) >= 1):
        return 0, "Enter a four-digit year from 0001 to 9999."
    if not (len(month) <= 2 and month.isascii() and month.isdecimal() and 1 <= int(month) <= 12):
        return 1, "Enter a month from 1 to 12."
    last_day = monthrange(int(year), int(month))[1]
    if not (len(day) <= 2 and day.isascii() and day.isdecimal() and 1 <= int(day) <= last_day):
        return 2, f"{month_name[int(month)]} has {last_day} days. Enter a day from 1 to {last_day}."
    return None


def read_date(label: str) -> date:
    """Ask for a date as YYYY-MM-DD (or "year month day").

    A wrong part (for example day 31 in June) is asked for again on its own.

    Raises:
        Cancelled, Back: the user typed /cancel or /back.
    """
    full_prompt = f"{label} date (YYYY-MM-DD): "
    fields: List[str] = []
    active: Optional[int] = None
    while True:
        if active is None:
            prompt = full_prompt
        else:
            prompt = f"{label} date: enter the {('year', 'month', 'day')[active]}: "
        value = ask(prompt, date_mode="date" if active is None else "").strip()
        if not value:
            continue
        if value.isascii() and value.isdecimal() and len(value) == 8:
            value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
        parts = value.split("-") if "-" in value else value.split()
        if len(parts) == 3:
            fields = parts
        elif active is not None and len(parts) == 1:
            fields[active] = value
        else:
            print("Enter a full date, such as 2026-09-05.")
            continue
        error = _date_error(fields)
        if error is None:
            return date(*map(int, fields))
        active, message = error
        print(f"Invalid date. {message}")


def _read_time(label: str) -> time:
    prompt = f"{label} time (HH:MM): "
    while True:
        value = ask(prompt, date_mode="time").strip()
        if not value:
            continue
        try:
            return _parse_time(value)
        except ValueError as error:
            print(error)


def _parse_time(value: str) -> time:
    """Parse HH:MM (or "HH MM"); raise ValueError with a hint if it is not a time."""
    if value.isascii() and value.isdecimal() and len(value) == 4:
        value = f"{value[:2]}:{value[2:]}"
    for pattern in ("%H:%M", "%H %M"):
        try:
            return datetime.strptime(value, pattern).time()
        except ValueError:
            continue
    raise ValueError("Use HH:MM, for example 09:05.")


def _parse_when(text: str) -> Tuple[Optional[date], Optional[time]]:
    """Read "DATE", "TIME" or "DATE TIME" (DATE as YYYY-MM-DD; TIME as HH:MM).

    Returns (date or None, time or None); raises ValueError with a hint if it cannot be read."""
    if text.isascii() and text.isdecimal() and len(text) in (8, 12):
        day_text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        text = day_text + (f" {text[8:10]}:{text[10:]}" if len(text) == 12 else "")
    tokens = text.replace(",", " ").split()
    clock = _parse_time(tokens.pop()) if tokens and ":" in tokens[-1] else None
    day = None
    if tokens:
        fields = tokens[0].split("-") if len(tokens) == 1 and "-" in tokens[0] else tokens
        if len(fields) != 3:
            raise ValueError("Type a date like 2026-09-05, a time like 09:30, or both.")
        error = _date_error(fields)
        if error is not None:
            raise ValueError(f"Invalid date. {error[1]}")
        day = date(*map(int, fields))
    return day, clock


def read_datetime(label: str, default: Optional[str] = None) -> str:
    """Ask for a date and time on one line and return "YYYY-MM-DD HH:MM".

    Type both ("2026-12-01 09:30"), or only one part: a part left out is taken from default
    if there is one (Enter alone keeps default), otherwise it is asked for next.

    Raises:
        Cancelled, Back: the user typed /cancel, or /back at the first prompt.
    """
    prompt = f"{label} [{default}]: " if default else f"{label} (YYYY-MM-DD HH:MM): "
    while True:
        text = ask(prompt, date_mode="datetime").strip()
        if not text and default:
            return default
        if not text:
            continue
        try:
            day, clock = _parse_when(text)
        except ValueError as error:
            print(error)
            continue
        if default:
            day = day or date.fromisoformat(default[:10])
            clock = clock or time.fromisoformat(default[11:16])
        try:
            if day is None:
                day = read_date(label)
            if clock is None:
                clock = _read_time(label)
        except Back:
            continue  # return to the one-line prompt
        return f"{day.isoformat()} {clock.isoformat(timespec='minutes')}"
