"""Explicit Unicode naming conventions; these functions do no validation or I/O."""

import unicodedata

__all__ = ['words', 'snake_case', 'kebab_case', 'camel_case', 'pascal_case']


def words(value: str) -> tuple[str, ...]:
    """Return NFC-normalized lowercase words split on punctuation/case boundaries.

    Acronyms split before the following title word (HTTPServer -> http, server).
    Digits stay with neighboring text (version2ID -> version2, id). Combining
    marks stay attached to a preceding alphanumeric character. Uncased scripts
    remain intact. This is deterministic text conversion, not linguistic parsing,
    transliteration, identifier validation, or a guarantee of unique names.
    """
    if not isinstance(value, str):
        raise TypeError('value must be a string')
    runs: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for char in unicodedata.normalize('NFC', value):
        if unicodedata.category(char).startswith('M') and current:
            text, kind = current[-1]
            current[-1] = (text + char, kind)
        elif char.isalnum():
            kind = ('upper' if char.isupper() or char.istitle() else
                    'lower' if char.islower() else 'digit' if char.isnumeric() else 'letter')
            current.append((char, kind))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    result: list[str] = []
    for run in runs:
        start = 0
        for index in range(1, len(run)):
            previous, kind = run[index - 1][1], run[index][1]
            following = run[index + 1][1] if index + 1 < len(run) else None
            if (kind == 'upper' and previous in {'lower', 'digit', 'letter'}
                    or previous == kind == 'upper' and following == 'lower'):
                result.append(''.join(part for part, _ in run[start:index]))
                start = index
        result.append(''.join(part for part, _ in run[start:]))
    return tuple(unicodedata.normalize('NFC', word.lower()) for word in result)


def snake_case(value: str) -> str:
    """Join normalized words with underscores."""
    return '_'.join(words(value))


def kebab_case(value: str) -> str:
    """Join normalized words with hyphens; no filesystem or URL safety implied."""
    return '-'.join(words(value))


def _capitalized(word: str) -> str:
    return unicodedata.normalize('NFC', word[:1].upper() + word[1:])


def camel_case(value: str) -> str:
    """Join words with an initial lowercase word and capitalized later words."""
    parts = words(value)
    return parts[0] + ''.join(_capitalized(word) for word in parts[1:]) if parts else ''


def pascal_case(value: str) -> str:
    """Capitalize each word's first character and join without separators."""
    return ''.join(_capitalized(word) for word in words(value))
