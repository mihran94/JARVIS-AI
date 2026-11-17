"""User-authored, bounded conversation plans using existing approved actions."""
from dataclasses import dataclass
import re

from automation.desktop_tasks import DesktopTask, parse_desktop_task
from core.conversation import addressed_request
from desktop.voice_commands import parse_voice_command

MAX_STEPS = 6


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
    clauses = re.split(r'\s+(?:and\s+then|then|apram|பிறகு|அப்புறம்)\s+', head, flags=re.IGNORECASE)
    if not explicit and len(clauses) < 2:
        return None
    # Questions and negations with a conjunction stay conversation.
    if not explicit and parse_voice_command(clauses[0]) is None:
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


class ConversationPlan:
    """Progress reporting only; execution stays in the window's existing gateway."""
    def __init__(self, window):
        self.window = window
        self.active = None

    def report(self, text):
        w, state = self.window, self.active
        if state is None:
            return
        w.store.message(state['session'], 'system', text)
        if w.session == state['session']:
            w.render_chat()
        w.refresh_history()

    def start(self, request, steps):
        w = self.window
        if (self.active or w.chat_launch is not None or w.desktop_pending is not None
                or w.coding_task_active() or w.worker is not None):
            raise ValueError('Finish or cancel the current task first.')
        ticket = w.policy.ticket()
        summary = '\n'.join(f'{i}. {step.label}' for i, step in enumerate(steps, 1))
        ident = w.store.task('conversation_plan', summary)
        self.active = dict(id=ident, session=w.session, steps=steps,
                           index=0, ticket=ticket, summary=summary,
                           reactor_height=w.chat_reactor.height())
        w.chat_reactor.setFixedHeight(88)
        w.store.finish(ident, 'running')
        w.store.message(w.session, 'local command', request)
        self.report('Plan:\n' + summary + '\nApprove each step below. /cancel stops remaining work. '
                    'Launch requests and typing are not proof of saved or edited content.')
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
        self.report(f'Step {state["index"] + 1}/{len(state["steps"])}: awaiting approval — {step.label}')
        command = f'Plan step {state["index"] + 1}'
        if step.typing:
            queued = w.queue_desktop_task(command, step.typing)
        else:
            queued = w.queue_chat_launch(command, step.app)
        if not queued:
            self.finish('failed', 'Step could not be prepared. Remaining steps were cancelled.')

    def result(self, success, detail):
        state = self.active
        if state is None:
            return
        if not success:
            self.finish('cancelled' if detail == 'declined' else 'failed',
                        'Remaining steps cancelled: ' + detail)
            return
        self.report(f'Step {state["index"] + 1}: {detail}')
        state['index'] += 1
        if state['index'] == len(state['steps']):
            self.finish('completed', 'All approved requests dispatched. '
                        'Check the application windows; content and saved files are not verified.')
        else:
            self.queue_step()

    def finish(self, status, detail):
        state = self.active
        if state is None:
            return
        self.report(f'Plan {status}: {detail}')
        self.window.store.finish(state['id'], status, state['summary'] + '\n' + detail)
        self.window.chat_reactor.setFixedHeight(state['reactor_height'])
        self.active = None
        self.window.refresh_history()

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
