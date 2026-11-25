"""Tamil written in Latin letters, and sentences that mix both scripts.

WHAT THIS IS
    Tamil speakers write Tamil in Latin letters all the time. They call
    it Tanglish, and it is not broken English: "vanakkam, computer la
    oru report ezhuthunga" is a whole, ordinary Tamil sentence.

    Windows has an offline Tamil recogniser, but it only understands the
    Tamil script. So a Tanglish sentence has to be turned into the Tamil
    script before the recogniser hears it, and the owner has to be able
    to ask for a reply in Latin letters when that is how they write.

    This module does three things and nothing else:

    * it says which script a piece of text is written in;
    * it turns Tanglish into the Tamil script, using a word list for the
      words that matter and a phonetic rule for the rest;
    * it splits a sentence that mixes Tamil and English into its parts,
      so each part can be handled by the model that understands it.

WHAT THIS IS NOT
    * It is not a spell checker. The phonetic rule is approximate, and
      the module says so wherever it is used.
    * It never changes the meaning of a Tamil sentence that is already in
      the Tamil script.
"""
from __future__ import annotations

import re

#: The Tamil script, the combining signs and the digits Tamil uses.
TAMIL_PATTERN = re.compile(
    '[\u0B80-\u0BFF\u0964-\u0965\u0BE6-\u0BEF\u0BF0-\u0BFA]+')

#: Latin letters.
LATIN_PATTERN = re.compile(r'[A-Za-z]+')

#: A Latin word inside a token, with the punctuation around it left out.
_LATIN_WORD = re.compile(r'[A-Za-z]+')

#: The independent vowels, written as they are typed in Latin letters.
INDEPENDENT_VOWELS = {
    'a': 'அ', 'aa': 'ஆ', 'i': 'இ', 'ii': 'ஈ',
    'u': 'உ', 'uu': 'ஊ', 'e': 'எ', 'ee': 'ஏ',
    'ai': 'ஐ', 'o': 'ஒ', 'oo': 'ஓ', 'au': 'ஔ',
}

#: The vowel signs, which are written after the consonant.
DEPENDENT_VOWELS = {
    'a': '', 'aa': 'ா', 'i': 'ி', 'ii': 'ீ',
    'u': 'ு', 'uu': 'ூ', 'e': 'ெ', 'ee': 'ே',
    'ai': 'ை', 'o': 'ொ', 'oo': 'ோ', 'au': 'ௌ',
}

#: The consonants, written as they are typed in Latin letters.
CONSONANTS = {
    'k': 'க', 'g': 'க', 'f': 'ஃ', 'c': 'ச', 'j': 'ஜ',
    's': 'ஸ', 'h': 'ஹ', 't': 'ட', 'd': 'ட', 'n': 'ன',
    'p': 'ப', 'b': 'ப', 'm': 'ம', 'y': 'ய', 'r': 'ர',
    'l': 'ல', 'v': 'வ', 'z': 'ழ', 'w': 'ற',
}

#: Two-letter clusters, which are one letter in Tamil.
CLUSTERS = {
    'ng': 'ங', 'nj': 'ஞ', 'ch': 'ச', 'sh': 'ஷ', 'th': 'த',
    'dh': 'த', 'kh': 'க', 'gh': 'க', 'ph': 'ப', 'zh': 'ழ',
    'ny': 'ண',
}

