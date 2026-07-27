# MANAS — Agent Rules (Layer 10)

## AGENT DEFINITION SCHEMA
Every agent MUST declare (enforced by the kernel at registration):
- name            unique, lowercase, e.g. "planner"
- purpose         one sentence
- inputs          typed schema of what it accepts
- outputs         typed schema of what it returns
- tools           explicit allowlist (empty = no tool access)
- memory_scopes   which tiers it may read/write (least privilege)
- risk_level      SAFE | REVIEW | APPROVAL
- escalation      when to hand off to another agent or the human

## CORE AGENT ROSTER (Phase 1 → Phase N)
Phase 1: orchestrator, planner, researcher, coder, critic
Phase 2: memory-curator, qa, docs, devops
Phase 3: vision, voice, meeting, email, calendar
Phase N: robotics, learning (self-improvement loop)

## COLLABORATION PROTOCOL
- Agents communicate ONLY through the kernel event bus (typed messages).
  No agent imports another agent directly.
- The orchestrator owns the task graph; workers own single tasks.
- Critic reviews every REVIEW/APPROVAL-level output before it reaches the user.
- Any agent may return NEED_HUMAN with a specific question; never guess on
  irreversible actions.

## FAILURE RULES
- Retries: max 2, with changed strategy (never identical retry).
- On repeated failure: summarize what was tried, why it failed, and escalate.
- Partial results are returned as partial, clearly labeled — never silently
  presented as complete.
