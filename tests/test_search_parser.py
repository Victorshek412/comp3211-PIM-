"""Unit tests for model.search_parser: the typed `search where ...` syntax."""
import unittest

from model.record_manager import RecordManager
from model.search import search_records
from model.search_parser import keywords_condition, parse_condition

T = "2026-12-01 09:00"


class ParseTests(unittest.TestCase):
    def test_type_condition(self):
        """type = task becomes ("type", "task"); keywords and the type name ignore case."""
        self.assertEqual(parse_condition("type = task"), ("type", "task"))
        self.assertEqual(parse_condition("TYPE=Contact"), ("type", "contact"))

    def test_contains_condition(self):
        """FIELD contains "text" becomes a contains condition."""
        self.assertEqual(parse_condition('description contains "annual report"'),
                         ("contains", "description", "annual report"))

    def test_time_conditions(self):
        """FIELD < / = / > "time" become time conditions."""
        for op in "<=>":
            with self.subTest(op=op):
                self.assertEqual(parse_condition(f'deadline {op} "{T}"'),
                                 ("time", "deadline", op, T))

    def test_and_or_not_symbols(self):
        """&&, || and ! map to and, or and not."""
        self.assertEqual(parse_condition('type = task && !description contains "x"'),
                         ("and", ("type", "task"), ("not", ("contains", "description", "x"))))
        self.assertEqual(parse_condition("type = task || type = note"),
                         ("or", ("type", "task"), ("type", "note")))

    def test_precedence_not_over_and_over_or(self):
        """a || b && c means a || (b && c); and && is left-associative."""
        got = parse_condition("type = note || type = task && type = event")
        self.assertEqual(got, ("or", ("type", "note"), ("and", ("type", "task"), ("type", "event"))))
        got = parse_condition('name contains "a" && name contains "b" && name contains "c"')
        self.assertEqual(got[0], "and")
        self.assertEqual(got[1][0], "and")

    def test_parentheses_override_precedence(self):
        """Parentheses group a condition; !(...) negates the whole group."""
        got = parse_condition("(type = note || type = task) && type = event")
        self.assertEqual(got, ("and", ("or", ("type", "note"), ("type", "task")), ("type", "event")))
        self.assertEqual(parse_condition("!(type = note || type = task)")[0], "not")

    def test_string_escapes_and_special_characters(self):
        """Inside quotes, \\" and \\\\ are escapes; | && ( ) need no escaping."""
        self.assertEqual(parse_condition(r'text contains "say \"hi\" a|b && (c)"'),
                         ("contains", "text", 'say "hi" a|b && (c)'))
        self.assertEqual(parse_condition(r'text contains "back\\slash"'),
                         ("contains", "text", "back\\slash"))

    def test_whitespace_is_flexible(self):
        """Extra spaces and none around symbols are fine."""
        self.assertEqual(parse_condition('  type=task&&!type=note '),
                         ("and", ("type", "task"), ("not", ("type", "note"))))

    def test_syntax_errors_report_a_position(self):
        """Each malformed condition raises ValueError whose message says where."""
        bad = ["", "   ", "type", "type =", "type = memo", "type task", "foo contains \"x\"",
               'deadline contains "x"', 'description < "2026-12-01 09:00"',
               'deadline < "tomorrow"', 'deadline < "2026-1-5 9:5"', 'deadline < 5',
               'description contains x', 'description contains "unterminated',
               "type = task &&", "&& type = task", "type = task type = note",
               "(type = task", "type = task)", "()", "type = task # note", "type == task",
               'name contains "a" || ', "! ", "type = task ||| type = note"]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as ctx:
                    parse_condition(text)
                message = str(ctx.exception).lower()
                self.assertTrue("position" in message or not text.strip(), message)

    def test_unknown_field_error_lists_valid_fields(self):
        """An unknown field name tells the user what is allowed."""
        with self.assertRaises(ValueError) as ctx:
            parse_condition('descr contains "x"')
        self.assertIn("description", str(ctx.exception))
        self.assertIn("position 1", str(ctx.exception))

    def test_error_messages_end_with_the_position_in_brackets(self):
        """Messages read "... (at position N)" with no stray full stop before the bracket."""
        with self.assertRaises(ValueError) as ctx:
            parse_condition('deadline < "tomorrow"')
        self.assertEqual(str(ctx.exception), "Time must be a valid YYYY-MM-DD HH:MM value (at position 12)")

    def test_non_string_input_is_rejected(self):
        """parse_condition(None) raises ValueError instead of crashing."""
        with self.assertRaises(ValueError):
            parse_condition(None)

    def test_overlong_condition_is_rejected(self):
        """A condition with more than 200 tokens raises ValueError (protects recursion)."""
        text = " && ".join(["type = task"] * 100)
        with self.assertRaises(ValueError):
            parse_condition(text)
        deep = "(" * 150 + "type = task" + ")" * 150
        with self.assertRaises(ValueError):
            parse_condition(deep)

    def test_deeply_nested_parentheses_give_a_clear_error(self):
        """41 or more nested parentheses (with or without a body) raise ValueError, never another exception."""
        for text in ("(" * 41, "(" * 45, "(" * 45 + "type = task" + ")" * 45):
            with self.subTest(length=len(text)), self.assertRaises(ValueError) as ctx:
                parse_condition(text)
            self.assertIn("nested", str(ctx.exception))

    def test_group_closed_by_the_wrong_token(self):
        """A group not closed by ")" (here a second condition without && ) names the bad position."""
        with self.assertRaises(ValueError) as ctx:
            parse_condition("(type = task type = note)")
        self.assertIn('Expected ")"', str(ctx.exception))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        m = RecordManager()
        m.create("task", {"description": "Annual report", "deadline": "2026-11-20 20:00"})  # 1
        m.create("task", {"description": "Buy milk", "deadline": "2027-01-01 08:00"})       # 2
        m.create("note", {"text": "report ideas | draft"})                                  # 3
        m.create("contact", {"name": "Alice", "address": "Hung Hom", "mobile": "91234567"})  # 4
        self.rows = m.list_records()

    def ids(self, text):
        return [r["id"] for r in search_records(self.rows, parse_condition(text))]

    def test_example_searches(self):
        """Typed conditions return the expected record IDs."""
        self.assertEqual(self.ids('type = task && deadline < "2026-12-01 00:00"'), [1])
        self.assertEqual(self.ids('description contains "report" || text contains "report"'), [1, 3])
        self.assertEqual(self.ids('!(type = task) && !(type = contact)'), [3])
        self.assertEqual(self.ids('text contains "a | d"'), [])
        self.assertEqual(self.ids('text contains "ideas | draft"'), [3])  # literal | is searchable


