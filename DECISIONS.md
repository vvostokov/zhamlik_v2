# Decision Log

Append-only. Each entry: iteration, what, why, alternatives rejected.

## 003 — 2026-06-28 — Pluggable validation rule registry

**What:** Refactored `validate_claim` in `pipeline.py` from a hardcoded if-chain to a registry. New API: `pipeline.register_rule(callable)`. Rule = `Claim -> str | None`. 4 new tests in `tests/test_pipeline.py`. All 34 tests pass. No external behavior change.

**Why:** Adding a real financial rule (max amount, blacklist, sanctions check, FX rate sanity, etc.) previously required editing `validate_claim` directly. Registry makes rules first-class extensions: add/remove without touching the pipeline control flow.

**Contract preserved:** Default behavior unchanged (same three default rules, same outputs for same inputs). Verified by all 20 existing pipeline tests passing unmodified.

**Rejected:** Decorator pattern (`@pipeline.rule`) — implicit; harder to debug. JSON rule config — over-engineering for MVP. Per-source rule scoping — added complexity without observed need.

## 002 — 2026-06-28 — Derived Ledger layer

**What:** `src/ledger.py` — derived aggregation over Recognition events. Per-subject × per-currency account balances, totals, counts. 10 tests in `tests/test_ledger.py`. No changes to `pipeline.py`.

**Why:** MVP was stateless. After N recognitions there was no way to ask "what's the current state?" without replaying all events. The ontology says Account/Ledger/Snapshot are *derived*, not primitives, so this layer must be pure aggregation over existing primitives.

**Contract preserved:** `pipeline.py` reads/writes the same JSON shape. Ledger reads the same JSON shape from stdin and writes one snapshot to stdout. Composable via Unix pipe.

**Decimal arithmetic:** used throughout to avoid float drift on fractional amounts (important for any financial aggregation).

**Rejected:** SQLite persistence (would force a file format and locking model before the derived layer is exercised), in-memory state across CLI invocations (would require daemonization; not needed for a derived view).

## 001 — 2026-06-28 — Add test suite

**What:** `tests/test_pipeline.py`, stdlib `unittest`, 20 tests. No production code changes.

**Why:** MVP was runnable only via ad-hoc stdin piping. Verifiability was manual. Tests lock the contract so the next iteration can't silently break Observation → Claim → Validation → Recognition.

**Rejected:** pytest (extra dep, not needed for 20 tests), hypothesis (overkill at MVP scale).