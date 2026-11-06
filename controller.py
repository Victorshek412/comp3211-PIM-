"""Part C: translate terminal commands into calls to the team's services."""

from pathlib import Path
import sys

from model import FIELDS, TIME_FIELDS
from search_flow import build_condition
from terminal_view import (Back, Cancelled, ask, choose, command_palette, confirm,
                           read_datetime, read_note, read_text, read_steps)


HELP = """Commands
  add [note|task|event|contact]   Create a record. Example: add task
  view [ID|all]                  Choose one, open an ID, or print all details.
  search [keywords]              Search all records, or type search to choose filters.
  ?                              Find and run a command.
  edit [ID]                      Choose one field to change. Example: edit 12
  delete ID                      Review the record and confirm with Y or N.
  save / load                    Enter a .pim filename when prompted.
  help / exit                    Show commands or leave the organiser.
At pim>, Up/Down recalls commands. Left/Right edits text.
Esc or Back returns one step. /back also works at text prompts.
/cancel or Ctrl+C abandons the current action. Use exit at pim> to close."""
PALETTE = [
    ("add note", "Add note"), ("add task", "Add task"), ("add event", "Add event"),
    ("add contact", "Add contact"), ("view", "View record"), ("view all", "View all records"),
    ("search", "Search records"), ("edit", "Edit record"), ("delete", "Delete record"),
    ("save", "Save file"), ("load", "Load file"), ("help", "Help"), ("exit", "Exit"),
]

LABELS = {"start": "Start time", "alarm": "Alarm time", "mobile": "Mobile number"}


def label(field):
    return LABELS.get(field, field.capitalize())


def display_text(value):
    # Keep note paragraphs, but never replay control sequences from a saved file.
    return "".join(c if c.isprintable() or c == "\n" else repr(c)[1:-1] for c in str(value))


def summary(record):
    kind = record["type"]
    first_line = display_text(record[FIELDS[kind][0]]).strip().splitlines()[0]
    return f"{kind.title()} — {first_line[:72]}"


def show_record(record):
    print(f"#{record['id']}  {record['type'].title()}")
    for field in FIELDS[record["type"]]:
        print(f"  {label(field)}: {display_text(record[field])}")


def read_field(field, previous=""):
    if field in TIME_FIELDS:
        prompt = {"deadline": "Due", "start": "Start", "alarm": "Alarm"}[field]
        return read_datetime(prompt)
    if field == "text":
        return read_note()
    return read_text(label(field), default=previous)