class KeywordTests(unittest.TestCase):
    def setUp(self):
        m = RecordManager()
        m.create("note", {"text": "buy milk"})                                    # 1
        m.create("task", {"description": "eggs", "deadline": "2026-11-20 20:00"})  # 2
        m.create("contact", {"name": "Milk Man", "address": "A", "mobile": "123"})  # 3
        self.rows = m.list_records()

    def ids(self, text):
        return [r["id"] for r in search_records(self.rows, keywords_condition(text))]

    def test_keyword_searches_every_text_field_ignoring_case(self):
        """"MILK" finds the note and the contact whatever the capitals."""
        self.assertEqual(self.ids("MILK"), [1, 3])

    def test_pipe_means_either_phrase(self):
        """"milk | eggs" finds records with either phrase."""
        self.assertEqual(self.ids("milk | eggs"), [1, 2, 3])

    def test_blank_keywords_match_every_record(self):
        """Blank text selects every record of every type."""
        self.assertEqual(self.ids(""), [1, 2, 3])
        self.assertEqual(self.ids("   "), [1, 2, 3])

    def test_empty_phrase_is_rejected(self):
        """A missing phrase around | ("milk |", "| milk", "a || b") raises ValueError."""
        for text in ("milk |", "| milk", "a || b"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                keywords_condition(text)

    def test_many_phrases_do_not_exhaust_the_recursion_limit(self):
        """Hundreds of phrases still build a shallow tree and search without error."""
        text = " | ".join(f"word{i}" for i in range(500))
        self.assertEqual(self.ids(text + " | eggs"), [2])


if __name__ == "__main__":
    unittest.main()
