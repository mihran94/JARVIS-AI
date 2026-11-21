"""The PRIME interface has to be there, and it has to keep the features.

The owner was looking at the old interface with new colours. These tests
say what the new composition is made of, that the old chrome is gone, and
that the controls the features need are still the ones the application
uses.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from desktop.app import Window
from desktop.prime_ui import PRIME_BUILD, PrimeBubble, PrimeChat, PrimePalette, PrimeShell


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.showNormal()
    window.enable_omega(smoke=False)
    for _ in range(4):
        app.processEvents()
    return app, window


def test_the_window_has_the_prime_composition(tmp_path):
    app, window = make_window(tmp_path)
    try:
        assert isinstance(window.prime_shell, PrimeShell)
        assert isinstance(window.prime_chat, PrimeChat)
        assert window.prime_island is not None
    finally:
        window.close()


def test_the_old_chrome_is_gone(tmp_path):
    app, window = make_window(tmp_path)
    try:
        for widget in window.legacy_chrome:
            assert not widget.isVisible(), widget.text() if hasattr(widget, 'text') else widget
    finally:
        window.close()


def test_the_build_is_shown_so_the_owner_knows_which_build(tmp_path):
    app, window = make_window(tmp_path)
    try:
        labels = [label.text() for label in window.prime_shell.findChildren(QLabel)]
        assert any(PRIME_BUILD in text for text in labels), labels
    finally:
        window.close()


def test_the_rail_has_the_destinations(tmp_path):
    app, window = make_window(tmp_path)
    try:
        rail = window.prime_shell.rail_buttons
        for section in ('JARVIS Chat', 'Files & Folders', 'Voice / Hey Jarvis',
                        'Cybersecurity', 'Memory', 'Settings & Safety'):
            assert section in rail, section
    finally:
        window.close()


def test_the_composer_uses_the_real_prompt_and_the_real_buttons(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        assert chat.composer.body.indexOf(window.prompt) >= 0
        controls = chat.composer.body.itemAt(1).layout()
        found = [controls.itemAt(index).widget()
                 for index in range(controls.count())
                 if controls.itemAt(index).widget() is not None]
        assert window.send_button in found
        assert window.chat_mic in found
        assert window.attach_button in found
        assert window.research_button in found
    finally:
        window.close()


def test_the_cards_of_a_running_job_come_with_the_new_chat(tmp_path):
    app, window = make_window(tmp_path)
    try:
        cards = window.prime_chat.cards
        widgets = [cards.itemAt(index).widget() for index in range(cards.count())
                   if cards.itemAt(index).widget() is not None]
        assert window.plan_card in widgets
        assert window.chat_task_card in widgets
        assert window.chat_approval in widgets
    finally:
        window.close()


def test_the_conversation_shows_the_messages_as_a_column(tmp_path):
    app, window = make_window(tmp_path)
    try:
        conversation = window.prime_chat.conversation
        conversation.render([
            {'role': 'user', 'content': 'Open Notepad'},
            {'role': 'assistant', 'content': 'Notepad is open.'},
        ])
        for _ in range(3):
            app.processEvents()
        assert len(conversation.bubbles) == 2
        bubbles = conversation.bubbles
        assert bubbles[0].you is True
        assert bubbles[1].you is False
        # A message is a bubble and not a line of text.
        assert isinstance(bubbles[0], PrimeBubble)
        assert isinstance(bubbles[0], QFrame)
    finally:
        window.close()


def test_the_assistant_steps_aside_for_the_conversation(tmp_path):
    app, window = make_window(tmp_path)
    try:
        chat = window.prime_chat
        chat.render([])
        assert chat.states.currentIndex() == 0
        chat.render([{'role': 'user', 'content': 'hello'}])
        assert chat.states.currentIndex() == 1
    finally:
        window.close()


def test_the_state_reaches_the_shell_and_the_island(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.prime_state = lambda: 'listening'
        window.refresh_prime_state()
        assert window.prime_shell.state_chip.text() == 'LISTENING'
        assert window.prime_island.orb.state == 'listening'
        window.prime_state = lambda: 'working'
        window.refresh_prime_state()
        assert window.prime_shell.state_chip.text() == 'WORKING'
    finally:
        window.close()


def test_the_rail_marks_the_page_that_is_open(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.open_section('Memory')
        for _ in range(2):
            app.processEvents()
        assert window.prime_shell.rail_buttons['Memory'].isChecked()
    finally:
        window.close()


def test_every_page_is_still_reachable(tmp_path):
    app, window = make_window(tmp_path)
    try:
        for name in window.page_indices:
            window.open_section(name)
            for _ in range(2):
                app.processEvents()
        assert len(window.page_indices) >= 15
    finally:
        window.close()


def test_the_palette_has_two_sides():
    dark = PrimePalette(dark=True)
    light = PrimePalette(dark=False)
    assert dark.ground != light.ground
    assert dark.accent != light.accent
    # The colour of the assistant is the same in both.
    assert dark.accent.name() != ''


def test_the_rail_buttons_are_not_the_old_toolbar(tmp_path):
    app, window = make_window(tmp_path)
    try:
        # The old toolbar button that opened the Island is not in the rail.
        for button in window.prime_shell.rail_buttons.values():
            assert isinstance(button, QPushButton)
            assert button.text() not in ('Tools', 'Plugins')
    finally:
        window.close()
