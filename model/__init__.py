"""Model layer: records, validation, search and .pim storage. No terminal input or output."""

from typing import Any, Dict, Tuple

# A record as plain data: {"id": int, "type": str, <one entry per field of that type>}.
RecordData = Dict[str, Any]
# A search condition: nested tuples, see model.search.
Condition = Tuple[Any, ...]

# The one place that lists which fields each record type has.
FIELDS = {
    "note": ("text",),
    "task": ("description", "deadline"),
    "event": ("description", "start_time", "alarm"),
    "contact": ("name", "address", "mobile"),
}
TIME_FIELDS = ("deadline", "start_time", "alarm")

# Every field that holds free text (searchable with "contains"): derived, never hand-listed.
TEXT_FIELDS = tuple(dict.fromkeys(
    name for names in FIELDS.values() for name in names if name not in TIME_FIELDS))
