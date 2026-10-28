# SankofaGuard

A Unicode **covert-channel normalization preprocessor** for LLM and MT
pipelines. Place it in front of a model (or a machine-translation step feeding
one) so that payloads hidden in invisible or confusable Unicode characters
never reach the model as-is.

This artifact accompanies the SANKOFA research project on African-language LLM
safety. It contains **defensive code only** — no attack tooling, no attack
payloads, no harmful content.

## What it does

Given input text and a language code, `SankofaGuard.normalize()` returns a
canonical text plus an audit trail of the operations applied:

1. **Strip covert-channel characters**
   - zero-width characters: ZWSP (U+200B), ZWNJ (U+200C), ZWJ (U+200D), ZWNBSP/BOM (U+FEFF)
   - the Unicode Tags block (U+E0000–U+E01EF), which includes the invisible ASCII-range tags
   - all Private Use Area planes (U+E000–U+F8FF, U+F0000–U+FFFFD, U+100000–U+10FFFD)
   - NBSP (U+00A0) → regular space; soft hyphen (U+00AD) → removed
2. **Reverse homoglyph confusables** — Cyrillic lookalikes mapped back to their Latin originals (e.g. Cyrillic `А` → Latin `A`)
3. **NFC normalization** (canonical composition)
4. **Script canonicalization** — Hausa Ajami (Arabic script) → Latin
5. **Code-switch segmentation** — labels per-span languages (matrix language vs. embedded English)

An optional `restorer` callable (a learned re-diacritizer) can be plugged in to
restore stripped diacritics for languages like Yoruba/Twi, where tone marks are
phonemically significant. v1 ships without one: prompt-based re-diacritization
was found unfaithful (models rewrite and over-mark rather than restore
character-for-character), so a trained character-level model is required.

## What it does NOT do (honest limitations)

- **No defense against instruction-level encodings.** base64/hex/ROT47/unicode-escape
  wrapped payloads with a decode instruction are *semantic* attacks; character
  normalization cannot see them. Detecting them needs learned detection or a
  decode-and-inspect stage — future work.
- **No attack-success-rate (ASR) effectiveness claim.** Channel removal is
  deterministic and unit-tested: after normalization, the stripped characters
  are provably absent from the text. A controlled before/after ASR evaluation
  (same seeds, same n) is future work; an initial uncontrolled comparison was
  confounded and showed no measurable benefit, which we report rather than hide.
- Zero-width stripping is lossy by design: a legitimate (rare) use of ZWJ, e.g.
  in emoji ZWJ sequences or some orthographies, is removed with the payload.

## Status

Version 0.1.1 — research artifact accompanying a paper under review. The API may
change before 1.0. The test suite runs on Python 3.10–3.12 via CI. This repository
contains defensive code only: no encoding/attack tooling and no attack payloads.

## Install

Python ≥ 3.10. Not on PyPI yet — install from a checkout:

```bash
pip install -e .                # core normalizer: zero dependencies (stdlib only)
pip install -e ".[service]"     # + FastAPI/uvicorn/httpx for the HTTP proxy
pip install -e ".[dev]"         # + pytest
```

The core (`sankofaguard/guard.py`) imports nothing outside the standard library,
so it can be vendored into a pipeline without adding dependencies.

## Use as a library

```python
from sankofaguard import SankofaGuard

guard = SankofaGuard()
poisoned = "hello" + "\u200b" + "\ue900"    # ZWSP + a private-use char hidden in the text
norm = guard.normalize(poisoned, lang="yor")
print(norm.canonical_text)  # "hello"  (zero-width + PUA stripped)
print(norm.ops)             # ["strip_covert_chars", ...]
```

Wrap any model adapter so it never sees un-normalized prompts:

```python
guarded = GuardedAdapter(my_model_adapter, SankofaGuard())
out = guarded.generate(prompt, lang="yor")
```

## Run as a service

```bash
python -m sankofaguard.service        # uvicorn on :8000
```

- `POST /normalize` — `{"text": "...", "lang": "yor"}` → canonical text + ops + spans
- `POST /v1/chat/completions` — OpenAI-compatible **drop-in proxy**: normalizes
  user turns, forwards to your backend (default OpenRouter; set
  `SANKOFA_BACKEND_URL`), returns the reply. Point an existing app at
  `http://localhost:8000/v1/chat/completions` for guarded behavior with no code
  change.

For MT pipelines, apply the guard **before** translation so covert characters
are stripped before reaching the target-language model.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q      # 9 tests, no network, no model needed
```

The test suite constructs poisoned inputs inline from Unicode escapes — the
repository deliberately contains no encoding/attack tooling.

## Scope and safety

This is a defensive normalizer, and the boundary is deliberate:

- It **removes** channels; it does not demonstrate or distribute attacks. No
  encoder, no payload corpus, no harmful text is included.
- The homoglyph table is present because it is needed in reverse (restoring Latin
  characters that were replaced by Cyrillic lookalikes).
- Zero-width and soft-hyphen handling is **lossy by design**; do not place this in
  front of general-purpose text processing where emoji ZWJ sequences or soft
  hyphens are meaningful.
- It does **not** decode instruction-level encodings (base64/hex/ROT47/unicode-escape).
  Those payloads are visible ASCII and pass through unchanged.

See [docs/DESIGN.md](docs/DESIGN.md) for the threat model, the order-of-operations
rationale, and exactly what is and is not guaranteed.

## Repository layout

```
sankofaguard/guard.py      core normalizer (stdlib only)
sankofaguard/service.py    FastAPI service: /normalize + OpenAI-compatible proxy
tests/test_guard.py        unit tests, inline Unicode fixtures
docs/DESIGN.md             threat model, guarantees, non-goals
CHANGELOG.md               release history
```

## Citing

If you use this artifact, please cite the accompanying paper:

```bibtex
@misc{agyemang2026sankofaguard,
  title  = {Covert Unicode Channels Bypass LLM Safety Alignment: A Model- and
            Channel-Dependent Attack Surface with a Language-Independence Control},
  author = {Agyemang, Justice Owusu and Acheampong, Enoch and Kasore, Vida and
            Kponyo, Betty Agyei and Kponyo, Jerry John and Owusu Ansah, Elizabeth and
            Ahene, Emmanuel and Mensah Gyening, Rose-Mary Owusuaa and Frowne, Christian Idan},
  year   = {2026},
  note   = {Manuscript under review}
}
```

## Provenance & license

Techniques (which Unicode ranges constitute covert channels) are drawn from the
published tokenizer-security and imperceptible-perturbation literature; the
character tables here are the defensive constants only. MIT license — see
[LICENSE](LICENSE).
