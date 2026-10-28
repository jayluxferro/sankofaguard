# Design notes

Why SankofaGuard looks the way it does, what it guarantees, and what it deliberately
does not do. Companion to [README.md](README.md).

## Threat model

Input text reaches an LLM (directly, or after a machine-translation step) carrying
characters that are not visible to the user but are visible to the model: zero-width
characters, the Unicode Tags block, Private Use Area codepoints, homoglyphs,
non-breaking spaces, soft hyphens. The attacker's goal is either to smuggle
instructions past a filter written against plain text, or to make a tokenizer see a
different string than a human reviewer does.

SankofaGuard sits immediately before the model (or before translation) and
normalizes the input to a canonical, visible form.

## Pipeline and order of operations

`normalize(text, lang)` applies these steps in order, recording each one that fires
in `NormalizedInput.ops`:

| # | Step | Targets |
|---|------|---------|
| 1 | strip covert characters | ZWSP U+200B, ZWNJ U+200C, ZWJ U+200D, BOM/ZWNBSP U+FEFF, Tags block U+E0000–U+E01EF, Private Use Areas U+E000–U+F8FF / U+F0000–U+FFFFD / U+100000–U+10FFFD; NBSP U+00A0 → space; soft hyphen U+00AD → removed |
| 2 | reverse homoglyphs | Cyrillic lookalikes → Latin originals |
| 3 | NFC | canonical composition |
| 4 | script canonicalization | Hausa Ajami (Arabic script) → Latin |
| 5 | code-switch segmentation | labels each span by script/language for downstream handling |
| 6 | optional restorer | caller-supplied learned re-diacritizer |

**Why this order.** Strip first (a covert character can sit between the components of
a combining sequence and break step 3), then confusable reversal (operates on base
characters), then NFC (so composition runs on clean input), then script
canonicalization, then segmentation (which must see final orthography). The optional
restorer runs last because it needs the finalized string.

**Why strip all of PUA.** Private Use Areas carry no standard meaning by definition;
no plain-text orthography requires them. Subsetting to "the range we have seen in
attacks" would leave a trivially reachable gap.

## Guarantees

Deterministic and unit-tested:

- after `normalize`, none of the stripped codepoints remain in `canonical_text`;
- homoglyph reversal is idempotent;
- clean text is returned unchanged apart from read-only segmentation labels;
- the wrapper adapter (`GuardedAdapter`) normalizes before the inner model is called.

Not guaranteed:

- **attack-success-rate reduction.** Removing a channel is not the same as preventing
  a bypass; a controlled before/after evaluation is future work (see the paper).
- **semantic preservation of lossy edits.** Stripping ZWJ breaks emoji ZWJ sequences;
  stripping soft hyphens joins hyphenated words. This is intended for
  safety-critical instruction paths, not for general-purpose text processing.
- **instruction-level encodings.** base64/hex/ROT47/unicode-escape payloads are
  visible ASCII and pass through untouched. Detecting them needs semantic analysis,
  not normalization.

## Extension points

- `SankofaGuard(restorer=fn)` — plug in a trained re-diacritizer. Prompt-based
  re-diacritization was found unfaithful (models rewrite and over-mark rather than
  restore character-for-character), so a trained character-level model is required.
- The character tables in `guard.py` are module-level constants; extending the
  covered ranges is a data change, not a control-flow change.

## Provenance

The set of Unicode ranges that constitute covert channels is drawn from the published
tokenizer-security and imperceptible-perturbation literature. This repository ships the
defensive constants only: it contains no encoding/attack tooling and no attack payloads.
