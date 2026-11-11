from datetime import datetime
from . import FIELDS, TIME_FIELDS
from .records import Note, Task, Event, Contact


def check_fields(kind, fields):
    if not isinstance(kind, str) or kind not in FIELDS:
        raise ValueError("Unknown record type.")
    if not isinstance(fields, dict) or set(fields) != set(FIELDS[kind]):
        raise ValueError(f"A {kind} requires these fields: {', '.join(FIELDS[kind])}.")
    for field, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} requires a non-empty string.")
        if field in TIME_FIELDS:
            check_time(value)


def check_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.isoformat(sep=" ", timespec="minutes") == value and parsed.tzinfo is None:
            return
    except (TypeError, ValueError):
        pass
    raise ValueError("Time must be a valid YYYY-MM-DD HH:MM value.")


class RecordManager:
    def __init__(self):
        self._records = {}
        self._next_id = 1

    def create(self, kind, fields):
        check_fields(kind, fields)
        record_id = self._next_id
        if kind == "note":
            rec = Note(record_id, fields["text"].strip())
        elif kind == "task":
            rec = Task(record_id, fields["description"].strip(), fields["deadline"].strip())
        elif kind == "event":
            rec = Event(record_id, fields["description"].strip(), fields["start"].strip(), fields["alarm"].strip())
        elif kind == "contact":
            rec = Contact(record_id, fields["name"].strip(), fields["address"].strip(), fields["mobile"].strip())
        else:
            raise ValueError("Unknown record type.")
        self._records[record_id] = rec
        self._next_id += 1
        return record_id

    def get(self, record_id):
        if record_id not in self._records:
            raise KeyError(f"Record with ID {record_id} not found.")
        return self._records[record_id].to_dict()

    def list_records(self):
        return [self.get(rec_id) for rec_id in sorted(self._records)]

    def update(self, record_id, field, value):
        if record_id not in self._records:
            raise KeyError(f"Record with ID {record_id} not found.")
        rec = self._records[record_id]
        kind = rec.type
        current_fields = {k: v for k, v in rec.to_dict().items() if k not in ("id", "type")}
        current_fields[field] = value
        check_fields(kind, current_fields)
        rec.update(**{field: value.strip()})

    def delete(self, record_id):
        if record_id not in self._records:
            raise KeyError(f"Record with ID {record_id} not found.")
        del self._records[record_id]

    def snapshot(self):
        return {"next_id": self._next_id, "records": self.list_records()}

    def replace_snapshot(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise ValueError("Expected a list of records in the .pim file.")
        new_records = {}
        for item in data["records"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid record in the .pim file.")
            rec_id = item.get("id")
            if type(rec_id) is not int or rec_id <= 0 or rec_id in new_records:
                raise ValueError("Record IDs must be unique positive integers.")
            kind = item.get("type")
            fields = {k: v for k, v in item.items() if k not in ("id", "type")}
            check_fields(kind, fields)
            if kind == "note":
                rec = Note(rec_id, fields["text"].strip())
            elif kind == "task":
                rec = Task(rec_id, fields["description"].strip(), fields["deadline"].strip())
            elif kind == "event":
                rec = Event(rec_id, fields["description"].strip(), fields["start"].strip(), fields["alarm"].strip())
            elif kind == "contact":
                rec = Contact(rec_id, fields["name"].strip(), fields["address"].strip(), fields["mobile"].strip())
            new_records[rec_id] = rec
        next_id = data.get("next_id")
        if type(next_id) is not int or next_id <= max(new_records, default=0):
            raise ValueError("Invalid next ID in the .pim file.")
        self._records = new_records
        self._next_id = next_id