#: The words JARVIS hears most, with the Tamil they really mean.
#:
#: The phonetic rule alone gets "vanakkam" almost right and gets "nala"
#: wrong. These are the words that are said often enough, or wrong
#: enough, to be worth writing down.
WORDS = {
    'a': 'அ',
    'appa': 'அப்பா', 'amma': 'அம்மா', 'akka': 'அக்கா', 'appu': 'அப்பு',
    'akkа': 'அக்கா',
    'computer': 'கணினி', 'koonini': 'கணினி', 'kumpiyutha': 'கம்பியூட்டா',
    'report': 'அறிக்கை', 'arikkai': 'அறிக்கை',
    'kurrupu': 'குறிப்பு', 'kurruppu': 'குறிப்பு',
    'vaanga': 'வாங்க', 'vaangunga': 'வாங்குங்க', 'vaangungal': 'வாங்குங்க',
    'va': 'வா', 'po': 'போ', 'na': 'ந', 'ka': 'க', 'pa': 'ப', 'la': 'ல',
    'venna': 'வேண்டும்', 'vennum': 'வேண்டும்', 'vennunga': 'வேண்டுங்க',
    'pannunga': 'பண்ணுங்க', 'pannungal': 'பண்ணுங்க', 'panlunga': 'பண்ணுங்க',
    'seiyunga': 'செய்யுங்க', 'seiyungal': 'செய்யுங்க', 'seivunga': 'செய்யுங்க',
    'seiyvanum': 'செய்யவும்', 'seivadhu': 'செய்வது',
    'thodunga': 'தொடங்கு', 'thodungunga': 'தொடங்குங்க', 'thodungal': 'தொடங்குங்க',
    'vanakkam': 'வணக்கம்', 'vanakkama': 'வணக்கமா',
    'nanban': 'நண்பன்', 'nanba': 'நண்பா', 'nanbargal': 'நண்பர்கள்',
    'naan': 'நான்', 'naanum': 'நானும்', 'naanume': 'நானும்',
    'nal': 'நல்', 'nala': 'நல்ல', 'naal': 'நாள்', 'naalai': 'நாளை',
    'nee': 'நீ', 'neenga': 'நீங்க', 'neer': 'நீர்', 'neeyum': 'நீயும்',
    'appadi': 'அப்படி', 'epdi': 'எப்படி', 'eppadi': 'எப்படி',
    'enga': 'எங்கே', 'enkala': 'எங்கே', 'eppo': 'எப்போ', 'eppozhuthu': 'எப்போழுது',
    'indru': 'இன்று', 'indro': 'இன்று', 'nungali': 'நுங்காலி',
    'ungal': 'உங்கள்', 'ungalukku': 'உங்களுக்கு', 'unga': 'உங்கா',
    'kaal': 'கால்', 'kaalam': 'காலம்', 'vaaru': 'வாரு', 'vaaram': 'வாரம்',
    'ippothe': 'இப்போது', 'ipothe': 'இப்போது', 'ippadi': 'இப்படி',
    'romba': 'ரொம்ப', 'romba naala': 'ரொம்ப நல்ல',
    'sappadu': 'சப்பாடு', 'sapadu': 'சப்பாடு', 'saapadu': 'சப்பாடு',
    'kannu': 'கண்ணு', 'kannukku': 'கண்ணுக்கு', 'kannukkul': 'கண்ணுக்குள்',
    'thooru': 'தூரு', 'thoongu': 'தூங்கு', 'thooram': 'தூரம்',
    'sollunga': 'சொல்லுங்க', 'sollungal': 'சொல்லுங்க', 'sollala': 'சொல்ல',
    'podhu': 'பொது', 'podhuvum': 'பொதுவும்', 'mattum': 'மட்டும்',
    'kondu': 'கொண்டு', 'kond': 'கொண்ட', 'konduro': 'கொண்டு',
    'sunniyavargal': 'சுண்ணியவர்கள்', 'thambi': 'தம்பி', 'thangachi': 'தங்காசி',
    'thuduppu': 'துடுப்பு', 'vaali': 'வாலி', 'kudi': 'குடி', 'kudigal': 'குடிகள்',
    'kaalai': 'காலை', 'ippadi seyal': 'இப்படி செயல்',
    'aagum': 'ஆகும்', 'aagum': 'ஆகும்', 'naagum': 'நாகும்',
    'konjam': 'சற்று', 'konjam': 'சற்று',
    'illai': 'இல்லை', 'irukku': 'இருக்கு', 'irundhu': 'இருந்து',
    'naan pesuren': 'நான் பேசுறேன்', 'sollunga': 'சொல்லுங்க',
}

