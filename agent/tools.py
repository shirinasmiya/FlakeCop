"""FlakeCop tools: four triage actions for Selenium + TestNG test failures.

Keep a clear one-line docstring on each tool: the ToolSelector pattern uses it as the
option description that Strands Decider 2B reads when picking between tools.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from typing import Any

from strands import tool

# In-memory store so the demo runs without external services.
_ACTIONS: list[dict[str, Any]] = []


@tool
def rerun_test(test_name: str, reason: str) -> dict[str, Any]:
    """Schedule an immediate rerun for a test that likely failed due to a transient environment issue."""
    record = {
        "action": "rerun",
        "test_name": test_name,
        "reason": reason,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIONS.append(record)
    return {"status": "queued", **record}


@tool
def quarantine_test(test_name: str, reason: str) -> dict[str, Any]:
    """Move an intermittently failing test to the quarantine suite so it no longer blocks CI."""
    record = {
        "action": "quarantine",
        "test_name": test_name,
        "reason": reason,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIONS.append(record)
    return {"status": "quarantined", **record}


@tool
def open_bug_report(test_name: str, summary: str, details: str) -> dict[str, Any]:
    """Create a bug report for a test that has a consistent, reproducible assertion or logic failure."""
    record = {
        "action": "bug_report",
        "test_name": test_name,
        "summary": summary,
        "details": textwrap.shorten(details, width=500),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIONS.append(record)
    return {"status": "created", "bug_id": f"BUG-{len(_ACTIONS):04d}", **record}


@tool
def suggest_locator_fix(test_name: str, element_description: str, suggestion: str) -> dict[str, Any]:
    """Propose an updated Selenium locator for a test broken by a missing, stale, or changed DOM element."""
    record = {
        "action": "locator_fix",
        "test_name": test_name,
        "element_description": element_description,
        "suggestion": suggestion,
        "suggested_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIONS.append(record)
    return {"status": "suggested", **record}


TOOLS = [rerun_test, quarantine_test, open_bug_report, suggest_locator_fix]
