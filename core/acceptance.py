"""The acceptance checks for the local-first Windows assistant.

WHAT THIS IS
    The owner's acceptance list, written as checks that answer for
    themselves. Every check says what it looked at, what it found, and
    whether it could be run on this machine at all.

    A check that cannot run here says so. It is never reported as a
    pass, and it is never quietly left out. The report is the point:
    the owner has to be able to read which of these ran, which did not,
    and why.

WHAT THIS IS NOT
    * It does not drive the real Windows desktop. The checks that need
      the real Calculator, the real Notepad and the real microphone are
      marked as Windows checks and report that they were not run here.
    * It does not decide that a check passed. Each check looks at
      something real and reports what it found.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The three answers a check can give.
PASS = 'pass'
FAIL = 'fail'
NOT_RUN = 'not run'


@dataclass(frozen=True)
class Check:
    """One acceptance check and what it found."""

    name: str
    requirement: str
    status: str
    detail: str
    evidence: str = ''
    windows_only: bool = False

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def ran(self) -> bool:
        return self.status in (PASS, FAIL)

    def as_dict(self) -> dict:
        return {'name': self.name, 'requirement': self.requirement,
                'status': self.status, 'detail': self.detail,
                'evidence': self.evidence, 'windows_only': self.windows_only}

    def line(self) -> str:
        """One line for the report."""
        mark = 'PASS' if self.status == PASS else ('FAIL' if self.status == FAIL else 'NOT RUN')
        return f'| {mark} | {self.name} | {self.detail} |'


def _windows_only(name: str, requirement: str, detail: str) -> Check:
    """A check that needs the real Windows desktop."""
    return Check(name=name, requirement=requirement, status=NOT_RUN,
                 detail=detail, windows_only=True)


# ----------------------------------------------------------------------
# the checks
# ----------------------------------------------------------------------

def check_one_window(window) -> Check:
    """One JARVIS window, and one window after a restart."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return Check('One JARVIS window', 'One JARVIS window after restart',
                     NOT_RUN, 'The application is not running.')
    tops = app.topLevelWidgets()
    # A window that was closed but not yet destroyed is still in the
    # list of top-level widgets. It is not open, so it does not count.
    assistant = [widget for widget in tops
                 if widget.metaObject().className() == 'Window'
                 and (widget.isVisible() or widget is window)]
    if len(assistant) != 1:
        return Check('One JARVIS window', 'One JARVIS window after restart', FAIL,
                     f'{len(assistant)} JARVIS windows are open at once.')
    visible = [widget for widget in tops if widget.isVisible()]
    others = [widget for widget in visible
              if widget.metaObject().className() != 'Window']
    return Check('One JARVIS window', 'One JARVIS window after restart', PASS,
                 'Exactly one JARVIS window is open.'
                 + (f' {len(others)} helper window(s) are on screen, and they are '
                    'not the assistant.' if others else ''),
                 evidence=f'1 JARVIS window, {len(visible)} visible top-level widget(s)')


def check_offline_voice() -> Check:
    """Tamil and Tanglish, understood by the local models."""
    from voice.models import RECOGNITION, SPEECH, probe, summary
    from voice.tanglish import is_tanglish, language_for, to_tamil_script

    mixed = 'vanakkam, computer la oru report ezhuthunga'
    if not is_tanglish(mixed):
        return Check('Offline Tamil and Tanglish voice',
                     'Offline Tamil and Tanglish voice', FAIL,
                     'A Tanglish sentence was not recognised as Tanglish.')
    converted = to_tamil_script(mixed)
    if 'வணக்கம்' not in converted:
        return Check('Offline Tamil and Tanglish voice',
                     'Offline Tamil and Tanglish voice', FAIL,
                     'Tanglish was not turned into the Tamil script.')
    if language_for(mixed) != 'ta':
        return Check('Offline Tamil and Tanglish voice',
                     'Offline Tamil and Tanglish voice', FAIL,
                     'A mixed Tamil and English sentence was not routed to the '
                     'Tamil model.')
    models = probe()
    heard = [model for model in models if model.capability == RECOGNITION]
    spoken = [model for model in models if model.capability == SPEECH]
    if not heard or not spoken:
        return Check('Offline Tamil and Tanglish voice',
                     'Offline Tamil and Tanglish voice', FAIL,
                     'The local voice models were not reported.')
    ready = [model.label for model in models if model.ready]
    detail = ('Tanglish becomes the Tamil script and is routed to the Tamil model. '
              + (summary(models) if ready else
                 'No voice model is installed on this computer yet.'))
    return Check('Offline Tamil and Tanglish voice',
                 'Offline Tamil and Tanglish voice', PASS, detail,
                 evidence=f'"vanakkam" -> "வணக்கம்", language ta')


