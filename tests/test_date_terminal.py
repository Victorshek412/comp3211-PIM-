"""Exercise actual terminal keystrokes and restoration through a POSIX PTY."""
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import unittest


@unittest.skipUnless(os.name == 'posix', 'Live date editing uses POSIX terminals')
class DateTerminalTests(unittest.TestCase):
    def start(self, default=None):
        import pty
        master, slave = pty.openpty()
        code = '''
import termios
from view.terminal_view import read_datetime, Back, Cancelled
before = termios.tcgetattr(0)
try:
    result = read_datetime('Deadline', DEFAULT)
    print('RESULT=' + result, flush=True)
except (KeyboardInterrupt, EOFError, Back, Cancelled) as error:
    print('STOP=' + type(error).__name__, flush=True)
finally:
    after = termios.tcgetattr(0)
    # macOS sets its transient PENDIN flag when returning to canonical mode.
    before[3] &= ~getattr(termios, 'PENDIN', 0)
    after[3] &= ~getattr(termios, 'PENDIN', 0)
    print('RESTORED=' + str(before == after), flush=True)
'''.replace('DEFAULT', repr(default))
        proc = subprocess.Popen([sys.executable, '-u', '-c', code],
                                stdin=slave, stdout=slave, stderr=slave,
                                cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, 'TERM': 'xterm-256color'},
                                start_new_session=True)
        os.close(slave)
        self.master, self.proc, self.output = master, proc, b''
        self.addCleanup(self.cleanup_process, proc, master)
        self.expect(b'Deadline')

    def cleanup_process(self, proc, master):
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        os.close(master)

    def expect(self, value):
        deadline = time.monotonic() + 5
        while value not in self.output and time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.output += chunk
        self.assertIn(value, self.output, self.output.decode(errors='replace'))

    def send(self, keys):
        os.write(self.master, keys)

    def finished(self, result):
        self.expect(result)
        self.expect(b'RESTORED=True')
        self.assertEqual(self.proc.wait(timeout=5), 0)

    def test_digits_show_separators_live_before_enter(self):
        self.start()
        for keys, visible in [(b'2026', b'2026-'), (b'12', b'2026-12-'),
                              (b'05', b'2026-12-05 '), (b'18', b'2026-12-05 18:'),
                              (b'00', b'2026-12-05 18:00')]:
            self.send(keys)
            self.expect(visible)
            self.assertIsNone(self.proc.poll())
            self.assertNotIn(b'RESULT=', self.output)
        self.send(b'\r')
        self.finished(b'RESULT=2026-12-05 18:00')

    def test_backspace_arrows_delete_and_insertion(self):
        self.start()
        self.send(b'202612051800\x1b[D\x7f3')
        self.expect(b'2026-12-05 18:30')
        self.send(b'\x01\x1b[C\x1b[C\x1b[C\x1b[3~7\r')
        self.finished(b'RESULT=2027-12-05 18:30')

    def test_formatted_bracketed_paste(self):
        self.start()
        self.send(b'\x1b[200~2026-12-05 18:00\x1b[201~\r')
        self.finished(b'RESULT=2026-12-05 18:00')

    def test_invalid_date_retries_without_losing_terminal_mode(self):
        self.start()
        self.send(b'202602301800\r')
        self.expect(b'February has 28 days')
        self.send(b'202602281800\r')
        self.finished(b'RESULT=2026-02-28 18:00')

    def test_default_kept_on_enter(self):
        self.start('2026-12-05 18:00')
        self.send(b'\r')
        self.finished(b'RESULT=2026-12-05 18:00')

    def test_time_only_keeps_date(self):
        self.start('2026-12-05 18:00')
        self.send(b'17:30\r')
        self.finished(b'RESULT=2026-12-05 17:30')

    def test_legacy_spaces_still_work_with_live_input(self):
        self.start()
        self.send(b'2026 9 5\r')
        self.expect(b'Deadline time (HH:MM):')
        self.send(b'18 00\r')
        self.finished(b'RESULT=2026-09-05 18:00')

    def test_cancel_back_interrupt_and_eof_restore_terminal(self):
        for keys, expected in [(b'/cancel\r', b'Cancelled'), (b'/back\r', b'Back'),
                               (b'2026\x03', b'KeyboardInterrupt'), (b'\x04', b'EOFError')]:
            with self.subTest(expected=expected):
                self.start()
                self.send(keys)
                self.finished(b'STOP=' + expected)
                # Each iteration owns its own descriptors and cleanup callback.
                self.doCleanups()


if __name__ == '__main__':
    unittest.main()
