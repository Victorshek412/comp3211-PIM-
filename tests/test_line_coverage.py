"""The bundled coverage tool must discover nested bytecode on supported Python."""
from pathlib import Path
import tempfile
import unittest

from tools.line_coverage import executable_lines


class CoverageTests(unittest.TestCase):
    def test_nested_function_lines_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.py'
            path.write_text('def outer():\n    def inner():\n        return 42\n    return inner()\n',
                            encoding='utf-8')
            self.assertTrue({1, 2, 3, 4}.issubset(executable_lines(str(path))))
