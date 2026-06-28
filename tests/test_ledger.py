"""Tests for the derived Ledger layer.

Uses stdlib unittest only.

Run from repo root:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from decimal import Decimal

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import ledger  # noqa: E402


def event(amount, currency, subject="identity:Bank1",
          rec_status="recognized", source="Bank1"):
    return {
        "observation": {"amount": amount, "currency": currency, "source": source,
                        "timestamp": "2026-06-28T10:00:00", "reason": "t"},
        "claim": {"subject": subject, "confidence": 0.9, "derived_from_observation": True},
        "validation": {"status": "pass", "confidence": 0.9, "method": "t"},
        "recognition": {"status": rec_status, "reason": "t"},
    }


class LedgerApply(unittest.TestCase):
    def test_recognized_increments_balance(self):
        L = ledger.Ledger()
        L.apply_event(event("100", "USD"))
        snap = L.snapshot()
        self.assertEqual(snap["accounts"][0]["balance"], "100")
        self.assertEqual(snap["recognized_total"], 1)
        self.assertEqual(snap["rejected_total"], 0)

    def test_rejected_does_not_touch_balance_but_counts(self):
        L = ledger.Ledger()
        L.apply_event(event("100", "USD", rec_status="rejected"))
        snap = L.snapshot()
        self.assertEqual(snap["accounts"][0]["balance"], "0")
        self.assertEqual(snap["rejected_total"], 1)

    def test_negative_amounts_apply_signed(self):
        L = ledger.Ledger()
        L.apply_event(event("1000", "USD"))
        L.apply_event(event("-200", "USD"))
        snap = L.snapshot()
        self.assertEqual(snap["accounts"][0]["balance"], "800")

    def test_separate_currencies_not_aggregated(self):
        L = ledger.Ledger()
        L.apply_event(event("100", "USD"))
        L.apply_event(event("100", "EUR"))
        snap = L.snapshot()
        self.assertEqual(snap["totals_by_currency"]["USD"], "100")
        self.assertEqual(snap["totals_by_currency"]["EUR"], "100")

    def test_separate_subjects_kept_separate(self):
        L = ledger.Ledger()
        L.apply_event(event("100", "USD", subject="identity:Bank1"))
        L.apply_event(event("200", "USD", subject="identity:Bank2"))
        snap = L.snapshot()
        balances = {a["subject"]: a["balance"] for a in snap["accounts"]}
        self.assertEqual(balances["identity:Bank1"], "100")
        self.assertEqual(balances["identity:Bank2"], "200")

    def test_skips_malformed_amount_silently(self):
        L = ledger.Ledger()
        L.apply_event({"observation": {"amount": "abc", "currency": "USD"},
                       "claim": {"subject": "identity:Bank1"},
                       "recognition": {"status": "recognized"}})
        self.assertEqual(L.snapshot()["recognized_total"], 0)

    def test_skips_event_with_missing_currency_or_subject(self):
        L = ledger.Ledger()
        L.apply_event({"observation": {"amount": "100"},
                       "claim": {"subject": ""},
                       "recognition": {"status": "recognized"}})
        self.assertEqual(L.snapshot()["recognized_total"], 0)


class BuildLedger(unittest.TestCase):
    def test_consumes_stream_of_json_lines(self):
        stream = io.StringIO("\n".join(json.dumps(e) for e in [
            event("100", "USD"),
            event("-30", "USD"),
            event("50", "EUR", subject="identity:Bank2"),
        ]) + "\n")
        L = ledger.build_ledger(stream)
        snap = L.snapshot()
        self.assertEqual(snap["recognized_total"], 3)
        bank1_usd = next(a for a in snap["accounts"]
                         if a["subject"] == "identity:Bank1" and a["currency"] == "USD")
        self.assertEqual(bank1_usd["balance"], "70")

    def test_skips_blank_and_malformed_lines(self):
        stream = io.StringIO('\nnot_json\n   \n' + json.dumps(event("10", "USD")) + '\n')
        L = ledger.build_ledger(stream)
        self.assertEqual(L.snapshot()["recognized_total"], 1)


class LedgerDecimalPrecision(unittest.TestCase):
    def test_decimal_arithmetic_preserves_precision(self):
        L = ledger.Ledger()
        L.apply_event(event("0.10", "USD"))
        L.apply_event(event("0.20", "USD"))
        L.apply_event(event("-0.05", "USD"))
        snap = L.snapshot()
        self.assertEqual(snap["accounts"][0]["balance"], "0.25")


if __name__ == "__main__":
    unittest.main()