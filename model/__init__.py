"""Record fields shared by the Part C view and the demo service."""

FIELDS = {
    "note": ("text",),
    "task": ("description", "deadline"),
    "event": ("description", "start", "alarm"),
    "contact": ("name", "address", "mobile"),
}
TIME_FIELDS = ("deadline", "start", "alarm")
