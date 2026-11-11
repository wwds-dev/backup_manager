---
role: business-finance
last-reviewed: 2026-11-10
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
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
  A reduction shown against an earlier price uses the lowest price of the preceding period the
  law names, not an invented "was" price.
- VAT and income tax are flagged, not decided: the case states the questions (registration
  thresholds, place of supply for digital services to consumers in other member states, the
  One-Stop-Shop, whether a merchant of record would take that on) and the `## Sign-off` section
  records who answered them.
- A client quote states scope, exclusions, fixed price or rate, payment schedule, acceptance
  criteria, how a change request is priced, the warranty period, and what the client must
  supply and by when. Nothing is promised that the spec does not contain.
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
