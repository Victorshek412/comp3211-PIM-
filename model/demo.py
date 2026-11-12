"""Reference implementation for Part C until A, B and D supply their services.

The provisional .pim format is UTF-8 JSON with records and a next_id counter.
"""

import operator
from datetime import datetime

from . import FIELDS, TIME_FIELDS
from .storage import load_records, save_records


def _check_fields(kind, fields):
    if not isinstance(kind, str) or kind not in FIELDS:
        raise ValueError("Unknown record type.")
    if not isinstance(fields, dict) or set(fields) != set(FIELDS[kind]):
        raise ValueError(f"A {kind} requires these fields: {', '.join(FIELDS[kind])}.")
    for field, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} requires a non-empty string.")
        if field in TIME_FIELDS:
            _check_time(value)


def _check_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.isoformat(sep=" ", timespec="minutes") == value and parsed.tzinfo is None:
            return
    except (TypeError, ValueError):
        pass
    raise ValueError("Time must be a valid YYYY-MM-DD HH:MM value.")


def _matches(record, condition):
    operation, *args = condition
    if operation == "type":
        return record["type"] == args[0]
    if operation == "contains":
        field, text = args
        return field in record and text.casefold() in record[field].casefold()
    if operation == "time":
        field, comparison, value = args
        _check_time(value)
        compare = {"<": operator.lt, "=": operator.eq, ">": operator.gt}[comparison]
        return field in record and compare(record[field], value)
    if operation == "and":
        return _matches(record, args[0]) and _matches(record, args[1])
    if operation == "or":
        return _matches(record, args[0]) or _matches(record, args[1])
    if operation == "not":
        return not _matches(record, args[0])
    raise ValueError(f"Unknown search operation: {operation}.")


class DemoModel:
    """A's reference record manager, with a validated state exchange for D."""

    def __init__(self):
        self._records = {}
        self._next_id = 1

    def create(self, kind, fields):
        _check_fields(kind, fields)
        record_id = self._next_id
        self._records[record_id] = {"id": record_id, "type": kind, **fields}
        self._next_id += 1
        return record_id

    def get(self, record_id):
        return self._records[record_id].copy()

    def list_records(self):
        return [self.get(record_id) for record_id in sorted(self._records)]

    def update(self, record_id, field, value):
        record = self._records[record_id]
        kind = record["type"]
        fields = {name: record[name] for name in FIELDS[kind]}
        fields[field] = value
        _check_fields(kind, fields)
        record[field] = value

    def delete(self, record_id):
        del self._records[record_id]

    def snapshot(self):
        return {"next_id": self._next_id, "records": self.list_records()}

    def replace_snapshot(self, data):
        """Validate the whole state before replacing live records or the ID counter."""
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError("Expected a list of records in the .pim file.")
        records = {}
        for record in data["records"]:
            if not isinstance(record, dict):
                raise ValueError("Invalid record in the .pim file.")
            record_id = record.get("id")
            if type(record_id) is not int or record_id <= 0 or record_id in records:
                raise ValueError("Record IDs must be unique positive integers.")
            fields = {key: value for key, value in record.items() if key not in ("id", "type")}
            _check_fields(record.get("type"), fields)
            records[record_id] = record.copy()
        next_id = data.get("next_id")
        if type(next_id) is not int or next_id <= max(records, default=0):
            raise ValueError("Invalid next ID in the .pim file.")
        self._records, self._next_id = records, next_id


class DemoServices:
    """B and D's reference services operate on the supplied A record manager."""

    def __init__(self, records):
        self.records = records

    def search(self, condition):
        return [record for record in self.records.list_records() if _matches(record, condition)]

    def save(self, path):
        save_records(self.records, path)

    def load(self, path):
        load_records(self.records, path)
