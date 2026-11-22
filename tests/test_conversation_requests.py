"""Natural addressing must retain approvals and literal user payloads."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from core.conversation import addressed_request
from desktop.voice_commands import parse_voice_command
from automation.desktop_tasks import parse_desktop_task
from developer_studio.commands import parse_command
from desktop.app import Window


@pytest.mark.parametrize('text,app', [
    ('Jarvis, CapCut open pannu', 'CapCut'),
    ('Hey Jarvis, please open Notepad', 'Notepad'),
    ('ஜார்விஸ், calculator திறந்து வை', 'Calculator'),
    ('J.A.R.V.I.S., launch CapCut', 'CapCut'),
])
def test_direct_requests_select_only_known_apps(text, app):
    assert parse_voice_command(text) == app


@pytest.mark.parametrize('text', [
    'please open notepad',
    'Jarvis, do not open Notepad',
    'Jarvis, how do I open Notepad?',
    'Jarvis, "open Notepad"',
    'Jarvis, open Notepad and delete my files',
    'Jarvis, open powershell',
    'Jarvis, if I say open Notepad what happens?',
])
def test_questions_negations_and_extra_actions_do_not_launch(text):
    assert parse_voice_command(text) is None
    assert parse_desktop_task(text) is None
    assert parse_command(text) is None


def test_addressing_does_not_modify_literal_task_payload():
    task = parse_desktop_task('Jarvis, please open Notepad and type: Hey Jarvis,\nPlease KEEP My தமிழ் Text!')
    assert task.text == 'Hey Jarvis,\nPlease KEEP My தமிழ் Text!'
    assert addressed_request('Jarvisville open Notepad') == 'Jarvisville open Notepad'


def test_conversational_commands_stay_local_and_preserve_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda name: launches.append(name))
    monkeypatch.setattr(win, 'get_key', lambda *_: pytest.fail('local request needs no provider'))
    try:
        win.prompt.setPlainText('Jarvis, ennoda projects kattu')
        win.send()
        assert 'No saved projects' in win.transcript.toPlainText()
        win.prompt.setPlainText('Hey Jarvis, please open Notepad')
        win.send()
        assert win.chat_launch is not None
        assert launches == []
        win.finish_chat_launch(False)
        assert launches == []
        win.prompt.setPlainText('Jarvis, open Notepad')
        win.send()
        win.stop()
        assert launches == []
        assert win.chat_launch is None
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_chat_keeps_original_user_words_and_honest_personality(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    calls = []
    monkeypatch.setattr(win, 'get_key', lambda *_: 'test-only')
    monkeypatch.setattr(win, 'start_worker', lambda *args, **kwargs: calls.append(args))
    try:
        text = 'Jarvis, எனக்கு ஒரு நல்ல நண்பன் மாதிரி பேசு'
        win.prompt.setPlainText(text)
        win.send()
        assert len(calls) == 1
        messages = calls[0][3]
        assert messages[-1]['content'] == text
        assert 'friendly, practical personal AI assistant' in messages[0]['content']
        assert 'Never claim' in messages[0]['content']
        assert win.chat_launch is None
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_addressed_video_brief_reaches_existing_workflow_unchanged(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    briefs = []
    monkeypatch.setattr(win, 'generate_video_plan', lambda **kwargs: briefs.append(kwargs['chat_brief']))
    try:
        win.prompt.setPlainText('Jarvis, /video தமிழ் Story: KEEP This Case')
        win.send()
        assert briefs == ['தமிழ் Story: KEEP This Case']
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_explicit_analysis_cannot_schedule_coding(tmp_path, monkeypatch):
    from developer_studio.projects import SavedProject
    from providers.profiles import model_for

    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    calls = []
    monkeypatch.setattr(win, 'get_key', lambda *_: 'test-only')
    monkeypatch.setattr(win, 'start_worker', lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr('desktop.app.load_projects', lambda _: [
        SavedProject('project-a', str(tmp_path), 'VS Code', 'pytest'),
    ])
    monkeypatch.setattr(win, 'start_coding_task', lambda *_: pytest.fail('Analysis scheduled a change'))
    try:
        win.prompt.setPlainText('/analyze project-a fix login and run tests')
        win.send()
        provider, model, _, messages, kind = calls[0]
        assert (provider, model, kind) == ('Gemini', model_for('Gemini', 'deep'), 'chat')
        assert messages[-1]['content'] == 'project-a fix login and run tests'
        assert win.stored_profile('Gemini') == 'fast'
    finally:
        win.close()
        app.processEvents()



@pytest.mark.parametrize('text', [
    'Déboguer les erreurs du projet',
    'இந்தப் பிழையைக் கண்டுபிடி',
    'padi padiya explain pannu',
])
def test_auto_effort_recognizes_multilingual_analysis(text):
    from providers.task_brain import effort_for

    assert effort_for(text) == 'deep'
    assert effort_for(text, 'Fast') == 'fast'


def test_suggestion_mode_keeps_action_requests_in_chat(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    requests = []

    def start_worker(provider, model, key, messages, kind, backup=None):
        requests.append((messages, backup))
        win.worker_kind = kind
        win.chat_task = win.store.task(kind, model)
        win.on_result('completed', 'First, decide what you want to write.')

    monkeypatch.setattr(win, 'get_key', lambda *_: 'test-only')
    monkeypatch.setattr(win, 'start_worker', start_worker)
    monkeypatch.setattr(win.browser, 'command', lambda *_: pytest.fail('Browser dispatched'))
    monkeypatch.setattr(win.memory_service, 'as_context',
                        lambda *_: pytest.fail('Suggestion read saved notes'))
    monkeypatch.setattr('desktop.app.as_untrusted_context',
                        lambda *_: pytest.fail('Suggestion shared attachments'))

    try:
        assert not win.suggestion_mode.isChecked()
        assert win.prime_chat.composer.isAncestorOf(win.suggestion_mode)
        win.suggestion_mode.click()
        assert win.send_button.text() == 'Get suggestions'
        win.attachments = [object()]
        win.files_share_once.setChecked(True)
        win.use_notes.setChecked(True)
        win.backup_consent.setChecked(True)
        for text in ('Open Notepad', '/browser open https://example.com'):
            win.prompt.setPlainText(text)
            win.send()
            messages, backup = requests[-1]
            assert messages[-1]['content'] == text
            assert 'Suggestion Mode is active' in messages[0]['content']
            assert backup is None
            assert win.desktop_pending is None
            assert win.chat_launch is None
            assert win.prime_chat.conversation.bubbles[-1].body.text() == (
                'First, decide what you want to write.')
        assert len(requests) == 2
        win.attachments = []
        assert not win.files_share_once.isChecked()
        assert not win.use_notes.isChecked()
        assert not win.backup_consent.isChecked()

        win.suggestion_mode.click()
        assert win.send_button.text() == 'Send'
        win.prompt.setPlainText('Jarvis, /suggest\tHow should I organize my notes?')
        win.send()
        assert len(requests) == 3
        assert requests[-1][0][-1]['content'] == 'How should I organize my notes?'
        win.prompt.setPlainText('Open Notepad')
        win.send()
        assert win.chat_launch is not None
        assert len(requests) == 3
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_suggestion_mode_dictation_bypasses_spoken_task_routing(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    command = 'Prepare Google Flow prompts for a short Reel'
    monkeypatch.setattr(win, 'route_task', lambda *_: pytest.fail('Spoken task dispatched'))
    try:
        win.voice_panel.allow.setChecked(True)
        win.suggestion_mode.setChecked(True)
        win.on_wake_detected('Hey Jarvis', command)
        assert win.prompt.toPlainText() == command
        win.prompt.clear()
        win.suggestion_mode.setChecked(False)
        win.on_voice_transcript('/suggest ' + command)
        assert win.prompt.toPlainText() == '/suggest ' + command
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_suggestion_requires_review_then_existing_step_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', launches.append)
    try:
        win.worker_kind = 'suggestion'
        win.chat_ticket = win.policy.ticket()
        win.chat_task = win.store.task('suggestion', 'test')
        win.on_result('completed', 'Open the editor.\nJARVIS_PLAN: /do open Notepad')
        assert win.suggested_steps[0].app == 'Notepad'
        assert win.chat_launch is None
        assert 'Open Notepad' in win.suggestion_preview.text()

        win.review_suggested_plan()
        assert win.chat_launch is not None
        assert not win.suggested_steps
        assert launches == []
        win.finish_chat_launch(False)
        assert launches == []
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('proposal', [
    '/do open Notepad and type: example',
    '/do open Notepad then open PowerShell',
    '/do open Calculator\nMore text',
])
def test_unsupported_suggestion_stays_advice(proposal):
    from desktop.conversation_plan import extract_suggested_plan

    reply = 'Possible steps.\nJARVIS_PLAN: ' + proposal
    assert extract_suggested_plan(reply) == (reply, ())


def test_suggested_notepad_uses_user_text_and_existing_approval(tmp_path, monkeypatch):
    from automation.desktop_tasks import VerifiedEdit

    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    typed = []
    payload = 'நாளைக்கு Promo edit\nKeep: Case and punctuation!'
    monkeypatch.setattr(win, 'start_worker', lambda *_a, **_kw: pytest.fail('Text sent to AI'))
    monkeypatch.setattr('desktop.app.target_is_foreground', lambda _: True)

    def type_text(target, text):
        typed.append((target, text))
        return VerifiedEdit('Text verified in the editor')

    monkeypatch.setattr('desktop.app.type_into_target', type_text)
    try:
        win.prompt.setPlainText('/suggest type in Notepad: ' + payload)
        win.send()
        assert win.suggested_steps[0].typing.text == payload
        assert 'Typing will not save a file.' in win.transcript.toPlainText()
        assert win.chat_launch is None
        win.review_suggested_plan()
        assert typed == []
        assert win.chat_launch is not None
        activity = win.prime_shell.activity
        assert activity.state.text() == 'Approval required'
        assert 'Review the exact text' in activity.live_detail.text()
        win.finish_chat_launch(True)
        assert 'Checking the foreground window' in activity.live_detail.text()
        assert typed == []
        win.complete_desktop_task()
        assert typed == [('Notepad', payload)]
        assert 'Text verified in the editor' in win.transcript.toPlainText()
        row = next(row for row in win.store.tasks() if row['kind'] == 'desktop_type')
        assert row['status'] == 'verified'
        assert 'foreground confirmed' in row['detail']
        assert 'JARVIS did not save a file.' in row['detail']
        assert activity.live_detail.text() == ''
        destination = tmp_path / 'inserted.txt'
        monkeypatch.setattr('desktop.app.QFileDialog.getSaveFileName',
                            lambda *_a, **_kw: (str(destination), ''))
        assert not win.desktop_save_button.isHidden()
        win.desktop_save_button.click()
        assert destination.read_bytes() == payload.encode('utf-8')
        assert 'saved and verified' in win.desktop_result_label.text()
        assert win.desktop_save_button.isHidden()
        assert any(row['kind'] == 'desktop_text_export' and row['status'] == 'verified'
                   for row in win.store.tasks())

    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('utterance, app, payload', [
    ('நோட்பேடை திறந்து எழுது நாளைக்கு promo video', 'Notepad', 'நாளைக்கு promo video'),
    ('Notepad open panni ezhuthu நாளைக்கு promo video', 'Notepad', 'நாளைக்கு promo video'),
    ('Calculator open pannu', 'Calculator', None),
])
def test_voice_desktop_action_is_editable_and_requires_approval(tmp_path, monkeypatch,
                                                               utterance, app, payload):
    qt = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    monkeypatch.setattr(win, 'start_worker', lambda *_a, **_kw: pytest.fail('Sent to AI'))
    monkeypatch.setattr('desktop.app.launch_app', lambda *_: pytest.fail('Launched without approval'))
    try:
        win.voice_panel.allow.setChecked(True)
        win.on_voice_transcript(utterance)
        assert win.prompt.toPlainText() == '/suggest ' + utterance
        assert not win.suggested_steps
        assert win.chat_launch is None
        win.send()
        step, = win.suggested_steps
        assert step.app == app
        assert (step.typing.text if step.typing else None) == payload
        assert win.chat_launch is None
        win.review_suggested_plan()
        assert win.chat_launch is not None
        win.finish_chat_launch(False)
        assert win.desktop_pending is None
    finally:
        win.close()
        win.deleteLater()
        qt.processEvents()
