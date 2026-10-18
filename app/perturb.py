"""Text normalisation (for the `normalized` state field) and the 4 perturbation generators.

The generators are deterministic so perturbation runs are comparable; the remaining
run-to-run variance is the model's own stochasticity.
"""

import unicodedata

# Common leet digits/symbols and lookalike letters, mapped back to ASCII.
_LEET_TO_ASCII = str.maketrans(
    {
        "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
        "@": "a", "$": "s", "€": "e", "£": "l", "!": "i",
        # Cyrillic lookalikes
        "а": "a", "е": "e", "о": "o", "с": "c", "р": "p", "х": "x", "у": "y", "і": "i",
        # Greek lookalikes
        "α": "a", "ο": "o", "ε": "e", "ι": "i", "ν": "v", "τ": "t",
    }
)

_ZERO_WIDTH = str.maketrans({c: None for c in "​‌‍⁠﻿"})


def normalize(text: str) -> str:
    """NFKC + strip zero-width chars + leet/homoglyph fold + lowercase."""
    out = unicodedata.normalize("NFKC", text)
    out = out.translate(_ZERO_WIDTH)
    out = out.lower().translate(_LEET_TO_ASCII)
    return " ".join(out.split())


_ASCII_TO_LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"})
_ASCII_TO_HOMOGLYPH = str.maketrans({"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "y": "у"})


def leetspeak(text: str) -> str:
    return text.lower().translate(_ASCII_TO_LEET)


def homoglyphs(text: str) -> str:
    return text.lower().translate(_ASCII_TO_HOMOGLYPH)


def spaced_letters(text: str) -> str:
    """Space out the letters of each word of 4+ chars: 'grosse' -> 'g r o s s e'."""
    return " ".join(" ".join(w) if len(w) >= 4 and w.isalpha() else w for w in text.split())


def trailing_emojis(text: str) -> str:
    return f"{text} 😂💀🔥"


PERTURBATIONS = {
    "leetspeak": leetspeak,
    "homoglyphs": homoglyphs,
    "spaced": spaced_letters,
    "emojis": trailing_emojis,
}
