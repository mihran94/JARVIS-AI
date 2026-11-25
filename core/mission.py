"""JARVIS missions: a supervised, bounded agent loop.

WHAT THIS IS
    A mission turns one goal into a short, visible sequence of real
    actions. JARVIS proposes the next action, this module decides whether
    it may run, the tool runs it, and the result goes back to the model
    as an observation. The owner sees every step in the HUD.

THE RULES
    * The model may only choose a tool that is in the catalogue. A tool
      that is not registered does not exist for it.
    * A tool that changes something needs the owner's approval, through
      the same gateway every other action in JARVIS uses. The approval
      names the exact call and is used once.
    * An emergency stop cancels the mission at the next step.
    * The loop is bounded: a maximum number of steps and a time budget.
      A mission that runs out of steps reports that it did, and does not
      pretend the goal was reached.
    * A tool result is the only evidence. The mission records what ran
      and what it returned. It never says something happened that did
      not happen.

WHAT THIS IS NOT
    * It is not a chat. The model is not asked to be helpful; it is asked
      for one decision at a time, and every decision is checked.
    * It does not parse prose into commands. Only the one JSON envelope
      is read, and anything else is refused with the reason.
    * It does not run anything on its own initiative. It runs what the
      owner asked for, and it stops at the first refusal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
import uuid

from core.mission_tools import ToolError
from security.policy import Action, Denied, Stopped

#: How many steps one mission may take.
MAX_STEPS = 6

#: How long one mission may run, in seconds.
BUDGET_SECONDS = 180

#: How many events one mission keeps.
MAX_EVENTS = 200

#: How many readable failures are allowed before the mission stops.
MAX_RECOVERABLE_ERRORS = 2


class MissionError(RuntimeError):
    """The mission could not be run at all."""


@dataclass(frozen=True)
class MissionEvent:
    """One thing that happened during a mission.

    The kinds are fixed, so the HUD and the owner see the same words
    every time: goal, thought, tool, approval, result, answer, error and
    cancelled.

    `step` is the step of the mission the event belongs to, so the
    interface can say which step of how many without counting anything
    twice.
    """

    kind: str
    label: str
    detail: str = ''
    step: int = 0

    def as_dict(self) -> dict:
        return {'kind': self.kind, 'label': self.label, 'detail': self.detail,
                'step': self.step}


@dataclass
class Mission:
    """One goal, the steps it took and what came of it."""

    id: str
    goal: str
    status: str = 'running'
    answer: str = ''
    steps: int = 0
    events: list = field(default_factory=list)
    tools_used: list = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return self.status == 'completed'

    @property
    def evidence(self) -> list:
        """The calls that really ran, and what they returned."""
        return list(self.tools_used)

    def as_dict(self) -> dict:
        return {
            'id': self.id,
            'goal': self.goal,
            'status': self.status,
            'answer': self.answer,
            'steps': self.steps,
            'events': [event.as_dict() for event in self.events],
            'tools_used': list(self.tools_used),
        }


def _first_json_object(text: str):
    """The first JSON object in a block of text, or None."""
    body = text.strip()
    if body.startswith('```'):
        lines = body.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        body = '\n'.join(lines).strip()
    decoder = json.JSONDecoder()
    index = body.find('{')
    while index != -1:
        try:
            value, _ = decoder.raw_decode(body[index:])
        except ValueError:
            value = None
        if isinstance(value, dict):
            return body[index:]
        index = body.find('{', index + 1)
    return None


def _text(value) -> str:
    """A short piece of the model's own words, or nothing."""
    if isinstance(value, str):
        return value.strip()
    return ''


def parse_decision(text):
    """Read one decision out of the model's answer.

    The model answers with a single JSON object. Anything else is
    refused, and the refusal says what was expected, so the model can
    correct itself on the next turn instead of the mission guessing.
    """
    if not isinstance(text, str) or not text.strip():
        return None, 'The model did not answer.'
    body = _first_json_object(text)
    if body is None:
        return None, 'The answer was not a JSON object.'
    try:
        data = json.loads(body)
    except ValueError:
        return None, 'The JSON object could not be read.'
    if not isinstance(data, dict):
        return None, 'The answer was not a JSON object.'
    action = data.get('action')
    thought = _text(data.get('thought'))
    if action == 'answer':
        answer = data.get('answer')
        if not isinstance(answer, str) or not answer.strip():
            return None, 'The final answer was empty.'
        return {'action': 'answer', 'answer': answer.strip(), 'thought': thought}, None
    if action == 'skip':
        reason = data.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            return None, 'The reason for skipping was empty.'
        return {'action': 'skip', 'reason': reason.strip(), 'thought': thought}, None
    if action == 'tool':
        name = data.get('tool')
        if not isinstance(name, str) or not name.strip():
            return None, 'The tool name was missing.'
        arguments = data.get('arguments')
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return None, 'The arguments were not an object.'
        return {'action': 'tool', 'tool': name.strip(), 'arguments': arguments,
                'thought': thought}, None
    return None, 'The action must be "tool", "answer" or "skip".'


