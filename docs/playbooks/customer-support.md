---
role: customer-support
last-reviewed: 2026-11-11
status: current
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
- Deadlines to put in the procedure (CRA 2022): cancellation refund within 14 days of the notice
  (s.117); digital content or service refund after a remedy within 14 days, by the same means,
  with no fee (s.68).
- A data request (access, correction, deletion) is recognised as one however it is phrased,
  logged with its date, and routed to the owner at once: the statutory clock starts on receipt.
- A suspected personal-data breach or exploited vulnerability goes to the owner and
  `legal-compliance` immediately; notification deadlines are counted in hours.
- Clocks: personal-data breach, 72 hours to the DPC (GDPR Art. 33). Actively exploited
  vulnerability or severe incident in a product made available commercially: 24-hour early
  warning and 72-hour notification through ENISA's Single Reporting Platform (CRA Art. 14, since
  11 Sep 2026); final report 14 days after a fix (vulnerability) or one month (incident). The
  owner decides and files; support records the time of first awareness.
- A released app made available commercially names who holds the CRA reporting-platform account
  before Release.
- Incident write-ups are blameless and dated: timeline, who was affected, what users were
  told and when, follow-up items in the backlog. The user message says what happened, what to
  do, and what changes, in plain words.
- A reply drafted by an agent is marked as a draft; if a reply is sent without a person
  editing it, it says it was written by an AI. A chat or auto-reply that converses with
  customers says it is an AI at the first message (AI Act Art. 50(1), (5)).
- A support chat run by a model says it is an AI at the start of every session (provider policy,
  e.g. Anthropic AUP 2026-11-12).
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
reporting guidance (ENISA); ENISA CRA Single Reporting Platform
(portal.cra-srp.enisa.europa.eu) and its FAQ; RFC 9116 (`security.txt`) and coordinated-disclosure practice;
incident-communication practice; store policies on support contact details.

## Change log
- 2026-11-10: seeded (baseline) with Foundry v6.
- 2026-11-11: client handover and warranty triage added with Foundry v9; baseline.
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-legal.md`, owner-accepted rows A-C2, A-C3, A-C4, B-C1, B-C2. P3 row A-C1 not applied.
