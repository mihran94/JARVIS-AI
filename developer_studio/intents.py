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

from core.conversation import addressed_request


#: The Tamil Unicode block, used to spot a request written in Tamil script.
TAMIL_SCRIPT = re.compile(r'[\u0b80-\u0bff]')


#: Phrases that mean "open this project".
OPEN_PHRASES = (
    'open panni', 'open pannu', 'open pann', 'open the project',
    'open project', 'open', 'திற', 'தொடக்கு',
)

#: Phrases that mean "make a change".
CHANGE_PHRASES = (
    'fix pannu', 'fix panni', 'change pannu', 'change panni', 'do pannu',
    'debug pannu', 'debug panni', 'பிழையைச் சரிசெய்', 'பிழையை சரிசெய்', 'seiyyungal', 'seiyyum', 'fix', 'add', 'change', 'update', 'implement',
    'refactor', 'correct', 'create', 'write', 'remove', 'delete', 'rename',
    'மாற்று', 'செய்', 'பண்ணு', 'நிர்',
)

#: Phrases that mean "run the tests".
TEST_PHRASES = (
    'tests run panni', 'tests run pannu', 'run the tests', 'run tests',
    'சோதனைகளை இயக்கு', 'சோதனை செய்', 'test run panni', 'test run', 'tests run', 'run test', 'tests',
)

#: Phrases that mean "tell me the result".
REPORT_PHRASES = (
    'முடிவைச் சொல்', 'முடிவை சொல்', 'result sollu', 'result sol', 'tell the result', 'report the result',
    'say the result', 'result', 'sollu', 'sol',
)

#: Words removed from the request once the intent has been recognised.
_NOISE = re.compile(
    r'\b(?:my|the|a|an|please|kindly|naan|na|ennakku|and|then|also|okay|ok|hey'
    r'|enna|pannina|nu|jarvis|la|il|va)\b',
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
    question_kind: str = ''
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


def parse_coding_request(text: str, projects, editor_from_text=None,
                          default_project: str = '') -> CodingRequest:
    """Read a chat sentence as a coding request.

    `projects` is the list of saved projects. `editor_from_text` is the
    helper that finds an editor named in the sentence; it is passed in so
    this module does not have to know how editors are found.

    `default_project` is the project this conversation is already about. It
    is used when the sentence names no project, so "also fix the logout" is
    understood without repeating the name.
    """
    if not isinstance(text, str) or not text.strip():
        return CodingRequest()

    # The sentence as the owner wrote it, and the sentence with the
    # "Jarvis," in front of it taken off. The first one says whether the
    # owner asked a question, the second one is what the request is about.
    original = ' '.join(text.split())
    working = ' '.join(addressed_request(text).split())
    folded = working.casefold()
    if (working.startswith(('"', "'", '“', '/'))
            or folded.startswith(('how ', 'what ', 'why ', 'should ', 'do not ', "don't "))
            or _contains(working, ('வேண்டாம்', 'pannatha', 'panna vendam'))):
        return CodingRequest()

    project = _match_project(working, projects)
    if project is None and default_project:
        for item in projects:
            if getattr(item, 'name', '').casefold() == default_project.casefold():
                project = item
                break
    editor = editor_from_text(working) if editor_from_text else ''

    open_project = _contains(working, OPEN_PHRASES)
    change_probe = _strip_phrases(working, TEST_PHRASES)
    make_change = _contains(change_probe, CHANGE_PHRASES)
    run_tests = _contains(working, TEST_PHRASES)
    report = _contains(working, REPORT_PHRASES)

    # A sentence that names a test but never says "run" is still a request to
    # run the tests, and a sentence that says "run tests" is not a request to
    # make a change.
    if 'test' in working.casefold() and not make_change:
        run_tests = True

    change = strip_language_marker(working)
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
    change = ' '.join(change.replace(',', ' ').replace('.', ' ').split()).strip(' -—,;:')

    question = ''
    question_kind = ''
    if project is None:
        # The sentence asks for work but names no project.
        if open_project or make_change or run_tests:
            names = ', '.join(getattr(item, 'name', '') for item in projects[:6])
            question = ('Which saved project is this for?' + (f' Your saved projects are: {names}.'
                                                              if names else ''))
            question_kind = 'project'
    elif not (open_project or make_change or run_tests):
        # The sentence names a project and asks for work, but never says what.
        if asks_for_a_task(original):
            question = f'What should JARVIS do in {project.name}?'
            question_kind = 'action'
    elif make_change and change_is_unclear(change):
        # The sentence asks for a change, but the change is never said.
        question = f'What change should JARVIS make in {project.name}?'
        question_kind = 'change'

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
        question_kind=question_kind,
    )

# ── Follow-ups ───────────────────────────────────────────────────────────────

#: The words that stand in for "something" — a change that is never said.
PLACEHOLDER_CHANGE = {
    'it', 'that', 'this', 'them', 'these', 'those', 'something', 'anything',
    'some change', 'a change', 'changes', 'the change', 'change', 'code',
    'edhavadhu', 'edhavu', 'venna', 'va', 'illa', 'theerpu',
}

