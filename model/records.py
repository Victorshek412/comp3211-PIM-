"""PIR classes. Which fields each type has is listed once, in model.FIELDS."""

from . import FIELDS, RecordData


class Record:
    """Base class of every personal information record (PIR)."""

    def __init__(self, record_id: int, record_type: str) -> None:
        self.id = record_id
        self.type = record_type

    def to_dict(self) -> RecordData:
        """Return the record as {"id", "type", <fields>}; the result is a copy."""
        data: RecordData = {"id": self.id, "type": self.type}
        data.update({name: getattr(self, name) for name in FIELDS[self.type]})
        return data


class Note(Record):
    """Plain text for quick notes (US2)."""

    def __init__(self, record_id: int, text: str) -> None:
        super().__init__(record_id, "note")
        self.text = text


class Task(Record):
    """A to-do with a description and a deadline (US3)."""

    def __init__(self, record_id: int, description: str, deadline: str) -> None:
        super().__init__(record_id, "task")
        self.description = description
        self.deadline = deadline


class Event(Record):
    """A scheduled event with a start time and an alarm (US4)."""

    def __init__(self, record_id: int, description: str, start_time: str, alarm: str) -> None:
        super().__init__(record_id, "event")
        self.description = description
        self.start_time = start_time
        self.alarm = alarm


class Contact(Record):
    """A person with a name, an address and a mobile number (US5)."""

    def __init__(self, record_id: int, name: str, address: str, mobile: str) -> None:
        super().__init__(record_id, "contact")
        self.name = name
        self.address = address
        self.mobile = mobile
