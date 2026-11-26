"""Tamil written in Latin letters, and sentences that mix both scripts.

WHAT IS COVERED
    * The script of a piece of text is told: Tamil, Latin, mixed, empty.
    * A Tanglish sentence is recognised as Tanglish, and an ordinary
      English sentence is not.
    * Tanglish becomes the Tamil script, so the offline Tamil recogniser
      can hear it.
    * A sentence that mixes Tamil and English keeps both, and each part
      is handled by the model that understands it.
"""
import pytest

from voice.tanglish import (
    is_tanglish, language_for, script_of, split_mixed, to_tamil_script, words_of,
)


def test_the_script_of_a_text_is_told():
    assert script_of('வணக்கம்') == 'tamil'
    assert script_of('hello there') == 'latin'
    assert script_of('வணக்கம் hello') == 'mixed'
    assert script_of('   ') == 'empty'
    assert script_of('1234') == 'empty'


def test_a_tanglish_sentence_is_recognised():
    assert is_tanglish('vanakkam, computer la oru report ezhuthunga') is True
    assert is_tanglish('naan oru kaalam irukken') is True


def test_ordinary_english_is_not_tanglish():
    assert is_tanglish('open the calculator and calculate 17 times 23') is False
    assert is_tanglish('hello there') is False


def test_tamil_in_the_tamil_script_is_not_tanglish():
    assert is_tanglish('வணக்கம்') is False


def test_a_known_word_becomes_the_tamil_it_means():
    assert to_tamil_script('vanakkam') == 'வணக்கம்'
    assert to_tamil_script('naan') == 'நான்'
    assert to_tamil_script('pannunga') == 'பண்ணுங்க'


def test_a_tamil_word_is_left_alone():
    assert to_tamil_script('வணக்கம்') == 'வணக்கம்'


def test_english_is_left_alone():
    assert to_tamil_script('calculator') == 'calculator'
    assert to_tamil_script('report') == 'report'


def test_a_mixed_sentence_keeps_both_parts():
    converted = to_tamil_script('vanakkam, open the calculator')
    assert 'வணக்கம்' in converted
    assert 'calculator' in converted


def test_a_mixed_sentence_is_split_into_its_parts():
    parts = split_mixed('வணக்கம் calculator')
    assert [part for part, _ in parts] == ['tamil', 'latin']
    assert split_mixed('calculator only') == [('latin', 'calculator only')]


def test_the_language_that_should_hear_a_text():
    assert language_for('வணக்கம்') == 'ta'
    assert language_for('vanakkam, naan oru report ezhuthunga') == 'ta'
    assert language_for('open the calculator') == 'en'
    assert language_for('வணக்கம், open the calculator') == 'ta'


def test_the_words_of_a_text_are_lower_cased():
    assert words_of('Vanakkam Naan') == ['vanakkam', 'naan']
    assert words_of('') == []


def test_a_tanglish_sentence_becomes_readable_tamil():
    converted = to_tamil_script('naan computer la report ezhuthunga')
    # The Tamil words are now in the Tamil script, and the English words
    # the owner wrote in English are still English.
    assert converted.startswith('நான்')
    assert 'computer' in converted
    assert 'report' in converted
    assert 'எழுதுங' in converted
