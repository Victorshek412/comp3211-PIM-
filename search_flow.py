"""Build a search condition for Part B from the terminal menus."""

import json

import terminal_view as view
from model import FIELDS


_SCOPES = {
    "all": "All records",
    "task": "Tasks",
    "note": "Notes",
    "event": "Events",
    "contact": "Contacts",
    "advanced": "Advanced filters",
}
_TEXT_OPTIONS = (
    ("text", "Note text"),
    ("description", "Description (Task or Event)"),
    ("name", "Contact name"),
    ("address", "Contact address"),
    ("mobile", "Contact mobile number"),
)
_TIME_OPTIONS = (
    ("deadline", "Task deadline"),
    ("start", "Event start"),
    ("alarm", "Event alarm"),
)


def _describe(condition):
    operation = condition[0]
    if operation == "type":
        return f"Type is {condition[1].title()}"
    if operation == "contains":
        return f"{condition[1].title()} contains {json.dumps(condition[2], ensure_ascii=False)}"
    if operation == "time":
        _, field, comparison, value = condition
        return f"{field.title()} {comparison} {value}"
    if operation == "not":
        return f"NOT {_describe(condition[1])}"
    _, left, right = condition
    return f"({_describe(left)} {operation.upper()} {_describe(right)})"


def _pick_condition(title):
    while True:
        choice = view.choose(title, (
            ("type", "Record type"),
            ("contains", "Text field contains a phrase"),
            ("time", "Compare a date and time"),
            ("group", "Build a group in parentheses"),
        ))
        try:
            if choice == "type":
                kinds = [(kind, kind.title()) for kind in FIELDS]
                return ("type", view.choose("Which record type?", kinds))
            if choice == "contains":
                field, phrase = view.read_steps([
                    lambda values: view.choose("Which text field?", _TEXT_OPTIONS),
                    lambda values: view.read_text("Text to find"),
                ])
                return ("contains", field, phrase)
            if choice == "time":
                field, comparison, timestamp = view.read_steps([
                    lambda values: view.choose("Which time field?", _TIME_OPTIONS),
                    lambda values: view.choose("Compare with the time you enter", (
                        ("<", "Earlier than (<)"), ("=", "Equal to (=)"), (">", "Later than (>)"),
                    )),
                    lambda values: view.read_datetime("Comparison"),
                ])
                return ("time", field, comparison, timestamp)
            return _build("Choose the first condition inside the group", "Finish group")
        except view.Back:
            continue


def _build(title, finish_label):
    condition = _pick_condition(title)
    history = []
    while True:
        try:
            action = view.choose(f"Current condition: {_describe(condition)}", (
                ("done", finish_label),
                ("and", "AND — add a condition"),
                ("or", "OR — add a condition"),
                ("not", "NOT — reverse the current condition"),
            ))
        except view.Back:
            if history:
                condition = history.pop()
            else:
                condition = _pick_condition(title)
            continue
        if action == "done":
            return condition
        if action == "not":
            history.append(condition)
            condition = ("not", condition)
        else:
            try:
                right = _pick_condition(f"Choose the condition after {action.upper()}")
            except view.Back:
                continue
            history.append(condition)
            condition = (action, condition, right)


def _any_of(conditions):
    """Build a binary OR tree shallow enough for long keyword lists."""
    if len(conditions) == 1:
        return conditions[0]
    mid = len(conditions) // 2
    return ("or", _any_of(conditions[:mid]), _any_of(conditions[mid:]))


def build_condition(keywords=None):
    """Return a Part B condition, preserving a route back through each prompt."""
    while True:
        scope = "all" if keywords is not None else view.choose(
            "Where do you want to search?", list(_SCOPES.items()))
        try:
            if scope == "advanced":
                return _build("Choose a search condition", "Run search")
            return _quick_condition(scope, keywords)
        except view.Back:
            keywords = None


def _quick_condition(scope, keywords):
    label = _SCOPES[scope].lower()
    value = keywords
    while True:
        if value is None:
            value = view.ask(f"Keywords for {label} (report | exam for either, Enter for all, /cancel): ")
        if not value.strip():
            print(f"Searching {label}.")
            if scope == "all":
                return _any_of([("type", kind) for kind in FIELDS])
            return ("type", scope)
        phrases = [part.strip() for part in value.split("|")]
        if all(phrases):
            break
        value = None
        print("A phrase is empty. Enter a phrase on each side of |.")

    summary = " OR ".join(json.dumps(phrase, ensure_ascii=False) for phrase in phrases)
    print(f"Searching {label} for {summary}.")
    fields = [field for field, _ in _TEXT_OPTIONS if scope == "all" or field in FIELDS[scope]]
    contains = _any_of([("contains", field, phrase) for field in fields for phrase in phrases])
    if scope == "all":
        return contains
    return ("and", ("type", scope), contains)
