# COMP3211 Personal Information Manager (PIM) — v8

A command-line organiser for notes, tasks, events and contacts. Python 3, standard library only.
This source copy is verified with Python 3.9.6 on macOS using model unit tests.
Uses the standard library only. Live date formatting runs on macOS/Linux ANSI terminals;
Windows, redirected input and TERM=dumb use ordinary line input. Windows/Linux were not tested for this source copy.

## Submission source copy

This folder contains the v8 application and the four model test modules required
for the project's unit-testing deliverable. The complete development test suite
remains in the original v8 folder and GitHub repository.

Open a terminal in this folder to use the commands below. Relative `.pim` paths
are resolved from the current working directory.

This is the source-code portion of the submission, not the complete final ZIP.
Add the required SRS, design document, formal manuals, requirements coverage
report, model coverage report in an accepted document format, videos,
presentation slides and Honour Declaration before submitting the project.

## Run

    python3 main.py                         # start the PIM
    python3 -m unittest discover tests      # run the 60 model tests
    python3 tools/line_coverage.py          # run tests and write COVERAGE.txt (line coverage of model/)

## Project layout (MVC)

| Path | Layer | Owner | Purpose |
| --- | --- | --- | --- |
| `model/__init__.py` | Model | A | `FIELDS` (the one list of fields per record type), shared type aliases |
| `model/records.py` | Model | A | `Note`, `Task`, `Event`, `Contact` |
| `model/record_manager.py` | Model | A | Create, view, update, delete, unique IDs, validation (`FieldError` names the wrong field) |
| `model/search.py` | Model | B | Search by type, text and time with and / or / not |
| `model/search_parser.py` | Model | B | Typed conditions (`search where ...`) and quick keywords -> search conditions |
| `model/storage.py` | Model | D | Atomic `.pim` saving and validated loading |
| `controller/commands.py` | Controller | C | One method per command (`cmd_add`, `cmd_search`, ...), unsaved-change state |
| `view/terminal_view.py` | View | C | Left-aligned forms, prompts and menus; `/back`, `/cancel`, `/done` |
| `view/date_input.py` | View | C | Live date separators and keyboard editing on POSIX terminals |
| `main.py` | | C | Starts the controller |
| `tests/` | | all | Unit tests for the model (four modules) |
| `tools/line_coverage.py` | | D | Standard-library line-coverage report |
| `COVERAGE.txt` | | D | Latest line coverage of `model/` |

Dependencies point one way: `view` and `controller` use `model`; `model` never prints or reads input.

## Using the PIM

Type `help` for the compact command table and `help search` for search syntax.
Forms and records use left-aligned text between two short rules. Success messages
follow the closing rule immediately; newly created records are not printed twice.
The prompt shows `pim*>` while there are unsaved changes. Up-arrow recalls commands
on Linux and macOS.

| Command | Meaning |
| --- | --- |
| `add note buy milk` | Quick note on one line |
| `add` / `add note` / `add task` / `add event` / `add contact` | Choose a type / open its form |
| `view` / `view #3` | Show every record / one record |
| `edit #3` / `delete #3` | Change one field / remove after confirmation |
| `save` / `load` | Ask for a `.pim` filename, offering the last successful filename |
| `save demo` / `load demo` | Use the specified filename; `.pim` is added if needed |
| `exit` | Ask `[S]ave, [D]iscard, [C]ancel` when there are unsaved changes |

`#3` identifies a record; legacy `view 3`, `edit 3`, and `delete 3` still work.
Menu choices use `1.`, `2.`, etc.; `0` returns. A record picker accepts `#3` or `3`.
Commands and IDs need a space: use `view #3`, not `view3`.

**Notes:** In `add note` or note editing, Enter adds a line and `/done` on its own
finishes. Internal blank lines, Chinese text and literal backslashes are preserved.
`/done`, `/back` and `/cancel` are reserved standalone lines in the note editor.
Quick input such as `add note /done` can store a reserved word as a one-line note.
Editing a note replaces its entire text; `/cancel` keeps the previous version.

**Dates:** In a macOS/Linux terminal, type `202612051800` and the date field visibly
adds `-`, a space, and `:` as you type, producing `2026-12-05 18:00` before Enter.
Backspace/Delete, Left/Right, Home/End (also Ctrl+A/Ctrl+E), Ctrl+U to clear, and
formatted date paste work. Pasted newlines do not submit commands. Calendar and time
validation still runs on Enter. Existing formatted input remains accepted.