#: The phrases that mean "do something" without saying what.
TASK_INTENT_PHRASES = (
    'work on', 'work with', 'do something', 'do something about', 'do it',
    'do the work', 'make a change', 'make some changes', 'some change',
    'a change', 'take a look', 'look into', 'get started', 'have a go',
    'edhavadhu', 'edhavu', 'maathu', 'theerpu', 'thakkali', 'venna',
)

#: The words that make a sentence a question about a project, not a task.
QUESTION_MARKERS = (
    'what', 'who', 'why', 'how', 'when', 'where', 'which', 'explain',
    'tell me about', 'sollanum', 'means', 'difference', 'who wrote',
)


def change_is_unclear(change: str) -> bool:
    """True when the requested change is a placeholder instead of a real one."""
    text = ' '.join((change or '').casefold().split()).strip(' .,!?')
    if not text:
        return True
    return all(word in PLACEHOLDER_CHANGE for word in text.split())


def asks_for_a_task(text: str) -> bool:
    """True when the sentence asks for work without saying what to do.

    A question about a project ("what does project-a do?") is not a task, so
    it never becomes a request to JARVIS.
    """
    lowered = (text or '').casefold()
    if '?' in (text or ''):
        return False
    if any(marker in lowered for marker in QUESTION_MARKERS):
        return False
    return any(phrase in lowered for phrase in TASK_INTENT_PHRASES)


#: A follow-up is a short message that refers to the task already running.
#: The phrases are the ones a person actually types, in the three languages
#: the owner uses.
FOLLOW_UPS = {
    'continue': (
        'continue that task', 'continue the task', 'continue', 'resume that task',
        'resume', 'carry on', 'continue pannu', 'continue panni', 'vatathu',
        'தொடர்ந்து செய்', 'தொடர்',
    ),
    'show_diff': (
        'show the diff', 'show diff', 'show me the diff', 'diff kaattu',
        'diff காட்டு', 'kaattu', 'காட்டு',
    ),
    'run_tests': (
        'run the tests again', 'run tests again', 'run the tests', 'run tests',
        'tests run pannu', 'tests again', 'tests mathiri', 'மீண்டும் ஓடு',
    ),
    'stop': (
        'stop this task', 'stop the task', 'stop that task', 'stop', 'cancel the task',
        'stop pannu', 'நிறுத்து',
    ),
}

#: Words that may sit in front of a follow-up without changing it.
FOLLOW_UP_PREFIXES = ('jarvis', 'please', 'ok', 'okay', 'and', 'na', 'hey jarvis', 'now')


def parse_follow_up(text):
    """Return 'continue', 'show_diff', 'run_tests', 'stop' or None.

    A follow-up has to BE the request. "add a stopwatch to the project" is a
    new task, not a request to stop one, so the phrase only counts when the
    message is essentially nothing else.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = ' '.join(text.casefold().split()).strip(' .!?।,')
    for name, phrases in FOLLOW_UPS.items():
        for phrase in phrases:
            if normalized == phrase:
                return name
            if normalized.endswith(' ' + phrase):
                prefix = normalized[: -len(phrase)].strip(' ,.')
                if prefix in FOLLOW_UP_PREFIXES:
                    return name
    return None


# ── The language the owner wants the answer in ────────────────────────────────

#: Phrases that ask for the answer in a particular language.
REPLY_LANGUAGES = (
    ('ta', ('tamil-la', 'tamil la', 'in tamil', 'tamil irundhu', 'தமிழ்ல', 'தமிழாக')),
    ('fr', ('french-la', 'french la', 'in french', 'en français', 'en francais',
            'français-la', 'francais-la')),
    ('en', ('english-la', 'english la', 'in english')),
)


def detect_reply_language(text):
    """The language the owner asked the answer in, or '' when they did not say."""
    if not isinstance(text, str) or not text.strip():
        return ''
    lowered = text.casefold()
    for code, markers in REPLY_LANGUAGES:
        for marker in markers:
            if marker in lowered:
                return code
    if TAMIL_SCRIPT.search(text):
        return 'ta'
    return ''


def strip_language_marker(text):
    """Remove the language marker from a request, so it is not part of the change."""
    result = text
    for _, markers in REPLY_LANGUAGES:
        for marker in markers:
            pattern = re.compile(r'(?<![a-z])' + re.escape(marker) + r'(?![a-z])',
                                 re.IGNORECASE)
            result = pattern.sub(' ', result)
    return ' '.join(result.split())


# ── Which project did the owner mean? ─────────────────────────────────────────

def match_projects(text, projects):
    """The saved projects the sentence could mean.

    Returns a list. An empty list means the sentence named none. More than one
    means the owner was not specific enough, and JARVIS has to ask.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    lowered = text.casefold()
    matches = []
    for project in projects:
        name = getattr(project, 'name', '')
        if not name:
            continue
        letters = [char for char in name if char.isalnum()]
        if not letters:
            continue
        pattern = re.compile(r'[\s\-_]*'.join(re.escape(char) for char in letters),
                             re.IGNORECASE)
        if pattern.search(lowered):
            matches.append(project)
    return matches


