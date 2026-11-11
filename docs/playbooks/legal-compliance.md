---
role: legal-compliance
last-reviewed: 2026-11-10
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
---

# Playbook: legal-compliance

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
The owner's duties as publisher and seller of software from Ireland into the EU: which regimes
apply, privacy and GDPR, terms and disclaimers, licences, name clearance, the EU AI Act, and
the contract pack for client work. The agent prepares and checks; the owner or a lawyer signs.

## Current practices
_Baseline: seeded from general practice on 2026-11-10; not yet verified by a radar run. Every
rule below is a prompt to check the primary source and cite it with a date, not a fact to copy.
Dates, thresholds and exemptions in particular must be read from the source each time._

**What each tier's pack holds**
- `internal`: `register.md` (regimes ruled out and why) and `licences.md`. No sign-off.
- `public`: plus a `LICENSE` file that states the licence the owner chose, third-party notices,
  `privacy.md` (even when the answer is "collects nothing": say so and show the grep) and
  `name.md`. The gate requires those four files. `terms.md` when the product needs disclaimers
  (advice-like, health, money, betting, safety), and `ai-act.md` whenever a model is involved,
  at any tier.
- `commercial`: plus `terms.md` always (terms of sale or licence, consumer information,
  withdrawal and refund wording, subscription renewal) and the full privacy pack.
- `client`: plus the contract pack in `docs/legal/client/` (services agreement, statement of
  work, data-processing agreement, acceptance and warranty terms, open-source and AI-use
  disclosure to the client).

