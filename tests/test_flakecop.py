"""FlakeCop unit tests.

Covers:
- all four triage tools (shape and status values)
- FlakeCopSelector: each of the four verdicts + insufficient-evidence fallback
- low-confidence fallback (confidence below threshold)
- HackathonAgent.chat interface contract
- eval_cases.jsonl format
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import FakeDecider

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TestTools:
    def setup_method(self):
        import agent.tools as mod
        mod._ACTIONS.clear()

    def test_rerun_queues_and_returns_status(self):
        from agent.tools import rerun_test
        r = rerun_test("LoginTest#testFoo", "SocketTimeoutException in shared pool")
        assert r["status"] == "queued"
        assert r["action"] == "rerun"
        assert r["test_name"] == "LoginTest#testFoo"
        assert "queued_at" in r

    def test_quarantine_returns_status(self):
        from agent.tools import quarantine_test
        r = quarantine_test("DashboardTest#testWidget", "intermittent 4/10 runs")
        assert r["status"] == "quarantined"
        assert r["action"] == "quarantine"
        assert "quarantined_at" in r

    def test_open_bug_report_assigns_id(self):
        from agent.tools import open_bug_report
        r = open_bug_report("PricingTest#testDiscount", "wrong amount", "expected 95.0 got 100.0")
        assert r["status"] == "created"
        assert r["action"] == "bug_report"
        assert r["bug_id"].startswith("BUG-")
        assert "created_at" in r

    def test_suggest_locator_fix_returns_status(self):
        from agent.tools import suggest_locator_fix
        r = suggest_locator_fix("LoginTest#testAdmin", "id=submit-btn", "use css .login-form button[type=submit]")
        assert r["status"] == "suggested"
        assert r["action"] == "locator_fix"
        assert "suggested_at" in r

    def test_bug_report_truncates_long_details(self):
        from agent.tools import open_bug_report
        long = "x" * 1000
        r = open_bug_report("T#t", "s", long)
        assert len(r["details"]) <= 503  # textwrap.shorten width=500 + ellipsis

    def test_action_log_accumulates(self):
        import agent.tools as mod
        from agent.tools import rerun_test, quarantine_test
        rerun_test("A", "r1")
        quarantine_test("B", "r2")
        assert len(mod._ACTIONS) == 2


# ---------------------------------------------------------------------------
# Decision: FlakeCopSelector with controlled FakeDecider
# ---------------------------------------------------------------------------

def _make_selector(chosen: str, confidence: float = 0.85):
    """FlakeCopSelector whose decider always returns `chosen` at `confidence`."""
    from agent.decision import CONFIDENCE_THRESHOLD, FlakeCopSelector
    from decider_kit.client import Decision

    class ControlledDecider(FakeDecider):
        def ask(self, state, questions, images=None):
            result = super().ask(state, questions, images=images)
            for k, d in result.items():
                if d.kind == "choice":
                    rest = (1.0 - confidence) / max(1, len(d.probabilities) - 1)
                    probs = {o: (confidence if o == chosen else rest) for o in d.probabilities}
                    result[k] = Decision.parse({
                        "type": "choice",
                        "choice": chosen,
                        "probabilities": probs,
                        "confidence": confidence,
                    })
            return result

    d = ControlledDecider(lambda state, name, q: chosen)
    d.last_latency_ms = 15.0
    return FlakeCopSelector(d, threshold=CONFIDENCE_THRESHOLD)


@pytest.mark.parametrize("chosen", [
    "rerun_test", "quarantine_test", "open_bug_report", "suggest_locator_fix"
])
def test_selector_picks_each_tool(chosen):
    sel = _make_selector(chosen, confidence=0.85)
    result = sel.triage("some failure log")
    assert result["chosen"] == chosen
    assert result["verdict"] == "selected"
    assert result["confidence"] >= 0.55


def test_selector_insufficient_evidence_option():
    """Decider explicitly picks insufficient_evidence → verdict is fallback."""
    sel = _make_selector("insufficient_evidence", confidence=0.80)
    result = sel.triage("vague log with no stack trace")
    assert result["chosen"] == "insufficient_evidence"
    assert result["verdict"] == "fallback"


def test_selector_low_confidence_fallback():
    """Confidence below threshold → fallback regardless of label."""
    sel = _make_selector("open_bug_report", confidence=0.40)
    result = sel.triage("ambiguous log")
    assert result["verdict"] == "fallback"
    assert result["chosen"] == "insufficient_evidence"


def test_selector_log_records_every_call():
    sel = _make_selector("rerun_test")
    sel.triage("log1")
    sel.triage("log2")
    assert len(sel.log) == 2
    for rec in sel.log:
        assert "pattern" in rec
        assert "probabilities" in rec
        assert "decider_ms" in rec


def test_selector_probabilities_sum_to_one():
    sel = _make_selector("quarantine_test", confidence=0.75)
    result = sel.triage("intermittent failure")
    total = sum(result["probabilities"].values())
    # Allow for standard IEEE-754 rounding across 5 options (< 1e-9 per op).
    assert abs(total - 1.0) < 1e-4


def test_selector_pattern_tag():
    from agent.decision import PATTERN_TAG
    assert PATTERN_TAG == "#tool-selection"


# ---------------------------------------------------------------------------
# HackathonAgent interface (LLM stubbed out)
# ---------------------------------------------------------------------------

class TestAgentInterface:
    def _make_agent(self, chosen="rerun_test"):
        """Build a HackathonAgent whose LLM session is pre-populated with a
        fake Strands session object.  _session() checks self.sessions first,
        so Agent() and agent_model() are never called — no AWS credentials
        are needed and no real network calls are made."""
        import agent.agent as amod

        class FakeSession:
            """Minimal stand-in for a strands.Agent session."""
            def __init__(self):
                self.tools = []
            def __call__(self, msg, **kw):
                return f"FlakeCop recommendation: {chosen}"

        a = amod.HackathonAgent.__new__(amod.HackathonAgent)
        a.decider = _make_selector(chosen).decider
        a.model_id = "fake-model"
        a.selector = _make_selector(chosen)
        # Pre-populate the session so _session() never reaches Agent().
        fake_session = FakeSession()
        a.sessions = {"default": fake_session}
        return a

    def test_chat_returns_required_keys(self):
        a = self._make_agent("rerun_test")
        out = a.chat("LoginTest failed: SocketTimeoutException")
        assert {"reply", "decisions", "model_id", "latency_ms", "agent"} <= set(out.keys())

    def test_chat_decisions_is_one_item_list(self):
        a = self._make_agent("quarantine_test")
        out = a.chat("DashboardTest intermittent failure")
        assert isinstance(out["decisions"], list) and len(out["decisions"]) == 1

    def test_chat_reply_is_non_empty_string(self):
        a = self._make_agent("open_bug_report")
        out = a.chat("PricingTest: expected 95.0 but was 100.0")
        assert isinstance(out["reply"], str) and len(out["reply"]) > 0

    def test_chat_latency_ms_is_int(self):
        a = self._make_agent("suggest_locator_fix")
        out = a.chat("LoginTest: NoSuchElementException on id=submit-btn")
        assert isinstance(out["latency_ms"], int)

    def test_agent_name_contains_flakecop(self):
        from agent.agent import NAME
        assert "FlakeCop" in NAME


# ---------------------------------------------------------------------------
# eval_cases.jsonl format
# ---------------------------------------------------------------------------

VALID_LABELS = {
    "rerun_test", "quarantine_test", "open_bug_report",
    "suggest_locator_fix", "insufficient_evidence",
}


def _load_cases():
    path = ROOT / "agent" / "eval_cases.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_eval_cases_have_required_fields():
    for c in _load_cases():
        assert "state" in c and "expected" in c and "split" in c, c


def test_eval_cases_state_non_empty():
    for c in _load_cases():
        assert isinstance(c["state"], str) and len(c["state"]) > 20, c["state"]


def test_eval_cases_labels_valid():
    for c in _load_cases():
        for label in c["expected"].values():
            assert label in VALID_LABELS, f"unknown label {label!r}"


def test_eval_cases_split_values():
    for c in _load_cases():
        assert c["split"] in ("tune", "test"), c


def test_eval_cases_both_splits_present():
    splits = {c["split"] for c in _load_cases()}
    assert "tune" in splits and "test" in splits


def test_eval_cases_all_four_categories_covered():
    labels = {list(c["expected"].values())[0] for c in _load_cases()}
    assert {"rerun_test", "quarantine_test", "open_bug_report", "suggest_locator_fix"} <= labels


def test_eval_cases_at_least_twelve():
    assert len(_load_cases()) >= 12
