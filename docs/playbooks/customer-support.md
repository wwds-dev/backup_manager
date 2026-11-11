---
role: customer-support
last-reviewed: 2026-11-10
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
---

# Playbook: customer-support

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Support plan, FAQ, known issues, refund and complaint handling, feedback triage, incident
messages, and what happens after Release. The agent drafts; the owner replies and decides.

## Current practices
_Baseline: seeded from general practice on 2026-11-10; not yet verified by a radar run.
Statutory deadlines are read from the source each time._

- A released app above tier `internal` has a `SUPPORT.md`: where to ask, what to include, and a
  response target one person can keep. A target that was missed is changed or met, not left.
- A private route for security reports is published (`SECURITY.md` or a `security.txt`), and a
  report is acknowledged before it is fixed.
- Known issues are listed with the version they affect and the workaround; each is checked
  against the app before it is published and removed when fixed.
- Every piece of feedback ends as a backlog item or a recorded "won't do" with the reason.
  The user is quoted; names, emails and other personal data are removed first.
- Refund, withdrawal and complaint handling follow the procedure `legal-compliance` drafted
  and the owner signed off. Support never tells a customer what their legal rights are beyond
  quoting that procedure.
- A data request (access, correction, deletion) is recognised as one however it is phrased,
  logged with its date, and routed to the owner at once: the statutory clock starts on receipt.
- A suspected personal-data breach or exploited vulnerability goes to the owner and
  `legal-compliance` immediately; notification deadlines are counted in hours.
- Incident write-ups are blameless and dated: timeline, who was affected, what users were
  told and when, follow-up items in the backlog. The user message says what happened, what to
  do, and what changes, in plain words.
- A reply drafted by an agent is marked as a draft; if a reply is sent without a person
  editing it, it says it was written by an AI.
- Client handover _(baseline 2026-11-11, client-delivery mode: not yet verified by a radar run)_: at Release the handover checklist
  (`docs/foundry/tooling/handover_template.md`) is filled from the app's files and every item
  names its evidence or is marked not applicable with the reason. Credentials and accounts the
  client must own are transferred to the client's own accounts, never shared by sending
  values in a document or a chat; the checklist names them, it never contains them.
- The warranty covers what the accepted quote and the acceptance-and-warranty terms say, for
  the period they say, starting from the handover date. A report inside it is triaged as in
  warranty or as a change request, with the reason, before any work starts.
- Retiring an app: users are told ahead, with the date, how to export their data, and when it
  is deleted.

## Watch list
CCPC guidance on consumer remedies, refunds and complaints; Data Protection Commission guidance
on access requests and breach notification; Cyber Resilience Act vulnerability-handling and
reporting guidance (ENISA); RFC 9116 (`security.txt`) and coordinated-disclosure practice;
incident-communication practice; store policies on support contact details.

## Change log
- 2026-11-10: seeded (baseline) with Foundry v6.
- 2026-11-11: client handover and warranty triage added with Foundry v9; baseline.
