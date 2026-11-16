"""Unit tests for model.record_manager (Part A)."""
import unittest

from model.record_manager import FieldError, RecordManager

NOTE = {"text": "Buy milk"}
TASK = {"description": "Submit report", "deadline": "2026-11-20 20:00"}
EVENT = {"description": "Meeting", "start_time": "2026-11-18 09:00", "alarm": "2026-11-18 08:30"}
CONTACT = {"name": "Alice", "address": "PolyU", "mobile": "91234567"}


class CreateTests(unittest.TestCase):
    def test_create_all_types_returns_sequential_ids(self):  # US1-US5
        m = RecordManager()
        ids = [m.create(k, f) for k, f in
               (("note", NOTE), ("task", TASK), ("event", EVENT), ("contact", CONTACT))]
        self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual(m.get(3), {"id": 3, "type": "event", **EVENT})

    def test_values_are_stripped(self):
        """Leading and trailing spaces are removed from stored values."""
        m = RecordManager()
        rid = m.create("note", {"text": "  hi  "})
        self.assertEqual(m.get(rid)["text"], "hi")

    def test_invalid_input_is_rejected_and_consumes_no_id(self):  # field validation
        m = RecordManager()
        bad = [("memo", NOTE), ("note", {}), ("note", {"text": "  "}), ("note", {"text": 5}),
               ("note", {"text": "x", "extra": "y"}), ("note", None),
               ("task", {**TASK, "deadline": "2026-02-30 10:00"}),
               ("task", {**TASK, "deadline": "2026-11-20"}),
               ("task", {**TASK, "deadline": "2026-11-20T20:00"}),
               ("task", {**TASK, "deadline": "2026-11-20 20:00+08:00"}),
               (None, NOTE)]
        for kind, fields in bad:
            with self.subTest(kind=kind, fields=fields):
                with self.assertRaises(ValueError):
                    m.create(kind, fields)
        self.assertEqual(m.create("note", NOTE), 1)

    def test_ids_are_never_reused_after_delete(self):  # unique IDs
        m = RecordManager()
        m.create("note", NOTE)
        m.create("note", NOTE)
        m.delete(2)
        self.assertEqual(m.create("note", NOTE), 3)


class AlarmRuleTests(unittest.TestCase):
    """An event's alarm must not be later than its start time."""

    def test_alarm_before_or_equal_to_start_is_accepted(self):
        """Alarm earlier than, or equal to, the start time creates the event."""
        m = RecordManager()
        m.create("event", {**EVENT, "alarm": "2026-11-18 09:00"})
        m.create("event", {**EVENT, "alarm": "2026-11-17 09:00"})
        self.assertEqual(len(m.list_records()), 2)

    def test_alarm_after_start_is_rejected_on_create(self):
        """Alarm later than the start time raises ValueError and consumes no ID."""
        m = RecordManager()
        with self.assertRaisesRegex(ValueError, "[Aa]larm"):
            m.create("event", {**EVENT, "alarm": "2026-11-18 09:01"})
        self.assertEqual(m.create("note", NOTE), 1)

    def test_update_cannot_break_the_rule(self):
        """Moving the alarm after the start, or the start before the alarm, is refused."""
        m = RecordManager()
        m.create("event", EVENT)
        with self.assertRaises(ValueError):
            m.update(1, "alarm", "2026-11-18 09:30")
        with self.assertRaises(ValueError):
            m.update(1, "start_time", "2026-11-18 08:00")
        self.assertEqual(m.get(1)["alarm"], "2026-11-18 08:30")
        m.update(1, "start_time", "2026-11-19 09:00")  # later start is fine
        self.assertEqual(m.get(1)["start_time"], "2026-11-19 09:00")

    def test_snapshot_with_late_alarm_is_rejected(self):
        """A loaded file that breaks the rule is refused as a whole."""
        m = RecordManager()
        bad = {"next_id": 2, "records": [{"id": 1, "type": "event", **EVENT,
                                           "alarm": "2026-11-18 10:00"}]}
        with self.assertRaises(ValueError):
            m.replace_snapshot(bad)


class MobileRuleTests(unittest.TestCase):
    """A mobile number is 3-15 digits, optional leading +, spaces or hyphens between digit groups."""

    def test_valid_numbers_are_accepted(self):
        """Plain, international, spaced and hyphenated numbers are stored."""
        m = RecordManager()
        for number in ("91234567", "+852 9123 4567", "+852-9123-4567", "123", "123456789012345"):
            with self.subTest(number=number):
                rid = m.create("contact", {**CONTACT, "mobile": number})
                self.assertEqual(m.get(rid)["mobile"], number)

    def test_invalid_numbers_are_rejected(self):
        """Letters, symbols, too few or too many digits, and stray separators raise ValueError."""
        m = RecordManager()
        for number in ("call me maybe", "abc", "12", "+", "++85212345678", "1234567890123456",
                       "9123_4567", "９１２３４５６７", "-9123", "9123--4567", "(852) 91234567",
                       "9123 ", "+852 "):
            if number.strip() != number:
                continue  # surrounding spaces are stripped, so these are valid, not invalid
            with self.subTest(number=number):
                with self.assertRaises(ValueError):
                    m.create("contact", {**CONTACT, "mobile": number})

    def test_update_mobile_is_validated(self):
        """Editing a contact's mobile applies the same rule and keeps the old value on error."""
        m = RecordManager()
        m.create("contact", CONTACT)
        with self.assertRaises(ValueError):
            m.update(1, "mobile", "not a number")
        self.assertEqual(m.get(1)["mobile"], "91234567")
        m.update(1, "mobile", "+44 20 7946 0958")
        self.assertEqual(m.get(1)["mobile"], "+44 20 7946 0958")


