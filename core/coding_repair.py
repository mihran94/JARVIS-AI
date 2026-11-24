"""The repair loop: read the failure, change one thing, run it again.

WHAT THIS IS
    The loop that turns "the tests fail" into "the tests pass", without
    anyone pretending that a change fixed something.

    It runs the tests, reads what failed out of the real output, asks for
    a change, applies that change through the approval boundary, runs the
    tests again, and stops. It is bounded: a fixed number of attempts,
    and a cancellation that works between every step.

    The loop reports one of four things:

    * **verified** — the tests passed after the change. The output of
      the run that passed is kept;
    * **failed** — the tests still fail after every attempt, and the
      last real failure is reported;
    * **blocked** — the failure could not be read, or the change was
      refused, so another attempt would only guess;
    * **cancelled** — the owner stopped it.

WHAT THIS IS NOT
    * It does not claim a fix it did not see. Only a run that passed is
      reported as verified.
    * It does not loop for ever. Two attempts by default.
    * It does not apply a change by itself. The change goes through
      `apply_change`, which is where the owner's approval lives.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.coding_diagnostics import parse_failures, summarize

#: How many times the loop tries a change by default.
MAX_ATTEMPTS = 2


@dataclass
class RepairOutcome:
    """What the loop did, and what it proved."""

    status: str = 'failed'
    attempts: int = 0
    failures: list = field(default_factory=list)
    output: str = ''
    changes: list = field(default_factory=list)
    message: str = ''

    @property
    def verified(self) -> bool:
        return self.status == 'verified'

    def as_dict(self) -> dict:
        return {'status': self.status, 'attempts': self.attempts,
                'failures': [failure.as_dict() for failure in self.failures],
                'changes': list(self.changes), 'message': self.message}


def repair(workspace, *, run_tests, propose, apply_change, attempts=MAX_ATTEMPTS,
           cancel=None) -> RepairOutcome:
    """Run the tests, and try to fix what is broken.

    `run_tests` runs the project's tests and returns the real result.
    `propose` is given the failures and returns the change to make.
    `apply_change` makes that change, through the owner's approval.
    """
    outcome = RepairOutcome()
    limit = max(1, int(attempts))

    def stopped():
        return cancel is not None and cancel()

    try:
        result = run_tests()
    except Exception as error:
        outcome.status = 'blocked'
        outcome.message = f'The tests could not be run. {error}'
        return outcome
    if stopped():
        outcome.status = 'cancelled'
        outcome.message = 'Cancelled before the tests ran.'
        return outcome

    outcome.output = result.output
    if result.passed:
        outcome.status = 'verified'
        outcome.message = 'The tests passed. Nothing had to be changed.'
        return outcome

    failures = parse_failures(result.output)
    outcome.failures = failures
    if not failures:
        outcome.status = 'blocked'
        outcome.message = ('The tests failed, but the output did not say why, so a change '
                           'would be a guess. The output was kept.')
        return outcome

    for attempt in range(1, limit + 1):
        if stopped():
            outcome.status = 'cancelled'
            outcome.message = 'Cancelled before the next attempt.'
            return outcome
        outcome.attempts = attempt
        try:
            proposal = propose(failures, result.output)
        except Exception as error:
            outcome.status = 'blocked'
            outcome.message = f'A change could not be prepared. {error}'
            return outcome
        if not proposal:
            outcome.status = 'blocked'
            outcome.message = 'No change could be prepared from that failure.'
            return outcome
        try:
            note = apply_change(proposal)
        except Exception as error:
            outcome.status = 'blocked'
            outcome.message = f'The change was not applied. {error}'
            return outcome
        outcome.changes.append(note or 'a change was applied')
        if stopped():
            outcome.status = 'cancelled'
            outcome.message = 'Cancelled after the change.'
            return outcome
        try:
            result = run_tests()
        except Exception as error:
            outcome.status = 'blocked'
            outcome.message = f'The tests could not be run again. {error}'
            return outcome
        outcome.output = result.output
        if result.passed:
            outcome.status = 'verified'
            outcome.message = (f'The tests passed after {attempt} change(s). '
                                'The output of the run that passed is below.')
            outcome.failures = []
            return outcome
        failures = parse_failures(result.output)
        outcome.failures = failures
        if not failures:
            outcome.status = 'blocked'
            outcome.message = 'The tests still fail, but the output did not say why.'
            return outcome

    outcome.status = 'failed'
    outcome.message = (f'The tests still fail after {outcome.attempts} attempt(s). '
                       'The last real failure is below.')
    return outcome


def failure_report(outcome) -> str:
    """The outcome as the owner and the model read it."""
    parts = [outcome.message]
    if outcome.failures:
        parts.append(summarize(outcome.failures))
    if outcome.changes:
        parts.append('What was changed:')
        parts.extend(f'- {note}' for note in outcome.changes)
    if outcome.output:
        parts.append('The last output of the test run:')
        parts.append(outcome.output[-4000:])
    return '\n\n'.join(parts)


__all__ = ['MAX_ATTEMPTS', 'RepairOutcome', 'failure_report', 'repair']
