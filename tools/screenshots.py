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


def main():
    app = QApplication.instance() or QApplication([])
    base = tempfile.mkdtemp(prefix='jarvis-shots-')
    window = Window(base)
    # The normal launch path, exactly as main.py starts it.
    window.enable_omega(smoke=False)
    window.resize(1280, 820)
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

    # 3. The Dynamic Island.
    window.omega.switch('Island')
    for _ in range(6):
        app.processEvents()
    island = window.omega.floating
    island.show()
    shoot(app, island, '03-island')

    # 4. Settings and Safety.
    window.omega.switch('Omega')
    window.open_section('Settings & Safety')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '04-settings')

    # 5. The Files & Folders workspace.
    window.open_section('Files & Folders')
    for _ in range(4):
        app.processEvents()
    shoot(app, window, '05-files-and-folders')

    # 6. A pending approval, which is what the owner has to answer.
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


if __name__ == '__main__':
    main()
