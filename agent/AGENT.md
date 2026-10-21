# Use case

- **Pitch:** FlakeCop — a test-triage agent for Selenium + TestNG suites that reads a failure
  log and stack trace, uses Strands Decider 2B to pick the right action, and explains its
  reasoning through Amazon Bedrock.
- **Who it is for:** developers and CI teams who run Selenium + TestNG automated test suites and
  want instant, calibrated triage of every failure without reviewing each log by hand.
- **Features:**
  - paste any TestNG failure log and stack trace into chat;
  - Strands Decider 2B reads the failure context and picks the best tool: rerun, quarantine,
    bug report, or locator fix;
  - insufficient-evidence cases fall back to a safe recommendation instead of guessing;
  - Amazon Bedrock drafts the human-readable explanation and bug-report body;
  - a live decision panel in the demo UI shows the confidence and probabilities per tool;
  - deployed on Amazon Bedrock AgentCore Runtime.
- **The decision handed to Strands Decider 2B:** given a test failure log and stack trace,
  which of the four triage tools should handle it? (`#tool-selection`)
- **Why a decision model:** triage runs on every CI failure; it must be fast, cheap and
  return a typed answer with confidence the code can branch on.
- **Amazon Bedrock:** explanation prose and bug-report generation (Amazon Nova Pro by default).
