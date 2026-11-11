---
role: business-finance
last-reviewed: 2026-11-11
status: current
---

# Playbook: business-finance

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Business case, pricing, unit cost, build budget, quotes for client work, and the post-launch
review. The agent prepares figures; go/no-go is the owner's, tax is the owner's or an
accountant's.

## Current practices
_Baseline: seeded from general practice on 2026-11-10; not yet verified by a radar run. Tax
rules, thresholds and fee schedules are read from the source each time, with its date._

- No Define without a case for tiers `commercial` and `client`. The case names a payer and the
  evidence that they would pay (a conversation, a pre-order, a comparable product's price), or
  says there is none yet.
- Cost per unit is built from published price lists: model and API usage per typical session,
  payment-provider fee, store commission, hosting. A price that could not be found is
  "unknown" and blocks a margin claim; it is never entered as zero.
- The build has a budget in the case (owner hours and paid model usage), copied into
  `docs/foundry/plan.toml` once accepted so the Foundry workspace can compare it with the
  measured agent time and model use, and the review compares
  it with what was spent.
- Price is a decision with reasons: cost floor, what alternatives charge, what the payer said.
  A reduction shown against an earlier price: for goods, the prior price is the lowest price in
  the 30 days before the reduction (CCPC; S.I. of 2022 on product prices); for apps, digital
  content and services that rule does not apply, but a 'was' price must still be a real one, or
  it is a misleading practice.
- VAT and income tax are flagged, not decided: the case states the questions (registration
  thresholds, place of supply for digital services to consumers in other member states — Irish
  VAT only while EU cross-border B2C digital services plus distance sales of goods stay at or
  under €10,000 in the current and previous calendar year, then the customer's country's VAT
  through the One-Stop-Shop, whether a merchant of record would take that on) and the
  `## Sign-off` section records who answered them.
- Read the thresholds from Revenue each time (2026-10-27 page: €42,500 services, €85,000 goods);
  the case records turnover against them, and registration falls due within 30 days of the sale
  that crosses one.
- A client quote states scope, exclusions, fixed price or rate, payment schedule, acceptance
  criteria, how a change request is priced, the warranty period, and what the client must
  supply and by when. Nothing is promised that the spec does not contain.
- Client delivery _(baseline 2026-11-11, client-delivery mode: not yet verified by a radar run)_: the order (client, quote, invoices, acceptances, change
  requests, handover and warranty dates) lives in the Foundry HQ's private `orders/<id>.toml`;
  the app repo holds only the documents (`docs/engagement/`), because the repo may be handed to
  the client. The client accepts the quote and SOW in a way that can be shown later (a reply
  email, a signature, minutes of a meeting) and that evidence is the acceptance's reference.
- A change request after spec acceptance is priced like the quote: the scope difference, the
  hours and the rate behind the price difference, and the date effect. Small changes are not
  free by default; the owner may decide to waive a price, and that is recorded as their decision.
- Payment schedule for fixed-price work ties instalments to accepted milestones (for example a
  deposit at acceptance of the quote, the balance at acceptance of the delivery). A deposit is
  taken only once a signed contract and, where personal data is involved, a DPA exist.
- Invoices are records until the owner sends them: draft, sent, paid, each with its date. The
  invoice template's required particulars (VAT number and rate, or the reason none is charged,
  sequential number, supplier and customer details, date of supply) are checked against
  Revenue's current guidance before the first one is sent.
- Before the first paid order: business records separate from personal ones, an invoice
  template with the legally required particulars, and the owner's decision on professional
  indemnity and cyber insurance, each recorded with a date.
- The 30-day review reports every number in the case against a measured value and its source.
  "Not measured" is a finding for the next spec, not a blank.
- Copy and docs never state income, savings or return figures the owner cannot show.

## Watch list
Revenue (revenue.ie): VAT registration and rates, One-Stop-Shop, invoicing rules, sole-trader
and company obligations; Companies Registration Office; payment-provider, merchant-of-record
and app-store fee schedules and policy changes; EU VAT rule changes for digital services and
e-invoicing; CCPC guidance on price display and price reductions; model and API price lists
for every provider in `apps.md` stacks.

## Change log
- 2026-11-10: seeded (baseline) with Foundry v6.
- 2026-11-11: client-delivery practices added with Foundry v9 (order records, change-request
  pricing, milestone payments, invoice records); baseline.
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-legal.md`, owner-accepted rows B-B1, B-B2, B-B5. A-B1 superseded by B-B5; P3 rows (A-B2, B-B3, B-B4) not applied.
