"""Reading the failures out of what a test run really printed.

WHAT IS COVERED
    * The output of a **real** pytest run is read: the file, the line,
      the kind of failure, the test name and the message.
    * A unittest failure is read.
    * A plain Python traceback is read.
    * A Node test failure is read.
    * A compiler error line is read.
    * A run that failed without saying why is reported as such, rather
      than being given a made-up location.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import subprocess
import sys
import textwrap

import pytest

from core.coding_diagnostics import parse_failures, summarize


def run_pytest(folder, source, name='test_sample.py'):
    """Run a real pytest in a real folder and return what it printed."""
    path = folder / name
    path.write_text(textwrap.dedent(source), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(path)],
                            cwd=str(folder), capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=120, check=False)
    return result.stdout + result.stderr


# ── a real pytest run ──────────────────────────────────────────────────────

def test_a_real_pytest_failure_is_read(tmp_path):
    output = run_pytest(tmp_path, '''
        def test_passes():
            assert 1 + 1 == 2

        def test_fails():
            expected = "Friday"
            actual = "Monday"
            assert actual == expected, f"the launch moved to {actual}"
    ''')
    failures = parse_failures(output)
    assert len(failures) == 1
    failure = failures[0]
    assert failure.file.endswith('test_sample.py')
    assert failure.line == 8, 'the line of the failing assert was not found'
    assert failure.kind == 'assertion'
    assert 'the launch moved to Monday' in failure.message
    assert 'test_fails' in failure.test


def test_a_real_exception_is_read_as_an_exception(tmp_path):
    output = run_pytest(tmp_path, '''
        def test_raises():
            raise ValueError("the note was not there")
    ''')
    failures = parse_failures(output)
    assert failures
    assert failures[0].kind == 'exception'
    assert 'the note was not there' in failures[0].message
    assert failures[0].line == 3


def test_a_passing_run_has_no_failures(tmp_path):
    output = run_pytest(tmp_path, '''
        def test_passes():
            assert True
    ''')
    assert parse_failures(output) == []


# ── the other runners ──────────────────────────────────────────────────────

def test_a_unittest_failure_is_read():
    output = textwrap.dedent('''
        FAIL: test_value (tests.test_thing.TestThing)
        ----------------------------------------------------------------------
        Traceback (most recent call last):
          File "tests/test_thing.py", line 12, in test_value
            self.assertEqual(actual, expected)
        AssertionError: 'Monday' != 'Friday'
    ''')
    failures = parse_failures(output)
    assert failures
    assert failures[0].file.endswith('test_thing.py')
    assert failures[0].line == 12
    assert 'test_value' in failures[0].test


def test_a_plain_traceback_is_read():
    output = textwrap.dedent('''
        Traceback (most recent call last):
          File "app/main.py", line 42, in run
            do_the_thing()
          File "app/main.py", line 11, in do_the_thing
            return 1 / 0
        ZeroDivisionError: division by zero
    ''')
    failures = parse_failures(output)
    assert failures
    assert failures[0].file.endswith('main.py')
    # The deepest frame is where the exception was raised, and that is
    # the line worth editing. The frame above it is the caller.
    assert failures[0].line == 11
    assert 'division by zero' in failures[0].message


def test_a_node_failure_is_read():
    output = textwrap.dedent('''
        not ok 3 - the launch date
          ---
          duration_ms: 4
          error: |-
            Expected values to be strictly equal:
            + actual - expected
          at TestContext (test/launch.test.js:14:9)
    ''')
    failures = parse_failures(output)
    assert failures
    assert failures[0].file.endswith('launch.test.js')
    assert failures[0].line == 14
    assert 'the launch date' in failures[0].test


def test_a_compiler_error_is_read():
    output = 'src/thing.c:12: error: unused variable \'x\'\n'
    failures = parse_failures(output)
    assert failures
    assert failures[0].kind == 'compile'
    assert failures[0].file == 'src/thing.c'
    assert failures[0].line == 12
    assert 'unused variable' in failures[0].message


# ── when nothing can be read ───────────────────────────────────────────────

def test_a_run_with_nothing_in_it_says_so():
    failures = parse_failures('no tests ran in 0.02s')
    assert failures
    assert failures[0].kind == 'unknown'


def test_empty_output_has_no_failures():
    assert parse_failures('') == []
    assert parse_failures('everything is fine\n') == []


def test_the_failures_read_as_words():
    failures = parse_failures(textwrap.dedent('''
        FAILED test_sample.py::test_fails - AssertionError: it moved
    '''))
    text = failures[0].describe()
    assert 'ASSERTION' in text
    assert 'test_fails' in text


def test_the_summary_is_readable():
    failures = parse_failures('FAILED test_sample.py::test_fails - AssertionError: it moved')
    assert 'it moved' in summarize(failures)
    assert 'No readable failure' in summarize([])
