"""Text helpers used by the voice layer.

This is a faithful port of the Android implementation in
`core/common/src/main/kotlin/com/jarvisblue/core/common/TextTools.kt`
(jarvis-blue-android), so a transcript is normalised and scored the same way
on both platforms.
"""
import unicodedata

#: The ranges of combining diacritical marks that are stripped. The list
#: matches the Android implementation, which uses the Unicode
#: Combining_Diacritical_Marks property. Indic viramas such as the Tamil
#: sign are deliberately not in it, so Tamil text survives normalisation.
_COMBINING_RANGES = (
    (0x0300, 0x036F), (0x0483, 0x0489), (0x0591, 0x05BD), (0x05BF, 0x05BF),
    (0x05C1, 0x05C2), (0x05C4, 0x05C5), (0x05C7, 0x05C7), (0x0610, 0x061A),
    (0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06DC), (0x06DF, 0x06E4),
    (0x06E7, 0x06E8), (0x06EA, 0x06ED), (0x0711, 0x0711), (0x0730, 0x074A),
    (0x07A6, 0x07B0), (0x0816, 0x0819), (0x081B, 0x0823), (0x0825, 0x0827),
    (0x0829, 0x082D), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF), (0x20D0, 0x20F0),
    (0x2CEF, 0x2CF1), (0xFE20, 0xFE2F),
)


def _is_combining_diacritical(char: str) -> bool:
    point = ord(char)
    return any(low <= point <= high for low, high in _COMBINING_RANGES)


def normalize(text: str) -> str:
    """Lowercase, strip accents and collapse punctuation to single spaces."""
    if not isinstance(text, str):
        raise TypeError('Text must be a string')
    decomposed = unicodedata.normalize('NFD', text.lower().strip())
    without_marks = ''.join(char for char in decomposed
                             if not _is_combining_diacritical(char))
    cleaned = []
    for char in without_marks:
        if char.isalpha() or char.isdigit() or char.isspace():
            cleaned.append(char)
        else:
            cleaned.append(' ')
    return ' '.join(''.join(cleaned).split())


def tokens(text: str) -> list[str]:
    """The normalised words of a text."""
    return [word for word in normalize(text).split(' ') if word]


def similarity(first: str, second: str) -> float:
    """Jaccard similarity over token sets, 0.0 to 1.0."""
    set_a = set(tokens(first))
    set_b = set(tokens(second))
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


def levenshtein(first: str, second: str) -> int:
    """The edit distance between two strings."""
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)
    previous = list(range(len(second) + 1))
    for i, source in enumerate(first, start=1):
        current = [i]
        for j, target in enumerate(second, start=1):
            cost = 0 if source == target else 1
            current.append(min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def fuzzy_similarity(first: str, second: str) -> float:
    """Similarity tolerant of speech recognition noise.

    Blends token overlap with edit distance, exactly like the Android
    implementation, so a transcript of "jarviss" still matches "jarvis".
    """
    normalised_a = normalize(first)
    normalised_b = normalize(second)
    if not normalised_a and not normalised_b:
        return 1.0
    if not normalised_a or not normalised_b:
        return 0.0
    longest = max(len(normalised_a), len(normalised_b))
    edit_similarity = max(0.0, min(1.0, 1.0 - (levenshtein(normalised_a, normalised_b) / longest)))
    blended = similarity(first, second) * 0.55 + edit_similarity * 0.45
    return max(0.0, min(1.0, blended))
