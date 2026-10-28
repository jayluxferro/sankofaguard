# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-10-21

### Added
- `docs/DESIGN.md`: threat model, step order rationale, guarantees and non-goals.
- CI workflow running the test suite on Python 3.10–3.12.
- `py.typed` marker; package data declared in `pyproject.toml`.

### Changed
- Service dependencies (FastAPI, uvicorn, httpx, pydantic) moved to the
  `[service]` extra. The core normalizer now installs with **zero** dependencies,
  matching what the README always claimed.
- Coverage of stripped characters widened to match the documented pipeline:
  all three Private Use Area planes (previously the BMP range only), full Tags
  block, NBSP → space, and soft-hyphen removal.

### Fixed
- Tests no longer import from an internal attack module; poisoned inputs are
  constructed inline from Unicode escapes, so the released artifact is self-contained.

## [0.1.0] — 2026-09-18

### Added
- Initial release: `SankofaGuard.normalize()` (strip covert characters, reverse
  homoglyphs, NFC, Hausa Ajami → Latin, code-switch segmentation), `GuardedAdapter`
  wrapper, FastAPI service with `POST /normalize` and an OpenAI-compatible
  `POST /v1/chat/completions` proxy, and the test suite.
