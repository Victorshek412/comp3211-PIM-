"""Prompt behavior: defaults, validation, navigation and multiline content."""
import contextlib
import io
import unittest
from unittest.mock import patch

from view import terminal_view as view
from view.terminal_view import Back, Cancelled


def run(function, *answers, **kwargs):
    prompts, feed, output = [], iter(answers), io.StringIO()
    def input_line(prompt):
        prompts.append(prompt)
        return next(feed)
    with patch('builtins.input', input_line), contextlib.redirect_stdout(output):
        result = function(**kwargs)
    return result, output.getvalue(), prompts


class PromptTests(unittest.TestCase):
    def test_notes_preserve_content_and_refuse_empty_body(self):
        cases = [(('buy milk', '/done'), 'buy milk'),
                 (('one', '', 'two', '/done'), 'one\n\ntwo'),
                 (('path\\', '/done'), 'path\\'),
                 (('   ', '/done', 'ok', '/done'), 'ok')]
        for answers, expected in cases:
            with self.subTest(answers=answers):
                result, out, prompts = run(view.read_note, *answers)
                self.assertEqual(result, expected)
                self.assertTrue(all(p == '> ' for p in prompts))
                if answers[0] == '   ':
                    self.assertIn('cannot be blank', out)

    def test_navigation_leaves_each_prompt(self):
        for function, kwargs in [(view.read_note, {}), (view.read_date, {'label': 'Due'}),
                                  (view.read_datetime, {'label': 'Due'})]:
            for answer, error in [('/back', Back), ('/cancel', Cancelled)]:
                with self.subTest(function=function.__name__, answer=answer), self.assertRaises(error):
                    run(function, answer, **kwargs)

    def test_confirm_defaults_and_invalid_answer(self):
        for answer, expected in [('', False), ('n', False), ('no', False), ('YES', True)]:
            with self.subTest(answer=answer):
                result, _, prompts = run(view.confirm, answer, prompt='Delete?')
                self.assertEqual(result, expected)
                self.assertEqual(prompts, ['Delete? [y/N] '])
        result, out, _ = run(view.confirm, 'maybe', 'y', prompt='Sure?')
        self.assertTrue(result)
        self.assertIn('Please type Y or N.', out)

    def test_pick_accepts_letter_or_word_and_retries_unknown_choice(self):
        options = (('s', 'save'), ('d', 'discard'), ('c', 'cancel'))
        for answer, expected in [('S', 'save'), (' Discard ', 'discard')]:
            self.assertEqual(run(view.pick, answer, prompt='?', options=options)[0], expected)
        result, out, _ = run(view.pick, 'x', 'c', prompt='?', options=options)
        self.assertEqual(result, 'cancel')
        self.assertIn('Please type S, D or C.', out)

    def test_menu_choice_record_id_and_validation(self):
        options = [('a', 'A'), ('b', 'B')]
        self.assertEqual(run(view.choose, '2', title='t', options=options)[0], 'b')
        result, out, prompts = run(view.choose, '9', '1', title='t', options=options)
        self.assertEqual(result, 'a')
        self.assertIn('Please enter a number from the list.', out)
        self.assertEqual(prompts[0], 'Choice: ')
        result, out, prompts = run(view.choose, '#5', title='t', options=[(5, 'Five')])
        self.assertEqual(result, 5)
        self.assertIn('#5  Five', out)
        self.assertEqual(prompts, ['Record: '])
        with self.assertRaises(Back):
            run(view.choose, '0', title='t', options=options)
        with self.assertRaises(ValueError):
            view.choose('t', [])

    def test_text_defaults_and_safe_menu_labels(self):
        result, _, prompts = run(view.read_text, '', label='Filename', default='data.pim')
        self.assertEqual(result, 'data.pim')
        self.assertEqual(prompts, ['Filename [data.pim]: '])
        for answer, expected in [('', 'd'), ('x', 'x')]:
            self.assertEqual(run(view.ask, answer, prompt='p', default='d')[0], expected)
        out = run(view.choose, '1', title='t\x1b[2J', options=[('a', 'bad\x1b[31mred')])[1]
        self.assertNotIn('\x1b', out)