#: The words that show a sentence is Tamil written in Latin letters.
TANGLISH_MARKERS = frozenset((
    'vanakkam', 'nanban', 'nanba', 'naan', 'nee', 'neenga', 'appa', 'amma',
    'epdi', 'eppadi', 'enga', 'eppo', 'indru', 'naalai', 'nungali', 'ungal',
    'vaanga', 'venna', 'vennum', 'pannunga', 'seiyunga', 'thodunga', 'kaal',
    'kaalam', 'vaaru', 'ippothe', 'romba', 'nala', 'sappadu', 'kannu',
    'thooru', 'thoongu', 'sollunga', 'kondu', 'kond', 'thooram', 'vaaram',
    'pattu', 'ippadi', 'naanum', 'ungalukku', 'vaali', 'mattum', 'podhu',
    'neer', 'kudi', 'thambi', 'akka', 'appu', 'po', 'va', 'na', 'ka', 'pa',
    'illai', 'irukku', 'aagum', 'konjam', 'appadi', 'vaal', 'nala',
))


#: The endings a Tanglish word has. A word that ends with one of these
#: is Tamil written in Latin letters.
TANGLISH_ENDINGS = ('unga', 'ngal', 'kkam', 'kkum', 'ppu', 'nni', 'nna',
                    'thu', 'dhu', 'pan', 'ral', 'gal', 'vum', 'yya', 'lla')

#: Words that are written in Latin letters but are really English.
#:
#: They are left exactly as they are, even when the word list knows
#: them, because turning "report" into Tamil in the middle of an English
#: sentence changes what the sentence says. The owner wrote English
#: there, and English is what the model should read.
ENGLISH_WORDS = frozenset((
    'report', 'open', 'close', 'save', 'file', 'folder', 'email', 'message',
    'calendar', 'notepad', 'calculator', 'browser', 'settings', 'project',
    'computer', 'printer', 'network', 'internet', 'download', 'upload',
    'search', 'system', 'server', 'screen', 'window', 'text', 'image',
    'video', 'audio', 'please', 'ok', 'yes', 'no', 'stop', 'start', 'next',
    'delete', 'copy', 'paste', 'undo', 'redo', 'google', 'whatsapp',
    'excel', 'word', 'powerpoint', 'outlook', 'zoom', 'teams',
))


def is_tanglish_word(word: str) -> bool:
    """Whether one Latin word is Tamil written in Latin letters.

    A word the owner wrote in English is not, even when the word list
    has a Tamil word that looks like it.
    """
    lowered = str(word or '').casefold()
    if not lowered:
        return False
    if lowered in ENGLISH_WORDS:
        return False
    if lowered in WORDS:
        return True
    return lowered.endswith(TANGLISH_ENDINGS)


def script_of(text: str) -> str:
    """Which script a piece of text is written in.

    One of ``'tamil'``, ``'latin'``, ``'mixed'`` or ``'empty'``. A
    sentence with Tamil and English in it is ``'mixed'``, which is the
    ordinary case for a Tamil speaker working on an English computer.
    """
    if not isinstance(text, str) or not text.strip():
        return 'empty'
    tamil = bool(TAMIL_PATTERN.search(text))
    latin = bool(LATIN_PATTERN.search(text))
    if tamil and latin:
        return 'mixed'
    if tamil:
        return 'tamil'
    if latin:
        return 'latin'
    return 'empty'


def words_of(text: str) -> list:
    """The Latin words of a text, lowercased."""
    if not isinstance(text, str):
        return []
    return [word.lower() for word in re.findall(r"[A-Za-z']+", text)]


def is_tanglish(text: str) -> bool:
    """Whether a piece of text is Tamil written in Latin letters.

    A text that already carries the Tamil script is never Tanglish, and
    a text with no Latin words at all is never Tanglish. Between those
    two, the words of the text are looked for in the list of Tanglish
    words, and a text is Tanglish when enough of its words are.
    """
    if script_of(text) != 'latin':
        return False
    words = words_of(text)
    if not words:
        return False
    if any(word in TANGLISH_MARKERS for word in words):
        return True
    # A word that ends the way Tamil words end is a second hint.
    return any(word.endswith(('unga', 'ngal', 'llunga', 'pannunga')) for word in words)