For an alarm or edited date with a displayed `[default]`, Enter keeps it; `17:00`
changes only the time, and `20261206` changes only the date. With no default, the
missing date or time is asked next (a time-only prompt accepts `1800`). On redirected
or unsupported terminals, compact dates are expanded after Enter instead of live.
Dates in `search where` remain explicitly formatted text, as in the examples below.

**Navigation:** `/back` returns one step; from the first field it returns to the
command prompt. `/cancel` cancels the current action without changing records.
Ctrl+C also cancels. At the main prompt cancellation reports that no action is active.
Navigation reminders live in help, not a one-time Tip inside a form.

**Files:** Interactive `load`/`save` retries the filename after an error; `/back` or
`/cancel` leaves the form. Direct `load NAME`/`save NAME` reports an error and returns.
Overwrite and unsaved-change confirmation remain required. Invalid files never
replace existing records. File paths with spaces are accepted as the rest of the
command (no shell quotes needed inside PIM). Relative paths use the working directory.
Phone numbers can be entered without spaces, e.g. `54441002` or `+85254441002`.

## Searching

| Command | Meaning |
| --- | --- |
| `search milk` | Quick search: any text field contains `milk` (also inside words, so `tea` finds `Team`). Use `\|` as a separator, e.g. `search milk \| eggs` matches either |
| `search` | Asks what to find; Enter lists everything |
| `search where CONDITION` | Typed condition (see below) |

Results show a count and the same short rules. One match shows the full record;
several matches are listed (`#ID  Type: text`), then use `view #ID` or `edit #ID`.

Typed conditions: `type = task`, `FIELD contains "text"` (text, description, name, address, mobile),
`FIELD < "YYYY-MM-DD HH:MM"` (also `=` and `>`; fields deadline, start_time, alarm). Combine with `&&`, `||`, `!` and
parentheses; `!` binds tightest, then `&&`, then `||`. Example:
`search where type = task && (description contains "report" || !deadline > "2026-12-01 09:00")`.
Errors name the position of the problem. Limitation: quick search treats `|` as a separator, so to find a literal `|`
use the typed form, e.g. `search where text contains "a|b"`.

## Interfaces shared between parts

Records are dicts: `{"id": int, "type": "note|task|event|contact", ...fields}`.

| Type | Fields |
| --- | --- |
| note | `text` |
| task | `description`, `deadline` |
| event | `description`, `start_time`, `alarm` |
| contact | `name`, `address`, `mobile` |

Times are strings in `YYYY-MM-DD HH:MM`. Unknown IDs raise `KeyError(id)`; invalid input raises `ValueError`.

Field rules (enforced by `RecordManager`, also when loading a `.pim` file):
- Every field is a non-empty string.
- An event's `alarm` must not be later than its `start_time`.
- A contact's `mobile` has 3 to 15 digits, may start with `+`, and may use single spaces or hyphens between digit groups
  (for example `+852 9123-4567`).

Search conditions are nested tuples: `("type", kind)`, `("contains", text_field, text)`,
`("time", time_field, "<" | "=" | ">", time)`, `("and", a, b)`, `("or", a, b)`, `("not", a)`.

The `.pim` file is UTF-8 JSON: `{"next_id": int, "records": [ ... ]}`. IDs are never reused, including after a reload.

## Verification

On macOS with Python 3.9.6, the four included model test modules contain 60 test
methods (including parameterized input cases). All pass, and model line coverage
is 384/384 executable lines (100%) using `tools/line_coverage.py`.

The test modules are `test_record_manager.py`, `test_search.py`,
`test_search_parser.py` and `test_storage.py`. Their scope covers records and
validation, search evaluation, search syntax, and file persistence. Assertions
state the expected results; comments and docstrings describe the tested behavior.

The included tests total 572 lines, including blank lines and comments.
Controller, view, live keyboard/PTY and coverage-tool tests are excluded from
this submission source copy. The application code is identical to the full v8.

Run `python3 tools/line_coverage.py` from this folder to regenerate `COVERAGE.txt`.
Use Python 3.9.6 to reproduce the figures above; executable-line counts and
exception paths may differ on other Python versions. The raw TXT output should
be accompanied by a formal coverage report in DOC, DOCX or PDF for submission.

## Deadline

Submission is due on 20 November 2026 at 8 pm Hong Kong time.