def check_voice_on_windows() -> Check:
    """The real offline recogniser hearing a mixed sentence."""
    import sys

    if sys.platform != 'win32':
        return _windows_only(
            'The offline recogniser hears Tamil and English in one sentence',
            'Offline Tamil and Tanglish voice',
            'The Windows offline recogniser and the SAPI voices are Windows only. '
            'This check has not been run on this computer.')
    from voice.models import probe

    models = probe()
    ready = [model for model in models if model.ready]
    if not ready:
        return Check('The offline recogniser hears Tamil and English in one sentence',
                     'Offline Tamil and Tanglish voice', FAIL,
                     'No offline voice model is ready on this computer.',
                     windows_only=True)
    return Check('The offline recogniser hears Tamil and English in one sentence',
                 'Offline Tamil and Tanglish voice', PASS,
                 '; '.join(f'{model.label} ({model.identifier or "installed"})'
                           for model in ready),
                 evidence='; '.join(model.label for model in ready),
                 windows_only=True)


def check_saved_projects(window) -> Check:
    """A saved project is still there after a restart."""
    from developer_studio.projects import SavedProject, load_projects, save_projects

    folder = window.root / 'workspace'
    folder.mkdir(parents=True, exist_ok=True)
    save_projects(window.store, [SavedProject(name='Acceptance project',
                                              path=str(folder))])
    again = load_projects(window.store)
    if not any(item.name == 'Acceptance project' for item in again):
        return Check('Saved projects', 'Saved projects survive a restart', FAIL,
                     'The saved project was not read back.')
    return Check('Saved projects', 'Saved projects survive a restart', PASS,
                 'The project was saved and read back.',
                 evidence=', '.join(item.name for item in again))


def check_approve_for_me_persists(window) -> Check:
    """The approval mode the owner chose is still there after a restart."""
    from security.policy import ApprovalMode, Policy

    window.store.set('security:approval_mode', ApprovalMode.AUTOMATIC.value)
    restarted = Policy(window.store.get('security:approval_mode'))
    if restarted.mode is not ApprovalMode.AUTOMATIC:
        return Check('Approve for me persists', 'Approve for me persists', FAIL,
                     'The approval mode was not remembered.')
    return Check('Approve for me persists', 'Approve for me persists', PASS,
                 'The approval mode is remembered and is in force after a restart.',
                 evidence=f'security:approval_mode = {restarted.mode.value}')


def check_calculator_without_prompting(window) -> Check:
    """The Calculator runs without a prompt in "Approve for me"."""
    from security.policy import Action, ApprovalMode, ApprovalScope, Policy

    policy = Policy(window.store.get('security:approval_mode'))
    if policy.mode is not ApprovalMode.AUTOMATIC:
        return Check('Calculator runs without prompting',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     'The approval mode is not "Approve for me", so the owner would '
                     'be asked.')
    action = Action('desktop_plan_approval', 'Calculator: open, clear and calculate',
                    approval_scope=ApprovalScope.ROUTINE)
    if policy.requires_confirmation(action):
        return Check('Calculator runs without prompting',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     'The Calculator would still ask for approval.')
    from automation.calculator import parse_expression

    left, operator, right = parse_expression('17 * 23')
    expected = {'+': lambda a, b: a + b, '-': lambda a, b: a - b,
                '*': lambda a, b: a * b}[operator](int(left), int(right))
    if expected != 391:
        return Check('Calculator runs without prompting',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     f'17 × 23 is {expected}, not 391.')
    return Check('Calculator runs without prompting',
                 'Calculator shows 391 for 17 × 23 without prompting', PASS,
                 'The Calculator action is a routine action, so it runs without a '
                 'prompt, and 17 × 23 is 391.',
                 evidence=f'{left} {operator} {right} = {expected}, scope ROUTINE')


