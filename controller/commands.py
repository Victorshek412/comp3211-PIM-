"""Part C: translate terminal commands into calls to the model and print the results."""

import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from model import FIELDS, TIME_FIELDS, RecordData
from model.record_manager import FieldError, RecordManager
from model.search import search_records
from model.search_parser import keywords_condition, parse_condition
from model.storage import load_records, save_records
from view.terminal_view import (Back, Cancelled, ask, choose, confirm, pick, read_datetime,
                                read_note, read_steps, read_text, section)

HELP = """Commands
------------------------
add           Create a record; e.g. add note buy milk
view [#ID]    Show all records or one by ID
search        Find records; see help search
edit [#ID]    Edit a record
delete #ID    Delete a record
save / load   Save / load a .pim file; filename optional
exit          Exit the PIM
------------------------
Types: note, task, event, contact
/back = previous step; /cancel = cancel action"""

HELP_SEARCH = """search milk              records containing "milk" (also inside words)
search milk | eggs       records containing either phrase
search where CONDITION   typed condition, for example:
  type = task && (deadline < "2026-12-01 09:00" || !description contains "x")
Fields: type, text, description, name, address, mobile (use contains "..."),
        deadline, start_time, alarm (use < = >). Combine with && || ! ( )
Literal |: search where text contains "a|b" """.rstrip()

NO_RECORDS = "No records yet. Type add note to create one."

# Field names shown differently from the model's names; every other field is derived.
LABELS = {"mobile": "Mobile", "alarm": "Alarm time"}

# A field whose prompt starts from another field's value, so Enter alone is often enough.
DEFAULT_FROM = {"alarm": "start_time"}


def label(field: str) -> str:
    """Return the name of a field as shown to the user, e.g. start_time -> "Start time"."""
    return LABELS.get(field, field.replace("_", " ").capitalize())


def display_text(value: object) -> str:
    """Return text that is safe to print: control characters are shown as escapes."""
    return "".join(c if c.isprintable() or c == "\n" else repr(c)[1:-1] for c in str(value))


def file_error(error: OSError, saving: bool = False) -> str:
    """Describe a file problem in plain words (instead of Python's "[Errno 2] ...")."""
    if isinstance(error, FileNotFoundError):
        return "That folder does not exist." if saving else "File not found."
    if isinstance(error, PermissionError):
        return "Permission denied."
    if isinstance(error, IsADirectoryError):
        return "That is a folder, not a file."
    return error.strerror or "The file could not be read or written."


def summary(record: RecordData) -> str:
    """One line describing a record, e.g. "Note — buy milk"."""
    kind = record["type"]
    first_line = display_text(record[FIELDS[kind][0]]).strip().splitlines()[0]
    return f"{kind.title()}: {first_line[:72]}"


def show_record(record: RecordData) -> None:
    """Print every field of a record."""
    with section(f"{record['type'].title()} #{record['id']}"):
        show_fields(record)


def show_fields(record: RecordData) -> None:
    """Print left-aligned fields; multiline values start below their label."""
    for field in FIELDS[record["type"]]:
        value = display_text(record[field])
        separator = "\n" if "\n" in value else " "
        print(f"{label(field)}:{separator}{value}")


def read_field(field: str, previous: str = "") -> str:
    """Prompt for one field; previous is offered as the starting value."""
    if field in TIME_FIELDS:
        return read_datetime(label(field).split()[0], default=previous or None)
    if field == "text":
        return read_note()
    if field == "mobile":
        return read_text("Mobile (spaces optional)", default=previous)
    return read_text(label(field), default=previous)