def _transliterate_word(word: str) -> str:
    """One Latin word, turned into the Tamil script.

    The rule is phonetic, so it is an approximation. The word list is
    consulted first, and the words in it are right. A word that is
    really English is left exactly as it was.
    """
    lowered = word.lower()
    if lowered in ENGLISH_WORDS:
        return word
    known = WORDS.get(lowered)
    if known:
        return known
    if not word:
        return ''
    out = []
    index = 0
    length = len(word)
    # True at the start of a syllable, where a vowel stands on its own.
    start_of_syllable = True
    while index < length:
        if start_of_syllable:
            pair = word[index:index + 2].lower()
            if len(pair) == 2 and pair in INDEPENDENT_VOWELS:
                out.append(INDEPENDENT_VOWELS[pair])
                index += 2
                continue
            letter = word[index].lower()
            if letter in INDEPENDENT_VOWELS:
                out.append(INDEPENDENT_VOWELS[letter])
                index += 1
                continue
            if len(pair) == 2 and pair in CLUSTERS:
                out.append(CLUSTERS[pair])
                index += 2
                start_of_syllable = False
                continue
            consonant = CONSONANTS.get(letter)
            if consonant is None:
                # Not a Tamil letter: leave it exactly as it was.
                out.append(word[index])
                index += 1
                continue
            out.append(consonant)
            index += 1
            start_of_syllable = False
            continue
        # A vowel after a consonant is written as a sign, not a letter.
        pair = word[index:index + 2].lower()
        if len(pair) == 2 and pair in DEPENDENT_VOWELS:
            out.append(DEPENDENT_VOWELS[pair])
            index += 2
            start_of_syllable = True
            continue
        letter = word[index].lower()
        if letter in DEPENDENT_VOWELS:
            out.append(DEPENDENT_VOWELS[letter])
            index += 1
            start_of_syllable = True
            continue
        # A consonant with no vowel after it keeps its own shape.
        out.append('்')
        start_of_syllable = True
    return ''.join(out)


def to_tamil_script(text: str) -> str:
    """Turn Tanglish into the Tamil script.

    A word that is already Tamil is left alone, and a word that is plain
    English is left alone too, so a sentence that mixes the two comes
    out with its Tamil in the Tamil script and its English as it was.
    """
    if not isinstance(text, str) or not text.strip():
        return ''
    pieces = []
    for token in re.findall(r"[\u0B80-\u0BFF\u0964-\u0965\u0BE6-\u0BEF]+|[^\s]+|\s+", text):
        if TAMIL_PATTERN.match(token):
            pieces.append(token)
            continue

        def convert(match):
            word = match.group(0)
            return _transliterate_word(word) if is_tanglish_word(word) else word

        # The word inside the token is converted and the punctuation
        # around it is left exactly as it was.
        pieces.append(_LATIN_WORD.sub(convert, token))
    return ''.join(pieces)


def split_mixed(text: str) -> list:
    """The parts of a sentence, each with the script it is written in.

    A part is a ``(script, text)`` pair, where the script is ``'tamil'``
    or ``'latin'``. A sentence that is only one script comes back as one
    part.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    parts = []
    for token in re.findall(r"[\u0B80-\u0BFF\u0964-\u0965\u0BE6-\u0BEF]+|[^\s]+|\s+", text):
        if not token.strip():
            continue
        script = script_of(token)
        if script == 'empty':
            continue
        if parts and parts[-1][0] == script:
            parts[-1] = (script, parts[-1][1] + ' ' + token)
        else:
            parts.append((script, token))
    return parts


def language_for(text: str) -> str:
    """Which speech model should hear this text.

    Tamil in either script is Tamil. English stays English, even when the
    sentence also has a few Tamil words, because the Windows recogniser
    follows the culture it was built with.
    """
    script = script_of(text)
    if script == 'tamil':
        return 'ta'
    if script == 'mixed':
        tamil_words = sum(1 for part, _ in split_mixed(text) if part == 'tamil')
        return 'ta' if tamil_words else 'en'
    if script == 'latin' and is_tanglish(text):
        return 'ta'
    return 'en'


__all__ = ['CLUSTERS', 'CONSONANTS', 'DEPENDENT_VOWELS', 'INDEPENDENT_VOWELS',
           'TAMIL_PATTERN', 'TANGLISH_MARKERS', 'WORDS', 'is_tanglish', 'language_for',
           'script_of', 'split_mixed', 'to_tamil_script', 'words_of']
