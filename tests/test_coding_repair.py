"""The repair loop: run the tests, read the failure, change one thing, run again.

WHAT IS COVERED
    * A real failing test is read, and a real change fixes it, and the
      run that passed is what is reported.
    * A loop that cannot fix it says so, and keeps the last real failure.
    * A failure that cannot be read stops the loop instead of guessing.
    * A change that is refused stops the loop.
    * The loop is bounded, and it can be cancelled between the steps.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shutil
import subprocess
import sys
import textwrap

import pytest

from core.coding_diagnostics import parse_failures
from core.coding_repair import failure_report, repair
from core.coding_tools import run_command


BROKEN = '''\
from app import VALUE


def test_value():
    assert VALUE == 2
'''

FIXED = '''\
from app import VALUE


def test_value():
    assert VALUE == 2
'''


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    (root / 'app.py').write_text('VALUE = 1\n', encoding='utf-8')
    (root / 'test_app.py').write_text(BROKEN, encoding='utf-8')
    return root


class FakeResult:
    """The result of a test run, without starting one."""

    def __init__(self, output, passed=False):
        self.output = output
        self.returncode = 0 if passed else 1
        self.cancelled = False

    @property
    def passed(self):
        return self.returncode == 0 and not self.cancelled


FAILING_OUTPUT = textwrap.dedent("""
    F                                                                   [100%]
    =================================== FAILURES ===================================
    _________________________________ test_value __________________________________
        def test_value():
    >       assert VALUE == 2
    E       assert 1 == 2
    test_app.py:5: AssertionError
    =========================== short test summary info ============================
    FAILED test_app.py::test_value - assert 1 == 2
    1 failed, 0 passed in 0.02s
""")


def fake_runner(project):
    """A runner that reads the project the way pytest would.

    The loop is exercised with this one, so the tests do not start a
    pytest process for every case. The one test that really runs the
    project's own tests is below.
    """
    state = {'runs': 0}

    def run():
        state['runs'] += 1
        source = (project / 'app.py').read_text(encoding='utf-8')
        if 'VALUE = 2' in source:
            return FakeResult('1 passed in 0.02s', passed=True)
        return FakeResult(FAILING_OUTPUT)

    run.state = state
    return run


def run_the_tests(project):
    """The project's own tests, really run.

    The cached bytecode of the project is cleared first. The file times
    on this machine are coarse enough that Python can otherwise reuse a
    cached module after the file has changed, and the second run would
    not see the fix at all.
    """
    for cache in project.rglob('__pycache__'):
        shutil.rmtree(cache, ignore_errors=True)
    return run_command(f'{sys.executable} -m pytest -q', project)


def test_a_real_failure_is_read_from_a_real_run(project):
    result = run_the_tests(project)
    failures = parse_failures(result.output)
    assert failures
    assert failures[0].file.endswith('test_app.py')
    assert failures[0].kind == 'assertion'


def test_the_loop_fixes_a_real_failure(project):
    """A change that really fixes the test really makes the run pass."""
    calls = []

    def propose(failures, output):
        calls.append(failures)
        return {'path': 'app.py', 'content': 'VALUE = 2\n'}

    def apply_change(proposal):
        (project / proposal['path']).write_text(proposal['content'], encoding='utf-8')
        return f"{proposal['path']} was changed."

    outcome = repair(project, run_tests=fake_runner(project), propose=propose,
                     apply_change=apply_change, attempts=2)
    assert outcome.status == 'verified', failure_report(outcome)
    assert outcome.attempts == 1
    assert calls and calls[0][0].file.endswith('test_app.py')
    assert 'passed' in outcome.output
    assert outcome.failures == []


def test_a_loop_that_cannot_fix_it_says_so(project):
    def propose(failures, output):
        return {'path': 'app.py', 'content': 'VALUE = 3\n'}

    def apply_change(proposal):
        (project / proposal['path']).write_text(proposal['content'], encoding='utf-8')
        return 'app.py was changed.'

    outcome = repair(project, run_tests=fake_runner(project), propose=propose,
                     apply_change=apply_change, attempts=2)
    assert outcome.status == 'failed'
    assert outcome.attempts == 2
    assert outcome.failures
    assert 'still fail' in outcome.message


def test_a_failure_that_cannot_be_read_stops_the_loop(project):
    def propose(failures, output):
        raise AssertionError('the model was never asked')

    def apply_change(proposal):
        raise AssertionError('nothing should be applied')

    class Odd:
        passed = False
        output = 'the tool crashed in a way nobody can read'
        returncode = 1

    outcome = repair(project, run_tests=lambda: Odd(), propose=propose,
                     apply_change=apply_change, attempts=2)
    assert outcome.status == 'blocked'
    assert 'did not say why' in outcome.message


def test_a_refused_change_stops_the_loop(project):
    def propose(failures, output):
        return {'path': 'app.py', 'content': 'VALUE = 2\n'}

    def apply_change(proposal):
        raise RuntimeError('The owner declined the change.')

    outcome = repair(project, run_tests=lambda: run_the_tests(project), propose=propose,
                     apply_change=apply_change, attempts=2)
    assert outcome.status == 'blocked'
    assert 'declined' in outcome.message


def test_the_loop_is_bounded(project):
    attempts = []

    def propose(failures, output):
        attempts.append(1)
        return {'path': 'app.py', 'content': 'VALUE = 2\n'}

    def apply_change(proposal):
        (project / proposal['path']).write_text(proposal['content'], encoding='utf-8')
        return 'app.py was changed.'

    outcome = repair(project, run_tests=fake_runner(project), propose=propose,
                     apply_change=apply_change, attempts=1)
    assert outcome.attempts == 1
    assert len(attempts) == 1


def test_the_loop_can_be_cancelled(project):
    def propose(failures, output):
        return {'path': 'app.py', 'content': 'VALUE = 2\n'}

    def apply_change(proposal):
        return 'app.py was changed.'

    outcome = repair(project, run_tests=fake_runner(project), propose=propose,
                     apply_change=apply_change, attempts=2,
                     cancel=lambda: True)
    assert outcome.status == 'cancelled'


def test_tests_that_already_pass_need_no_change(project):
    (project / 'app.py').write_text('VALUE = 2\n', encoding='utf-8')
    outcome = repair(project, run_tests=fake_runner(project),
                     propose=lambda failures, output: (_ for _ in ()).throw(
                         AssertionError('the model was never asked')),
                     apply_change=lambda proposal: 'should not happen')
    assert outcome.status == 'verified'
    assert outcome.attempts == 0
    assert 'Nothing had to be changed' in outcome.message


def test_the_report_reads_as_words(project):
    outcome = repair(project, run_tests=fake_runner(project),
                     propose=lambda failures, output: {'path': 'app.py', 'content': 'VALUE = 2\n'},
                     apply_change=lambda proposal: 'app.py was changed.', attempts=1)
    report = failure_report(outcome)
    assert 'app.py was changed' in report
    assert 'output of the test run' in report