class FieldErrorTests(unittest.TestCase):
    def test_validation_errors_name_the_field_to_fix(self):
        """Rule violations raise FieldError whose .field is the field a form should ask again."""
        m = RecordManager()
        cases = [("event", {**EVENT, "alarm": "2026-11-18 10:00"}, "alarm"),
                 ("contact", {**CONTACT, "mobile": "abc"}, "mobile"),
                 ("task", {**TASK, "deadline": "soon"}, "deadline"),
                 ("task", {**TASK, "description": " "}, "description")]
        for kind, fields, expected in cases:
            with self.subTest(field=expected), self.assertRaises(FieldError) as ctx:
                m.create(kind, fields)
            self.assertEqual(ctx.exception.field, expected)
            self.assertIsInstance(ctx.exception, ValueError)  # existing callers keep working


class ReadUpdateDeleteTests(unittest.TestCase):
    def setUp(self):
        self.m = RecordManager()
        self.m.create("task", TASK)

    def test_get_unknown_id_raises_keyerror_with_the_id(self):
        """get() of a missing ID raises KeyError whose argument is that ID."""
        with self.assertRaises(KeyError) as ctx:
            self.m.get(99)
        self.assertEqual(ctx.exception.args[0], 99)

    def test_get_returns_a_copy(self):  # callers cannot corrupt the model
        self.m.get(1)["description"] = "hacked"
        self.assertEqual(self.m.get(1)["description"], "Submit report")

    def test_list_records_sorted_by_id(self):
        """list_records() returns records in ascending ID order."""
        self.m.create("note", NOTE)
        self.assertEqual([r["id"] for r in self.m.list_records()], [1, 2])

    def test_update_changes_one_field(self):  # US6
        self.m.update(1, "deadline", "2026-12-01 10:00")
        self.assertEqual(self.m.get(1)["deadline"], "2026-12-01 10:00")
        self.assertEqual(self.m.get(1)["description"], "Submit report")

    def test_update_rejects_bad_value_and_keeps_old(self):
        """An invalid update (bad time, blank text, wrong field) raises ValueError and keeps the old value."""
        for field, value in (("deadline", "tomorrow"), ("description", " "), ("name", "x")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.m.update(1, field, value)
        self.assertEqual(self.m.get(1)["deadline"], "2026-11-20 20:00")

    def test_update_unknown_id(self):
        """update() of a missing ID raises KeyError."""
        with self.assertRaises(KeyError):
            self.m.update(5, "description", "x")

    def test_delete(self):  # US9
        self.m.delete(1)
        self.assertEqual(self.m.list_records(), [])
        with self.assertRaises(KeyError):
            self.m.delete(1)


class SnapshotTests(unittest.TestCase):
    def test_roundtrip_preserves_ids_and_counter(self):
        """snapshot() then replace_snapshot() restores records, IDs and the next-ID counter."""
        a = RecordManager()
        a.create("note", NOTE)
        a.create("task", TASK)
        a.delete(2)
        b = RecordManager()
        b.replace_snapshot(a.snapshot())
        self.assertEqual(b.list_records(), a.list_records())
        self.assertEqual(b.create("note", NOTE), 3)

    def test_empty_snapshot_is_valid(self):
        """A snapshot with no records is valid and empties the manager."""
        m = RecordManager()
        m.create("note", NOTE)
        m.replace_snapshot({"next_id": 1, "records": []})
        self.assertEqual(m.list_records(), [])

    def test_invalid_snapshot_leaves_state_unchanged(self):
        """Twelve kinds of malformed snapshot raise ValueError and change nothing."""
        m = RecordManager()
        m.create("note", NOTE)
        good = {"id": 1, "type": "note", "text": "a"}
        bad = [None, {}, {"records": "x", "next_id": 2}, {"records": [5], "next_id": 2},
               {"records": [good, good], "next_id": 3},
               {"records": [{**good, "id": 0}], "next_id": 2},
               {"records": [{**good, "id": True}], "next_id": 2},
               {"records": [{**good, "text": ""}], "next_id": 2},
               {"records": [{"id": 1, "type": "memo"}], "next_id": 2},
               {"records": [good], "next_id": 1},
               {"records": [good], "next_id": "2"},
               {"records": [good]}]
        for data in bad:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    m.replace_snapshot(data)
        self.assertEqual(m.get(1)["text"], "Buy milk")


if __name__ == "__main__":
    unittest.main()
