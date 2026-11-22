"""User-authored, bounded conversation plans using existing approved actions.

WHAT THIS IS
    A plan is a list of steps the owner asked for, and this class keeps
    track of where each step is. The rules live in `desktop.task_plan`,
    so they can be tested without a window.

    The owner sees every step and its real state, a step that failed can
    be tried again, and a step that already succeeded is never run a
    second time because a later step failed.

WHAT THIS DOES NOT DO
    * It does not execute anything itself. Every step goes through the
      same approval gateway as every other action.
    * It does not invent a progress percentage. The summary names the
      state of each step and counts them, and nothing else.
    * It does not repair a failure by pretending it did not happen.
"""
from dataclasses import dataclass
import re

from automation.desktop_tasks import DesktopTask, parse_desktop_task
from core.conversation import addressed_request
from desktop.task_plan import StepState, TaskPlan
from desktop.voice_commands import parse_voice_command

MAX_STEPS = 6
STEP_SEPARATOR = re.compile(
    r'(?:\s*,\s*|\s+)(?:and\s+then|then|apram|appuram|பிறகு|அப்புறம்|puis|ensuite)\s+',
    re.IGNORECASE,
)

#: Where the state of a plan is kept, so it survives a restart.
PLAN_KEY = 'task_plan:'


@dataclass(frozen=True)
class Step:
    app: str
    typing: DesktopTask | None = None

    @property
    def label(self):
        if self.typing:
            return f'{self.app}: {"open and type" if self.typing.launch else "type"} {len(self.typing.text)} characters'
        return f'Open {self.app}'


def parse_plan(text):
    """Match whole explicit clauses; never execute a partial or model-written plan.

    After the first colon, all text is literal Notepad payload, even if it
    contains 'then'. Typing is consequently always the last step.
    """
    raw = addressed_request(text)
    explicit = raw.casefold() == '/do' or raw.casefold().startswith('/do ')
    if explicit:
        raw = raw[3:].strip()
    head, colon, payload = raw.partition(':')
    clauses = STEP_SEPARATOR.split(head)
    if not explicit and len(clauses) < 2:
        return None
    # Questions and negations with a conjunction stay conversation.
    if not explicit and ('?' in head or parse_voice_command(clauses[0]) is None):
        return None
    if not 1 <= len(clauses) <= MAX_STEPS:
        raise ValueError(f'Use 1–{MAX_STEPS} supported steps. Nothing was started.')
    if colon:
        clauses[-1] += ':' + payload
    steps = []
    for clause in clauses:
        typing = parse_desktop_task(clause)
        app = typing.app if typing else parse_voice_command(clause)
        if app is None:
            raise ValueError('A step is not supported. Nothing was started. '
                             'Use: /do open Calculator then open Notepad and type: Your text')
        steps.append(Step(app, typing))
    return tuple(steps)


def extract_suggested_plan(reply):
    """Extract an optional final launch-only proposal for owner review."""
    advice, separator, proposal = reply.rstrip().rpartition('\n')
    marker = 'JARVIS_PLAN: /do '
    if not separator or not advice.strip() or not proposal.startswith(marker):
        return reply, ()
    command = proposal[len('JARVIS_PLAN: '):]
    if len(command) > 300:
        return reply, ()
    try:
        steps = parse_plan(command)
    except ValueError:
        return reply, ()
    if not steps or any(step.typing is not None for step in steps):
        return reply, ()
    return advice.rstrip(), steps