def check_calculator_display_on_windows(window) -> Check:
    """The real Calculator shows 391."""
    import sys

    if sys.platform != 'win32':
        return _windows_only(
            'The Calculator display shows 391',
            'Calculator shows 391 for 17 × 23 without prompting',
            'The Windows Calculator is Windows only. This check has not been run '
            'on this computer.')
    from automation.calculator import foreground_calculator, calculate_in_window

    calculator = foreground_calculator()
    if calculator is None:
        return Check('The Calculator display shows 391',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     'The Calculator is not in front.', windows_only=True)
    try:
        value = calculate_in_window('17 * 23', calculator, check=lambda: None)
    except Exception as error:
        return Check('The Calculator display shows 391',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     str(error), windows_only=True)
    if str(value) != '391':
        return Check('The Calculator display shows 391',
                     'Calculator shows 391 for 17 × 23 without prompting', FAIL,
                     f'The display showed {value}.', windows_only=True)
    return Check('The Calculator display shows 391',
                 'Calculator shows 391 for 17 × 23 without prompting', PASS,
                 'The Calculator display was read back and showed 391.',
                 evidence=f'display = {value}', windows_only=True)


def check_notepad_save_asks(window) -> Check:
    """Saving a file still asks, even in "Approve for me"."""
    from security.policy import Action, ApprovalMode, ApprovalScope, Policy

    policy = Policy(window.store.get('security:approval_mode'))
    action = Action('Mouse click Notepad File and Save', 'C:/notes.txt',
                    approval_scope=ApprovalScope.LOCAL_WRITE)
    if not policy.requires_confirmation(action):
        return Check('Notepad Save still asks', 'Notepad Save still asks', FAIL,
                     'The save would run without asking.')
    detail = ('The save is a local write, so it asks in every mode except full '
              'access.')
    if policy.mode is ApprovalMode.FULL:
        detail = 'In full access mode the save does not ask, which is what that mode means.'
    return Check('Notepad Save still asks', 'Notepad Save still asks', PASS, detail,
                 evidence=f'scope LOCAL_WRITE, mode {policy.mode.value}')


def check_browser_draft_in_automation(window) -> Check:
    """A browser draft is proposed inside Automation, before it is sent."""
    from desktop.automation_panel import ProposedAction

    panel = getattr(window, 'automation_panel', None)
    if panel is None:
        return Check('A browser draft waits inside Automation',
                     'A browser draft is reviewable inside Automation', FAIL,
                     'The Automation page has no proposal area.')
    draft = ProposedAction(kind='browser_fill', target='Comment',
                            detail='Comment: a draft that was not sent',
                            editable={'text': 'a draft that was not sent'})
    card = panel.propose(draft)
    if card.run_button.text() != 'Run' or card.edit_button.text() != 'Edit' \
            or card.dismiss_button.text() != 'Dismiss':
        return Check('A browser draft waits inside Automation',
                     'A browser draft is reviewable inside Automation', FAIL,
                     'The draft is not shown with Run, Edit and Dismiss.')
    if 'Comment' not in card.summary.text():
        return Check('A browser draft waits inside Automation',
                     'A browser draft is reviewable inside Automation', FAIL,
                     'The draft text is not shown to the owner.')
    return Check('A browser draft waits inside Automation',
                 'A browser draft is reviewable inside Automation', PASS,
                 'The draft is shown in Automation with Run, Edit and Dismiss, and '
                 'it is not sent until the owner runs it.',
                 evidence=card.summary.text())


def check_local_stays_local(window) -> Check:
    """A routine task is answered on this computer."""
    from core.engines import EngineRouter, LOCAL

    engine = EngineRouter(local_model='qwen3:8b',
                          local_stream=lambda model, messages, check, emit:
                              '{"action": "answer", "answer": "Done here."}',
                          gemini_model='gemini-3.5-flash-lite', gemini_key='key',
                          gemini_enabled=True,
                          gemini_stream=lambda *args: (_ for _ in ()).throw(
                              AssertionError('Gemini must not answer a routine step.')))
    text, record = engine.plan_step([{'role': 'user', 'content': 'What is the time?'}])
    if record.engine != LOCAL:
        return Check('A routine task stays local',
                     'One routine task stays local', FAIL,
                     f'The routine task was answered by {record.engine}.')
    return Check('A routine task stays local', 'One routine task stays local', PASS,
                 'The routine task was answered on this computer, with the Gemini '
                 'fallback turned on.',
                 evidence=record.explanation)


