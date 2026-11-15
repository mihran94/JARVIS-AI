"""The Memory page in the desktop."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.memory_page import MemoryPanel
from memory.memory_service import MemoryService


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def panel(app, tmp_path):
    return MemoryPanel(service=MemoryService(tmp_path / 'history.sqlite3'))


def test_the_page_starts_empty(panel):
    assert panel.results.count() == 0


def test_a_note_is_remembered(panel):
    panel.memory_title.setText('Greeting')
    panel.memory_body.setPlainText('Say good morning at four')
    panel.memory_tags.setText('habit, home')
    panel.remember()
    assert panel.results.count() == 1
    assert 'Remembered' in panel.memory_status.text()
    assert panel.memory_title.text() == ''


def test_a_note_without_a_title_is_refused(panel):
    panel.memory_body.setPlainText('Only a body')
    panel.remember()
    assert panel.results.count() == 0
    assert 'title' in panel.memory_status.text().lower()


def test_a_note_is_found_by_a_word(panel):
    panel.memory_title.setText('Meeting')
    panel.memory_body.setPlainText('Every Monday at ten')
    panel.remember()
    panel.query.setText('monday')
    panel.find()
    assert panel.results.count() == 1
    assert 'match' in panel.memory_status.text()


def test_a_search_that_finds_nothing_says_so(panel):
    panel.memory_title.setText('Meeting')
    panel.memory_body.setPlainText('Every Monday at ten')
    panel.remember()
    panel.query.setText('helicopter')
    panel.find()
    assert panel.results.count() == 0
    assert 'Nothing matches' in panel.memory_status.text()


def test_show_all_lists_everything(panel):
    for index in range(3):
        panel.memory_title.setText(f'Note {index}')
        panel.memory_body.setPlainText('some text')
        panel.remember()
    panel.show_all()
    assert panel.results.count() == 3


def test_a_note_can_be_forgotten(panel):
    panel.memory_title.setText('Greeting')
    panel.memory_body.setPlainText('Say good morning at four')
    panel.remember()
    panel.results.setCurrentRow(0)
    panel.forget()
    assert panel.results.count() == 0
    assert 'Forgotten' in panel.memory_status.text()


def test_forgetting_without_a_choice_says_so(panel):
    panel.forget()
    assert 'Choose a note' in panel.memory_status.text()


def test_a_note_can_be_opened_for_changing(panel):
    panel.memory_title.setText('Greeting')
    panel.memory_body.setPlainText('Say good morning at four')
    panel.memory_tags.setText('habit')
    panel.remember()
    panel.show_all()
    panel.results.itemDoubleClicked.emit(panel.results.item(0))
    assert panel.memory_title.text() == 'Greeting'
    assert panel.memory_body.toPlainText() == 'Say good morning at four'
    assert panel.memory_tags.text() == 'habit'


def test_the_tags_are_shown_in_the_tooltip(panel):
    panel.memory_title.setText('Greeting')
    panel.memory_body.setPlainText('Say good morning')
    panel.memory_tags.setText('habit')
    panel.remember()
    panel.show_all()
    assert 'habit' in panel.results.item(0).toolTip()