class Controller:
    def __init__(self, records, search, storage):
        self.records = records
        self.search = search
        self.storage = storage
        self.dirty = False

    def select(self, records, empty="No records yet."):
        if not records:
            print(empty)
            return None
        rows = sorted(records, key=lambda row: row["id"])
        record_id = choose("Select a record", [(row["id"], summary(row)) for row in rows])
        return self.records.get(record_id)

    def target(self, arg):
        if not arg:
            return self.select(self.records.list_records())
        if not (arg.isascii() and arg.isdecimal()) or int(arg) < 1:
            raise ValueError("Enter a positive record ID, for example: view 12.")
        return self.records.get(int(arg))

    def add(self, kind):
        if kind:
            return self.add_kind(kind)
        while True:
            selected = choose("Choose a record type", [(name, name.title()) for name in FIELDS])
            try:
                return self.add_kind(selected)
            except Back:
                continue

    def add_kind(self, kind):
        if kind not in FIELDS:
            raise ValueError("Choose note, task, event or contact. Example: add task")
        names = FIELDS[kind]
        values = read_steps([
            lambda values, field=field, index=index: read_field(
                field, values[index] if index < len(values) else "")
            for index, field in enumerate(names)
        ])
        fields = dict(zip(names, values))
        record_id = self.records.create(kind, fields)
        self.dirty = True
        print(f"Created {kind} #{record_id}.")
        show_record(self.records.get(record_id))

    def edit(self, record):
        fields = FIELDS[record["type"]]
        options = [(f, f"{label(f)}: {display_text(record[f]).replace(chr(10), ' / ')}")
                   for f in fields]
        field, value = read_steps([
            lambda values: choose(f"Edit {record['type']} #{record['id']} — choose one field", options),
            lambda values: read_field(values[0]),
        ])
        if value == record[field]:
            print("Value unchanged.")
            return
        self.records.update(record["id"], field, value)
        self.dirty = True
        print(f"Updated {record['type']} #{record['id']}. {label(field)}: {display_text(value)}")

    def file_command(self, action):
        while True:
            name = read_text("Filename (.pim)").strip()
            try:
                return self.file_path(action, name)
            except Back:
                continue

    def file_path(self, action, name):
        if not name.lower().endswith(".pim"):
            name += ".pim"
        path = Path(name)
        if action == "save":
            if path.exists() and not confirm(f"Overwrite {display_text(name)}?"):
                print("Save cancelled.")
                return
            self.storage.save(path)
            print(f"Saved {display_text(name)}.")
        else:
            if self.dirty and not confirm("Discard unsaved changes if the file loads?"):
                print("Load cancelled.")
                return
            try:
                self.storage.load(path)
            except (OSError, ValueError) as error:
                print(f"Could not load {display_text(name)}. Your current records are unchanged.")
                print(display_text(error))
                return
            print(f"Loaded {display_text(name)}.")
        self.dirty = False

    def execute(self, line):
        """Run one complete command. False asks the main loop to exit."""
        if line.strip() != "?":
            return self.execute_command(line)
        while True:
            selected = command_palette(PALETTE)
            try:
                return self.execute_command(selected, from_palette=True)
            except Back:
                continue

    def execute_command(self, line, from_palette=False):
        words = line.split(maxsplit=1)
        if not words:
            return True
        command, arg = words[0].lower(), words[1] if len(words) > 1 else ""
        if arg and command in ("help", "save", "load", "exit"):
            raise ValueError(f"Enter {command} on its own. Type help for examples.")
        if command == "help":
            print(HELP)
        elif command == "add":
            self.add(arg.lower())
        elif command == "view" and arg.lower() == "all":
            rows = sorted(self.records.list_records(), key=lambda row: row["id"])
            if not rows:
                print("No records yet.")
            for row in rows:
                show_record(row)
        elif command in ("view", "edit", "delete"):
            if command == "delete" and not arg and not from_palette:
                raise ValueError("Include the record ID, for example: delete 12.")
            while True:
                record = self.target(arg)
                if record is None:
                    return True
                try:
                    self.record_command(command, record)
                    break
                except Back:
                    if arg:
                        raise
        elif command == "search":
            if self.records.list_records():
                while True:
                    matches = self.search(build_condition(arg or None))
                    try:
                        result = matches[0] if len(matches) == 1 else self.select(matches, empty="No matches.")
                        break
                    except Back:
                        arg = ""

                if result is not None:
                    show_record(result)
                    print(f"To change this {result['type']}, type edit {result['id']}.")
            else:
                print("No records yet.")
        elif command in ("save", "load"):
            self.file_command(command)
        elif command == "exit":
            if not self.dirty:
                return False
            while True:
                action = choose("Unsaved changes", [
                    ("keep", "Keep editing"), ("save", "Save and exit"),
                    ("discard", "Discard changes and exit"),
                ])
                if action == "save":
                    try:
                        self.file_command("save")
                        return self.dirty
                    except Back:
                        continue
                if action == "keep":
                    print("Session kept open. Type save to keep your changes.")
                    break
                return False
        else:
            raise ValueError("Unknown command. Try add task or type help.")
        return True

    def record_command(self, command, record):
        if command == "view":
            show_record(record)
        elif command == "edit":
            self.edit(record)
        else:
            print(summary(record))
            if confirm(f"Delete {record['type']} #{record['id']}?"):
                self.records.delete(record["id"])
                self.dirty = True
                print(f"Deleted {record['type']} #{record['id']}.")
            else:
                print("Record kept.")

    def run(self):
        print("Try add task to create a task. Type ? to find commands, or help for examples.")
        print("Esc / Back returns one step. Ctrl+C cancels the action. Type exit at pim> to close.")
        while True:
            try:
                if not self.execute(ask("pim> ", command=True)):
                    return 0
            except Back:
                pass
            except (Cancelled, KeyboardInterrupt):
                print("\nCancelled.")
            except EOFError:
                if self.dirty:
                    if sys.stdin.isatty():
                        print("\nUnsaved changes. Type save or exit.")
                        continue
                    print("\nInput ended with unsaved changes.")
                    return 1
                return 0
            except KeyError as error:
                print(f"No record with ID {display_text(error.args[0])}.")
            except (OSError, ValueError) as error:
                print(display_text(error))
