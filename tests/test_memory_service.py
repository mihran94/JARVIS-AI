"""The memory the owner keeps between sessions."""
import os

import pytest

from memory.memory_service import (
    MemoryError, MemoryService, search_terms, tokenize,
)


@pytest.fixture()
def service(tmp_path):
    return MemoryService(tmp_path / 'history.sqlite3')


def test_a_memory_needs_a_title_and_some_text(service):
    with pytest.raises(MemoryError):
        service.remember('', 'the body')
    with pytest.raises(MemoryError):
        service.remember('the title', '   ')


def test_a_memory_is_kept(service):
    memory = service.remember('Greeting', 'Say good morning at four', ['habit'])
    assert memory.id
    assert memory.tags == ('habit',)
    assert [item.title for item in service.all()] == ['Greeting']


def test_a_memory_is_found_by_its_words(service):
    service.remember('Greeting', 'Say good morning at four in the morning')
    service.remember('Meeting', 'Every Monday at ten, review the budget')
    found = service.search('morning')
    assert [item.title for item in found] == ['Greeting']


def test_a_memory_is_found_by_its_title(service):
    service.remember('Budget review', 'Every Monday at ten')
    assert [item.title for item in service.search('budget')] == ['Budget review']


def test_a_memory_is_found_by_its_tag(service):
    service.remember('Greeting', 'Say good morning', ['habit', 'home'])
    assert [item.title for item in service.search('habit')] == ['Greeting']


def test_a_search_that_finds_nothing_returns_nothing(service):
    service.remember('Greeting', 'Say good morning at four')
    assert service.search('quantum chromodynamics') == []


def test_the_search_sorts_the_best_match_first(service):
    service.remember('A', 'budget budget budget')
    service.remember('B', 'budget once')
    assert [item.title for item in service.search('budget')] == ['A', 'B']


def test_the_search_works_in_tamil(service):
    service.remember('வணக்கம்', 'நான்கு காலை நேரம் வணக்கம் சொல்லவும்')
    assert [item.title for item in service.search('வணக்கம்')] == ['வணக்கம்']


def test_the_search_works_in_french(service):
    service.remember('Rendez-vous', 'Chaque lundi à dix heures, revoir le budget')
    assert [item.title for item in service.search('budget')] == ['Rendez-vous']


def test_the_words_that_mean_nothing_are_ignored():
    assert search_terms('the and for') == []
    assert search_terms('what is the plan') == ['plan']
    assert tokenize('The quick brown fox') == ['quick', 'brown', 'fox']


def test_a_memory_can_be_changed(service):
    memory = service.remember('Old', 'the old text', ['a'])
    changed = service.update(memory.id, title='New', body='the new text', tags=['b'])
    assert changed.title == 'New'
    assert changed.body == 'the new text'
    assert changed.tags == ('b',)
    assert service.get(memory.id).title == 'New'


def test_a_memory_that_is_not_there_cannot_be_changed(service):
    with pytest.raises(MemoryError):
        service.update('nothing', title='New')


def test_a_memory_can_be_forgotten(service):
    memory = service.remember('Old', 'the old text')
    assert service.forget(memory.id) is True
    assert service.get(memory.id) is None
    assert service.forget(memory.id) is False


def test_the_tags_are_counted(service):
    service.remember('A', 'text', ['work', 'home'])
    service.remember('B', 'text', ['work'])
    assert service.tags() == [('home', 1), ('work', 2)]


def test_the_matching_memories_become_prompt_context(service):
    service.remember('Greeting', 'Say good morning at four')
    service.remember('Meeting', 'Every Monday at ten')
    context = service.as_context('morning')
    assert 'Greeting' in context
    assert 'Meeting' not in context


def test_the_context_is_empty_when_nothing_matches(service):
    service.remember('Greeting', 'Say good morning at four')
    assert service.as_context('quantum chromodynamics') == ''


def test_the_context_stays_within_its_budget(service):
    for index in range(20):
        service.remember(f'Note {index}', 'word ' * 200)
    context = service.as_context('word', limit=10, max_characters=500)
    assert len(context) <= 500


def test_the_memories_survive_a_restart(tmp_path):
    path = tmp_path / 'history.sqlite3'
    first = MemoryService(path)
    first.remember('Kept', 'this one is kept')
    second = MemoryService(path)
    assert [item.title for item in second.all()] == ['Kept']
    assert [item.title for item in second.search('kept')] == ['Kept']
