# COMP3211 Personal Information Manager — Final version

A command-line program for keeping notes, tasks, events and contacts.
You can add, view, edit, search and delete records, then save them in a `.pim` file.

## How to run

Tested with Python 3.9.6 on macOS. No extra packages are needed.
Open a terminal in the project folder and run:

```sh
python3 main.py
```

## Commands

| Command | What it does |
| --- | --- |
| `help` | Show the commands |
| `add` | Choose a record type and fill in its details |
| `add note buy milk` | Add a quick note |
| `view` | Show all records |
| `view #3` | Show record 3 |
| `edit #3` | Edit record 3 |
| `delete #3` | Delete record 3 after confirmation |
| `search milk` | Find records containing “milk” |
| `save demo` | Save records to `demo.pim` |
| `load demo` | Load records from `demo.pim` |
| `exit` | Close the program |

Replace `#3` with the record ID shown by the program. You can also type
`add task`, `add event` or `add contact` to open that form directly.

- For a multiline note, type `/done` on a new line to finish. Editing a note replaces its text.
- Enter dates as `2026-12-05 18:00`. Compact input such as `202612051800` also works.
- Press Enter to keep a displayed default value. Use `/back` to go back or `/cancel` to cancel.
- Blank fields and invalid dates are rejected. An event's alarm must be at or before its start time.
- Phone numbers need 3–15 digits. A leading `+`, spaces and hyphens are allowed, e.g. `+852 9123-4567`.
- `pim*>` means there are unsaved changes. The program asks what to do before exiting.
- Files are saved in the current folder unless you give a full path. Loading replaces the current records after confirmation if there are unsaved changes.

If a command is invalid, the program shows an error message. Type `help` to check its format.

## Search examples

Use `search where` for more specific searches:

```text
search where type = task
search where name contains "Alice"
search where deadline < "2026-12-01 09:00"
search where type = task && (description contains "report" || description contains "exam")
```

Use `&&` for AND, `||` for OR and `!` for NOT. Parentheses group conditions.
Text fields are `text`, `description`, `name`, `address` and `mobile`.
Time fields are `deadline`, `start_time` and `alarm`; they support `<`, `>` and `=`.
Use the full date format shown above in search conditions.
Type `help search` for a reminder. Use `view #ID` to open a search result.

## Tests

Run the model tests and terminal regression tests:

```sh
python3 -m unittest discover tests
```

Generate the model line coverage report:

```sh
python3 tools/line_coverage.py
```

The result is saved in `COVERAGE.txt`.

## Files

- `main.py`: starts the program.
- `model/`: records, validation, searching, saving and loading.
- `controller/`: handles commands.
- `view/`: displays prompts and reads input.
- `tests/`: model unit tests and terminal regression tests.
- `tools/`: the coverage script.
