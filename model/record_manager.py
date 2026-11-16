"""Part A: create, view, update and delete PIRs, and hand out unique IDs."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import FIELDS, TIME_FIELDS, RecordData
from .records import Contact, Event, Note, Record, Task

_CLASSES = {"note": Note, "task": Task, "event": Event, "contact": Contact}


class FieldError(ValueError):
    """A ValueError that says which field is wrong, so a form can ask for just that field."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.field = field


def check_time(value: str) -> None:
    """Check that value is a valid 'YYYY-MM-DD HH:MM' time.

    Raises:
        ValueError: if it is not a string in exactly that format.
    """
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.isoformat(sep=" ", timespec="minutes") == value and parsed.tzinfo is None:
            return
    except (TypeError, ValueError):
        pass
    raise ValueError("Time must be a valid YYYY-MM-DD HH:MM value.")


_MOBILE = re.compile(r"\+?[0-9]+(?:[ -][0-9]+)*")


def check_mobile(value: str) -> None:
    """Check a mobile number: 3-15 digits, optional leading +, single spaces or hyphens
    only between digit groups.

    Raises:
        ValueError: if the number does not follow those rules.
    """
    value = value.strip()
    digits = sum(ch.isdigit() for ch in value)
    if not _MOBILE.fullmatch(value) or not 3 <= digits <= 15:
        raise ValueError("A mobile number has 3 to 15 digits, for example +852 9123 4567.")


def check_fields(kind: str, fields: Dict[str, str]) -> None:
    """Check that fields is exactly the field set of record type kind and every value is valid.

    Raises:
        FieldError: a value breaks a rule; .field names the field (a ValueError).
        ValueError: kind is unknown or fields has missing or extra names.
    """
    if not isinstance(kind, str) or kind not in FIELDS:
        raise ValueError("Unknown record type.")
    if not isinstance(fields, dict) or set(fields) != set(FIELDS[kind]):
        raise ValueError(f"A {kind} requires these fields: {', '.join(FIELDS[kind])}.")
    for field, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise FieldError(f"{field} requires a non-empty string.", field)
        if field in TIME_FIELDS:
            try:
                check_time(value)
            except ValueError as error:
                raise FieldError(str(error), field) from None
    if kind == "event" and fields["alarm"] > fields["start_time"]:
        raise FieldError("The alarm must not be later than the event's start time.", "alarm")
    if kind == "contact":
        try:
            check_mobile(fields["mobile"])
        except ValueError as error:
            raise FieldError(str(error), "mobile") from None


def _build(record_id: int, kind: str, fields: Dict[str, str]) -> Record:
    check_fields(kind, fields)
    return _CLASSES[kind](record_id, **{name: fields[name].strip() for name in FIELDS[kind]})


class RecordManager:
    """Owns all records in memory and hands out unique IDs (IDs are never reused)."""

    def __init__(self) -> None:
        self._records = {}
        self._next_id = 1

    def _find(self, record_id: int) -> Record:
        if record_id not in self._records:
            raise KeyError(record_id)
        return self._records[record_id]

    def create(self, kind: str, fields: Dict[str, str]) -> int:
        """Create a record and return its new unique ID.

        Raises:
            FieldError / ValueError: see check_fields; nothing is created and no ID is used.
        """
        record_id = self._next_id
        self._records[record_id] = _build(record_id, kind, fields)
        self._next_id += 1
        return record_id

    def get(self, record_id: int) -> RecordData:
        """Return a copy of a record as a dict.

        Raises:
            KeyError: the ID does not exist; args[0] is the ID.
        """
        return self._find(record_id).to_dict()

    def list_records(self) -> List[RecordData]:
        """Return copies of all records in ascending ID order."""
        return [self.get(record_id) for record_id in sorted(self._records)]

    def update(self, record_id: int, field: str, value: str) -> None:
        """Change one field of a record.

        Raises:
            KeyError: the ID does not exist.
            ValueError: the record has no such field (FieldError if the value breaks a rule);
                the record is left unchanged.
        """
        record = self._find(record_id)
        if field not in FIELDS[record.type]:
            raise ValueError(f"A {record.type} has no field named {field}.")
        fields = {name: getattr(record, name) for name in FIELDS[record.type]}
        fields[field] = value
        check_fields(record.type, fields)
        setattr(record, field, value.strip())

    def delete(self, record_id: int) -> None:
        """Delete a record.

        Raises:
            KeyError: the ID does not exist.
        """
        self._find(record_id)
        del self._records[record_id]

    def snapshot(self) -> Dict[str, Any]:
        """Return {"next_id": int, "records": [...]} describing the whole state."""
        return {"next_id": self._next_id, "records": self.list_records()}

    def replace_snapshot(self, data: Any) -> None:
        """Replace all records with those in a snapshot (the format of snapshot()).

        Raises:
            ValueError: the snapshot is malformed or any record is invalid (FieldError for a
                broken field rule); the current state is left unchanged.
        """
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError("Expected a list of records in the .pim file.")
        records = {}
        for item in data["records"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid record in the .pim file.")
            record_id = item.get("id")
            if type(record_id) is not int or record_id <= 0 or record_id in records:
                raise ValueError("Record IDs must be unique positive integers.")
            fields = {k: v for k, v in item.items() if k not in ("id", "type")}
            records[record_id] = _build(record_id, item.get("type"), fields)
        next_id = data.get("next_id")
        if type(next_id) is not int or next_id <= max(records, default=0):
            raise ValueError("Invalid next ID in the .pim file.")
        self._records, self._next_id = records, next_id
