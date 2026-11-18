"""PRIME file/folder UI: one-click selection and one-turn opt-in sending."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from desktop.app import Window
from desktop.attachments import stage_files


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.show()
    app.processEvents()
    return app, window


def test_file_and_folder_sections_reachable_without_another_main_menu(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        sample = tmp_path / "example.txt"
        sample.write_text("private user-selected context", encoding="utf-8")
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "hello.md").write_text("# folder context", encoding="utf-8")
        monkeypatch.setattr(
            QFileDialog, "getOpenFileNames",
            lambda *_args, **_kwargs: ([str(sample)], ""))
        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory",
            lambda *_args, **_kwargs: str(folder))
        window.attach_button.click()
        assert window.pages.currentIndex() == window.page_indices["Files & Folders"]
        window.choose_attachment_files()
        assert len(window.attachments) == 1
        assert window.attach_button.text() == "Attach (1)"
        window.files_share_once.setChecked(True)
        window.choose_attachment_folder()
        assert len(window.attachments) == 2
        assert window.attach_button.text() == "Attach (2)"
        assert not window.files_share_once.isChecked()  # new content needs new consent
        assert not window.files_share_once.isChecked()
        assert window.attachment_list.count() == 2
        window.open_section("JARVIS Chat")
        assert window.composer_bar.isVisibleTo(window)
        window.open_section("Settings & Safety")
        assert not window.composer_bar.isVisibleTo(window)
    finally:
        window.close()
        app.processEvents()


def test_local_selection_never_reaches_model_without_explicit_one_time_opt_in(
        tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    sent = []
    try:
        file = tmp_path / "notes.txt"
        file.write_text("private-local-text-abc", encoding="utf-8")
        window.attachments = stage_files([file])
        window.update_attachment_display()
        monkeypatch.setattr(window, "get_key", lambda *_args: "offline-test-token")
        monkeypatch.setattr(
            window, "start_worker", lambda *args, **kwargs: sent.append((args, kwargs)))

        window.prompt.setPlainText("Please summarize this note.")
        window.send()
        assert len(sent) == 1
        assert "private-local-text-abc" not in str(sent[0][0][3])
        assert len(window.attachments) == 1

        window.files_share_once.setChecked(True)
        window.prompt.setPlainText("Please summarize this note.")
        window.send()
        assert len(sent) == 2
        prompt_data = sent[1][0][3][-1]["content"]
        assert "private-local-text-abc" in prompt_data
        assert str(tmp_path) not in prompt_data
        assert window.attachments == []
        assert not window.files_share_once.isChecked()
        assert "private-local-text-abc" not in str(window.store.messages(window.session))
    finally:
        window.close()
        app.processEvents()


def test_new_conversation_clears_unsent_snapshots(tmp_path):
    app, window = make_window(tmp_path)
    try:
        file = tmp_path / "draft.txt"
        file.write_text("a text draft", encoding="utf-8")
        window.attachments = stage_files([file])
        window.update_attachment_display()
        window.files_share_once.setChecked(True)
        window.new_chat()
        assert not window.attachments
        assert not window.files_share_once.isChecked()
    finally:
        window.close()
        app.processEvents()
