# AI use cases — proposal to validate with the client (Feedback V1 — P1.7)

The feedback asks that AI features be **actually useful in the operational
context** rather than generic. This document lists concrete, ops-connected use
cases to review **with the client before building further**. Nothing here should
be implemented until the client confirms the priority and the exact workflow.

Existing surface: `apps/api/services/email_agent_service.py` +
`apps/api/routers/email_agent.py` (the "Email Agent", Phase 3 in the README).
It already parses a participant email and proposes field updates for human
validation — a good template for the "AI proposes, human approves" pattern that
should apply to every use case below.

## Guiding principle

Every AI feature must:
1. Attach to a real step of the consolidation workflow (import → match →
   resolve → communicate).
2. **Propose, never auto-apply.** A human validates before any write, and the
   touched field is locked (same non-destructive contract as conflict
   resolution).
3. Be explainable — surface *why* it suggested something.

## Candidate use cases (to prioritize with the client)

| # | Use case | Attaches to | Value | Data needed | Notes |
|---|----------|-------------|-------|-------------|-------|
| A | **Import anomaly detection** — on file upload, flag rows that look wrong (malformed emails, impossible dates, a departure after return, a "Source" value leaking into a real field) before consolidation. | Import (Sources) | High — catches bad data at the door | Only the uploaded file; deterministic rules can cover most of it, AI only for fuzzy cases | Much of this is doable **without** an LLM (extends `exception_service`). Confirm whether AI is even required. |
| B | **Exception-resolution suggestions** — for each conflict/duplicate, propose which value to keep and why (e.g. "keep FCM email: more recent, matches PNR"). | Resolve (Exceptions) | High — speeds the main manual bottleneck | The two conflicting records + their sources | Fits the existing "propose + approve + lock" pattern directly. Likely the best first candidate. |
| C | **Email Agent (existing)** — extend natural-language parsing of participant emails to more field types (flight changes, room preferences), still human-validated. | Communicate | Medium — depends on real email volume | Inbound participant emails | Already built for dietary; confirm the client actually receives such emails and in what volume. |
| D | **Smart duplicate explanation** — when two participants are flagged as possible duplicates, generate a one-line rationale to help the PM decide. | Resolve | Medium | The candidate pair | Thin layer on top of existing duplicate detection. |

## Explicitly out of scope (avoid)

- Generic "chat with your data" assistants not tied to a workflow step.
- Any AI that writes to the master list without human approval.
- ML/training pipelines — the matching engine is deliberately deterministic and
  explainable (see `matcher.py`); keep it that way.

## Questions for the client

1. Which of A–D would save the PM team the most time today?
2. For the Email Agent (C): do participants actually email changes, and roughly
   how many per event? (Drives whether it's worth extending.)
3. Is a human-in-the-loop approval acceptable for all AI suggestions? (Assumed
   yes for RGPD and data-integrity reasons.)
4. Any hard constraint on where AI processing runs (EU-only, no third-party LLM
   on personal data)? This gates provider choice.

## Recommendation

Start with **B (exception-resolution suggestions)**: it targets the biggest
manual cost, reuses the existing propose/approve/lock flow, and needs no new
data source. Defer C/D until real email and duplicate volumes justify them.
Treat A as mostly a deterministic `exception_service` extension first, adding AI
only for the genuinely fuzzy cases.
