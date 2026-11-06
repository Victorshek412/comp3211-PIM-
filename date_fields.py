"""Interactive date entry with visible year, month and day fields."""

from calendar import month_name, monthrange
from datetime import date

from terminal_keys import Back, Cancelled


MASKS = ("YYYY", "MM", "DD")


def _date_error(fields):
    year, month, day = fields
    if not (len(year) == 4 and year.isascii() and year.isdecimal() and int(year) >= 1):
        return 0, "Enter a four-digit year from 0001 to 9999."
    if not (len(month) <= 2 and month.isascii() and month.isdecimal() and 1 <= int(month) <= 12):
        return 1, "Enter a month from 1 to 12."
    last_day = monthrange(int(year), int(month))[1]
    if not (len(day) <= 2 and day.isascii() and day.isdecimal() and 1 <= int(day) <= last_day):
        return 2, f"{month_name[int(month)]} has {last_day} days. Enter a day from 1 to {last_day}."


def read_plain_date(label, ask, previous=None):
    keep = f", Enter to keep {previous.isoformat()}" if previous else ""
    full_prompt = f"{label} date (YYYY-MM-DD or year month day{keep}, /back, /cancel): "
    fields = []
    active = None
    while True:
        if active is None:
            prompt = full_prompt
        else:
            name = ("year", "month", "day")[active]
            prompt = f"{label} date (enter {name} or a full date, /back, /cancel): "
        value = ask(prompt).strip()
        if not value:
            if previous and active is None:
                return previous
            continue
        if value.lower() == "/cancel":
            raise Cancelled
        if value.lower() == "/back":
            raise Back
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


def read_date_fields(label, read_key, previous=None):
    fields = previous.isoformat().split("-") if previous else ["", "", ""]
    active = 0
    replace = previous is not None
    command = ""
    print("Space or - for next field, Left/Right to edit, Enter to accept, Esc or /back to go back, /cancel to cancel.")
    while True:
        slots = [(value.zfill(2) if len(mask) == 2 else value.ljust(4, "_")) if value else mask
                 for value, mask in zip(fields, MASKS)]
        slots[active] = "\x1b[7m" + slots[active] + "\x1b[0m"
        suffix = f"  {command}" if command else ""
        print(f"\r\x1b[2K{label} date: " + "-".join(slots) + suffix, end="", flush=True)
        key = read_key()
        if key == "escape":
            print()
            raise Back
        if command:
            if key == "enter":
                if command.lower() == "/cancel":
                    print()
                    raise Cancelled
                if command.lower() == "/back":
                    print()
                    raise Back
                print("\nUnknown command. Use /back or /cancel.")
                command = ""
            elif key == "backspace":
                command = command[:-1]
            elif key and len(key) == 1 and key.isprintable():
                command += key
            continue
        if key == "/":
            command = "/"
            continue
        if key == "enter":
            if not any(fields):
                continue
            error = _date_error(fields)
            if error:
                active, message = error
                print(f"\nInvalid date. {message}")
                replace = True
                continue
            result = date(*map(int, fields))
            print(f"\r\x1b[2K{label} date: {result.isoformat()}")
            return result
        if key in ("left", "right", "tab"):
            active = max(0, min(2, active + (-1 if key == "left" else 1)))
            replace = True
        elif key == "backspace":
            if not fields[active] and active:
                active -= 1
            fields[active] = fields[active][:-1]
            replace = False
        elif key in (" ", "-") and active < 2:
            if fields[active]:
                active += 1
                replace = bool(fields[active])
        elif key and len(key) == 1 and "0" <= key <= "9":
            if replace:
                fields[active] = key
            elif len(fields[active]) < len(MASKS[active]):
                fields[active] += key
            replace = False
