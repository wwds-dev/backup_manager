---
role: product-manager
last-reviewed: 2026-10-14
status: current
---

# Playbook: product-manager

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Specs, prioritisation, success measures, honest-copy rules

## Current practices
- A spec for any feature that publishes AI-generated or AI-altered content, or lets a third party converse with a model, states how it meets EU AI Act Art. 50: disclosure to the person, and machine-readable marking of synthetic audio, image and video (due 2026-12-02 for systems already on the market). If it is out of scope, the spec says why.
- A spec that makes an app commercially available in the EU (sale, subscription, paid download) lists its CRA duties: since 2026-09-11, actively exploited vulnerabilities and severe incidents are reported (24 h / 72 h / 14 d); full obligations apply from 2027-12-11.

- Client specs _(baseline 2026-11-11, client-delivery mode: not yet verified by a radar run)_: a spec for a `client` app is what the client accepts. Its
  acceptance criteria are checkable by the client without reading code. Design and Architecture
  sections are the studio's and are left out of the client's acceptance. After acceptance, a
  change goes through a change request with its price and date effect before the spec is edited.

## Watch list
product discovery practice, prioritisation frameworks, store/regulatory guidelines relevant to the app's domain

## Change log
- 2026-10-10: seeded (baseline).
- 2026-11-11: client-spec practice added with Foundry v9 (baseline, not radar-verified).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-build.md` (owner accepted all proposed edits).
