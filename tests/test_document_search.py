"""Searching inside the folders the owner has approved.

WHAT IS COVERED
    * The search finds the text and says which file and which line.
    * Files that are not text, that look like secrets, and that the
      project's own `.gitignore` keeps out are not searched.
    * The search is bounded, and it says when it did not look at
      everything.
    * Nothing is sent anywhere: the search happens on this computer.
    * A summary can be saved, and what is saved says when it was written.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.document_search import (
    MAX_FILES, search_folder, search_result_text, summary_export,
)


def make_folder(tmp_path):
    (tmp_path / 'notes.md').write_text('# Notes\n\nthe login is broken here\n',
                                       encoding='utf-8')
    (tmp_path / 'code.py').write_text('def login():\n    return "broken"\n',
                                       encoding='utf-8')
    (tmp_path / 'other.txt').write_text('nothing to see\n', encoding='utf-8')
    return tmp_path


def test_the_search_finds_the_text_and_says_where(tmp_path):
    result = search_folder(make_folder(tmp_path), 'login')
    assert result.match_count == 2
    assert 'notes.md' in result.files_with_matches
    assert 'code.py' in result.files_with_matches
    match = [m for m in result.matches if m.path == 'notes.md'][0]
    assert match.line == 3
    assert 'login is broken' in match.text


def test_the_search_does_not_look_at_the_whole_computer(tmp_path):
    """Only the folder that was chosen is searched."""
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'far.md').write_text('login is broken here too\n', encoding='utf-8')
    folder = tmp_path / 'here'
    folder.mkdir()
    (folder / 'close.md').write_text('login is broken here\n', encoding='utf-8')
    result = search_folder(folder, 'login')
    assert result.files_with_matches == ['close.md']


def test_a_file_that_is_not_text_is_skipped(tmp_path):
    (tmp_path / 'picture.png').write_bytes(b'\x89PNG\r\n\x1a\n\x00\x01')
    (tmp_path / 'note.txt').write_text('findable\n', encoding='utf-8')
    result = search_folder(tmp_path, 'findable')
    assert result.files_searched == 1
    assert result.files_skipped == 1


def test_a_file_that_looks_like_a_secret_is_not_searched(tmp_path):
    (tmp_path / 'secrets.json').write_text('{"password": "hunter2"}', encoding='utf-8')
    result = search_folder(tmp_path, 'password')
    assert result.match_count == 0
    assert result.files_skipped == 1


def test_a_file_the_project_keeps_out_is_not_searched(tmp_path):
    (tmp_path / '.gitignore').write_text('local/\n', encoding='utf-8')
    local = tmp_path / 'local'
    local.mkdir()
    (local / 'settings.json').write_text('{"token": "x"}', encoding='utf-8')
    result = search_folder(tmp_path, 'token')
    assert result.match_count == 0


def test_an_empty_query_searches_nothing(tmp_path):
    result = search_folder(make_folder(tmp_path), '   ')
    assert result.files_searched == 0
    assert result.match_count == 0


def test_the_search_is_bounded(tmp_path):
    for index in range(MAX_FILES + 20):
        (tmp_path / f'file{index}.txt').write_text('findable\n', encoding='utf-8')
    result = search_folder(tmp_path, 'findable')
    assert result.files_searched <= MAX_FILES
    assert result.truncated is True
    assert 'left out' in search_result_text(result)


def test_a_folder_that_is_not_there_is_handled(tmp_path):
    result = search_folder(tmp_path / 'missing', 'anything')
    assert result.files_searched == 0
    assert result.match_count == 0


def test_the_search_says_how_many_files_it_looked_at(tmp_path):
    result = search_folder(make_folder(tmp_path), 'login')
    text = search_result_text(result)
    assert '2 time(s)' in text
    assert 'file(s) searched' in text


# ── saving a summary ───────────────────────────────────────────────────────

def test_a_saved_summary_says_when_it_was_written():
    text = summary_export('The login check is broken.', title='Login')
    assert '# Login' in text
    assert 'The login check is broken.' in text
    assert 'Written by JARVIS on' in text


def test_a_saved_summary_adds_nothing_to_what_was_written():
    body = 'The login check is broken.'
    saved = summary_export(body)
    assert body in saved
    # Nothing is invented: every line of the body is still there, and the
    # only things added are the title and the date.
    added = [line for line in saved.splitlines()
             if line and line not in body and not line.startswith('#')
             and not line.startswith('Written by JARVIS')]
    assert added == []


# ── in the application ──────────────────────────────────────────────────────

def test_the_workspace_searches_the_folder_the_owner_chose(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QInputDialog

    from desktop.app import Window

    folder = make_folder(tmp_path / 'docs') if False else make_folder(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        monkeypatch.setattr(QFileDialog, 'getExistingDirectory',
                            lambda *_a, **_k: str(folder))
        monkeypatch.setattr(QInputDialog, 'getText',
                            lambda *_a, **_k: ('login', True))
        window.open_section('Files & Folders')
        window.search_chosen_folder()
        preview = window.document_preview.toPlainText()
        assert 'notes.md' in preview
        assert 'login' in preview
        assert 'Nothing was sent anywhere' in window.document_status.text()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
