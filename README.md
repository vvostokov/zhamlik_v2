# Zhamlik v0.1 — MVP Pipeline

> Status: experimental. Validation: in progress.
> Slice: ingestion Observations → Claim generation → Validation → Recognition gate.

## Scope

This is the **first executable vertical slice** of Zhamlik. One end-to-end pipeline, no persistence, no external systems.

## Pipeline

```
Observation -> Claim -> Validation -> Recognition
```

| Step | Primitive | Operation |
|---|---|---|
| 1 | Observation | Manual structured input via stdin (JSON) |
| 2 | Claim | Default interpretation: subject = `identity:<source>`, confidence = source baseline |
| 3 | Validation | Rules: positive amount, 3-letter currency, source in whitelist |
| 4 | Recognition | Pass if validation.status == "pass" AND confidence >= 0.50 |

## Run

```bash
cd src
python pipeline.py < input.jsonl
```

Input: one JSON object per line on stdin.
Output: one JSON object per line on stdout.
Errors: one JSON object per malformed line on stderr.

### Example

```bash
echo '{"amount":"1000","currency":"USD","source":"Bank1","timestamp":"2026-06-28T10:00:00","reason":"incoming_transfer"}' | python pipeline.py
```

Output:
```json
{"observation": {...}, "claim": {...}, "validation": {"status": "pass", "confidence": 0.9, ...}, "recognition": {"status": "recognized", ...}}
```

## Tests

```bash
python -m unittest discover -s tests -v
```

20 tests cover Observation parsing, Claim generation, Validation rules, Recognition gate, end-to-end, and the CLI stdin/stdout contract. 10 tests cover the derived Ledger layer. Stdlib only, no external deps.

## Derived layer

Ledger is a *derived* view over Recognitions (not a primitive). It aggregates Recognition events into per-subject, per-currency balances and per-currency totals.

```bash
cat events.jsonl | python pipeline.py | python ledger.py
```

Output:
```json
{
  "accounts": [
    {"subject": "identity:Bank1", "currency": "USD",
     "balance": "750", "recognized_count": 3, "rejected_count": 0},
    ...
  ],
  "totals_by_currency": {"USD": "750", "EUR": "500"},
  "recognized_total": 4, "rejected_total": 2
}
```

Decimal arithmetic is used throughout — no float drift on fractional amounts.

## Current state (v0.1.2)

- `src/pipeline.py` — Observation → Claim → Validation → Recognition.
- `src/ledger.py` — derived aggregation (Account, totals, counts).
- `tests/test_pipeline.py` — 20 tests.
- `tests/test_ledger.py` — 10 tests.
- 30/30 tests pass. No persistence yet.

## Frozen ontology

This implementation uses the 6 primitives from the frozen Zhamlik ontology:

- Observation
- Claim
- Validation
- Recognition
- Identity (referenced as `identity:<source>` in MVP)
- Confidence (propagated through pipeline)

Dimensions (Time, Source, Content, Reason) are **not** ontology — they are interpretation context.

## What's NOT in MVP

- Persistence (no DB, no files)
- API endpoints
- Authentication / multi-tenant
- UI
- Reconciliation
- Account as entity (Account is derived)
- NLP / unstructured input
- External data sources

## Requirements

- Python 3.11+
- No external dependencies (stdlib only)

## Next slice (deferred)

The next slice will be decided based on friction encountered during use of this MVP. Candidate next slices include:

- Persistence (SQLite or JSON file)
- Multi-Identity resolution
- Confidence calibration against ground truth
- Validation rules plug-in framework

These are **not** committed to. They will be proposed only after observed need.