def system_instructions(registry) -> str:
    """The instructions the model is given for one mission.

    The rules are the same ones this module enforces. They are written
    down for the model as well, because a model that is told the rules
    and a model that is only checked against them do not behave the same
    way.
    """
    return (
        'You are JARVIS, running one mission for the owner of this computer.\n'
        '\n'
        'Answer with ONE JSON object and nothing else.\n'
        '\n'
        'To use a tool:\n'
        '{"action": "tool", "tool": "<tool name>", "arguments": {<arguments>}, '
        '"thought": "<one sentence>"}\n'
        '\n'
        'To finish the mission:\n'
        '{"action": "answer", "answer": "<the final answer>", "thought": "<one sentence>"}\n'
        '\n'
        'To record that a step could not be done, and carry on:\n'
        '{"action": "skip", "reason": "<why this step cannot be done>", '
        '"thought": "<one sentence>"}\n'
        '\n'
        'The rules:\n'
        '* Use only the tools listed below. A tool that is not listed does not exist.\n'
        '* A tool that changes something is approved by the owner before it runs. '
        'If the owner declines it, do not try it again and do not do it another way.\n'
        '* One tool per answer. Wait for the result before the next answer.\n'
        '* Answer only from what the tool results show. If a tool failed, say that it failed.\n'
        '* Do not claim something was done that you did not observe in a result.\n'
        '* If the goal needs no tool, answer straight away.\n'
        '\n'
        'The tools:\n'
        + registry.describe()
    )


def observation(tool_name: str, result: str) -> str:
    """What the model is told after a tool ran."""
    return (f'The result of {tool_name}:\n{result}\n\n'
            'Continue with the next decision, or answer if the mission is done.')


def failure_observation(tool_name: str, message: str) -> str:
    """What the model is told when a tool could not run."""
    return (f'{tool_name} did not run: {message}\n\n'
            'Continue with the next decision, or answer and say what was not done.')


def skipped_observation(reason: str) -> str:
    """What the model is told when a step could not be done.

    A blocked step is not a failure of the whole mission. The model is
    told what was blocked and why, so the next decision can be made with
    that in hand.
    """
    return (f'That step could not be done: {reason}\n\n'
            'Continue with the next step you can do, or answer and say what was not done.')


def coerce_edit(tool, arguments: dict) -> dict:
    """Turn the owner's edited text back into the types the tool expects.

    The owner edits in a text box, so an argument that is a number
    arrives as text. It is converted here, using the tool's own schema,
    and the argument is checked again afterwards. An edit that cannot be
    converted is refused rather than guessed at.
    """
    properties = (tool.parameters or {}).get('properties', {})
    converted = {}
    for key, value in (arguments or {}).items():
        expected = properties.get(key, {}).get('type')
        if expected in ('integer', 'number') and isinstance(value, str):
            try:
                number = float(value) if expected == 'number' else int(value)
            except ValueError:
                raise ToolError(f'The argument {key} must be a number.') from None
            converted[key] = int(number) if expected == 'integer' else number
        elif expected == 'boolean' and isinstance(value, str):
            lowered = value.strip().casefold()
            if lowered in ('true', 'yes', '1'):
                converted[key] = True
            elif lowered in ('false', 'no', '0'):
                converted[key] = False
            else:
                raise ToolError(f'The argument {key} must be true or false.')
        else:
            converted[key] = value
    return converted


