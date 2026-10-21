# FlakeCop — Demo Narration

0. FlakeCop is an AI-powered test failure triage assistant for Selenium and TestNG. It uses Strands Decider 2B to select the most appropriate troubleshooting action.

1. Selenium test failures can happen because of outdated locators, intermittent failures, or insufficient evidence. FlakeCop analyzes the failure and chooses among rerunning a test, suggesting a locator fix, quarantining a test, or preparing a bug report.

2. The project uses Strands Decider 2B for decision-making and a language model to explain the selected action. The decision is restricted to the selected tool to help keep the response consistent.

3. When the failure description does not provide enough evidence, FlakeCop selects the insufficient-evidence fallback instead of guessing. It asks for the full stack trace, test name, and whether the failure is intermittent or reproducible.

4. When a Selenium NoSuchElementException clearly identifies an outdated element ID, FlakeCop can select the locator-fix suggestion action and explain the recommended change.

5. FlakeCop also provides separate triage actions for rerunning a test, quarantining a test, and preparing a bug report. In this prototype, these actions are recorded in memory; they do not modify a real CI pipeline or test repository.

6. The automated test suite passes all 65 tests in the current local run. The demo illustrates both a low-evidence fallback and a high-confidence locator-fix decision.

7. FlakeCop demonstrates how Strands Decider 2B can turn test failure information into a structured triage decision, with a fallback when the available evidence is insufficient.