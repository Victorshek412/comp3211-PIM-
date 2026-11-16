"""Part B: search records by type, text and time, combined with and / or / not.

A condition is a nested tuple (the format already used by Part C's search_flow):
    ("type", kind)
    ("contains", field, text)          text fields only, case-insensitive
    ("time", field, "<" | "=" | ">", "YYYY-MM-DD HH:MM")
    ("and", left, right) / ("or", left, right) / ("not", condition)
Records are the dicts returned by RecordManager.get() / list_records().
"""

import operator
from datetime import datetime
from typing import Iterable, List

from . import FIELDS, TEXT_FIELDS, TIME_FIELDS, Condition, RecordData
from .record_manager import check_time

_COMPARISONS = {"<": operator.lt, "=": operator.eq, ">": operator.gt}


def _parse_time(value: str) -> datetime:
    """Parse a time that check_time (Part A) has accepted: one format for records and searches."""
    check_time(value)
    return datetime.fromisoformat(value)


def validate_condition(condition: Condition) -> None:
    """Check a search condition.

    Raises:
        ValueError: the condition is malformed (unknown operation, field, type or time,
            or the wrong number of arguments).
    """
    if not isinstance(condition, tuple) or not condition:
        raise ValueError("A search condition must be a non-empty tuple.")
    op, args = condition[0], condition[1:]
    if op == "type":
        if len(args) != 1 or args[0] not in FIELDS:
            raise ValueError("Type must be note, task, event or contact.")
    elif op == "contains":
        if len(args) != 2 or args[0] not in TEXT_FIELDS or not isinstance(args[1], str):
            raise ValueError("Contains needs a text field and a string.")
    elif op == "time":
        if len(args) != 3 or args[0] not in TIME_FIELDS or args[1] not in _COMPARISONS:
            raise ValueError("Time needs a time field, one of < = >, and a time.")
        _parse_time(args[2])
    elif op in ("and", "or"):
        if len(args) != 2:
            raise ValueError(f"{op} needs exactly two conditions.")
        for sub in args:
            validate_condition(sub)
    elif op == "not":
        if len(args) != 1:
            raise ValueError("not needs exactly one condition.")
        validate_condition(args[0])
    else:
        raise ValueError(f"Unknown search operation: {op}.")


def matches(record: RecordData, condition: Condition) -> bool:
    """True if the record satisfies an already-validated condition."""
    op, args = condition[0], condition[1:]
    if op == "type":
        return record["type"] == args[0]
    if op == "contains":
        field, text = args
        return field in record and text.casefold() in str(record[field]).casefold()
    if op == "time":
        field, comparison, value = args
        return field in record and _COMPARISONS[comparison](
            _parse_time(record[field]), _parse_time(value))
    if op == "and":
        return matches(record, args[0]) and matches(record, args[1])
    if op == "or":
        return matches(record, args[0]) or matches(record, args[1])
    return not matches(record, args[0])  # "not"


def search_records(records: Iterable[RecordData], condition: Condition) -> List[RecordData]:
    """Return the records (dicts, each with its "id") that satisfy condition, in input order.

    Raises:
        ValueError: the condition is malformed (see validate_condition).
    """
    validate_condition(condition)
    return [record for record in records if matches(record, condition)]
