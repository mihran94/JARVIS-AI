"""What JARVIS remembers between messages, and what it can resume.

WHY THIS EXISTS
    "Continue that task" only means something if JARVIS still knows which task.
    "Open it in VS Code" only means something if it still knows which project.
    Both have to survive the window closing, because the owner closes the
    application and comes back to it, so the memory is stored in the local
    settings database rather than kept in a widget.

WHAT IS STORED
    Only what is needed to continue: the project that was chosen, the editor
    that was used, the language the owner wants the answer in, and a record of
    the last task — which folder it works in, which worktree it used, the
    commit it started from and how it ended.

    Nothing secret is stored here. API keys stay in Windows Credential
    Manager, and the worktree path is a local folder path.

WHY A RESUME CHECKS BEFORE IT CONTINUES
    The worktree is a real folder on the disk and the project is a real Git
    repository. Between one message and the next, the owner may have deleted
    the worktree, cleaned the branches, or moved the project. Resuming into
    something that is not there any more would report a result for work that
    never ran. So a resume checks the worktree and the starting commit first,
    and says plainly what is missing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import subprocess
from pathlib import Path


#: Where the conversation context lives in the settings store.
CONTEXT_KEY = 'assistant_context'

#: The task states that are finished and are not resumed.
FINISHED_STATES = ('completed', 'failed', 'cancelled', 'declined')


@dataclass(frozen=True)
class TaskRecord:
    """One task, remembered well enough to continue it."""

    ident: str = ''
    project: str = ''
    folder: str = ''
    editor: str = ''
    worktree: str = ''
    starting_commit: str = ''
    change: str = ''
    test_command: str = ''
    status: str = ''
    created: str = ''

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw) -> 'TaskRecord':
        if not isinstance(raw, dict):
            return cls()
        fields = {name: raw.get(name, '') for name in cls.__dataclass_fields__}
        return cls(**{name: (value if isinstance(value, str) else str(value))
                       for name, value in fields.items()})


@dataclass(frozen=True)
class ConversationContext:
    """The conversation's memory."""

    project: str = ''
    editor: str = ''
    language: str = ''
    last_task: TaskRecord | None = None

    def as_dict(self) -> dict:
        return {
            'project': self.project,
            'editor': self.editor,
            'language': self.language,
            'last_task': self.last_task.as_dict() if self.last_task else None,
        }

    @classmethod
    def from_dict(cls, raw) -> 'ConversationContext':
        if not isinstance(raw, dict):
            return cls()
        task = raw.get('last_task')
        return cls(
            project=str(raw.get('project', '') or ''),
            editor=str(raw.get('editor', '') or ''),
            language=str(raw.get('language', '') or ''),
            last_task=TaskRecord.from_dict(task) if task else None,
        )


class ConversationMemory:
    """Reads and writes the conversation context in the settings store."""

    def __init__(self, store):
        self.store = store

    def load(self) -> ConversationContext:
        """The remembered context, or an empty one."""
        try:
            raw = self.store.get(CONTEXT_KEY)
        except Exception:
            return ConversationContext()
        return ConversationContext.from_dict(raw)

    def save(self, context: ConversationContext) -> None:
        """Remember the context."""
        self.store.set(CONTEXT_KEY, context.as_dict())

    def remember(self, *, project: str = '', editor: str = '', language: str = '',
                task: TaskRecord | None = None) -> ConversationContext:
        """Update and store the context, keeping what was not changed."""
        current = self.load()
        updated = ConversationContext(
            project=project or current.project,
            editor=editor or current.editor,
            language=language or current.language,
            last_task=task if task is not None else current.last_task,
        )
        self.save(updated)
        return updated

    def remember_task(self, task: TaskRecord) -> ConversationContext:
        """Remember a task as the last one."""
        current = self.load()
        updated = ConversationContext(project=task.project or current.project,
                                      editor=task.editor or current.editor,
                                      language=current.language,
                                      last_task=task)
        self.save(updated)
        return updated

    def clear_task(self) -> ConversationContext:
        """Forget the last task but keep the chosen project."""
        current = self.load()
        updated = ConversationContext(project=current.project, editor=current.editor,
                                      language=current.language, last_task=None)
        self.save(updated)
        return updated

    def forget(self) -> ConversationContext:
        """Forget everything."""
        empty = ConversationContext()
        self.save(empty)
        return empty


def _git(folder: Path, *args):
    try:
        result = subprocess.run(['git', '-C', str(folder), *args], capture_output=True,
                                text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None
    return result.stdout


def task_is_resumable(record: TaskRecord) -> tuple[bool, str]:
    """Check that a task can still be continued.

    Returns the answer and the reason. The reason is a sentence the owner
    can act on, not a status code.
    """
    if not record or not record.ident:
        return False, 'There is no saved task to continue.'
    if not record.worktree:
        return False, ('That task never started a worktree, so there is nothing to continue. '
                       'Ask for it again.')
    worktree = Path(record.worktree)
    if not worktree.is_dir():
        return False, (f'The worktree for that task is gone ({worktree}). '
                       'Start the task again.')
    if record.starting_commit:
        listed = _git(worktree, 'cat-file', '-e', record.starting_commit + '^{commit}')
        if listed is None:
            return False, (f'The commit that task started from ({record.starting_commit[:8]}) '
                           'is no longer in this repository. Start the task again.')
    return True, 'The task and its worktree are still there.'


def describe_task(record: TaskRecord) -> str:
    """One line about a remembered task, for the owner to read."""
    if not record or not record.ident:
        return 'There is no saved task.'
    parts = [f'{record.project or "task"}']
    if record.change:
        parts.append(record.change)
    if record.status:
        parts.append(record.status)
    if record.worktree:
        parts.append(record.worktree)
    return ' · '.join(parts)


__all__ = ['CONTEXT_KEY', 'ConversationContext', 'ConversationMemory', 'TaskRecord',
           'describe_task', 'task_is_resumable']