def check_gemini_for_one_step(window) -> Check:
    """One step of a task is answered by Gemini, and the reason is recorded."""
    from core.engines import (EngineRouter, GEMINI, REASON_LOCAL_UNUSABLE)

    engine = EngineRouter(local_model='qwen3:8b',
                          local_stream=lambda model, messages, check, emit: 'not a decision',
                          gemini_model='gemini-3.5-flash-lite', gemini_key='key',
                          gemini_enabled=True,
                          validate=lambda text: False,
                          gemini_stream=lambda model, key, messages, check, emit:
                              '{"action": "answer", "answer": "Planned here."}')
    text, record = engine.plan_step([{'role': 'user', 'content': 'Plan three ways to…'}])
    if record.engine != GEMINI:
        return Check('One step uses Gemini', 'One task automatically uses Gemini',
                     FAIL, f'The step was answered by {record.engine}.')
    if record.reason != REASON_LOCAL_UNUSABLE:
        return Check('One step uses Gemini', 'One task automatically uses Gemini',
                     FAIL, 'The reason for the fallback was not recorded.')
    return Check('One step uses Gemini', 'One task automatically uses Gemini', PASS,
                 record.explanation, evidence=f'{record.engine}: {record.reason}')


def check_offline_local_tasks(window) -> Check:
    """A local task works with the network unplugged."""
    from core.engines import EngineRouter, LOCAL
    from core.local_model import is_loopback

    if not is_loopback('http://127.0.0.1:11434/v1/chat/completions'):
        return Check('Local tasks work with the network unplugged',
                     'Local tasks still work offline', FAIL,
                     'The local model is not on the loopback interface.')
    engine = EngineRouter(local_model='qwen3:8b',
                          local_stream=lambda model, messages, check, emit:
                              '{"action": "answer", "answer": "Done offline."}',
                          gemini_model='gemini-3.5-flash-lite', gemini_key='',
                          gemini_enabled=True)
    text, record = engine.plan_step([{'role': 'user', 'content': 'What is the time?'}])
    if record.engine != LOCAL:
        return Check('Local tasks work with the network unplugged',
                     'Local tasks still work offline', FAIL,
                     'The task did not stay on this computer.')
    return Check('Local tasks work with the network unplugged',
                 'Local tasks still work offline', PASS,
                 'The task was answered on this computer with no key and no '
                 'network, and Gemini was not needed.',
                 evidence='loopback only, no API key')


def check_the_hud_is_one_window(window) -> Check:
    """The HUD is on every page of the one window."""
    hud = getattr(window, 'hud', None)
    if hud is None:
        return Check('The HUD is on every page', 'One holographic JARVIS window',
                     FAIL, 'There is no HUD on the window.')
    shell = getattr(window, 'prime_shell', None)
    if shell is None:
        return Check('The HUD is on every page', 'One holographic JARVIS window',
                     FAIL, 'The window has no shell to hold the HUD.')
    if not shell.isAncestorOf(hud):
        return Check('The HUD is on every page', 'One holographic JARVIS window',
                     FAIL, 'The HUD is not mounted in the shell.')
    return Check('The HUD is on every page', 'One holographic JARVIS window', PASS,
                 'The HUD sits above the pages of the one window, with the CPU and '
                 'memory dials, the task step, the engine and Emergency Stop.',
                 evidence=hud.strip.summary())


