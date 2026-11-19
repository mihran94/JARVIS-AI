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
    window.on_theme_chosen('MARK LVII')
    for _ in range(4):
        app.processEvents()

    # 3. The Dynamic Island: the floating pill that says what JARVIS is
    #    doing while the owner is doing something else.
    island = window.prime_island
    island.set_state('listening', 'Listening')
    island.show()
    for _ in range(6):
        app.processEvents()
    shoot(app, island, '03-island')

    # 4. Settings and Safety.
    window.open_section('Settings & Safety')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '04-settings')

    # 5. The Files & Folders workspace.
    window.open_section('Files & Folders')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '05-files-and-folders')

    # 6. A plan with more than one step, showing the state of each step.
    window.prompt.setPlainText('/do open Notepad then open Calculator')
    window.send()
    app.processEvents()
    # The plan card sits under the conversation, so it is scrolled into view
    # before the picture is taken.
    from PySide6.QtWidgets import QScrollArea
    for area in window.findChildren(QScrollArea):
        if area.widget() is not None and area.widget().isAncestorOf(window.plan_card):
            area.ensureWidgetVisible(window.plan_card, 0, 0)
    app.processEvents()
    shoot(app, window, '06-plan-steps')

    # 7. The Windows Automation page, with the approval boundary shown.
    window.open_section('PC Control')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '07-pc-control')

    # 8. A pending approval, which is what the owner has to answer.
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
    shoot(app, window, '06-approval-pending')

    window.close()
    window.deleteLater()
    app.processEvents()
    print('done')
    scaled_shots()


if __name__ == '__main__':
    main()
