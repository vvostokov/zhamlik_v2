"""
Zhamlik v0.1 MVP Pipeline.

Single end-to-end flow:
    Observation -> Claim -> Validation -> Recognition

Minimal manual structured input via CLI. No persistence. No external systems.

Input format (stdin, one Observation per line, JSON):
    {"amount": "1000", "currency": "USD", "source": "Bank1",
     "timestamp": "2026-06-28T10:00:00", "reason": "incoming_transfer"}

Output (stdout, JSON, one result per input):
    {
      "observation": {...},
      "claim": {...},
      "validation": {"status": "pass"|"fail", "confidence": float},
      "recognition": {"status": "recognized"|"rejected", "reason": "..."}
    }

Usage:
    echo '{"amount":"1000","currency":"USD","source":"Bank1","timestamp":"2026-06-28T10:00:00","reason":"incoming_transfer"}' | python pipeline.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


# -----------------------------------------------------------------------------
# Primitives (from the frozen ontology)
# -----------------------------------------------------------------------------

@dataclass
class Observation:
    """A registered fact from an external source."""
    amount: Decimal
    currency: str
    source: str
    timestamp: str
    reason: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        try:
            amount = Decimal(str(d["amount"]))
        except (InvalidOperation, KeyError, TypeError) as e:
            raise ValueError(f"invalid amount: {e}")
        return cls(
            amount=amount,
            currency=str(d.get("currency", "")).strip().upper(),
            source=str(d.get("source", "")).strip(),
            timestamp=str(d.get("timestamp", "")).strip(),
            reason=str(d.get("reason", "")).strip(),
        )


@dataclass
class Claim:
    """An interpretation of an Observation, with confidence."""
    observation: Observation
    subject: str  # who/what this claim is about (Identity reference)
    confidence: float
    derived_from_observation: bool = True

    def __str__(self) -> str:
        return (f"Claim({self.subject}, {self.observation.amount} "
                f"{self.observation.currency}, conf={self.confidence:.2f})")


@dataclass
class Validation:
    """The result of checking a Claim against rules."""
    claim: Claim
    status: str  # "pass" | "fail"
    confidence: float
    method: str = "rule_amount_positive+source_known"

    def __str__(self) -> str:
        return f"Validation({self.status}, conf={self.confidence:.2f})"


@dataclass
class Recognition:
    """The decision to admit a validated Claim into the recognized state."""
    claim: Claim
    validation: Validation
    status: str  # "recognized" | "rejected"
    reason: str = ""

    def __str__(self) -> str:
        return f"Recognition({self.status}, {self.reason})"


# -----------------------------------------------------------------------------
# Pipeline steps
# -----------------------------------------------------------------------------

# Known sources (minimal whitelist). In a real system this would be
# configurable. For MVP we hardcode to keep the pipeline single-file.
KNOWN_SOURCES = {"Bank1", "Bank2", "Broker1", "Exchange1", "Manual"}


def generate_claim(obs: Observation) -> Claim:
    """Step 2: Observation -> Claim.

    Interpretation layer. For MVP: derive a default subject from source
    (a placeholder Identity), and assign a baseline confidence based on
    the source.
    """
    # Baseline confidence depends on source trust (very simple model).
    baseline = {
        "Bank1": 0.90,
        "Bank2": 0.90,
        "Broker1": 0.85,
        "Exchange1": 0.80,
        "Manual": 0.70,
    }.get(obs.source, 0.50)

    # Default subject: a placeholder reference. In a real system this
    # would resolve to an Identity primitive. For MVP we use source as
    # the subject proxy.
    subject = f"identity:{obs.source}"

    return Claim(
        observation=obs,
        subject=subject,
        confidence=baseline,
    )


def validate_claim(claim: Claim) -> Validation:
    """Step 3: Claim -> Validation.

    Rules (MVP):
      - amount must be positive (non-zero)
      - currency must be a 3-letter code
      - source must be in KNOWN_SOURCES
    """
    obs = claim.observation
    failures = []

    if obs.amount == 0:
        failures.append("amount_zero")
    if len(obs.currency) != 3 or not obs.currency.isalpha():
        failures.append("invalid_currency")
    if obs.source not in KNOWN_SOURCES:
        failures.append("unknown_source")

    if failures:
        return Validation(
            claim=claim,
            status="fail",
            confidence=0.0,
            method=f"fail:{'+'.join(failures)}",
        )

    # Pass: propagate claim confidence (no penalty for MVP).
    return Validation(
        claim=claim,
        status="pass",
        confidence=claim.confidence,
    )


def recognize(validation: Validation) -> Recognition:
    """Step 4: Validation -> Recognition.

    Recognized if validation passes and confidence meets the gate.
    For MVP the gate is 0.50.
    """
    GATE = 0.50
    if validation.status == "pass" and validation.confidence >= GATE:
        return Recognition(
            claim=validation.claim,
            validation=validation,
            status="recognized",
            reason=f"confidence {validation.confidence:.2f} >= gate {GATE}",
        )
    return Recognition(
        claim=validation.claim,
        validation=validation,
        status="rejected",
        reason=(f"validation={validation.status}, "
                f"confidence={validation.confidence:.2f}, "
                f"gate={GATE}"),
    )


def run_one(obs: Observation) -> dict:
    """Run the full pipeline on a single Observation."""
    claim = generate_claim(obs)
    validation = validate_claim(claim)
    recognition = recognize(validation)
    return {
        "observation": {
            "amount": str(obs.amount),
            "currency": obs.currency,
            "source": obs.source,
            "timestamp": obs.timestamp,
            "reason": obs.reason,
        },
        "claim": {
            "subject": claim.subject,
            "confidence": round(claim.confidence, 3),
            "derived_from_observation": claim.derived_from_observation,
        },
        "validation": {
            "status": validation.status,
            "confidence": round(validation.confidence, 3),
            "method": validation.method,
        },
        "recognition": {
            "status": recognition.status,
            "reason": recognition.reason,
        },
    }


def main() -> int:
    """Read Observations from stdin, one JSON object per line.
    Emit results to stdout, one JSON object per line.
    Exit 0 on success, 1 on any malformed input.
    """
    rc = 0
    for lineno, line in enumerate(sys.stdin, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            obs = Observation.from_dict(payload)
            result = run_one(obs)
            print(json.dumps(result, ensure_ascii=False))
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            print(json.dumps({
                "line": lineno,
                "error": str(e),
                "raw": line,
            }), file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())