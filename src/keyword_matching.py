from __future__ import annotations

import re
import unicodedata


def normalize_search_text(value: object) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or "").casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_accents.split())


def contains_complete_phrase(text: object, phrase: object) -> bool:
    normalized_text = normalize_search_text(text)
    normalized_phrase = normalize_search_text(phrase)
    if not normalized_phrase:
        return True
    words = [re.escape(word) for word in normalized_phrase.split() if word]
    if not words:
        return True
    phrase_pattern = r"\s+".join(words)
    pattern = rf"(?<!\w){phrase_pattern}(?!\w)"
    return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None


def contains_any_complete_phrase(text: object, phrases: list[str] | tuple[str, ...]) -> bool:
    return any(contains_complete_phrase(text, phrase) for phrase in phrases)
