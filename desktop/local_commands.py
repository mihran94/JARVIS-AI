"""The questions JARVIS answers itself, in the languages the owner speaks.

WHAT THIS IS FOR
    Some questions do not need a model: what JARVIS can do, what time it
    is, what the machine is doing. They are answered here, on this
    computer, with no provider call and no cost. The answer comes from
    the same place the assistant gets its own context, so it cannot drift
    away from what the application really does.

WHY A MATCHER AND NOT A LIST
    The owner speaks Tamil, Tanglish, English and French, and mixes them
    in one sentence. "Jarvis, enna help pannuva?" has to reach the same
    answer as "what can you do", and "help pannu" has to reach it too.
    So a phrase matches when every word of it is in the sentence, even
    when the sentence words it a little longer, the way a spoken verb
    ending is longer than the written one.

WHAT IT WILL NOT DO
    * It never runs anything and it never asks a provider. A question it
      does not recognise is not answered here; it goes on to the model.
    * It never answers a real request. "help me fix my project" is a
      request, not a question about what JARVIS can do, and it is not
      swallowed here.
"""
from __future__ import annotations

import re

from core.conversation import addressed_request

#: Words that carry no meaning for the match.
FILLER = frozenset({
    'is', 'it', 'the', 'a', 'an', 'please', 'now', 'currently', 'right',
    'tell', 'me', 'my', 'i', 'can', 'u', 'pls', 'pls.',
})

#: The local intents, and the ways the owner asks for them.
INTENTS = {
    'capabilities': (
        'what can you do',
        'what can jarvis do',
        'what are your abilities',
        'your skills',
        'your abilities',
        'jarvis capabilities',
        'help me with what you can do',
        'உன்னால் என்ன செய்ய முடியும்',
        'என்ன செய்ய முடியும்',
        'உன் திறன்கள் என்ன',
        'என்ன என்ன என்ன செய்ய முடியும்',
        'enna help pannuva',
        'enna help pannu',
        'enna seiya mudiyum',
        'enna pannuva',
        'epdi help pannu',
        'unakku enna venum',
        'unakku enna pannu',
        'tes capacites',
        'que peux-tu faire',
        'que sais-tu faire',
        'aide moi',
    ),
    'time': (
        'what time is it',
        'what is the time',
        'current time',
        'the time',
        'time now',
        'இப்போ நேரம் என்ன',
        'நேரம் என்ன',
        'நேரம்',
        'ippo neram enna',
        'neram enna',
        'quelle heure est-il',
        'quelle heure',
        "l'heure",
    ),
    'status': (
        'system status',
        'system stats',
        'status',
        'cpu usage',
        'ram usage',
        'கணினி நிலை',
        'கணினி நிலை என்ன',
        'system status enna',
        'etat du systeme',
        'état du système',
    ),
}

#: Words that are specific enough to mean an intent on their own. Every
#: other phrase needs at least two words, so a common word never decides
#: what the owner meant.
ALONE = frozenset({'capabilities', 'status'})

#: The slash commands that mean the same thing.
SLASH = {
    '/capabilities': 'capabilities',
    '/status': 'status',
    '/time': 'time',
}


def normalise(text) -> list:
    """The significant words of a sentence, in order."""
    if not isinstance(text, str):
        return []
    # The letters of every language are kept; only punctuation is dropped.
    words = re.findall(r'\w+', addressed_request(text).casefold(), flags=re.UNICODE)
    return [word for word in words if word not in FILLER]


def _word_matches(phrase_word: str, sentence_word: str) -> bool:
    """True when a sentence word stands for a phrase word.

    A spoken verb is longer than the written one: "pannuva" is "pannu".
    So one word may begin with the other, as long as it is long enough
    that the match means something.
    """
    if phrase_word == sentence_word:
        return True
    if len(phrase_word) < 4:
        return False
    return sentence_word.startswith(phrase_word) or phrase_word.startswith(sentence_word)


def _phrase_matches(phrase_words: list, sentence_words: list) -> bool:
    """True when the sentence carries the whole phrase and little else."""
    if len(phrase_words) < 2:
        # A single common word is never enough to decide an intent, unless
        # the word is one of the few that is specific enough on its own.
        if len(phrase_words) != 1 or phrase_words[0] not in ALONE:
            return False
    unmatched = list(sentence_words)
    for phrase_word in phrase_words:
        for index, sentence_word in enumerate(unmatched):
            if _word_matches(phrase_word, sentence_word):
                unmatched.pop(index)
                break
        else:
            return False
    # At most one word of the sentence may be left over, so a real
    # question is not swallowed by a phrase that happens to be inside it.
    return len(unmatched) <= 1


def match(text) -> str | None:
    """The intent of a sentence, or None when it is not a local question."""
    if not isinstance(text, str):
        return None
    stripped = addressed_request(text).strip()
    if stripped.casefold() in SLASH:
        return SLASH[stripped.casefold()]
    sentence = normalise(text)
    if not sentence:
        return None
    for intent, phrases in INTENTS.items():
        for phrase in phrases:
            if _phrase_matches(normalise(phrase), sentence):
                return intent
    return None
