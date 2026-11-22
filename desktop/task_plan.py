"""The state of a multi-step job, and the rule for retrying a step.

WHY THIS IS A MODULE
    A job with more than one step has to answer four questions at once:
    what the plan is, what each step is doing right now, which steps are
    finished, and what can be tried again without doing the finished work
    a second time.

    The answers live here rather than in the window, so the rules can be
    tested without a window, without a provider and without a network.

THE STATES
    pending               not started
    waiting for approval  the step is asking the owner for permission
    running               the step is doing its work
    verified              the step finished and the result was checked
    failed                the step did not finish
    cancelled             the step will not run

WHAT THIS WILL NOT DO
    * It never invents a progress percentage. A percentage is a guess
      about work that has not happened, and a guess that looks precise is
      worse than a number that is true.
    * It never runs anything. It records what happened and says which
      step may be tried again.
    * It never re-runs a step that was verified. Retrying a failed step
      goes back to that step and leaves the steps before it exactly as
      they were, so a consequence that already happened does not happen
      twice because a later step failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class StepState:
    """The state a step of a plan can be in."""

    PENDING = 'pending'
    WAITING = 'waiting for approval'
    RUNNING = 'running'
    DISPATCHED = 'dispatched'
    VERIFIED = 'verified'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    #: The states a step can never leave on its own.
    FINAL = (DISPATCHED, VERIFIED, CANCELLED)


@dataclass
class PlanStep:
    """One step of a plan."""

    ident: str
    label: str
    state: str = StepState.PENDING
    detail: str = ''
    #: True when the step does something that cannot be undone by running
    #: it again, such as opening an application or typing into one.
    consequential: bool = True
    attempts: int = 0

    def as_dict(self) -> dict:
        return {
            'ident': self.ident,
            'label': self.label,
            'state': self.state,
            'detail': self.detail,
            'consequential': self.consequential,
            'attempts': self.attempts,
        }

    @classmethod
    def from_dict(cls, raw) -> 'PlanStep':
        if not isinstance(raw, dict):
            return cls('', '')
        return cls(
            ident=str(raw.get('ident', '')),
            label=str(raw.get('label', '')),
            state=str(raw.get('state', StepState.PENDING)),
            detail=str(raw.get('detail', '')),
            consequential=bool(raw.get('consequential', True)),
            attempts=int(raw.get('attempts', 0) or 0),
        )


@dataclass
class TaskPlan:
    """An ordered list of steps and what has happened to them."""

    steps: list = field(default_factory=list)

    @classmethod
    def build(cls, labels) -> 'TaskPlan':
        """A plan from the labels of its steps."""
        return cls([PlanStep(str(index + 1), str(label))
                    for index, label in enumerate(labels)])

    # ------------------------------------------------------------------ lookup

    def step(self, ident) -> PlanStep | None:
        """The step with this identifier."""
        for step in self.steps:
            if step.ident == str(ident):
                return step
        return None

    def index_of(self, ident) -> int:
        """Where the step is in the plan, or -1."""
        for index, step in enumerate(self.steps):
            if step.ident == str(ident):
                return index
        return -1

    @property
    def verified_steps(self) -> list:
        return [step for step in self.steps if step.state == StepState.VERIFIED]

    @property
    def failed_steps(self) -> list:
        return [step for step in self.steps if step.state == StepState.FAILED]

    @property
    def counts(self) -> dict:
        """How many steps are in each state."""
        result = {}
        for step in self.steps:
            result[step.state] = result.get(step.state, 0) + 1
        return result

    # ----------------------------------------------------------------- changes

    def _move(self, ident, state, detail=None):
        step = self.step(ident)
        if step is None:
            raise KeyError(f'There is no step {ident} in this plan.')
        if step.state in StepState.FINAL:
            raise ValueError(
                f'Step {ident} is already {step.state} and cannot become {state}.')
        step.state = state
        if detail is not None:
            step.detail = str(detail)
        return step

    def wait(self, ident, detail='') -> PlanStep:
        """The step is asking the owner for permission."""
        return self._move(ident, StepState.WAITING, detail)

    def run(self, ident, detail='') -> PlanStep:
        """The step is doing its work."""
        step = self.step(ident)
        if step is not None and step.state in (StepState.PENDING, StepState.WAITING):
            step.attempts += 1
        return self._move(ident, StepState.RUNNING, detail)

    def verify(self, ident, detail='') -> PlanStep:
        """The step finished and the result was checked."""
        return self._move(ident, StepState.VERIFIED, detail)

    def dispatch(self, ident, detail='') -> PlanStep:
        """The OS accepted the request; repeating it may duplicate an effect."""
        return self._move(ident, StepState.DISPATCHED, detail)

    def fail(self, ident, detail='') -> PlanStep:
        """The step did not finish."""
        return self._move(ident, StepState.FAILED, detail)

    def cancel(self, ident, detail='') -> PlanStep:
        """The step will not run."""
        return self._move(ident, StepState.CANCELLED, detail)

    def cancel_remaining(self, detail='') -> list:
        """Every step that has not finished is cancelled."""
        changed = []
        for step in self.steps:
            if step.state in (StepState.PENDING, StepState.WAITING, StepState.RUNNING):
                step.state = StepState.CANCELLED
                step.detail = str(detail)
                changed.append(step)
        return changed

    # ------------------------------------------------------------------- retry

    def can_retry(self, ident) -> bool:
        """True when this step may be tried again.

        A step may be tried again when it failed. A step that was
        verified may not: its work already happened, and doing it a
        second time because a later step failed is exactly what the owner
        does not want.
        """
        step = self.step(ident)
        if step is None:
            return False
        return step.state == StepState.FAILED

    def retry(self, ident, detail='') -> PlanStep:
        """Put a failed step back in the queue.

        The step before it keeps its state, so a consequence that already
        happened does not happen again. The steps after it go back to
        pending, because they were stopped by the failure and never ran.
        """
        if not self.can_retry(ident):
            step = self.step(ident)
            state = step.state if step is not None else 'missing'
            raise ValueError(
                f'Step {ident} is {state} and cannot be tried again.')
        index = self.index_of(ident)
        for later in self.steps[index + 1:]:
            if later.state in (StepState.PENDING, StepState.WAITING, StepState.RUNNING,
                               StepState.FAILED):
                later.state = StepState.PENDING
                later.detail = ''
        step = self.step(ident)
        step.state = StepState.PENDING
        step.detail = str(detail)
        step.attempts += 1
        return step

    def next_pending(self) -> PlanStep | None:
        """The step that should run next."""
        for step in self.steps:
            if step.state == StepState.PENDING:
                return step
        return None

    # ------------------------------------------------------------------- text

    def summary(self) -> str:
        """The plan as the owner reads it.

        The counts are real counts. There is no percentage, because the
        work that is left cannot be measured before it is done.
        """
        if not self.steps:
            return 'No steps.'
        lines = []
        for index, step in enumerate(self.steps, 1):
            line = f'{index}. {step.label}'
            if step.ident != str(index):
                line += f' (id {step.ident})'
            line += f' — {step.state}'
            if step.detail:
                line += f': {step.detail}'
            if step.attempts > 1:
                line += f' (attempt {step.attempts})'
            lines.append(line)
        counts = self.counts
        tail = []
        for state in (StepState.VERIFIED, StepState.DISPATCHED, StepState.FAILED, StepState.CANCELLED,
                      StepState.RUNNING, StepState.WAITING, StepState.PENDING):
            if counts.get(state):
                tail.append(f'{counts[state]} {state}')
        lines.append('State: ' + ', '.join(tail) + '.')
        return '\n'.join(lines)

    # --------------------------------------------------------------- storage

    def as_dict(self) -> dict:
        return {'steps': [step.as_dict() for step in self.steps]}

    @classmethod
    def from_dict(cls, raw) -> 'TaskPlan':
        if not isinstance(raw, dict):
            return cls([])
        steps = raw.get('steps')
        if not isinstance(steps, list):
            return cls([])
        return cls([PlanStep.from_dict(item) for item in steps])