**Register**
- One row per regime: applies / does not apply / unclear, the reason, the evidence (file:line or
  a command's output), the source and its date, and status `DRAFT` or `CHECKED (agent)`.
  "Unclear" on anything in the lawyer-trigger list becomes a `- [ ] LAWYER:` line.
- A lawyer trigger needs evidence from the app (file:line) that a feature plausibly falls in a
  listed category. Not having read the rule is not a reason to drop it and not, alone, a
  reason to raise it: record "rule not verified" beside the trigger or in the row.
- Each row also answers "does this turn on commercial activity?". Several regimes exclude free,
  non-monetised open source; the row says what would end that (a paid build, paid support,
  donations tied to the app), so a later change of tier or monetisation reopens it.
- Regimes to rule in or out for every app: GDPR and the Irish Data Protection Act 2018;
  ePrivacy rules (S.I. 336/2011: cookies and local storage, electronic direct marketing);
  Consumer Rights Act 2022 (digital content and services, pre-contract information, withdrawal,
  unfair terms); seller-identification duties for online services and for a registered business
  name; EU AI Act; Cyber Resilience Act; European Accessibility Act; Digital Services Act (only
  when the app hosts other people's content); product-liability rules for software; and any
  sector rule the domain specialist names.
- A disclaimer describes the product; it does not make a regulated activity unregulated. "Not
  financial advice" on something that behaves like advice is a lawyer trigger, not a fix.

**Licences**
- Inventory from the lockfile or installed set, not from memory; record tool and command.
- Copyleft and weak copyleft components get their obligations spelled out per build: for an
  LGPL library shipped inside a bundle (Qt / PySide6), the licence text and notices ship with
  the app, the library stays replaceable (separate shared libraries, not statically merged),
  and the app's own licence does not forbid that. GPL components in a bundle the owner wants to
  keep closed are a P0.
- Models, APIs, datasets, fonts, icons and stock or generated media are components too: record
  the terms on commercial use, attribution, redistribution, training on inputs, and who owns
  the output. An unofficial or scraped endpoint is recorded as such, with the provider's terms.
- A public repository with no `LICENSE` grants nobody any rights and tells nobody that: the
  owner chooses a licence (or "all rights reserved", stated) deliberately. This holds for every
  nested or companion repo the app needs to run; the parent's licence does not reach them.
- No licence tool installed: use the lockfile for what is declared and a listing of the built
  bundle for what ships. The bundle listing is what finds missing notices and components pulled
  in by plugins (a Qt module under a different licence than the rest of Qt, for example).

**Privacy**
- Data map first, notice second: what, whose, purpose, lawful basis, storage, retention,
  recipients. Every model or API provider that receives personal data is a recipient: record
  the data-processing terms and the transfer mechanism for providers outside the EEA.
- DPIA screening against the Data Protection Commission's list on every new data flow; a
  possible "yes" is a lawyer trigger until a DPIA is done.
- Local-only claims ("nothing leaves this Mac") are verified against the code's network calls
  and stated in the privacy note only as far as the evidence goes.
- A breach procedure names who decides and the notification deadline to the regulator; the
  agent never decides whether a breach is notifiable.

**Terms and consumer law**
- Selling to consumers: pre-contract information, the withdrawal right and the conditions
  under which digital content loses it, conformity and remedies, and price shown inclusive of
  tax. Terms cannot remove statutory rights; draft them not to try.
- The seller is identified wherever the app is offered: name or registered business name,
  geographic address, contact route.

**Name**
- Before a name is used in public: identical and similar marks in the EUIPO and Irish registers
  (software and software-services classes, plus the app's own field), the companies and business
  names register, domains, app stores and package registries. Record queries, dates and hits.
  Registers an agent cannot query are listed for the owner with the exact query and URL; the
  name is not cleared until those rows are filled in.
  A hit is a fact for the owner; whether it is a conflict is a lawyer's call.
- A working name is recorded as one, and blocks tier `public` and above until cleared.

**EU AI Act**
- State the role (provider or deployer) and the reasoning. Screen against prohibited practices
  and the high-risk list; anything arguable is a lawyer trigger.
- Transparency: a person talking to a model is told so; synthetic audio, image, video and text
  published as content is marked as the Act and its guidance require. Record the mechanism.
- Keep the upstream model provider's documentation and usage terms with the pack.

**Client work**
- The first services agreement, statement of work and data-processing agreement templates are a
  lawyer trigger once; later engagements reuse them and record only the deviations.
- Before any client data reaches a model provider, the contract says so and names the provider.
- Tell the client, in writing, that the software is built with AI assistance and lists its
  open-source components; who owns the result is stated in the contract, not assumed.

**Client contract pack** _(baseline 2026-11-11, client-delivery mode: not yet verified by a radar run)_
- Four templates in `docs/legal/client/`: services agreement (parties, scope by reference to
  the SOW, fees and payment, IP and licence of the result, confidentiality, liability cap,
  termination, governing law), SOW template, data-processing agreement (Art. 28 GDPR content:
  subject matter, duration, nature and purpose, data types, categories of data subjects,
  sub-processors including every model or API provider from app-context's `## Models used`),
  and acceptance-and-warranty terms (how specs, changes and the delivery are accepted, the
  acceptance period, what silence means, warranty scope and period). Each is DRAFT and each
  carries a `- [ ] LAWYER:` trigger on first use. Articles and section numbers are read from the
  primary source and cited with a date.
- `## Models used` is the processor list's starting point: each provider that receives client
  or personal data is named in the DPA before that data reaches it; a local model is not a
  recipient as far as the code shows nothing leaves the machine.

**Wording**
- Documents are `DRAFT` or `CHECKED (agent)` until a person signs. The agent never writes
  "compliant", "approved", "legally reviewed" or "GDPR-ready", and flags any copy that does
  beyond what a signed-off document supports.

## Watch list
Data Protection Commission (dataprotection.ie) and EDPB guidelines; Competition and Consumer
Protection Commission (ccpc.ie); EUR-Lex and the Commission's AI Act and Cyber Resilience Act
pages (dates, delegated acts, guidance, codes of practice); Irish Statute Book and the
Oireachtas for transposing acts; EUIPO and TMview; Intellectual Property Office of Ireland;
Companies Registration Office; SPDX and OSI licence lists; Qt and PySide licensing pages; the
terms of every model and API provider in `apps.md` stacks.

## Change log
- 2026-11-10: seeded (baseline) with Foundry v6.
- 2026-11-11: client contract pack (four templates, first-use lawyer trigger) and the `## Models used`
  processor rule added with Foundry v9; baseline.
- 2026-11-10: per-tier file list, trigger evidence rule, commercial-activity column, nested-repo and bundle-listing licence checks and owner-run name searches added from the first pilot audit (`audits/sonar/legal.md`); still baseline.
