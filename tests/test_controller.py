"""CLI workflows: real prompts/model/files, with only keyboard input simulated."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from controller.commands import Controller, HELP, HELP_SEARCH, file_error
from model.record_manager import RecordManager


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(RecordManager())
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(tmp.name)

    def invoke(self, function, *answers):
        self.prompts = []
        feed, output = iter(answers), io.StringIO()

        def input_line(prompt):
            self.prompts.append(prompt)
            answer = next(feed)
            if isinstance(answer, type) and issubclass(answer, BaseException):
                raise answer
            return answer

        with patch('builtins.input', input_line), contextlib.redirect_stdout(output):
            result = function()
        return result, output.getvalue()

    def command(self, line, *answers):
        return self.invoke(lambda: self.c.execute(line), *answers)

    def session(self, *answers):
        return self.invoke(self.c.run, *answers)

    def test_help_and_invalid_commands(self):
        self.assertTrue(self.command('   ')[0])
        for command, expected in [('help', 'add note buy milk'), ('help search', 'deadline < ')]:
            with self.subTest(command=command):
                self.assertIn(expected, self.command(command)[1])
        self.assertIn('help search', HELP)
        self.assertLessEqual(len(HELP.splitlines()), 13)
        self.assertLessEqual(len(HELP_SEARCH.splitlines()), 7)
        self.assertTrue(all(len(line) < 80 for line in (HELP + '\n' + HELP_SEARCH).splitlines()))
        for command in ('help colours', 'frobnicate', 'exit now', 'add memo', 'delete',
                        'view abc', 'view 0', 'view -1', 'view ٣', 'view ##1'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.command(command)
        with self.assertRaisesRegex(ValueError, 'Only notes'):
            self.command('add task buy milk')
        for command, hint in [('view2', 'view #2'), ('edit2', 'edit #2')]:
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, hint):
                self.command(command)
        with self.assertRaises(KeyError) as error:
            self.command('view #42')
        self.assertEqual(error.exception.args, (42,))

    def test_empty_collection_commands(self):
        for command in ('view', 'view all', 'edit', 'search milk'):
            with self.subTest(command=command):
                self.assertIn('No records yet', self.command(command)[1])

    def test_quick_and_multiline_notes(self):  # US2: preserve text; no duplicate dump
        out = self.command('add note Buy Milk')[1]
        self.assertEqual(self.c.records.get(1)['text'], 'Buy Milk')
        self.assertEqual(out.strip(), 'Created note #1.')
        self.command('add note', '你好 hello', '', 'path\\', '/done')
        self.assertEqual(self.c.records.get(2)['text'], '你好 hello\n\npath\\')
        self.assertIn('Text:\n你好 hello\n\npath\\', self.command('view #2')[1])
        self.assertTrue(self.c.dirty)

    def test_type_menu_and_forms(self):  # US1, US3-US5: real field defaults and retries
        out = self.command('add', '1', 'from menu', '/done')[1]
        for option in ('1. Note', '2. Task', '3. Event', '4. Contact'):
            self.assertIn(option, out)
        self.assertEqual(self.c.records.get(1)['text'], 'from menu')
        self.command('add task', 'report', '2026-12-05 18:00')
        self.assertEqual(self.c.records.get(2)['deadline'], '2026-12-05 18:00')
        out = self.command('add event', 'Party', '2026-12-05 18:00', '2026-12-05 19:00', '')[1]
        event = self.c.records.get(3)
        self.assertEqual(event['alarm'], event['start_time'])
        self.assertIn('alarm must not be later', out)
        self.assertEqual(sum(p.startswith('Description') for p in self.prompts), 1)
        self.assertEqual(self.prompts[-1], 'Alarm [2026-12-05 18:00]: ')
        out = self.command('add contact', 'Bob', 'HK', 'abc', '+85291234567')[1]
        self.assertIn('3 to 15 digits', out)
        self.assertEqual(self.c.records.get(4)['mobile'], '+85291234567')
        self.assertEqual(sum(p.startswith('Name') for p in self.prompts), 1)
        self.assertEqual(len(self.c.records.list_records()), 4)

    def test_view_one_or_all(self):  # US8: IDs, complete records, blank between frames
        self.command('add note alpha')
        self.command('add note beta')
        for command in ('view 1', 'view #1'):
            with self.subTest(command=command):
                out = self.command(command)[1]
                self.assertIn('alpha', out)
                self.assertNotIn('beta', out)
        for command in ('view', 'view all'):
            out = self.command(command)[1]
            self.assertIn('Text: alpha\n------------------------\n\nNote #2', out)
            self.assertIn('Text: beta', out)

    def test_edit_note_picker_and_unchanged_value(self):  # US6: no field menu for a note
        self.command('add note old')
        self.command('save data')
        self.assertIn('unchanged', self.command('edit #1', 'old', '/done')[1])
        self.assertFalse(self.c.dirty)
        self.command('edit', '#1', 'new', '/done')
        self.assertEqual(self.c.records.get(1)['text'], 'new')
        self.assertNotIn('Field: ', self.prompts)
        self.assertTrue(self.c.dirty)

    def test_edit_task_default_and_only_selected_field_changes(self):
        self.command('add task', 'report', '2026-12-05 18:00')
        self.command('edit 1', '2', '17:30')
        task = self.c.records.get(1)
        self.assertEqual(task['deadline'], '2026-12-05 17:30')
        self.assertEqual(task['description'], 'report')
        self.assertIn('Deadline [2026-12-05 18:00]: ', self.prompts)

    def test_invalid_edit_retries_or_cancels_without_partial_changes(self):
        self.command('add contact', 'Alex', 'HK', '54441002')
        self.command('save data')
        before = self.c.records.snapshot()
        self.session('edit #1', '3', 'abc', '/cancel', 'exit')
        self.assertEqual(self.c.records.snapshot(), before)
        self.assertFalse(self.c.dirty)
        self.command('edit #1', '3', 'abc', '+85254441002')
        self.assertEqual(self.c.records.get(1)['mobile'], '+85254441002')
        self.assertEqual(self.c.records.get(1)['name'], 'Alex')
        self.assertEqual(self.prompts.count('Field: '), 1)

    def test_back_keeps_defaults_and_cancel_does_not_consume_id(self):
        self.command('add task', 'first', '/back', 'second', '2026-12-05 18:00')
        self.assertIn('Description [first]: ', self.prompts)
        self.assertEqual(self.c.records.get(1)['description'], 'second')
        out = self.session('add note', 'unfinished', '/cancel', 'add task', 'report',
                           '/back', '', '/cancel', 'add note kept', 'exit', 'd')[1]
        self.assertEqual(self.c.records.get(2)['text'], 'kept')
        self.assertEqual(len(self.c.records.list_records()), 2)
        self.assertIn('Note creation cancelled.', out)
        self.assertIn('Task creation cancelled.', out)
        self.assertNotIn('Tip:', out)

    def test_delete_requires_confirmation(self):  # US9
        self.command('add note kept')
        self.command('save data')
        for answer in ('', 'n'):
            self.command('delete #1', answer)
            self.assertEqual(self.c.records.get(1)['text'], 'kept')
            self.assertFalse(self.c.dirty)
        self.command('delete 1', 'y')
        self.assertEqual(self.c.records.list_records(), [])
        self.assertTrue(self.c.dirty)

    def test_search_results_and_syntax(self):  # US7: quick/typed search, count and #ID hints
        for text in ('buy milk', 'report one', 'report two', 'whereabouts unknown'):
            self.command('add note ' + text)
        cases = [('search milk', (), 'Text: buy milk', 'Edit: edit #1'),
                 ('search report', (), '#2  Note: report one', '#3  Note: report two'),
                 ('search where text contains "report"', (), 'Search: 2 matches', 'Details: view #ID'),
                 ('search whereabouts', (), 'whereabouts unknown', 'Edit: edit #4'),
                 ('search', ('milk',), 'Text: buy milk', 'Search: 1 match'),
                 ('search', ('',), 'Search: 4 matches', 'Details: view #ID'),
                 ('search zzz', (), 'No matches', 'Search: 0 matches')]
        for command, answers, *expected in cases:
            with self.subTest(command=command, answers=answers):
                out = self.command(command, *answers)[1]
                for text in expected:
                    self.assertIn(text, out)
                if 'report' in command:
                    self.assertNotIn('buy milk', out)
        for command in ('search where type = memo', 'search where', 'search WHERE   ', 'search milk |'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.command(command)

    def test_save_load_chinese_roundtrip_and_filename_default(self):  # US10-US11
        self.command('add note', '你好 hello', '', '第二行', '/done')
        self.command('save', '中文 notes')
        self.assertFalse(self.c.dirty)
        self.command('save', '', 'y')
        self.assertIn('Filename (.pim) [中文 notes.pim]: ', self.prompts)
        self.c = Controller(RecordManager())
        self.command('load 中文 notes')
        self.assertEqual(self.c.records.get(1)['text'], '你好 hello\n\n第二行')
        self.command('add note next')
        self.assertEqual(self.c.records.get(2)['text'], 'next')

    def test_declining_overwrite_or_load_preserves_data(self):
        self.command('add note saved')
        self.command('save data')
        original = Path('data.pim').read_bytes()
        self.command('add note unsaved')
        before = self.c.records.snapshot()
        for command in ('save data', 'load data'):
            with self.subTest(command=command):
                self.assertIn('cancelled', self.command(command, '')[1])
                self.assertEqual(Path('data.pim').read_bytes(), original)
                self.assertEqual(self.c.records.snapshot(), before)
                self.assertTrue(self.c.dirty)

    def test_load_retries_and_invalid_file_preserves_records(self):
        self.command('add note saved')
        self.command('save data')
        self.command('add note unsaved')
        before = self.c.records.snapshot()
        Path('bad.pim').write_text('{broken')
        out = self.command('load bad', 'y')[1]
        self.assertIn('current records are unchanged', out)
        self.assertEqual(self.c.records.snapshot(), before)
        self.assertTrue(self.c.dirty)
        out = self.command('load', 'missing', 'bad', 'y', 'data', 'y')[1]
        self.assertIn('File not found', out)
        self.assertEqual([r['text'] for r in self.c.records.list_records()], ['saved'])
        self.assertFalse(self.c.dirty)

    def test_file_failures_have_plain_messages(self):
        self.command('add note kept')
        Path('dir.pim').mkdir()
        cases = [('load missing', 'File not found.'), ('save missing/x', 'That folder does not exist.'),
                 ('load dir', 'That is a folder, not a file.')]
        for command, expected in cases:
            with self.subTest(command=command):
                answers = ('y',) if command == 'load dir' else ()
                out = self.command(command, *answers)[1]
                self.assertIn(expected, out)
                self.assertNotIn('Errno', out)
                self.assertTrue(self.c.dirty)
        for error, expected in [(PermissionError(13, 'x'), 'Permission denied.'),
                                (IsADirectoryError(21, 'x'), 'That is a folder, not a file.'),
                                (OSError(5, 'Input/output error'), 'Input/output error'),
                                (OSError(), 'The file could not be read or written.')]:
            with self.subTest(error=error):
                self.assertEqual(file_error(error), expected)

    def test_permission_error_retries_filename(self):
        self.command('add note kept')
        exists = Path.exists
        def check(path):
            if str(path) == 'private/blocked.pim':
                raise PermissionError(13, 'Permission denied')
            return exists(path)
        with patch.object(Path, 'exists', check):
            out = self.command('save', 'private/blocked', 'data')[1]
        self.assertIn('Permission denied', out)
        self.assertTrue(Path('data.pim').exists())
        self.assertFalse(self.c.dirty)

    def test_back_at_overwrite_retries_filename(self):
        self.command('add note x')
        self.command('save a')
        self.command('save', 'a', '/back', 'b')
        self.assertTrue(Path('b.pim').exists())

    def test_exit_options_and_back_from_filename(self):
        self.assertFalse(self.command('exit')[0])
        self.command('add note kept')
        for answers, leave in [(('c',), False), (('s', '/back'), False),
                               (('d',), True), (('s', 'bye'), True)]:
            with self.subTest(answers=answers):
                self.assertEqual(self.command('exit', *answers)[0], not leave)
        self.assertTrue(Path('bye.pim').exists())
        self.assertFalse(self.c.dirty)

    def test_run_loop_errors_navigation_and_dirty_prompt(self):
        code, out = self.session('/back', '/cancel', KeyboardInterrupt, 'frobnicate',
                                 'view #9', 'add task', '/back', 'add note x', 'save data', 'exit')
        self.assertEqual(code, 0)
        self.assertIn('Already at command prompt.', out)
        self.assertIn('Returned to command prompt.', out)
        self.assertEqual(out.count('No active action to cancel.'), 2)
        self.assertIn('Unknown command', out)
        self.assertIn('No record #9', out)
        self.assertEqual([p for p in self.prompts if p.startswith('pim')][-3:],
                         ['pim> ', 'pim*> ', 'pim> '])
        self.assertEqual(self.session(EOFError)[0], 0)
        self.command('add note unsaved')
        code, out = self.session(EOFError)
        self.assertEqual(code, 1)
        self.assertIn('unsaved changes', out)


if __name__ == '__main__':
    unittest.main()