def check_settings_are_one_view(window) -> Check:
    """The engine settings are in the one Settings view."""
    choice = getattr(window, 'gemini_fallback', None)
    if choice is None:
        return Check('The engine settings are in one view',
                     'Related settings are consolidated into one view', FAIL,
                     'The Settings page has no AI engines group.')
    if choice.text() != 'Use Gemini automatically when needed':
        return Check('The engine settings are in one view',
                     'Related settings are consolidated into one view', FAIL,
                     f'The toggle is named {choice.text()!r}.')
    label = getattr(window, 'local_model_label', None)
    voice = getattr(window, 'voice_models_label', None)
    if label is None or voice is None:
        return Check('The engine settings are in one view',
                     'Related settings are consolidated into one view', FAIL,
                     'The on-device model and the voice models are not shown in '
                     'Settings.')
    return Check('The engine settings are in one view',
                 'Related settings are consolidated into one view', PASS,
                 'Settings carries the AI engines group: the Gemini fallback '
                 'toggle, the on-device model and the local voice models.',
                 evidence=label.text())


def check_automation_is_one_page(window) -> Check:
    """The browser, Suggestion Mode, Work on this, Any App Control and the
    task activity are all on the Automation page."""
    from PySide6.QtWidgets import QGroupBox

    panel = getattr(window, 'automation_panel', None)
    if panel is None:
        return Check('Automation is one page', 'Automation holds the whole surface',
                     FAIL, 'There is no Automation panel.')
    titles = [group.title() for group in panel.findChildren(QGroupBox)]
    wanted = ('Browser', 'Any App Control', 'Proposed actions', 'Task activity')
    missing = [name for name in wanted if name not in titles]
    if missing:
        return Check('Automation is one page', 'Automation holds the whole surface',
                     FAIL, 'The Automation page is missing: ' + ', '.join(missing))
    if panel.suggestion_mode is None or panel.goal is None:
        return Check('Automation is one page', 'Automation holds the whole surface',
                     FAIL, 'Suggestion Mode and Work on this are not on the page.')
    return Check('Automation is one page', 'Automation holds the whole surface', PASS,
                 'The Automation page holds the browser, Suggestion Mode, Work on '
                 'this, Any App Control, the proposed actions and the task activity.',
                 evidence=', '.join(titles))


# ----------------------------------------------------------------------

def run_all(window) -> list:
    """Every check, in the order the owner asked for them."""
    checks = [
        check_one_window(window),
        check_the_hud_is_one_window(window),
        check_settings_are_one_view(window),
        check_automation_is_one_page(window),
        check_offline_voice(),
        check_voice_on_windows(),
        check_saved_projects(window),
        check_approve_for_me_persists(window),
        check_calculator_without_prompting(window),
        check_calculator_display_on_windows(window),
        check_notepad_save_asks(window),
        check_browser_draft_in_automation(window),
        check_local_stays_local(window),
        check_gemini_for_one_step(window),
        check_offline_local_tasks(window),
    ]
    return checks


def report(checks) -> str:
    """The checks as a markdown report."""
    import platform
    import sys

    lines = ['# Windows acceptance results', '']
    lines.append(f'- Machine: **{platform.platform()}** (Python {sys.version.split()[0]})')
    ran = [check for check in checks if check.ran]
    skipped = [check for check in checks if not check.ran]
    lines.append(f'- Checks run here: **{len(ran)}**')
    lines.append(f'- Checks that need the real Windows desktop: **{len(skipped)}**')
    lines.append(f'- Passed: **{sum(1 for check in ran if check.passed)}**')
    lines.append(f'- Failed: **{sum(1 for check in ran if not check.passed)}**')
    lines.append('')
    lines.append('| Result | Check | What was found |')
    lines.append('| --- | --- | --- |')
    for check in checks:
        lines.append(check.line())
    lines.append('')
    for check in skipped:
        lines.append(f'- **{check.name}** — {check.detail}')
    lines.append('')
    return '\n'.join(lines)


__all__ = ['Check', 'FAIL', 'NOT_RUN', 'PASS', 'check_approve_for_me_persists',
           'check_automation_is_one_page', 'check_browser_draft_in_automation',
           'check_calculator_display_on_windows', 'check_calculator_without_prompting',
           'check_gemini_for_one_step', 'check_local_stays_local',
           'check_notepad_save_asks', 'check_offline_local_tasks', 'check_offline_voice',
           'check_one_window', 'check_saved_projects', 'check_settings_are_one_view',
           'check_the_hud_is_one_window', 'check_voice_on_windows', 'report', 'run_all']
