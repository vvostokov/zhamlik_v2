"""
Zhamlik v0.1 derived layer: Ledger.

Ledger is a *derived* view over Recognitions. It is NOT a primitive.
It aggregates Recognition events into:
  - Account balances (per subject + currency)
  - Recognized event count, rejected event count
  - Per-currency totals

Reads JSON lines on stdin (the same shape that `pipeline.py` emits),
emits a final ledger snapshot as a single JSON object on stdout.

No new ontology. Uses only the 6 primitives; aggregates them.

Usage:
    cat events.jsonl | python pipeline.py | python ledger.py
    echo '...' | python pipeline.py | python ledger.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AccountState:
    """A derived projection: aggregates Recognitions for one subject+currency."""
    subject: str
    currency: str
    balance: Decimal = Decimal("0")
    recognized_count: int = 0
    rejected_count: int = 0

    def apply(self, amount: Decimal, recognized: bool) -> None:
        if recognized:
            self.balance += amount
            self.recognized_count += 1
        else:
            self.rejected_count += 1

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "currency": self.currency,
            "balance": str(self.balance),
            "recognized_count": self.recognized_count,
            "rejected_count": self.rejected_count,
        }


@dataclass
class Ledger:
    """Aggregated derived state. In-memory only; not persisted."""
    accounts: dict = field(default_factory=lambda: defaultdict(dict))
    totals_by_currency: dict = field(default_factory=lambda: defaultdict(lambda: Decimal("0")))
    recognized_total: int = 0
    rejected_total: int = 0

    def apply_event(self, event: dict) -> None:
        """Apply one event (shape: {claim:{subject}, observation:{amount,currency}, recognition:{status}})."""
        rec_status = event.get("recognition", {}).get("status")
        obs = event.get("observation", {})
        claim = event.get("claim", {})

        try:
            amount = Decimal(obs.get("amount", "0"))
        except Exception:
            return  # skip malformed event line silently at ledger layer
        currency = obs.get("currency", "")
        subject = claim.get("subject", "")

        if not currency or not subject:
            return

        key = (subject, currency)
        if key not in self.accounts[currency]:
            self.accounts[currency][key] = AccountState(subject=subject, currency=currency)
        acct = self.accounts[currency][key]

        recognized = rec_status == "recognized"
        acct.apply(amount, recognized)

        if recognized:
            self.totals_by_currency[currency] += amount
            self.recognized_total += 1
        else:
            self.rejected_total += 1

    def snapshot(self) -> dict:
        return {
            "accounts": [
                acct.to_dict()
                for by_currency in self.accounts.values()
                for acct in by_currency.values()
            ],
            "totals_by_currency": {
                cur: str(amt) for cur, amt in self.totals_by_currency.items()
            },
            "recognized_total": self.recognized_total,
            "rejected_total": self.rejected_total,
        }


def build_ledger(stream) -> Ledger:
    """Consume an iterable of JSON-line dicts and return a populated Ledger."""
    ledger = Ledger()
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # ledger layer is best-effort; bad lines counted elsewhere
        ledger.apply_event(event)
    return ledger


def main() -> int:
    ledger = build_ledger(sys.stdin)
    snapshot = ledger.snapshot()
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())