#: The headings of the final report, in the language the owner asked for.
SUMMARY_LABELS = {
    'en': {
        'changed': 'Changed files', 'tests': 'Tests', 'saved': 'Saved to',
        'diff': 'Reviewable diff', 'setup': 'Setup needed', 'none': 'no files changed',
        'task': 'Task', 'folder': 'Folder', 'editor': 'Editor', 'change': 'Change',
        'setup_needed': 'SETUP NEEDED',
        'protected': 'Your uncommitted work was untouched',
        'step_open': 'Open {project} in {editor}',
        'step_change': 'Ask Codex to: {change}',
        'step_tests': 'Run the configured tests: {command}',
        'step_report': 'Reporting the changed files, the diff and the test results.',
        'worktree_ready': ('Isolated worktree ready at {worktree}. '
                           'Your uncommitted work is untouched.'),
        'done': 'done', 'running': 'running', 'waiting': 'waiting',
        'declined': 'declined', 'failed': 'failed',
        'awaiting_approval': 'awaiting approval',
        'setup_set_up': 'Set up',
        'setup_not_found': 'the command was not found.',
        'setup_choose': 'choose its executable in Settings.',
        'setup_install': 'install it, or add "{command}" to PATH, or configure it as a launcher in Settings.',
    },
    'ta': {
        'changed': 'மாற்றப்பட்ட கோப்புகள்', 'tests': 'பரிட்சை முடிவு',
        'saved': 'சேமிக்கப்பட்ட இடம்', 'diff': 'பார்க்கக்கூடிய வேறுபாடு',
        'setup': 'அமைப்பு தேவை', 'none': 'கோப்புகள் மாற்றப்படவில்லை',
        'task': 'பணி', 'folder': 'கோப்புறை', 'editor': 'திருத்தி', 'change': 'மாற்றம்',
        'setup_needed': 'அமைப்பு தேவை',
        'protected': 'உங்கள் சேமிக்கப்படாத மாற்றங்கள் பாதுகாக்கப்பட்டன',
        'step_open': '{project} திறக்க — {editor}',
        'step_change': 'Codex-க்கு சொல்ல: {change}',
        'step_tests': 'அமைக்கப்பட்ட பரிட்சைகள்: {command}',
        'step_report': 'மாற்றப்பட்ட கோப்புகள், வேறுபாடு மற்றும் பரிட்சை முடிவுகளை அறிக்கிறது.',
        'worktree_ready': ('தனி வேலைப்பாதை {worktree} இல் தயாராக உள்ளது. '
                           'உங்கள் சேமிக்கப்படாத மாற்றங்கள் பாதுகாக்கப்பட்டன.'),
        'done': 'முடிந்தது', 'running': 'நடக்கிறது', 'waiting': 'காத்திருக்கிறது',
        'declined': 'நிராகரிக்கப்பட்டது', 'failed': 'தோல்வி',
        'awaiting_approval': 'ஒப்புதலுக்காக காத்திருக்கிறது',
        'setup_set_up': 'அமைக்கவும்',
        'setup_not_found': 'கமாண்ட் கிடைக்கவில்லை.',
        'setup_choose': 'Settings-இல் அதன் executable தேர்வு செய்யவும்.',
        'setup_install': 'அதை நிறுவியவும், அல்லது "{command}" ஐ PATH-இல் சேர்க்கவும், அல்லது Settings-இல் launcher ஆக அமைக்கவும்.',
    },
    'fr': {
        'changed': 'Fichiers modifiés', 'tests': 'Résultat des tests',
        'saved': 'Enregistré dans', 'diff': 'Diff à examiner',
        'setup': 'Configuration requise', 'none': 'aucun fichier modifié',
        'task': 'Tâche', 'folder': 'Dossier', 'editor': 'Éditeur', 'change': 'Modification',
        'setup_needed': 'CONFIGURATION REQUISE',
        'protected': 'Vos modifications non enregistrées sont intactes',
        'step_open': 'Ouvrir {project} dans {editor}',
        'step_change': 'Demander à Codex : {change}',
        'step_tests': 'Lancer les tests configurés : {command}',
        'step_report': 'Rapport des fichiers modifiés, du diff et des résultats des tests.',
        'worktree_ready': ('Copie de travail isolée prête dans {worktree}. '
                           'Vos modifications non enregistrées sont intactes.'),
        'done': 'terminé', 'running': 'en cours', 'waiting': 'en attente',
        'declined': 'refusé', 'failed': 'échec',
        'awaiting_approval': "en attente d'approbation",
        'setup_set_up': 'Configurer',
        'setup_not_found': 'la commande est introuvable.',
        'setup_choose': 'choisissez son executable dans les Paramètres.',
        'setup_install': 'installez-le, ou ajoutez "{command}" au PATH, ou configurez-le comme lanceur dans les Paramètres.',
    },
}


def summary_labels(language):
    """The report headings for a language, falling back to English."""
    return SUMMARY_LABELS.get((language or '').casefold(), SUMMARY_LABELS['en'])


#: The name of each language, for the instruction sent to the model.
LANGUAGE_NAMES = {'ta': 'Tamil', 'en': 'English', 'fr': 'French'}
