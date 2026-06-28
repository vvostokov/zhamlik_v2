# Decision Log

Append-only. Each entry: iteration, what, why, alternatives rejected.

## 001 — 2026-06-28 — Add test suite

**What:** `tests/test_pipeline.py`, stdlib `unittest`, 20 tests. No production code changes.

**Why:** MVP was runnable only via ad-hoc stdin piping. Verifiability was manual. Tests lock the contract so the next iteration can't silently break Observation → Claim → Validation → Recognition.

**Rejected:** pytest (extra dep, not needed for 20 tests), hypothesis (overkill at MVP scale).