class DateTimeTests(unittest.TestCase):
    def test_full_partial_default_and_back_inputs(self):
        default = '2026-11-30 18:00'
        cases = [(('2026-11-30 18:00',), None, default),
                 (('2026-11-30', '18:00'), None, default),
                 (('18:00', '2026-11-30'), None, default),
                 (('',), default, default),
                 (('09:05',), default, '2026-11-30 09:05'),
                 (('2026-12-01',), default, '2026-12-01 18:00'),
                 (('2026 12 01 07:30',), default, '2026-12-01 07:30'),
                 (('', '2026-11-30', '', '09:00'), None, '2026-11-30 09:00'),
                 (('2026-11-30', '/back', '2026-12-01 10:00'), None, '2026-12-01 10:00'),
                 (('18:00', '/back', '2026-12-01 10:00'), None, '2026-12-01 10:00')]
        for answers, previous, expected in cases:
            with self.subTest(answers=answers):
                result, _, prompts = run(view.read_datetime, *answers, label='Due', default=previous)
                self.assertEqual(result, expected)
                self.assertEqual(prompts[0], f'Due [{previous}]: ' if previous else 'Due (YYYY-MM-DD HH:MM): ')
                if answers == ('2026-11-30', '18:00'):
                    self.assertEqual(prompts[1], 'Due time (HH:MM): ')
                if answers == ('18:00', '2026-11-30'):
                    self.assertEqual(prompts[1], 'Due date (YYYY-MM-DD): ')
                if '/back' in answers:
                    self.assertEqual(prompts[2], prompts[0])

    def test_invalid_date_time_and_words_retry(self):
        result, out, _ = run(view.read_datetime, '2026-06-31 10:00', '2026-06-30 25:00',
                             'tomorrow', '2026-06-30 07:30', label='Due')
        self.assertEqual(result, '2026-06-30 07:30')
        for hint in ('June has 30 days', 'Use HH:MM', 'Type a date like'):
            self.assertIn(hint, out)
        result, out, _ = run(view.read_datetime, '2026-11-30', '25:00', '07:30', label='Due')
        self.assertEqual(result, '2026-11-30 07:30')
        self.assertIn('Use HH:MM', out)

    def test_date_input_formats_and_field_specific_retry(self):
        cases = [(('2026-09-05',), '2026-09-05', ''),
                 (('2026 9 5',), '2026-09-05', ''),
                 (('', '2026-01-02'), '2026-01-02', ''),
                 (('tomorrow', '2026-01-02'), '2026-01-02', 'such as 2026-09-05'),
                 (('2026-06-31', '15'), '2026-06-15', 'June has 30 days'),
                 (('26-01-01', '2026-13-01', '12'), '2026-12-01', 'month from 1 to 12')]
        for answers, expected, hint in cases:
            with self.subTest(answers=answers):
                result, out, prompts = run(view.read_date, *answers, label='Due')
                self.assertEqual(result.isoformat(), expected)
                self.assertIn(hint, out)
                if answers[0] == '2026-06-31':
                    self.assertEqual(prompts[1], 'Due date: enter the day: ')
                if answers[0] == '26-01-01':
                    self.assertIn('four-digit year', out)


class StepsTests(unittest.TestCase):
    def test_forms_reopen_at_invalid_field_without_injecting_tips(self):
        seen = []
        steps = [lambda values: 'x', lambda values: seen.append(list(values)) or 'y']
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(view.read_steps(steps, values=['kept', 'old'], start=1), ['kept', 'y'])
            self.assertEqual(seen, [['kept', 'old']])
            self.assertEqual(view.read_steps(steps), ['x', 'y'])
            self.assertEqual(view.read_steps(steps[:1]), ['x'])
        self.assertEqual(out.getvalue(), '')

    def test_back_revisits_previous_step_and_propagates_from_first(self):
        calls = []
        def second(values):
            calls.append('second')
            if len(calls) == 1:
                raise Back
            return 'b'
        def back(values):
            raise Back
        self.assertEqual(view.read_steps([lambda v: 'a', second]), ['a', 'b'])
        with self.assertRaises(Back):
            view.read_steps([back])


if __name__ == '__main__':
    unittest.main()
