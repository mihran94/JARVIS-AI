"""PRIME file/folder UI: one-click selection and one-turn opt-in sending."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

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
        display = window.prime_chat.displays.currentWidget()
        window.attach_button.click()
        assert window.upload_popup.isVisible()
        assert window.prime_chat.displays.currentWidget() is display
        window.choose_attachment_files()
        assert len(window.attachments) == 1
        assert window.upload_list.item(0).text() == "example.txt"
        assert window.attach_button.text() == "+  UPLOAD FILE (1)"
        window.upload_share_once.setChecked(True)
        assert window.files_share_once.isChecked()
        close = next(button for button in window.upload_popup.findChildren(QPushButton)
                     if button.text() == "Close")
        close.click()
        assert not window.upload_popup.isVisible()
        assert window.prime_chat.displays.currentWidget() is display
        window.open_section("Files & Folders")
        window.choose_attachment_folder()
        assert len(window.attachments) == 2
        assert window.attach_button.text() == "+  UPLOAD FILE (2)"
        assert not window.files_share_once.isChecked()  # new content needs new consent
        assert window.attachment_list.count() == 2
        window.open_section("JARVIS Chat")
        assert window.prime_chat.composer.isVisibleTo(window)
        window.open_section("Settings & Safety")
        assert window.prime_chat.composer.isVisibleTo(window)
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


def test_deleting_chat_discards_queued_file_content(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        file = tmp_path / "delete-me.txt"
        file.write_text("private draft", encoding="utf-8")
        window.attachments = stage_files([file])
        window.update_attachment_display()
        window.files_share_once.setChecked(True)
        monkeypatch.setattr(window, "confirm", lambda action: True)
        window.clear_chat()
        assert not window.attachments
        assert not window.files_share_once.isChecked()
        assert window.attach_button.text() == "+  UPLOAD FILE"
    finally:
        window.close()
        app.processEvents()


def test_a_document_is_read_and_shown_without_being_sent(tmp_path, monkeypatch):
    """Reading a document is local. Nothing is shared until it is asked for."""
    from document_fixtures import make_pdf

    app, window = make_window(tmp_path)
    try:
        path = make_pdf(tmp_path / "letter.pdf")
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *_args, **_kwargs: (str(path), ""))
        window.open_section("Files & Folders")
        window.read_document_file()
        assert "Hello from the PDF" in window.document_preview.toPlainText()
        assert "Nothing was sent anywhere" in window.document_status.text()
        # The document is not in the list of shared files, and consent is off.
        assert window.attachment_list.count() == 0
        assert not window.files_share_once.isChecked()
    finally:
        window.close()


def test_two_documents_can_be_compared(tmp_path, monkeypatch):
    from document_fixtures import make_pdf

    app, window = make_window(tmp_path)
    try:
        first = make_pdf(tmp_path / "first.pdf", lines=('alpha', 'beta'))
        second = make_pdf(tmp_path / "second.pdf", lines=('alpha', 'gamma'))
        chosen = [str(first), str(second)]
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *_args, **_kwargs: (chosen.pop(0), ""))
        window.open_section("Files & Folders")
        window.read_document_file()
        window.compare_document_file()
        preview = window.document_preview.toPlainText()
        assert "differ" in preview
        assert "beta" in preview
        assert "gamma" in preview
        assert "Nothing was sent anywhere" in window.document_status.text()
    finally:
        window.close()


def test_a_document_that_cannot_be_read_says_why(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"%PDF-1.7\nnot really a pdf")
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *_args, **_kwargs: (str(broken), ""))
        window.open_section("Files & Folders")
        window.read_document_file()
        assert window.document_preview.toPlainText() == ""
        assert window.document_status.text()
    finally:
        window.close()
