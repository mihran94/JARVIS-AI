"""A coding request that JARVIS works through itself.

WHAT THIS IS
    The owner says "open my project, find the errors, fix the code, run
    the tests and show me the working result", and this is the part that
    does it.

    It runs the **mission runtime** with the coding agent's tools, so the
    model reads the real project, plans, asks for approval, edits, runs
    the tests and reads the result — all through the same boundary every
    other action uses.

    Then it does the part a single pass cannot: if the tests still fail,
    it reads the failure out of the real output, prepares a change, asks
    for approval, makes the change and runs the tests again. That loop is
    bounded, and it only reports **verified** when a run really passed.

WHY THIS EXISTS BESIDE THE CODEX TASK
    `developer_studio.codex_task` drives the Codex CLI when it is
    installed. That is still the better way to do a large change, and it
    is untouched. This is the way JARVIS does the work when there is no
    CLI on the machine, or when the change is small enough to do
    directly: the same model, the same tools, the same approval, and
    the same evidence.

WHAT THIS IS NOT
    * It does not replace the Codex task. It is the other path.
    * It does not claim a fix it did not see. A mission that ended with
      failing tests is reported as failed, with the failure.
    * It does not work outside the project folder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json

from core.coding_repair import RepairOutcome, repair
from core.coding_tools import build_coding_registry, run_command
from core.coding_workspace import CodingWorkspace, WorkspaceRefused
from core.mission import AgentRuntime, Mission

#: The default test command of a project.
DEFAULT_TEST_COMMAND = 'python -m pytest'

#: How the model is asked for a repair.
REPAIR_GUIDANCE = (
    'You are fixing one failing test in a project. You are given the real failure '
    'output. Reply with ONE JSON object and nothing else:\n'
    '{"action": "write", "path": "<file>", "content": "<the whole new file>"}\n'
    'or\n'
    '{"action": "edit", "path": "<file>", "old": "<the exact text to replace>", '
    '"new": "<the text to put in its place>"}\n'
    'or\n'
    '{"action": "patch", "patch": "<a unified diff>"}\n'
    '\n'
    'Rules: only change the file that failed unless another file is clearly the '
    'cause. Keep the change as small as the failure allows. Do not remove the '
    'test. Do not weaken the assertion. Never claim the tests pass; the tests are '
    'run for you.'
)


@dataclass
class CodingMissionResult:
    """What the coding mission did, and what it proved.

    The fields carry the same names as the Codex task's outcome, so the
    coding card in the chat shows either kind of task in the same words.
    """

    status: str = 'failed'
    mission: Mission | None = None
    repair: RepairOutcome | None = None
    summary: str = ''
    steps: list = field(default_factory=list)
    changed_files: list = field(default_factory=list)
    test_status: str = 'not run'
    test_output: str = ''
    diff: str = ''
    protected: list = field(default_factory=list)
    files_inspected: int = 0
    problems_found: int = 0
    worktree: str = ''
    answer: str = ''
    refused: list = field(default_factory=list)
    reviewed: str = ''
    starting_commit: str = ''

    @property
    def message(self) -> str:
        """The result in one line, which is what the coding card shows."""
        return self.summary

    def as_dict(self) -> dict:
        return {'status': self.status, 'summary': self.summary,
                'steps': list(self.steps),
                'mission': self.mission.as_dict() if self.mission else None,
                'repair': self.repair.as_dict() if self.repair else None}


def parse_proposal(answer: str):
    """The change the model asked for, or None."""
    if not isinstance(answer, str) or not answer.strip():
        return None
    text = answer.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        text = '\n'.join(lines).strip()
    start = text.find('{')
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    action = data.get('action')
    if action == 'write' and isinstance(data.get('path'), str) and isinstance(data.get('content'), str):
        return {'action': 'write', 'path': data['path'], 'content': data['content']}
    if action == 'edit' and isinstance(data.get('path'), str) and isinstance(data.get('old'), str) \
            and isinstance(data.get('new'), str):
        return {'action': 'edit', 'path': data['path'], 'old': data['old'], 'new': data['new']}
    if action == 'patch' and isinstance(data.get('patch'), str):
        return {'action': 'patch', 'patch': data['patch']}
    return None


class CodingMission:
    """One coding request, worked through to a result that is proved."""

    def __init__(self, folder, goal, *, planner, gateway, confirm=None, on_event=None,
                 cancel=None, test_command=DEFAULT_TEST_COMMAND, max_steps=6):
        self.folder = folder
        self.goal = goal
        self.planner = planner
        self.gateway = gateway
        self.confirm = confirm
        self.on_event = on_event
        self.cancel = cancel
        self.test_command = test_command
        self.max_steps = max_steps
        self.workspace = CodingWorkspace(folder)
        self.registry = build_coding_registry(self.workspace, cancel=cancel)

    # ------------------------------------------------------------------

    def run_tests(self):
        """The project's own tests, really run."""
        return run_command(self.test_command, self.workspace.root, cancel=self.cancel)

    def propose(self, failures, output):
        """Ask the model for the change that would fix the failure."""
        from core.coding_diagnostics import summarize

        messages = [
            {'role': 'system', 'content': REPAIR_GUIDANCE},
            {'role': 'user', 'content':
                'The project tests fail. This is the real output:\n\n'
                + summarize(failures) + '\n\nThe raw output was:\n\n'
                + (output or '')[-3000:]},
        ]
        try:
            answer = self.planner(messages)
        except Exception:
            return None
        return parse_proposal(answer)

    def apply_change(self, proposal):
        """Make the change, through the owner's approval."""
        action = proposal.get('action')
        if action == 'write':
            def operation():
                return self.workspace.write_text(proposal['path'], proposal['content'])
            note = self._approved('coding_write', proposal['path'], operation)
            return f'{proposal["path"]} was written. {note}'
        if action == 'edit':
            def operation():
                return self.workspace.edit_file(proposal['path'], proposal['old'],
                                                proposal['new'])
            note = self._approved('coding_edit', proposal['path'], operation)
            return f'{proposal["path"]} was changed. {note}'
        if action == 'patch':
            def operation():
                result = self.workspace.apply_patch(proposal['patch'])
                if result.applied == 0:
                    raise WorkspaceRefused(result.as_text())
                return result.as_text()
            note = self._approved('coding_patch', 'a patch', operation)
            return f'The patch was applied. {note}'
        raise WorkspaceRefused('The change was not understood.')

    def _approved(self, kind, target, operation):
        """Run the operation through the owner's one-use approval."""
        from security.policy import Action

        if self.confirm is None:
            raise WorkspaceRefused('There is no way to ask the owner, so nothing was changed.')
        self.gateway.run(Action(kind, target), self.confirm, operation)
        return ''

    # ------------------------------------------------------------------

    def run(self) -> CodingMissionResult:
        """Work through the request, and prove what came of it."""
        result = CodingMissionResult()
        runtime = AgentRuntime(self.registry, self.gateway, self.planner,
                               max_steps=self.max_steps,
                               on_event=self.on_event,
                               check=self._check)
        try:
            mission = runtime.run(self.goal, confirm=self.confirm, check=self._check)
        except Exception as error:
            result.status = 'failed'
            result.summary = f'The coding mission could not run. {error}'
            return result
        result.mission = mission
        result.steps = [event.label for event in mission.events]
        if mission.status == 'cancelled':
            result.status = 'cancelled'
            result.summary = 'The coding mission was cancelled. Nothing was left half done.'
            return result
        result.files_inspected = len([entry for entry in mission.tools_used
                                      if entry['tool'] in ('read_file', 'list_files',
                                                           'search_code')])
        result.protected = self.workspace._protection.protected_files()

        # The mission may already have run the tests. If they still fail,
        # the failure is read and one bounded repair is attempted.
        try:
            tests = self.run_tests()
        except Exception as error:
            result.status = 'failed'
            result.summary = f'The project tests could not be run. {error}'
            return result

        result.test_output = tests.output
        result.test_status = 'passed' if tests.passed else 'failed'
        result.changed_files = self._changed_files()
        result.diff = self._diff()
        if tests.passed:
            result.status = 'verified'
            answer = (mission.answer or '').strip() if mission else ''
            result.summary = ((answer + '\n\n') if answer else '') + (
                'The project tests pass. The changes that were made are in the '
                'mission steps above.')
            return result

        repair_outcome = repair(self.workspace, run_tests=self.run_tests,
                                propose=self.propose, apply_change=self.apply_change,
                                attempts=2, cancel=self.cancel)
        result.repair = repair_outcome
        result.test_output = repair_outcome.output or result.test_output
        result.test_status = 'passed' if repair_outcome.verified else 'failed'
        result.changed_files = self._changed_files()
        result.diff = self._diff()
        if repair_outcome.verified:
            result.status = 'verified'
            result.summary = repair_outcome.message
            return result
        result.status = repair_outcome.status
        result.summary = repair_outcome.message
        return result

    def _changed_files(self) -> list:
        """The files the mission really changed, read from Git."""
        from core.coding_tools import git_output

        output = git_output(self.workspace.root, 'status', '--short')
        names = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            path = line.split('->')[-1].strip().strip('"')
            if path and path not in names:
                names.append(path)
        return names

    def _diff(self) -> str:
        """The difference the mission made, as Git reports it."""
        from core.coding_tools import git_output

        return git_output(self.workspace.root, 'diff', '--stat').strip()

    def _check(self):
        """The cancellation and the emergency stop, checked between steps."""
        if self.cancel is not None and self.cancel():
            from security.policy import Stopped

            raise Stopped('The coding mission was cancelled.')