class AgentRuntime:
    """Runs one mission: propose, check, run, observe, repeat.

    The runtime is deliberately free of any user interface, any network
    client and any provider name. It is given a registry of real tools, a
    gateway that asks the owner for permission, and a `planner` callable
    that returns the model's answer. That makes the whole loop testable
    without a window, without a key and without a network.
    """

    def __init__(self, registry, gateway, planner, *, max_steps=MAX_STEPS,
                 budget_seconds=BUDGET_SECONDS, on_event=None, check=None):
        self.registry = registry
        self.gateway = gateway
        self.planner = planner
        self.max_steps = max(1, int(max_steps))
        self.budget_seconds = max(1, int(budget_seconds))
        self.on_event = on_event
        #: Raised by the caller's check when an emergency stop is active.
        self.check = check or (lambda: None)

    # ------------------------------------------------------------------

    def _emit(self, mission: Mission, kind: str, label: str, detail: str = '',
              step: int = 0) -> None:
        event = MissionEvent(kind=kind, label=label, detail=detail, step=step)
        mission.events.append(event)
        if len(mission.events) > MAX_EVENTS:
            del mission.events[:-MAX_EVENTS]
        if self.on_event is not None:
            self.on_event(event)

    def _stop(self, mission: Mission, label: str, detail: str = '') -> Mission:
        mission.status = 'cancelled'
        self._emit(mission, 'cancelled', label, detail)
        return mission

    def _fail(self, mission: Mission, label: str, detail: str = '') -> Mission:
        mission.status = 'failed'
        self._emit(mission, 'error', label, detail)
        return mission

    # ------------------------------------------------------------------

    def run(self, goal: str, *, confirm=None, check=None) -> Mission:
        """Run one mission and return it.

        `confirm` is the owner's approval function; it is only called for
        a tool that changes something. `check` replaces the runtime's own
        cancellation check for this run, so a caller that owns a worker
        thread can stop the mission when the owner cancels it. The
        mission never reports success for a tool that did not run.
        """
        goal = (goal or '').strip()
        if not goal:
            raise MissionError('A mission needs a goal.')
        check = check or self.check
        mission = Mission(id=uuid.uuid4().hex, goal=goal)
        self._emit(mission, 'goal', 'Mission started', goal)

        messages = [
            {'role': 'system', 'content': system_instructions(self.registry)},
            {'role': 'user', 'content': goal},
        ]
        deadline = time.monotonic() + self.budget_seconds
        def checkpoint():
            check()
            if time.monotonic() > deadline:
                raise MissionError('The mission reached its time limit.')

        errors = 0

        for step in range(1, self.max_steps + 1):
            mission.steps = step
            try:
                check()
            except Stopped:
                return self._stop(mission, 'Mission cancelled',
                                  'The mission was cancelled before the next step.')
            if time.monotonic() > deadline:
                return self._fail(mission, 'Mission stopped',
                                  f'It used {step - 1} of {self.max_steps} steps and ran out of time.')

            try:
                raw = self.planner(messages)
                checkpoint()
            except MissionError as error:
                return self._fail(mission, 'Mission stopped', str(error))
            except Stopped:
                return self._stop(mission, 'Mission cancelled',
                                  'The mission was cancelled before the next step.')
            except Exception:
                return self._fail(mission, 'The model could not be reached',
                                  'No further step was taken.')

            decision, problem = parse_decision(raw)
            if decision is None:
                errors += 1
                self._emit(mission, 'error', 'The answer could not be read', problem, step)
                if errors >= MAX_RECOVERABLE_ERRORS:
                    return self._fail(mission, 'Mission stopped',
                                      f'The model did not give a usable decision ({problem}).')
                messages.append({'role': 'assistant', 'content': raw if isinstance(raw, str) else ''})
                messages.append({'role': 'user', 'content':
                                 f'That answer could not be used: {problem} '
                                 'Answer with one JSON object as instructed.'})
                continue

            if decision['action'] == 'answer':
                mission.answer = decision['answer']
                mission.status = 'completed'
                if decision['thought']:
                    self._emit(mission, 'thought', 'JARVIS decided', decision['thought'], step)
                self._emit(mission, 'answer', 'Mission complete', decision['answer'], step)
                return mission

            if decision['action'] == 'skip':
                # The step could not be done. The mission carries on with
                # the steps that can be done, and the blocked step is
                # recorded so the owner sees what did not happen.
                if decision['thought']:
                    self._emit(mission, 'thought', 'JARVIS decided', decision['thought'], step)
                self._emit(mission, 'skipped', 'Step blocked', decision['reason'], step)
                messages.append({'role': 'assistant', 'content': raw})
                messages.append({'role': 'user', 'content':
                                 skipped_observation(decision['reason'])})
                continue

            tool = self.registry.get(decision['tool'])
            if tool is None:
                return self._fail(
                    mission, 'That tool does not exist',
                    f'JARVIS has no tool called {decision["tool"]!r}. '
                    f'It has: {", ".join(self.registry.names()) or "none"}.')
            try:
                arguments = self.registry.check_arguments(tool, decision['arguments'])
            except ToolError as problem:
                errors += 1
                self._emit(mission, 'error', 'The arguments were refused', str(problem), step)
                if errors >= MAX_RECOVERABLE_ERRORS:
                    return self._fail(mission, 'Mission stopped', str(problem))
                messages.append({'role': 'assistant', 'content': raw})
                messages.append({'role': 'user', 'content':
                                 failure_observation(tool.name, str(problem))})
                continue

            if decision['thought']:
                self._emit(mission, 'thought', 'JARVIS decided', decision['thought'], step)
            summary = tool.summary(arguments)
            self._emit(mission, 'tool', f'Calling {tool.name}', summary, step)

            try:
                if tool.read_only:
                    result = self._call(tool, arguments, checkpoint)
                else:
                    if confirm is None:
                        # A tool that changes something is never run without a
                        # way to ask the owner. This is a programming mistake,
                        # so it is said plainly rather than hidden.
                        return self._fail(
                            mission, 'Nothing could be approved',
                            f'{tool.name} changes something and there was no way '
                            'to ask the owner, so it did not run.')
                    self._emit(mission, 'approval', 'Approval needed',
                               f'{tool.name}: {summary}', step)
                    # The owner may change the arguments before the call
                    # runs. What they change is checked against the
                    # schema again, so an edit cannot widen the call.
                    edited = {}

                    def ask(action):
                        answer = confirm(action)
                        if isinstance(answer, dict):
                            edited.update(answer)
                            return True
                        return bool(answer)

                    def run_approved():
                        merged = {**arguments, **coerce_edit(tool, edited)}
                        checked = self.registry.check_arguments(tool, merged)
                        return self._call(tool, checked, checkpoint)

                    result = self.gateway.run(
                        Action('mission_tool', summary, arguments=json.dumps(
                            arguments, ensure_ascii=False, default=str)),
                        ask, run_approved)
            except MissionError as error:
                return self._fail(mission, 'Mission stopped', str(error))
            except Denied:
                return self._fail(mission, 'The owner did not allow it',
                                  f'{tool.name} was not run.')
            except Stopped:
                return self._stop(mission, 'Mission cancelled',
                                  'The mission was cancelled before the next step.')
            except ToolError as problem:
                errors += 1
                self._emit(mission, 'error', f'{tool.name} did not run', str(problem), step)
                if errors >= MAX_RECOVERABLE_ERRORS:
                    return self._fail(mission, 'Mission stopped', str(problem))
                messages.append({'role': 'assistant', 'content': raw})
                messages.append({'role': 'user', 'content':
                                 failure_observation(tool.name, str(problem))})
                continue
            except Exception:
                return self._fail(mission, f'{tool.name} did not run',
                                  'The tool failed and nothing was changed.')

            text = str(result)
            self._emit(mission, 'result', f'{tool.name} finished', text[:400], step)
            mission.tools_used.append({'tool': tool.name, 'summary': summary, 'result': text[:400]})
            messages.append({'role': 'assistant', 'content': raw})
            messages.append({'role': 'user', 'content': observation(tool.name, text)})
            errors = 0

        return self._fail(
            mission, 'Mission stopped',
            f'It used all {self.max_steps} steps without a final answer. '
            'The steps that ran are listed above.')

    def _call(self, tool, arguments, check):
        """Run one tool, with the emergency stop checked on both sides."""
        check()
        result = tool.run(arguments, check) if tool.accepts_checkpoint else tool.run(arguments)
        check()
        return result


__all__ = ['BUDGET_SECONDS', 'MAX_EVENTS', 'MAX_RECOVERABLE_ERRORS', 'MAX_STEPS',
           'AgentRuntime', 'Mission', 'MissionError', 'MissionEvent', 'coerce_edit',
           'failure_observation', 'observation', 'parse_decision', 'skipped_observation',
           'system_instructions']