class Controller:
    """Reads commands, calls the model, and prints the results (the C of MVC)."""

    def __init__(self, records: RecordManager) -> None:
        self.records = records
        self.dirty = False  # True while there are changes not yet saved
        self.last_file = ""
        self._commands: Dict[str, Callable[[str], Optional[bool]]] = {
            "help": self.cmd_help, "add": self.cmd_add, "view": self.cmd_view,
            "edit": self.cmd_edit, "delete": self.cmd_delete, "search": self.cmd_search,
            "save": self.cmd_save, "load": self.cmd_load, "exit": self.cmd_exit,
        }

    # ----- running -----

    def execute(self, line: str) -> bool:
        """Run one command line. Returns False when the user chose to leave, else True.

        Raises:
            ValueError: unknown command or invalid input (the message is meant for the user).
            KeyError: a record ID does not exist.
            OSError: a file could not be read or written.
            Back, Cancelled: the user went back from, or cancelled, a prompt.
        """
        words = line.split(maxsplit=1)
        if not words:
            return True
        handler = self._commands.get(words[0].lower())
        if handler is None:
            joined = re.fullmatch(r"(view|edit|delete)#?([0-9]+)", words[0], re.IGNORECASE)
            if joined:
                raise ValueError("Use a space before the record ID. Example: "
                                 f"{joined[1].lower()} #{joined[2]}")
            raise ValueError("Unknown command. Type help.")
        return handler(words[1] if len(words) > 1 else "") is not False

    def run(self) -> int:
        """Read and run commands until the user exits. Returns the process exit code."""
        print("PIM ready. Type help.")
        while True:
            command = ""
            try:
                command = ask("pim*> " if self.dirty else "pim> ")
                if not self.execute(command):
                    return 0
            except Back:
                print("Returned to command prompt." if command else "Already at command prompt.")
            except Cancelled as error:
                print(str(error) or ("Cancelled." if command else "No active action to cancel."))
            except KeyboardInterrupt:
                print("Cancelled." if command else "\nNo active action to cancel.")
            except EOFError:
                if self.dirty:
                    print("\nInput ended with unsaved changes.")
                    return 1
                return 0
            except KeyError as error:
                print(f"No record #{display_text(error.args[0])}. Use view to list records.")
            except OSError as error:
                print(file_error(error))
            except ValueError as error:
                print(display_text(error))
            if command:
                print()

    # ----- commands (each takes the text after the command name) -----

    def cmd_help(self, arg: str) -> None:
        """help | help search: show the command list or the search syntax."""
        if arg.lower() == "search":
            print(HELP_SEARCH)
        elif arg:
            raise ValueError("Type help or help search.")
        else:
            print(HELP)

    def cmd_add(self, arg: str) -> None:
        """add [type] | add note TEXT: create a record; a note can be typed on one line."""
        kind, _, text = arg.partition(" ")
        kind, text = kind.lower(), text.strip()
        if text:
            if kind != "note":
                raise ValueError(f"Only notes can be added on one line. Type add {kind} instead.")
            print(self._create("note", {"text": text}))
            return
        if kind:
            return self._add_kind(kind)
        with section("New record"):
            kind = choose("Record type", [(name, name.title()) for name in FIELDS])
        self._add_kind(kind)

    def cmd_view(self, arg: str) -> None:
        """view | view all | view ID: show every record, or one."""
        if arg.lower() in ("", "all"):
            rows = self.records.list_records()
            if not rows:
                print(NO_RECORDS)
            for row in rows:
                show_record(row)
        else:
            show_record(self._target(arg))

    def cmd_edit(self, arg: str) -> None:
        """edit [ID]: change one field of a record (choose the record if no ID is given)."""
        record = self._target(arg) if arg else self._choose_record()
        if record is not None:
            with section(f"Edit {record['type']} #{record['id']}"):
                result = self._edit(record)
            print(result)

    def cmd_delete(self, arg: str) -> None:
        """delete ID: remove a record after confirmation."""
        if not arg:
            raise ValueError("Give a record ID, for example: delete #12.")
        record = self._target(arg)
        with section(f"Delete {record['type']} #{record['id']}"):
            show_fields(record)
            if confirm("Confirm deletion?"):
                self.records.delete(record["id"])
                self.dirty = True
                result = f"Deleted {record['type']} #{record['id']}."
            else:
                result = "Record kept."
        print(result)

    def cmd_search(self, arg: str) -> None:
        """search [words] | search where CONDITION: list the records that match."""
        if not self.records.list_records():
            with section("Search: 0 matches"):
                print(NO_RECORDS)
            return
        where = re.fullmatch(r"where(?:\s+(.*))?", arg, flags=re.IGNORECASE | re.DOTALL)
        if where:
            condition = parse_condition((where.group(1) or "").strip())
        else:
            words = arg or ask("Search for (words, Enter = all records): ")
            condition = keywords_condition(words)
        matches = search_records(self.records.list_records(), condition)
        with section(f"Search: {len(matches)} {'match' if len(matches) == 1 else 'matches'}"):
            if not matches:
                print("No matches.")
            elif len(matches) == 1:
                print(f"{matches[0]['type'].title()} #{matches[0]['id']}")
                show_fields(matches[0])
            else:
                for row in matches:
                    print(f"#{row['id']}  {summary(row)}")
        if len(matches) == 1:
            print(f"Edit: edit #{matches[0]['id']}")
        elif matches:
            print("Details: view #ID\nEdit: edit #ID")

    def cmd_save(self, arg: str) -> None:
        """save [filename]: write all records, asking for a filename if omitted."""
        self._file_command("save", arg)

    def cmd_load(self, arg: str) -> None:
        """load [filename]: validate and replace all records from a .pim file."""
        self._file_command("load", arg)

    def cmd_exit(self, arg: str) -> bool:
        """exit: leave, after asking what to do with unsaved changes. False means leave."""
        self._no_argument("exit", arg)
        if not self.dirty:
            return False
        with section("Exit PIM"):
            action = pick("Unsaved changes: [S]ave, [D]iscard or [C]ancel? ",
                          (("s", "save"), ("d", "discard"), ("c", "cancel")))
        if action == "discard":
            return False
        if action == "cancel":
            print("Not exiting.")
            return True
        try:
            self._file_command("save", "")
        except Back:
            return True
        return self.dirty  # still dirty if the user declined to overwrite

    # ----- helpers -----

    @staticmethod
    def _no_argument(command: str, arg: str) -> None:
        if arg:
            raise ValueError(f"Type {command} on its own.")

    def _choose_record(self) -> Optional[RecordData]:
        rows = self.records.list_records()
        if not rows:
            print(NO_RECORDS)
            return None
        with section("Select a record"):
            record_id = choose("", [(r["id"], summary(r)) for r in rows])
        return self.records.get(record_id)

    def _target(self, arg: str) -> RecordData:
        if arg.startswith("#"):
            arg = arg[1:]
        if not (arg.isascii() and arg.isdecimal()) or int(arg) < 1:
            raise ValueError("Give a record ID, for example: view #12.")
        return self.records.get(int(arg))

    def _create(self, kind: str, fields: Dict[str, str]) -> str:
        record_id = self.records.create(kind, fields)
        self.dirty = True
        return f"Created {kind} #{record_id}."

    def _add_kind(self, kind: str) -> None:
        if kind not in FIELDS:
            raise ValueError("Choose note, task, event or contact, e.g. add task.")
        names = FIELDS[kind]

        def step(index: int, field: str) -> Callable[[List[str]], str]:
            def read(values: List[str]) -> str:
                if index < len(values):
                    return read_field(field, values[index])
                source = DEFAULT_FROM.get(field)
                return read_field(field, values[names.index(source)] if source in names else "")
            return read

        steps = [step(index, field) for index, field in enumerate(names)]
        values: Optional[List[str]] = None
        start = 0
        with section(f"New {kind}"):
            while True:
                values = read_steps(steps, values=values, start=start)
                try:
                    result = self._create(kind, dict(zip(names, values)))
                    break
                except FieldError as error:  # keep earlier answers; retry the invalid field
                    print(error)
                    start = names.index(error.field) if error.field in names else 0
                    source = DEFAULT_FROM.get(error.field)
                    if source in names:
                        values[start] = values[names.index(source)]
        print(result)

    def _edit(self, record: RecordData) -> str:
        fields = FIELDS[record["type"]]
        if len(fields) == 1:  # nothing to choose: go straight to the new value
            steps = [lambda values: read_field(fields[0], record[fields[0]])]
        else:
            options = [(f, f"{label(f)}: {display_text(record[f]).replace(chr(10), ' / ')}")
                       for f in fields]
            steps = [
                lambda values: choose("", options),
                lambda values: read_field(values[0], record[values[0]]),
            ]
        answers, start = None, 0
        while True:
            answers = read_steps(steps, values=answers, start=start)
            field, value = (fields[0], answers[0]) if len(fields) == 1 else answers
            if value == record[field]:
                return "Value unchanged."
            try:
                self.records.update(record["id"], field, value)
            except FieldError as error:
                print(error)
                start = len(steps) - 1
                continue
            self.dirty = True
            return f"Updated {record['type']} #{record['id']}."

    def _file_command(self, action: str, arg: str) -> None:
        with section(f"{action.title()} records"):
            name = arg.strip()
            if name:
                print(f"Filename: {display_text(name)}")
            while True:
                if not name:
                    name = read_text("Filename (.pim)", default=self.last_file).strip()
                if not name.lower().endswith(".pim"):
                    name += ".pim"
                try:
                    result = self._file_path(action, name)
                except Back:
                    name = ""
                    continue
                except (OSError, ValueError) as error:
                    reason = (file_error(error, saving=action == "save")
                              if isinstance(error, OSError) else display_text(error))
                    print(f"Could not {action} {display_text(name)}. {reason}")
                    if action == "load":
                        print("Your current records are unchanged.")
                    result = None
                if result is not None or arg:
                    break
                name = ""
        if result:
            print(result)

    def _file_path(self, action: str, name: str) -> Optional[str]:
        path = Path(name)
        if action == "save":
            if path.exists() and not confirm(f"Overwrite {display_text(name)}?"):
                return "Save cancelled."
            save_records(self.records, path)
            result = f"Saved {display_text(name)}."
        else:
            if not path.exists():  # say so before asking about unsaved changes
                print(f"Could not load {display_text(name)}. File not found.")
                return
            if self.dirty and not confirm("Discard unsaved changes if the file loads?"):
                return "Load cancelled."
            load_records(self.records, path)
            result = f"Loaded {display_text(name)}."
        self.last_file = name
        self.dirty = False
        return result
