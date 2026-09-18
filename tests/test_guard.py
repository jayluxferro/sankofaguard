"""SankofaGuard: covert-channel strip, homoglyph reverse, Ajami→Latin, codeswitch segment.

Poisoned test inputs are built inline from Unicode escapes — this repo contains
no attack tooling, only the defensive normalizer.
"""

from sankofaguard import GuardedAdapter, SankofaGuard

# a few covert-channel characters, spelled by codepoint
ZWSP, ZWNJ, ZWJ, ZWNBSP = "​", "‌", "‍", "﻿"
TAG_A = "󠀡"  # U+E0061 'a' in the invisible Tags block
PUA_BMP = ""  # U+E900 (BMP private use)
PUA_SUPP = "\U000F1234"  # supplementary private use plane 15
NBSP = " "
SOFT_HYPHEN = "­"


def test_strips_covert_channels():
    g = SankofaGuard()
    text = "hello" + ZWJ + ZWSP + TAG_A + ZWNBSP + ZWNJ
    norm = g.normalize(text, lang="yor")
    assert "strip_covert_chars" in norm.ops
    assert norm.canonical_text == "hello"


def test_strips_all_pua_planes():
    g = SankofaGuard()
    norm = g.normalize("a" + PUA_BMP + "b" + PUA_SUPP, lang="eng")
    assert "strip_covert_chars" in norm.ops
    assert norm.canonical_text == "ab"


def test_nbsp_becomes_space_and_soft_hyphen_removed():
    g = SankofaGuard()
    norm = g.normalize("a" + NBSP + "b" + SOFT_HYPHEN + "c", lang="eng")
    assert norm.canonical_text == "a bc"  # NBSP->space; soft hyphen removed (bc join)


def test_reverses_homoglyphs():
    g = SankofaGuard()
    # 'Аttack' with a Cyrillic А — visually identical to Latin 'Attack'
    norm = g.normalize("Аttack", lang="eng")
    assert "reverse_homoglyph" in norm.ops
    assert norm.canonical_text == "Attack"


def test_ajami_to_latin_for_hausa():
    g = SankofaGuard()
    ajami = "ب ا ب"  # ب=ب(b) ا=ا(a) → 'b a b'
    norm = g.normalize(ajami, lang="hau")
    assert "ajami_to_latin" in norm.ops
    assert set(norm.canonical_text) <= set("ab ")


def test_codeswitch_segmentation():
    g = SankofaGuard()
    norm = g.normalize("ọwọ́ money ilé", lang="yor")
    assert "segment_codeswitch" in norm.ops
    langs = [s.lang for s in norm.spans]
    assert "eng" in langs and "yor" in langs


def test_guarded_adapter_normalizes_before_generate():
    class Inner:
        name = "mock"

        def __init__(self):
            self.seen = None

        def generate(self, prompt, *, lang, system=None, max_tokens=512, temperature=0.0):
            self.seen = prompt
            return "ok"

    inner = Inner()
    guarded = GuardedAdapter(inner, SankofaGuard())
    assert guarded.name.endswith("+guard")
    poisoned = "hello" + TAG_A + PUA_BMP
    guarded.generate(poisoned, lang="yor")
    assert inner.seen == "hello"  # model sees cleaned text, not the covert payload


def test_no_ops_on_clean_text():
    g = SankofaGuard()
    clean = "ọwọ́ mi wà n'ílé"
    norm = g.normalize(clean, lang="yor")
    assert norm.canonical_text == clean
    # no *mutating* ops fire on clean text (segmentation is read-only labeling)
    assert all(op == "segment_codeswitch" for op in norm.ops)


def test_restorer_hook():
    g = SankofaGuard(restorer=lambda text, lang: text.replace("o", "ó"))
    norm = g.normalize("owo", lang="yor")
    assert "rediacritize" in norm.ops
    assert norm.canonical_text == "ówó"  # placeholder restorer applied verbatim