class ConversationPlan:
    """Progress reporting only; execution stays in the window's existing gateway."""
    def __init__(self, window):
        self.window = window
        self.active = None
        #: The plan of a run that failed, so the owner can try the step again.
        self.retryable = None

    # ------------------------------------------------------------------ report

    def report(self, text):
        w, state = self.window, self.active or self.retryable
        if state is None:
            return
        w.store.message(state['session'], 'system', text)
        if w.session == state['session']:
            w.render_chat()
        w.refresh_history()

    def refresh_card(self):
        """Show the plan and its steps in the chat."""
        w = self.window
        state = self.active or self.retryable
        if state is None:
            w.plan_card.hide()
            return
        plan = state['plan']
        w.plan_text.setText(plan.summary())
        failed = plan.failed_steps
        w.plan_retry_button.setVisible(bool(failed) and self.active is None)
        w.plan_card.show()

    def save_plan(self, state):
        """Keep the state of the plan, so it survives a restart."""
        self.window.store.set(PLAN_KEY + state['id'], state['plan'].as_dict())

    # ------------------------------------------------------------------- start

    def start(self, request, steps):
        w = self.window
        if (self.active or w.chat_launch is not None or w.desktop_pending is not None
                or w.coding_task_active() or w.worker is not None):
            raise ValueError('Finish or cancel the current task first.')
        ticket = w.policy.ticket()
        plan = TaskPlan.build([step.label for step in steps])
        summary = plan.summary()
        ident = w.store.task('conversation_plan', summary)
        self.active = dict(id=ident, session=w.session, steps=steps,
                           index=0, ticket=ticket, summary=summary,
                           plan=plan, reactor_height=w.chat_reactor.height())
        self.retryable = None
        w.chat_reactor.setFixedHeight(88)
        w.store.finish(ident, 'running')
        w.store.message(w.session, 'local command', request)
        self.save_plan(self.active)
        self.report('Plan:\n' + summary + '\nApprove each step below. /cancel stops remaining work. '
                    'Launch requests and typing are not proof of saved or edited content.')
        self.refresh_card()
        self.queue_step()

    def queue_step(self):
        w, state = self.window, self.active
        if state is None:
            return
        try:
            w.policy.check(state['ticket'])
        except RuntimeError:
            self.finish('cancelled', 'The approval session was cancelled.')
            return
        step = state['steps'][state['index']]
        plan = state['plan']
        current = plan.steps[state['index']]
        plan.wait(current.ident, 'awaiting your approval')
        self.save_plan(state)
        self.report(f'Step {state["index"] + 1}/{len(state["steps"])}: waiting for approval — {step.label}')
        command = f'Plan step {state["index"] + 1}'
        if step.typing:
            queued = w.queue_desktop_task(command, step.typing)
        else:
            queued = w.queue_chat_launch(command, step.app)
        if not queued:
            self.fail_step('The step could not be prepared.')
        self.refresh_card()

    # ------------------------------------------------------------------ result

    def result(self, success, detail, *, verified=False):
        state = self.active
        if state is None:
            return
        plan = state['plan']
        current = plan.steps[state['index']]
        if not success:
            if detail == 'declined':
                current.state = StepState.CANCELLED
                current.detail = 'declined by the owner'
                self.save_plan(state)
                self.finish('cancelled', 'Remaining steps cancelled: ' + detail)
            else:
                self.fail_step(detail)
            return
        if verified:
            plan.verify(current.ident, detail)
        else:
            plan.dispatch(current.ident, detail)
        self.save_plan(state)
        self.report(f'Step {state["index"] + 1}: {detail}')
        state['index'] += 1
        if state['index'] == len(state['steps']):
            if len(plan.verified_steps) == len(plan.steps):
                self.finish('verified', 'Every step has an observed result.')
            else:
                self.finish('dispatched', 'Review the results of the dispatched steps.')
        else:
            self.refresh_card()
            self.queue_step()

    def fail_step(self, detail):
        """A step did not finish. The owner may try it again."""
        state = self.active
        if state is None:
            return
        plan = state['plan']
        current = plan.steps[state['index']]
        current.state = StepState.FAILED
        current.detail = detail
        self.save_plan(state)
        self.report(f'Plan failed at step {state["index"] + 1}/{len(state["steps"])}: {detail}. '
                    'The steps that already succeeded will not run again. '
                    'Press "Try this step again" to run only this step.')
        # The plan is not active any more, but it can be tried again.
        self.active = None
        self.retryable = state
        self.window.store.finish(state['id'], 'failed', state['summary'] + '\n' + detail)
        self.window.chat_reactor.setFixedHeight(state['reactor_height'])
        self.window.refresh_history()
        self.refresh_card()

    def retry_failed(self):
        """Run only the step that failed."""
        state = self.retryable
        if state is None:
            return
        plan = state['plan']
        failed = plan.failed_steps
        if not failed:
            self.retryable = None
            self.refresh_card()
            return
        step = failed[0]
        try:
            plan.retry(step.ident)
        except ValueError as error:
            self.window.statusBar().showMessage(str(error), 10000)
            return
        index = plan.index_of(step.ident)
        state['index'] = index
        state['ticket'] = self.window.policy.ticket()
        # The step before the failed one keeps its state, so a consequence
        # that already happened does not happen again.
        self.window.store.finish(state['id'], 'running', state['summary'])
        self.active = state
        self.retryable = None
        self.report(f'Trying step {index + 1} again: {step.label}. '
                    'The steps before it are not run again.')
        self.refresh_card()
        self.queue_step()

    # ------------------------------------------------------------------ finish

    def finish(self, status, detail):
        state = self.active
        if state is None:
            return
        plan = state['plan']
        if status == 'cancelled':
            plan.cancel_remaining(detail)
        self.save_plan(state)
        self.report(f'Plan {status}: {detail}')
        self.window.store.finish(state['id'], status, plan.summary() + '\n' + detail)
        self.window.chat_reactor.setFixedHeight(state['reactor_height'])
        self.active = None
        self.retryable = None
        self.window.refresh_history()
        self.refresh_card()

    def cancel(self, reason='Cancelled by owner. Already opened apps remain open.'):
        if self.active is None:
            return False
        self.finish('cancelled', reason)
        w = self.window
        w.desktop_task_timer.stop()
        w.desktop_pending = None
        if w.chat_launch is not None:
            w.finish_chat_launch(False)
        return True
