"""REUSABLE DECISION PATTERN: FlakeCop test-failure triage  (#tool-selection)

What it does
    Before the agent calls any triage tool, Strands Decider 2B reads the failure log and
    stack trace and picks the best action from four options:

        rerun_test          — transient environment / timing / network failure; retry it.
        quarantine_test     — intermittent failure across multiple runs; pull it from CI.
        open_bug_report     — consistent assertion or logic defect; file a bug.
        suggest_locator_fix — NoSuchElementException / StaleElementReferenceException; fix the locator.

    When signals overlap (e.g., a flaky network test that also matches a bad locator), the
    decider uses a four-way choice question so probabilities are compared directly and the
    highest-confidence answer wins.  If overall confidence is below `threshold`, the agent
    falls back to "insufficient evidence" rather than guessing.

Typed questions
    `triage_action` (choice): one option per tool (+ `insufficient_evidence`).

Wiring
    `FlakeCopSelector` wraps `ToolSelector` and is wired into `FlakeCopAgent`:

        selector = FlakeCopSelector(Decider())
        selector.triage(failure_context)   ->  Selection

How to reuse it
    Copy this file and replace the five option descriptions in `TRIAGE_OPTIONS` with the
    tools meaningful for your domain. The rest of the wiring is generic.
"""

from __future__ import annotations

from typing import Any

from decider_kit import Decider
from decider_kit.patterns.tool_selection import ToolSelector

from .tools import TOOLS


PATTERN_TAG = "#tool-selection"

# One sentence per option — this is exactly what Strands Decider 2B reads when choosing.
TRIAGE_OPTIONS: dict[str, str] = {
    "rerun_test": (
        "The failure is most likely transient: a network timeout, a CI environment hiccup, "
        "a race condition, or a flaky external dependency — not a code or DOM defect. "
        "A single retry is the safest first step."
    ),
    "quarantine_test": (
        "The test has failed intermittently across several recent runs with no consistent "
        "root cause. It is disrupting CI without pointing to a real defect. "
        "Moving it to quarantine stops the noise while the team investigates."
    ),
    "open_bug_report": (
        "The failure is deterministic and reproducible: an assertion fails on a specific "
        "value, a NullPointerException is thrown at the same line every time, or business "
        "logic clearly produces the wrong result. This needs a filed defect."
    ),
    "suggest_locator_fix": (
        "The stack trace contains NoSuchElementException or StaleElementReferenceException, "
        "or the log shows that Selenium could not find or interact with an element whose "
        "locator has likely changed in the UI. A locator update is needed."
    ),
    "insufficient_evidence": (
        "The log is too short, too generic, or ambiguous to determine root cause with "
        "confidence. Return a safe recommendation and ask for more context."
    ),
}

# Confidence below this → fall back to insufficient_evidence regardless of the top label.
CONFIDENCE_THRESHOLD = 0.55

# Module-level QUESTIONS dict required by the kit contract (test_agent_contract, ./kit bench,
# ./kit check). The single choice question encodes all four tools plus the safe fallback.
QUESTIONS: dict[str, dict] = {
    "triage_action": Decider.choice(
        "Which triage action best matches this Selenium + TestNG test failure?",
        TRIAGE_OPTIONS,
    )
}


class FlakeCopSelector:
    """Thin wrapper around ToolSelector that enforces the insufficient-evidence fallback."""

    def __init__(self, decider: Decider, threshold: float = CONFIDENCE_THRESHOLD):
        self.decider = decider
        self.threshold = threshold
        self.log: list[dict[str, Any]] = []
        # ToolSelector handles the choice question and confidence bookkeeping.
        self._selector = ToolSelector(decider, TOOLS, threshold=threshold,
                                      context="(Selenium + TestNG test failure triage)")

    def triage(self, failure_context: str) -> dict[str, Any]:
        """Run the triage decision and return a result dict ready for the agent."""
        answers = self.decider.ask(failure_context, QUESTIONS)
        dec = answers["triage_action"]

        if dec.confidence < self.threshold or dec.label == "insufficient_evidence":
            chosen = "insufficient_evidence"
            verdict = "fallback"
        else:
            chosen = dec.label or "insufficient_evidence"
            verdict = "selected"

        rec: dict[str, Any] = {
            "pattern": PATTERN_TAG,
            "chosen": chosen,
            "confidence": round(dec.confidence, 3),
            "verdict": verdict,
            "probabilities": (lambda p: {**p, chosen: round(1.0 - sum(v for k, v in p.items() if k != chosen), 6)})(
                {k: round(v, 3) for k, v in dec.probabilities.items()}
            ),
            "decider_ms": round(self.decider.last_latency_ms or 0),
        }
        self.log.append(rec)
        return rec
