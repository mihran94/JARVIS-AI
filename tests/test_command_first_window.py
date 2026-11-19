"""End-to-end checks: command-first UI reuses existing JARVIS services."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from desktop.app import Window
from developer_studio.projects import SavedProject, save_projects


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.show()
    app.processEvents()
    return app, window


def test_main_toolbar_is_chat_island_settings_and_safety(tmp_path):
    app, window = make_window(tmp_path)
    try:
        assert window.island_button.isVisible()
        assert window.settings_button.isVisible()
        assert not window.resume_button.isVisible()
        assert any(button.text() == "EMERGENCY STOP" and button.isVisible()
                   for button in window.findChildren(QPushButton))
        assert window.plugins_button.isHidden()
        assert window.tools_button.isHidden()
        assert window.pages.currentIndex() == window.page_indices["JARVIS Chat"]
        assert not window.chat_provider.isVisible()
        window.enable_omega()
        app.processEvents()
        assert not window.omega.dock.isVisible()
        assert window.omega.reveal.isHidden()
        window.open_island()
        app.processEvents()
        assert window.omega.mode == "Island"
        assert window.omega.floating.isVisible()
        window.omega.switch("Omega")
        window.settings_button.click()
        app.processEvents()
        assert window.pages.currentIndex() == window.page_indices["Settings & Safety"]
        assert window.chat_provider.isVisible()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_project_list_and_unknown_command_stay_local(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        save_projects(window.store, [
            SavedProject("project-a", str(tmp_path), "VS Code", "pytest -q")
        ])
        monkeypatch.setattr(window, "get_key", lambda *_: (
            (_ for _ in ()).throw(AssertionError("No provider needed for commands"))))
        window.prompt.setPlainText("/projects")
        window.send()
        assert "project-a" in window.transcript.toPlainText()
        assert window.worker is None
        window.prompt.setPlainText("/shell format C:")
        window.send()
        assert "Unknown command" in window.transcript.toPlainText()
        assert window.worker is None
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_project_fix_reuses_existing_coding_approval_path(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        save_projects(window.store, [
            SavedProject("AI Creative Studio", str(tmp_path), "VS Code", "pytest -q")
        ])
        seen = []
        monkeypatch.setattr(window, "start_coding_task",
                            lambda request, text: seen.append((request, text)))
        window.prompt.setPlainText("/project AI Creative Studio fix login validation")
        window.send()
        assert window.prompt.toPlainText() == ""
        assert len(seen) == 1
        request, source = seen[0]
        assert request.project == "AI Creative Studio"
        assert request.make_change and request.change == "login validation"
        assert not request.run_tests
        assert source.startswith("/project")
        window.prompt.setPlainText("/project AI Creative Studio test")
        window.send()
        assert seen[-1][0].run_tests is True
        assert seen[-1][0].make_change is False
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_read_replies_preference_persists_after_restart(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = Window(tmp_path)
    try:
        assert not first.read_replies.isChecked()
        first.read_replies.setChecked(True)
        assert first.store.get('voice:read_replies') is True
    finally:
        first.close()
        first.deleteLater()
        app.processEvents()

    reopened = Window(tmp_path)
    try:
        assert reopened.read_replies.isChecked()
        reopened.read_replies.setChecked(False)
        assert reopened.store.get('voice:read_replies') is False
    finally:
        reopened.close()
        reopened.deleteLater()
        app.processEvents()
