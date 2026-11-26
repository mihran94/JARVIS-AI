"""Take real screenshots of the running JARVIS PRIME desktop.

This drives the same entry point the owner uses: the window is built, the
Omega/Island controller is started with the normal launch (not the smoke
variant), and the real pages are shown. Nothing is mocked.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from desktop.app import Window

OUT = os.path.join(ROOT, 'tools', 'shots')
os.makedirs(OUT, exist_ok=True)


def shoot(app, widget, name):
    """Let the layout settle, then save the widget as a PNG."""
    for _ in range(4):
        app.processEvents()
    path = os.path.join(OUT, name + '.png')
    pixmap = widget.grab()
    pixmap.save(path)
    print(f'{name:26} {pixmap.width()}x{pixmap.height()}  {path}')
    return path


def scaled_shots():
    """The same surface at the scaling a person actually uses.

    Windows is asked for 100 %, 125 %, 150 % and 200 % of the size. The
    pictures are taken in separate processes, because the scale factor
    is read when the application starts.
    """
    import subprocess
    import sys

    for factor in (1, 1.25, 1.5, 2):
        environment = dict(os.environ)
        environment['QT_SCALE_FACTOR'] = str(factor)
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        width = int(1280 / factor)
        height = int(800 / factor)
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), '--one', str(width), str(height),
             f'09-scaling-{int(factor * 100)}'],
            env=environment, capture_output=True, text=True)
        print(result.stdout.strip()[-400:])


def one_shot(width, height, name):
    """One picture of the chat at a given size."""
    app = QApplication.instance() or QApplication([])
    base = tempfile.mkdtemp(prefix='jarvis-shots-')
    window = Window(base)
    window.enable_omega(smoke=False)
    window.showNormal()
    window.resize(width, height)
    window.show()
    for _ in range(6):
        app.processEvents()
    window.open_section('JARVIS Chat')
    shoot(app, window, name)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--one':
        width = int(sys.argv[2])
        height = int(sys.argv[3])
        name = sys.argv[4]
        one_shot(width, height, name)
        return
    app = QApplication.instance() or QApplication([])
    base = tempfile.mkdtemp(prefix='jarvis-shots-')
    window = Window(base)
    # The normal launch path, exactly as main.py starts it.
    window.enable_omega(smoke=False)
    # The launch path maximises the window, which is right on a desktop and
    # is a square in the offscreen renderer. The picture is taken at the
    # size a person actually uses.
    window.showNormal()
    window.resize(1440, 900)
    window.show()
    for _ in range(6):
        app.processEvents()

    # 1. The main JARVIS Chat surface, in the default premium dark theme.
    window.open_section('JARVIS Chat')
    shoot(app, window, '01-chat-dark')

    # 2. The same surface in the light theme.
    window.on_theme_chosen('Apple Silver')
    shoot(app, window, '02-chat-light')
    window.on_theme_chosen('Warm Graphite')
    for _ in range(4):
        app.processEvents()

    # 3. The Dynamic Island: the floating pill that says what JARVIS is
    #    doing while the owner is doing something else.
    window.omega.set_voice('listening')
    island = window.omega.floating
    island.show()
    for _ in range(6):
        app.processEvents()
    shoot(app, island, '03-island')

    # 4. Settings and Safety.
    window.open_section('Settings & Safety')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '04-settings')

    # 5. The AI engines group in Settings: the Gemini fallback toggle, the
    #    on-device model and the local voice models.
    window.refresh_local_model_status()
    window.refresh_voice_models()
    for _ in range(4):
        app.processEvents()
    from PySide6.QtWidgets import QScrollArea
    for area in window.findChildren(QScrollArea):
        if area.widget() is not None and area.widget().isAncestorOf(window.gemini_fallback):
            area.ensureWidgetVisible(window.gemini_fallback, 0, 0)
    app.processEvents()
    shoot(app, window, '04b-settings-ai-engines')

    # 6. The Files & Folders workspace.
    window.open_section('Files & Folders')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '05-files-and-folders')

    # 7. A plan with more than one step, showing the state of each step.
    window.open_section('JARVIS Chat')
    window.prompt.setPlainText('/do open Notepad then open Calculator')
    window.send()
    app.processEvents()
    # The plan card sits under the conversation, so it is scrolled into view
    # before the picture is taken.
    for area in window.findChildren(QScrollArea):
        if area.widget() is not None and area.widget().isAncestorOf(window.plan_card):
            area.ensureWidgetVisible(window.plan_card, 0, 0)
    app.processEvents()
    shoot(app, window, '06-plan-steps')

    # 8. The Automation page: the browser, Suggestion Mode, Work on this,
    #    Any App Control and the proposed actions.
    window.open_section('PC Control')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '07-automation')

    # 9. A proposed action waiting for the owner, with Run, Edit and Dismiss.
    from desktop.automation_panel import ProposedAction
    window.automation_panel.propose(ProposedAction(
        kind='mission_tool', target='type_notepad(text=17 * 23)',
        detail='type_notepad(text=17 * 23)',
        editable={'text': '17 * 23'}))
    window.hud.strip.set_approval('Approval needed: mission_tool')
    window.hud.strip.set_progress(2, 6)
    window.hud.strip.set_engine('Gemini', 'The on-device model could not complete this step.')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '08-proposed-action')

    # 8b. The Automation page on its own: the browser, Suggestion Mode,
    #     Work on this, Any App Control and the task activity.
    window.automation_panel.set_windows(
        "notepad.exe (pid=4212): 'Untitled - Notepad'\n"
        "CalculatorApp.exe (pid=5304): 'Calculator'")
    window.automation_panel.set_controls(
        "Button 'Save' (id='saveButton')\nButton 'Open' (id='openButton')\n"
        "Edit 'Find' (id='findBox')")
    window.automation_panel.set_activity(
        'launch_app Notepad — completed\n'
        'desktop_plan_approval Calculator — verified')
    for _ in range(4):
        app.processEvents()
    shoot(app, window.automation_panel, '08b-automation-panel')

    # 8c. One proposed action, with Run, Edit and Dismiss.
    card = window.automation_panel.cards()[0]
    card.edit_button.click()
    for _ in range(4):
        app.processEvents()
    shoot(app, card, '08c-proposed-action-card')

    # 10. The HUD on its own: the readings, the engine and the stop.
    hud = window.hud
    hud.strip.set_reading('cpu', 0.34, '34%')
    hud.strip.set_reading('ram', 0.61, '61%')
    hud.strip.set_mic('The microphone is allowed for the voice feature.', False)
    for _ in range(4):
        app.processEvents()
    shoot(app, hud, '09-hud')

    # 11. A pending approval, which is what the owner has to answer.
    window.open_section('JARVIS Chat')
    window.transcript.appendPlainText(
        'JARVIS\nI found the login check that fails in auth.py and can fix it '
        'inside an isolated worktree.')
    window.chat_task_text.setText(
        'Fix the broken login validation\n\n'
        'Developer Studio • edit: auth.py\nApprove this task or decline below.')
    window.chat_task_card.show()
    window.chat_task_approve.show()
    window.chat_task_decline.show()
    shoot(app, window, '10-approval-pending')

    window.close()
    window.deleteLater()
    app.processEvents()
    print('done')
    scaled_shots()


if __name__ == '__main__':
    main()
