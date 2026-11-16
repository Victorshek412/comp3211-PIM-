"""Keyboard editing and parsing contracts for the live date field."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

from view import terminal_view as view


class DateInputTests(unittest.TestCase):
    def buffer(self, text='', mode='datetime'):
        from view.date_input import DateBuffer
        buffer = DateBuffer(mode)
        for char in text:
            buffer.feed(char)
        return buffer

    def test_separators_appear_before_enter(self):
        buffer = self.buffer()
        for digits, expected in [('2026', '2026-'), ('12', '2026-12-'),
                                 ('05', '2026-12-05 '), ('18', '2026-12-05 18:'),
                                 ('00', '2026-12-05 18:00')]:
            for char in digits:
                buffer.feed(char)
            self.assertEqual(buffer.display()[0], expected)

    def test_backspace_crosses_auto_separator_and_removes_digit(self):
        buffer = self.buffer('202612')
        buffer.feed('BACKSPACE')
        self.assertEqual(buffer.display()[0], '2026-1')
        buffer.feed('1')
        self.assertEqual(buffer.display()[0], '2026-11-')

    def test_arrow_delete_and_insertion_edit_the_date(self):
        buffer = self.buffer('202612051800')
        buffer.feed('HOME')
        for _ in range(3):
            buffer.feed('RIGHT')
        buffer.feed('DELETE')
        buffer.feed('7')
        self.assertEqual(buffer.display()[0], '2027-12-05 18:00')
        buffer.feed('END')
        buffer.feed('LEFT')
        buffer.feed('BACKSPACE')
        buffer.feed('3')
        self.assertEqual(buffer.display()[0], '2027-12-05 18:30')

    def test_formatted_input_does_not_duplicate_separators(self):
        self.assertEqual(self.buffer('2026-12-05 18:00').display()[0], '2026-12-05 18:00')
        self.assertEqual(self.buffer('17:30').display()[0], '17:30')
        self.assertEqual(self.buffer('/cancel').display()[0], '/cancel')

    def test_pasted_date_and_newlines_cannot_submit_commands(self):
        buffer = self.buffer()
        buffer.paste('2026-12-05 18:00')
        self.assertEqual(buffer.display()[0], '2026-12-05 18:00')
        buffer = self.buffer()
        buffer.paste('2026-12-05 18:00\nexit')
        self.assertNotIn('\n', buffer.display()[0])
        self.assertIn('exit', buffer.display()[0])

    def test_date_and_time_follow_up_masks(self):
        self.assertEqual(self.buffer('20261205', 'date').display()[0], '2026-12-05')
        self.assertEqual(self.buffer('1800', 'time').display()[0], '18:00')

    def test_manual_spaces_preserve_supported_legacy_input(self):
        for value, mode in [('2026 12 05 18:00', 'datetime'),
                            ('2026 9 5', 'datetime'), ('18 00', 'time')]:
            with self.subTest(value=value):
                self.assertEqual(self.buffer(value, mode).display()[0], value)

    @unittest.skipUnless(os.name == 'posix', 'POSIX keyboard reader')
    def test_escape_does_not_swallow_next_control_or_ordinary_key(self):
        from view.date_input import _key
        for value, expected in [(b'\x1b\x03', '\x03'), (b'\x1b2', '2'),
                                (b'\x1b[\x03', '\x03')]:
            with self.subTest(value=value):
                reader, writer = os.pipe()
                try:
                    os.write(writer, value)
                    os.close(writer)
                    self.assertEqual(_key(reader), expected)
                finally:
                    os.close(reader)

    def test_non_tty_fallback_accepts_compact_dates_and_still_validates(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch('builtins.input', side_effect=[
                '202602301800', '202612051800']):
            result = view.read_datetime('Deadline')
        self.assertEqual(result, '2026-12-05 18:00')
        self.assertIn('February', out.getvalue())

    def test_compact_date_then_time_and_default_partial_update(self):
        with contextlib.redirect_stdout(io.StringIO()), \
                patch('builtins.input', side_effect=['20261205', '1800']):
            self.assertEqual(view.read_datetime('Deadline'), '2026-12-05 18:00')
        with patch('builtins.input', return_value='17:00'):
            self.assertEqual(view.read_datetime('Deadline', '2026-12-05 18:00'),
                             '2026-12-05 17:00')


if __name__ == '__main__':
    unittest.main()
