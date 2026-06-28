"""Tests for the Zhamlik v0.1 MVP pipeline.

Uses stdlib unittest only. No external deps.

Run from repo root:
    python -m unittest discover -s tests -v

Exercises the public pipeline behavior end-to-end through Observation,
Claim, Validation, Recognition — no internals coupling.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from decimal import Decimal

# Make src/ importable when running tests from repo root.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pipeline  # noqa: E402


def make_obs(amount="100", currency="USD", source="Bank1",
             timestamp="2026-06-28T10:00:00", reason="test"):
    return pipeline.Observation.from_dict({
        "amount": amount, "currency": currency, "source": source,
        "timestamp": timestamp, "reason": reason,
    })


# -----------------------------------------------------------------------------
# Dataclass construction
# -----------------------------------------------------------------------------

class ObservationParsing(unittest.TestCase):
    def test_parses_valid(self):
        obs = make_obs(amount="1000.50", currency="usd")
        self.assertEqual(obs.amount, Decimal("1000.50"))
        self.assertEqual(obs.currency, "USD")  # normalized to upper

    def test_rejects_non_numeric_amount(self):
        with self.assertRaises(ValueError):
            make_obs(amount="not_a_number")

    def test_missing_amount(self):
        with self.assertRaises((ValueError, KeyError)):
            pipeline.Observation.from_dict({
                "currency": "USD", "source": "Bank1",
                "timestamp": "2026-06-28T10:00:00",
            })


# -----------------------------------------------------------------------------
# Claim generation
# -----------------------------------------------------------------------------

class ClaimGeneration(unittest.TestCase):
    def test_subject_uses_source(self):
        obs = make_obs(source="Bank1")
        claim = pipeline.generate_claim(obs)
        self.assertEqual(claim.subject, "identity:Bank1")

    def test_confidence_is_baseline_per_source(self):
        self.assertEqual(pipeline.generate_claim(make_obs(source="Bank1")).confidence, 0.90)
        self.assertEqual(pipeline.generate_claim(make_obs(source="Broker1")).confidence, 0.85)
        self.assertEqual(pipeline.generate_claim(make_obs(source="Manual")).confidence, 0.70)

    def test_unknown_source_has_low_baseline(self):
        self.assertEqual(pipeline.generate_claim(make_obs(source="Stranger")).confidence, 0.50)


# -----------------------------------------------------------------------------
# Validation rules
# -----------------------------------------------------------------------------

class ValidationRules(unittest.TestCase):
    def test_pass_for_known_source_valid_currency_positive_amount(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(amount="100", currency="USD", source="Bank1")))
        self.assertEqual(v.status, "pass")
        self.assertGreater(v.confidence, 0)

    def test_fail_on_zero_amount(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(amount="0")))
        self.assertEqual(v.status, "fail")
        self.assertIn("amount_zero", v.method)

    def test_fail_on_invalid_currency_length(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(currency="US")))
        self.assertEqual(v.status, "fail")
        self.assertIn("invalid_currency", v.method)

    def test_fail_on_unknown_source(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(source="GhostBank")))
        self.assertEqual(v.status, "fail")
        self.assertIn("unknown_source", v.method)

    def test_multiple_failures_all_reported(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(amount="0", currency="US", source="Ghost")))
        self.assertIn("amount_zero", v.method)
        self.assertIn("invalid_currency", v.method)
        self.assertIn("unknown_source", v.method)


# -----------------------------------------------------------------------------
# Recognition gate
# -----------------------------------------------------------------------------

class RecognitionGate(unittest.TestCase):
    def test_recognized_when_pass_and_high_confidence(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(source="Bank1")))
        r = pipeline.recognize(v)
        self.assertEqual(r.status, "recognized")

    def test_rejected_when_validation_failed(self):
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs(amount="0")))
        r = pipeline.recognize(v)
        self.assertEqual(r.status, "rejected")

    def test_rejected_when_confidence_below_gate(self):
        # Build a Validation that passed but with confidence < gate.
        v = pipeline.Validation(
            claim=pipeline.generate_claim(make_obs(source="Bank1")),
            status="pass",
            confidence=0.40,  # below 0.50 gate
            method="forced",
        )
        r = pipeline.recognize(v)
        self.assertEqual(r.status, "rejected")
        self.assertIn("0.40", r.reason)


# -----------------------------------------------------------------------------
# End-to-end via run_one
# -----------------------------------------------------------------------------

class EndToEnd(unittest.TestCase):
    def test_happy_path_recognized(self):
        result = pipeline.run_one(make_obs(amount="1000", currency="USD", source="Bank1"))
        self.assertEqual(result["validation"]["status"], "pass")
        self.assertEqual(result["recognition"]["status"], "recognized")
        self.assertEqual(result["claim"]["subject"], "identity:Bank1")
        self.assertEqual(result["claim"]["confidence"], 0.90)

    def test_zero_amount_rejected(self):
        result = pipeline.run_one(make_obs(amount="0"))
        self.assertEqual(result["recognition"]["status"], "rejected")

    def test_amount_preserved_as_decimal_string(self):
        result = pipeline.run_one(make_obs(amount="1000.50"))
        self.assertEqual(result["observation"]["amount"], "1000.50")


# -----------------------------------------------------------------------------
# Validation rule registry (pluggable rules)
# -----------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402

class RuleRegistry(unittest.TestCase):
    """Adding a rule must work without editing validate_claim()."""

    def setUp(self):
        # Snapshot the default rules so test mutations don't leak.
        self._snapshot = list(pipeline._DEFAULT_RULES)

    def tearDown(self):
        pipeline._DEFAULT_RULES.clear()
        pipeline._DEFAULT_RULES.extend(self._snapshot)

    def test_register_appends_rule(self):
        before = len(pipeline._DEFAULT_RULES)
        def always_pass(_claim): return None
        pipeline.register_rule(always_pass)
        self.assertEqual(len(pipeline._DEFAULT_RULES), before + 1)

    def test_new_rule_takes_effect_on_next_validate(self):
        def reject_all(_claim): return "rejected_by_test"
        pipeline.register_rule(reject_all)
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs()))
        self.assertEqual(v.status, "fail")
        self.assertIn("rejected_by_test", v.method)

    def test_real_financial_rule_max_amount(self):
        """Real-world example: reject transactions above 1M USD."""
        MAX_USD = Decimal("1000000")
        def max_amount_usd(claim):
            if (claim.observation.currency == "USD"
                    and claim.observation.amount > MAX_USD):
                return "amount_exceeds_1M_USD"
            return None
        pipeline.register_rule(max_amount_usd)
        ok = pipeline.validate_claim(
            pipeline.generate_claim(make_obs(amount="999999", currency="USD")))
        self.assertEqual(ok.status, "pass")
        too_big = pipeline.validate_claim(
            pipeline.generate_claim(make_obs(amount="1000001", currency="USD")))
        self.assertEqual(too_big.status, "fail")
        self.assertIn("amount_exceeds_1M_USD", too_big.method)

    def test_multiple_registered_rules_combine_failures(self):
        def r1(_c): return "rule1"
        def r2(_c): return "rule2"
        pipeline.register_rule(r1)
        pipeline.register_rule(r2)
        v = pipeline.validate_claim(pipeline.generate_claim(make_obs()))
        self.assertEqual(v.status, "fail")
        self.assertIn("rule1", v.method)
        self.assertIn("rule2", v.method)


# -----------------------------------------------------------------------------
# CLI contract (subprocess, line-based JSON)
# -----------------------------------------------------------------------------

class CLIStdinContract(unittest.TestCase):
    """The pipeline must be invokable as a CLI: one JSON per line in, one out."""

    def _run_cli(self, stdin_text: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "pipeline.py"],
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=SRC_DIR,
        )

    def test_single_line_happy(self):
        line = json.dumps({
            "amount": "100", "currency": "USD", "source": "Bank1",
            "timestamp": "2026-06-28T10:00:00", "reason": "cli_test",
        })
        proc = self._run_cli(line + "\n")
        self.assertEqual(proc.returncode, 0)
        out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(out_lines), 1)
        result = json.loads(out_lines[0])
        self.assertEqual(result["recognition"]["status"], "recognized")

    def test_malformed_line_goes_to_stderr_and_nonzero_exit(self):
        proc = self._run_cli("not_json\n")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not_json", proc.stderr)

    def test_bad_amount_still_zeroes_other_valid_input(self):
        good = json.dumps({
            "amount": "42", "currency": "USD", "source": "Bank1",
            "timestamp": "2026-06-28T10:00:00", "reason": "good",
        })
        proc = self._run_cli(good + "\nnot_json\n")
        # One valid result on stdout, error on stderr, exit 1.
        self.assertEqual(proc.returncode, 1)
        out_lines = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(out_lines), 1)
        self.assertEqual(json.loads(out_lines[0])["recognition"]["status"], "recognized")


if __name__ == "__main__":
    unittest.main()