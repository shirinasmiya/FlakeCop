
"""FlakeCop agent: Strands Decider 2B picks the triage tool; Amazon Bedrock explains and drafts.

    from agent.agent import HackathonAgent
    out = HackathonAgent().chat(
        "Test LoginTest#testAdminLogin failed: NoSuchElementException on #submit-btn"
    )
    out["reply"], out["decisions"]

Interface
    HackathonAgent.chat(message, session_id, images) returns:
        reply       — LLM-generated explanation or fallback request
        decisions   — list of triage decision records from FlakeCopSelector
        model_id    — LLM model used
        latency_ms  — wall time
        agent       — agent name
"""

from __future__ import annotations

import time
from typing import Any

from strands import Agent

from decider_kit import Decider
from decider_kit.llm import agent_model, default_model_id, image_blocks, strip_thinking

from .decision import FlakeCopSelector
from .tools import TOOLS

NAME = "FlakeCop: Selenium + TestNG triage agent"

SYSTEM_PROMPT = """You are FlakeCop, a test-triage assistant for Selenium and TestNG suites.

The system has already selected the permitted triage action using Strands Decider 2B.
You must call only the selected tool, then explain the result returned by that tool.

Rules:
- Call exactly one selected triage tool per failure log.
- Never choose a different action from the one selected by the Decider.
- Never claim an action succeeded unless the tool result confirms it.
- Never invent stack trace details or test names not present in the message.
- Be concise and developer-friendly.
"""


class HackathonAgent:
    """One Strands agent per session, with FlakeCopSelector wired in before every tool call."""

    def __init__(
        self,
        decider: Decider | None = None,
        model_id: str | None = None,
    ):
        self.decider = decider or Decider()
        self.model_id = model_id or default_model_id()
        self.selector = FlakeCopSelector(self.decider)
        self.sessions: dict[str, Agent] = {}

    def _session(self, session_id: str) -> Agent:
        if session_id not in self.sessions:
            self.sessions[session_id] = Agent(
                model=agent_model(self.model_id),
                system_prompt=SYSTEM_PROMPT,
                tools=TOOLS,
                callback_handler=None,
            )
        return self.sessions[session_id]

    def chat(
        self,
        message: str,
        session_id: str = "default",
        images: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Triage one test failure.

        1. FlakeCopSelector asks Strands Decider 2B which action to take.
        2. Low-confidence decisions return a request for more evidence.
        3. Otherwise, the LLM is restricted to the selected tool.
        4. The LLM explains the tool result.
        """
        # Step 1: decide which tool to invoke before the LLM sees the message.
        decision = self.selector.triage(message)
        chosen = decision["chosen"]

        # Step 2: handle low confidence without allowing a different action.
        if (
            chosen == "insufficient_evidence"
            or decision["verdict"] == "fallback"
        ):
            return {
                "reply": (
                    "I don't have enough evidence to recommend a triage action "
                    "confidently. Please provide the full stack trace, the test "
                    "name, and whether the failure is intermittent or reproducible."
                ),
                "decisions": self.selector.log[-1:],
                "model_id": self.model_id,
                "latency_ms": 0,
                "agent": NAME,
            }

        # Step 3: expose only the tool selected by Decider 2B.
        active_tools = [tool for tool in TOOLS if tool.__name__ == chosen]

        if not active_tools:
            raise RuntimeError(
                f"Decider selected '{chosen}', but no matching tool was found."
            )

        prefix = (
            f"[FlakeCop decision: {chosen}. "
            "You must use only this selected action. "
            "Call the selected tool with arguments supported by the user's message. "
            "Explain the action returned by the tool. Do not recommend or claim "
            "that a different action was performed.]\n\n"
        )

        agent = self._session(session_id)

        # Swap the tool list for this turn.
        agent.tools = active_tools  # type: ignore[assignment]

        content: Any = (
            [*image_blocks(images), {"text": prefix + message}]
            if images
            else prefix + message
        )

        t0 = time.perf_counter()
        result = agent(content)
        reply = strip_thinking(str(result))

        return {
            "reply": reply,
            "decisions": self.selector.log[-1:],
            "model_id": self.model_id,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "agent": NAME,
        }


if __name__ == "__main__":
    import json
    import sys

    a = HackathonAgent()
    samples = [
        "LoginTest#testAdminLogin failed: "
        "org.openqa.selenium.NoSuchElementException: no such element: "
        'Unable to locate element: {"method":"id","selector":"submit-btn"}',
        "CheckoutTest#testPaymentFlow failed 3 times this week with "
        "SocketTimeoutException at line 42. Other tests pass fine.",
        "PricingTest#testDiscountCalculation FAILED: expected:<95.0> "
        "but was:<100.0> — same result on every run since yesterday's deploy.",
    ]

    for msg in (sys.argv[1:] or samples):
        print(json.dumps(a.chat(msg), indent=2, default=str))
        print("---")
