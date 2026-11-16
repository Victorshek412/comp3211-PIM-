"""Measure line coverage of the model/ package using only the standard library.

Usage (from the project root):  python3 tools/line_coverage.py [package ...]
Runs every test in tests/. Without arguments it measures model/ and writes COVERAGE.txt;
with package names (for example controller view) it only prints their coverage. If coverage.py is installed,
`coverage run --source=model -m unittest discover tests` gives the same kind of report.
"""
import dis
import os
import sys
from types import CodeType
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_tests():
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)
    return unittest.TextTestRunner(verbosity=0).run(suite)


def executable_lines(path):
    """Line numbers that carry bytecode (the lines a line-coverage tool counts)."""
    with open(path, encoding="utf-8") as source:
        code = compile(source.read(), path, "exec")
    lines = set()

    def walk(co):
        lines.update(line for _, line in dis.findlinestarts(co) if line)
        for const in co.co_consts:
            if isinstance(const, CodeType):
                walk(const)

    walk(code)
    return lines


def main():
    packages = sys.argv[1:] or ["model"]
    sys.path.insert(0, ROOT)
    hits = set()

    def tracer(frame, event, arg):
        filename = frame.f_code.co_filename
        if not any(filename.startswith(os.path.join(ROOT, name) + os.sep) for name in packages):
            return None
        if event == "line":
            hits.add((filename, frame.f_lineno))
        return tracer

    sys.settrace(tracer)
    try:
        result = run_tests()
    finally:
        sys.settrace(None)
    lines = [f"Line coverage of {', '.join(packages)} (stdlib sys.settrace)", ""]
    lines.append(f"{'File':<28}{'Lines':>7}{'Run':>7}{'Cover':>8}  Missing")
    total = hit_total = 0
    files = [(package, name) for package in packages
             for name in sorted(os.listdir(os.path.join(ROOT, package))) if name.endswith(".py")]
    for package, name in files:
        path = os.path.join(ROOT, package, name)
        executable = executable_lines(path)
        hit = {n for n in executable if (path, n) in hits}
        missing = sorted(executable - hit)
        total += len(executable)
        hit_total += len(hit)
        pct = 100 * len(hit) / len(executable) if executable else 100
        lines.append(f"{package + '/' + name:<28}{len(executable):>7}{len(hit):>7}{pct:>7.0f}%  "
                     f"{', '.join(map(str, missing))}")
    pct = 100 * hit_total / total if total else 100
    lines += ["", f"TOTAL{'':<23}{total:>7}{hit_total:>7}{pct:>7.0f}%",
              f"Tests run: {result.testsRun}, failures: {len(result.failures)}, "
              f"errors: {len(result.errors)}"]
    report = "\n".join(lines) + "\n"
    if packages == ["model"]:
        with open(os.path.join(ROOT, "COVERAGE.txt"), "w", encoding="utf-8") as out:
            out.write(report)
    print(report)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
