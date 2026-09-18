"""SankofaGuard — a Unicode covert-channel normalization preprocessor.

Placed in front of an LLM (or an MT pipeline feeding one) so the model sees
clean input. v1 is rule-based:

  1. strip covert-channel characters (zero-width, invisible Tags block,
     all Private Use Area planes; NBSP -> space; soft hyphen removed)
  2. reverse homoglyph confusables (Cyrillic -> Latin)
  3. NFC normalization
  4. script canonicalization (Ajami -> Latin for Hausa; ASCII Yoruba left
     as-is — restoring stripped diacritics needs the optional learned
     ``restorer``)
  5. code-switch segmentation -> per-span language labels

A learned re-diacritizer can be plugged in via ``restorer`` for text where
diacritic information was lost.

``GuardedAdapter`` wraps any object with a ``generate(prompt, *, lang, ...)``
method so evaluations can measure behavior before/after the guard.

What SankofaGuard does NOT do: it does not detect or decode instruction-level
encodings (base64, hex, ROT47, unicode-escape). Those require semantic
detection, not character normalization.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# --- Unicode tables (vendored; the defensive constants only) -----------------

# Latin -> Cyrillic confusables (visual lookalikes). Reversed for restoration.
HOMOGLYPH_MAP: dict[str, str] = {
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'I': 'І',
    'J': 'Ј', 'K': 'К', 'M': 'М', 'N': 'Н', 'O': 'О', 'P': 'Р',
    'S': 'Ѕ', 'T': 'Т', 'X': 'Х', 'Y': 'У', 'a': 'а', 'c': 'с',
    'e': 'е', 'i': 'і', 'j': 'ј', 'o': 'о', 'p': 'р', 's': 'ѕ',
    'x': 'х', 'y': 'у',
}
HOMOGLYPH_REV: dict[str, str] = {v: k for k, v in HOMOGLYPH_MAP.items()}

# Unicode "Tags" block (language tags incl. the invisible ASCII-range tags
# U+E0020..U+E007F). No legitimate plain-text characters live here.
_TAGS_BLOCK = range(0xE0000, 0xE01F0)

# Private Use Areas: BMP (U+E000–U+F8FF) and the two supplementary planes.
# By definition these carry no standard assignments — safe to strip.
_PUA_RANGES = (
    range(0xE000, 0xF900),
    range(0xF0000, 0x100000),
    range(0x100000, 0x110000),
)

# Zero-width characters: ZWSP, ZWNJ, ZWJ, BOM/ZWNBSP.
_ZW_CHARS = {"​", "‌", "‍", "﻿"}

_NBSP = " "
_SOFT_HYPHEN = "­"


def _is_covert(c: str) -> bool:
    return (
        c in _ZW_CHARS
        or ord(c) in _TAGS_BLOCK
        or any(ord(c) in r for r in _PUA_RANGES)
    )


# Reverse of Hausa Latin->Ajami transliteration (many-to-one; canonical Latin).
_AJAMI_TO_LATIN: dict[str, str] = {
    "ا": "a", "ب": "b", "چ": "c", "د": "d", "ى": "e", "ف": "f", "گ": "g",
    "ه": "h", "ی": "i", "ج": "j", "ک": "k", "ل": "l", "م": "m", "ن": "n",
    "و": "o", "ر": "r", "س": "s", "ت": "t", "ز": "z", "ع": "'",
    "ش": "sh", "ث": "ts",
}


@dataclass
class Span:
    lang: str
    text: str


@dataclass
class NormalizedInput:
    canonical_text: str
    spans: list[Span] = field(default_factory=list)
    ops: list[str] = field(default_factory=list)


class SankofaGuard:
    def __init__(self, restorer=None):
        self.restorer = restorer  # optional callable(text, lang) -> str (learned re-diacritizer)

    def normalize(self, text: str, lang: str) -> NormalizedInput:
        ops: list[str] = []
        t = text

        # 1. strip covert-channel characters
        stripped = "".join(
            (" " if c == _NBSP else "" if c == _SOFT_HYPHEN else c)
            if not _is_covert(c) else ""
            for c in t
        )
        if stripped != t:
            ops.append("strip_covert_chars")
        t = stripped

        # 2. reverse homoglyph confusables
        dehomo = "".join(HOMOGLYPH_REV.get(c, c) for c in t)
        if dehomo != t:
            ops.append("reverse_homoglyph")
        t = dehomo

        # 3. NFC normalization
        nfc = unicodedata.normalize("NFC", t)
        if nfc != t:
            ops.append("nfc")
        t = nfc

        # 4. script canonicalization (Hausa Ajami -> Latin)
        if lang == "hau":
            latin = "".join(_AJAMI_TO_LATIN.get(c, c) for c in t)
            if latin != t:
                ops.append("ajami_to_latin")
            t = latin

        # 5. code-switch segmentation
        spans = self._segment(t, lang)
        if len(spans) > 1:
            ops.append("segment_codeswitch")

        # optional learned re-diacritization
        if self.restorer is not None:
            restored = self.restorer(t, lang)
            if restored and restored != t:
                ops.append("rediacritize")
                t = restored

        return NormalizedInput(canonical_text=t, spans=spans, ops=ops)

    @staticmethod
    def _segment(text: str, lang: str) -> list[Span]:
        spans: list[Span] = []
        cur: str | None = None
        buf: list[str] = []
        for c in text:
            tag = "eng" if (c.isascii() and c.isalpha()) else lang
            if tag != cur:
                if buf:
                    spans.append(Span(cur, "".join(buf)))
                cur = tag
                buf = [c]
            else:
                buf.append(c)
        if buf:
            spans.append(Span(cur, "".join(buf)))
        return spans


class GuardedAdapter:
    """Wraps a model adapter: normalize(prompt) before generate()."""

    def __init__(self, inner, guard: SankofaGuard):
        self.inner = inner
        self.guard = guard
        self.name = getattr(inner, "name", "model") + "+guard"

    def generate(self, prompt, *, lang, system=None, max_tokens=512, temperature=0.0):
        norm = self.guard.normalize(prompt, lang)
        return self.inner.generate(
            norm.canonical_text, lang=lang, system=system, max_tokens=max_tokens, temperature=temperature
        )
