"""Run the Windows acceptance checks and write the report.

WHAT THIS IS
    The owner's acceptance list, run for real and written down. The
    script builds the actual JARVIS window, runs every check that can
    run on this computer, restarts the window and runs the "one window"
    check again, and writes the result to ``docs/WINDOWS_ACCEPTANCE.md``.

    A check that needs the real Windows desktop says that it was not
    run. It is never reported as a pass.

HOW TO RUN IT
    On Windows::

        python scripts/run_windows_acceptance.py

    On any other machine the checks that do not need Windows still run,
    and the report says which ones were left out and why.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

from core import acceptance
from desktop.app import Window

REPORT = os.path.join(ROOT, 'docs', 'WINDOWS_ACCEPTANCE.md')


def build(base):
    """One real JARVIS window."""
    window = Window(base)
    window.showNormal()
    window.resize(1360, 790)
    window.show()
    app = QApplication.instance()
    for _ in range(6):
        app.processEvents()
    return window


def main():
    app = QApplication.instance() or QApplication([])
    first_base = tempfile.mkdtemp(prefix='jarvis-acceptance-')
    window = build(first_base)
    checks = acceptance.run_all(window)
    first_window = next(check for check in checks if check.name == 'One JARVIS window')

    # The restart: the window is closed and a new one is opened, exactly
    # as the owner does when they start JARVIS again.
    window.close()
    window.deleteLater()
    app.processEvents()
    second_base = tempfile.mkdtemp(prefix='jarvis-acceptance-restart-')
    restarted = build(second_base)
    after = acceptance.check_one_window(restarted)
    checks = [after if check.name == 'One JARVIS window' else check
              for check in checks]
    restarted.close()
    restarted.deleteLater()
    app.processEvents()

    text = acceptance.report(checks)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as handle:
        handle.write(text)
    for check in checks:
        print(f'{check.status:8} {check.name}: {check.detail}')
    print('')
    print(f'The report was written to {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
