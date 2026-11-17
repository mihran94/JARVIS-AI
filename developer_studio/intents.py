"""Turn a chat sentence into a coding request, in English, Tamil or Tanglish.

WHAT THIS IS
    The owner does not learn a command language. They say what they want:

        "JARVIS, my project-a VS Code-la open panni login page validation fix
         pannu. Tests run panni result sollu."

    and JARVIS works out that this is: open project-a in VS Code, fix the login
    page validation, run the tests and report the result.

    The parser is DETERMINISTIC and LOCAL, like `desktop/voice_commands.py`.
    It is a table of known phrases, not a guess. A sentence it does not
    understand is not turned into a task; it is left to the assistant.

WHY A TABLE AND NOT A MODEL
    Two reasons. A task that runs code must be certain what was asked for, and
    a model that is wrong here changes files. And the phrases are known:
    "open panni", "fix pannu", "tests run panni", "result sollu" are the
    Tanglish forms a Tamil speaker actually types, not a translation.

WHEN IT ASKS A QUESTION
    Only when the project or the scope is materially unclear: no saved project
    was named, or a project was named but nothing was asked of it. Everything
    else is answered without interrupting.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


#: Phrases that mean "open this project".
OPEN_PHRASES = (
    'open panni', 'open pannu', 'open pann', 'open the project',
    'open project', 'open', 'திற', 'தொடக்கு',
)

#: Phrases that mean "make a change".
CHANGE_PHRASES = (
    'fix pannu', 'fix panni', 'change pannu', 'change panni', 'do pannu',
    'seiyyungal', 'seiyyum', 'fix', 'add', 'change', 'update', 'implement',
    'refactor', 'correct', 'create', 'write', 'remove', 'delete', 'rename',
    'மாற்று', 'செய்', 'பண்ணு', 'நிர்',
)

#: Phrases that mean "run the tests".
TEST_PHRASES = (
    'tests run panni', 'tests run pannu', 'run the tests', 'run tests',
    'test run panni', 'test run', 'tests run', 'run test', 'tests',
)

#: Phrases that mean "tell me the result".
REPORT_PHRASES = (
    'result sollu', 'result sol', 'tell the result', 'report the result',
    'say the result', 'result', 'sollu', 'sol',
)

#: The words that open a sentence and carry no instruction.
WAKE_WORDS = ('hey jarvis', 'jarvis,', 'jarvis:', 'jarvis')

#: Words removed from the request once the intent has been recognised.
_NOISE = re.compile(
    r'\b(?:my|the|a|an|please|kindly|naan|na|ennakku|and|then|also|okay|ok|hey)\b',
    re.IGNORECASE)

#: The Tamil case suffix that clings to the word before it, as in "VS Code-la".
_CASE_SUFFIX = re.compile(r'(?<![a-z])(?:-\s*)?(?:la|illa|yil|il)(?![a-z])', re.IGNORECASE)


@dataclass(frozen=True)
class CodingRequest:
    """What the owner asked for, as far as the local parser can tell."""

    project: str = ''
    editor: str = ''
    change: str = ''
    open_project: bool = False
    make_change: bool = False
    run_tests: bool = False
    report: bool = False
    question: str = ''
    #: True when the sentence asked for work, whether or not a project was named.
    mentions_work: bool = False

    @property
    def is_coding_request(self) -> bool:
        """True when the sentence asked for something a task can do."""
        return bool(self.project) and (self.open_project or self.make_change or self.run_tests)

    @property
    def needs_question(self) -> bool:
        """True when the request is too unclear to act on."""
        return bool(self.question)


def _normalise_for_matching(text: str) -> str:
    """Fold punctuation into spaces so a phrase is found wherever it sits."""
    folded = text.casefold()
    for char in '.,;:!?()[]"\u2019\u201c\u201d':
        folded = folded.replace(char, ' ')
    return ' ' + ' '.join(folded.split()) + ' '


def _contains(text: str, phrases) -> bool:
    lowered = _normalise_for_matching(text)
    for phrase in phrases:
        if ' ' + _normalise_for_matching(phrase).strip() + ' ' in lowered:
            return True
    return False


def _match_project(text: str, projects):
    """The saved project the owner named, or None.

    The name is matched loosely: "project A" finds the project saved as
    "project-a", because that is how people say it out loud.
    """
    lowered = text.casefold()
    best = None
    best_length = 0
    for project in projects:
        name = getattr(project, 'name', '')
        if not name:
            continue
        pattern = re.compile(r'[\s\-_]*'.join(re.escape(char) for char in name if char.isalnum()),
                             re.IGNORECASE)
        if pattern.search(lowered) and len(name) > best_length:
            best, best_length = project, len(name)
    return best


def _strip_phrases(text: str, phrases) -> str:
    """Remove the recognised action phrases, leaving the requested change."""
    result = text
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = re.compile(r'(?<![a-z])' + re.escape(phrase) + r'(?![a-z])', re.IGNORECASE)
        result = pattern.sub(' ', result)
    return result


def parse_coding_request(text: str, projects, editor_from_text=None) -> CodingRequest:
    """Read a chat sentence as a coding request.

    `projects` is the list of saved projects. `editor_from_text` is the
    helper that finds an editor named in the sentence; it is passed in so
    this module does not have to know how editors are found.
    """
    if not isinstance(text, str) or not text.strip():
        return CodingRequest()

    original = ' '.join(text.split())
    working = original
    for wake in WAKE_WORDS:
        if working.casefold().startswith(wake):
            working = working[len(wake):].lstrip(' ,:')
            break

    project = _match_project(working, projects)
    editor = editor_from_text(working) if editor_from_text else ''

    open_project = _contains(working, OPEN_PHRASES)
    make_change = _contains(working, CHANGE_PHRASES)
    run_tests = _contains(working, TEST_PHRASES)
    report = _contains(working, REPORT_PHRASES)

    # A sentence that names a test but never says "run" is still a request to
    # run the tests, and a sentence that says "run tests" is not a request to
    # make a change.
    if 'test' in working.casefold() and not make_change:
        run_tests = True

    change = working
    if project is not None:
        change = _strip_phrases(change, (project.name,))
        change = _CASE_SUFFIX.sub(' ', change)
    if editor:
        change = _strip_phrases(change, (editor,))
        change = _CASE_SUFFIX.sub(' ', change)
    change = _strip_phrases(change, OPEN_PHRASES)
    change = _strip_phrases(change, TEST_PHRASES)
    change = _strip_phrases(change, REPORT_PHRASES)
    change = _strip_phrases(change, CHANGE_PHRASES)
    change = _NOISE.sub(' ', change)
    change = ' '.join(change.replace(',', ' ').replace('.', ' ').split()).strip(' -')

    question = ''
    if project is None:
        names = ', '.join(getattr(item, 'name', '') for item in projects[:6])
        question = ('Which saved project is this for?' + (f' Your saved projects are: {names}.'
                                                          if names else ''))
    elif not (open_project or make_change or run_tests):
        question = f'What should JARVIS do in {project.name}?'

    return CodingRequest(
        mentions_work=bool(open_project or make_change or run_tests),
        project=getattr(project, 'name', '') if project is not None else '',
        editor=editor or '',
        change=change,
        open_project=open_project,
        make_change=make_change,
        run_tests=run_tests,
        report=report,
        question=question,
    )
