---
role: legal-compliance
last-reviewed: 2026-11-11
status: current
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
  non-monetised open source; the row says what would end that (a paid build; support charged
  above cost recovery; monetising through another service; requiring personal data beyond what
  security, compatibility or interoperability need; donations above design, development and
  provision costs — CRA recitals 15-18), so a later change of tier or monetisation reopens it.
- Regimes to rule in or out for every app: GDPR and the Irish Data Protection Act 2018;
  ePrivacy rules (S.I. 336/2011: cookies and local storage, electronic direct marketing);
  Consumer Rights Act 2022 (Part 3 digital content and digital services, including free ones
  paid for with personal data; Part 5 information and cancellation; Part 6 unfair terms; in force
  29 Nov 2022, S.I. 596/2022); seller-identification duties for online services and for a registered business
  name; EU AI Act; Cyber Resilience Act; European Accessibility Act; Digital Services Act (only
  when the app hosts other people's content); product-liability rules for software; and any
  sector rule the domain specialist names.
- CRA (Reg. 2024/2847): applies from 11 Dec 2027; reporting of actively exploited
  vulnerabilities and severe incidents (Art. 14) since 11 Sep 2026.
- Product Liability Directive (EU) 2024/2853: software is a product; FOSS developed or supplied
  outside a commercial activity is excluded (Art. 2(2)); applies to products placed on the
  market after 9 Dec 2026 (transposition deadline the same day; check the Irish transposing act).
- EAA (Dir. 2019/882): services to consumers from 28 June 2025, incl. e-commerce and e-books with
  their dedicated software. A microenterprise (<10 staff and turnover or balance sheet ≤ €2m) is
  exempt for services, not for products. A client who is a microenterprise is exempt; the owner
  building the site is not the service provider.
- Gambling (Ireland): the Gambling Regulation Act 2024 licenses providing betting (bookmaker,
  remote betting intermediary, taking bets: s.3) and, once s.70 is commenced, *selling or
  supplying* a gambling product (software used in connection with gambling) or a gambling related
  service (any service in the course of business relating to a gambling activity) without a
  Business-to-Business licence. A tool that prices bets or sizes stakes but takes none is outside
  s.3; whether a *paid* version is a gambling product or related service under s.70 is a lawyer
  trigger. Check the commencement table (irishstatutebook.ie/eli/isbc/2024_35.html) at every
  audit; on 2026-11-11 ss.70-72 and 143-151 were not commenced.
- A disclaimer describes the product; it does not make a regulated activity unregulated. "Not
  financial advice" on something that behaves like advice is a lawyer trigger, not a fix.

**Licences**
- Inventory from the lockfile or installed set, not from memory; record tool and command.
- Copyleft and weak copyleft components get their obligations spelled out per build. For an
  LGPL-3.0 library shipped inside a bundle (Qt / PySide6, FFmpeg's LGPL builds): ship the LGPL
  **and** GPL texts and a prominent notice that the library is used; put the library's copyright
  notice in any About box; keep it dynamically linked and replaceable; provide the library's
  corresponding source (for the exact version shipped, even unmodified) with the app or a
  written offer for it; and make sure the app's licence or terms do not forbid modifying the
  library or reverse engineering to debug such modifications (LGPL-3.0 §4; qt.io 'Obligations
  of the GPL and LGPL'). GPL components in a bundle the owner wants to keep closed are a P0.
  Qt modules that are GPL-only for open-source users are listed on doc.qt.io/qt-6/licensing.html
  for the version in the bundle (Qt 6.12, read 2026-11-11: Canvas Painter, CoAP, Graphs, GRPC,
  HTTP Server, Lottie, MQTT, Network Authorization, Qml Compiler, Quick 3D (+Physics), Quick
  Timeline, Virtual Keyboard, Wayland Compositor). Check the bundle listing against that list on
  every Qt upgrade; plugins pull some in unasked (Virtual Keyboard via `platforminputcontexts`).
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
- DPIA screening on every new data flow, written down: Art. 35(3) cases, then the DPC's
  Art. 35(4) list (10 types; for these apps chiefly profiling of children or vulnerable people
  for marketing, algorithmic decisions on access to services, tracking behaviour or location,
  large-scale profiling, indirectly sourced data, combined datasets), then the WP248 criteria
  (two or more usually means a DPIA). Record why a DPIA is or is not needed; a possible 'yes' is
  a lawyer trigger until a DPIA is done.
- For a US provider, record whether it is certified under the EU-US Data Privacy Framework
  (Decision (EU) 2023/1795, Art. 45) or relies on SCCs (Art. 46). The DPF is under appeal
  (C-703/25 P); a ruling against it would leave SCCs as the fallback, so keep the provider's DPA
  with SCCs on file.
- Local-only claims ("nothing leaves this Mac") are verified against the code's network calls
  and stated in the privacy note only as far as the evidence goes.
- A breach procedure names who decides and the notification deadline to the regulator; the
  agent never decides whether a breach is notifiable.

**Terms and consumer law**
- Selling to consumers: pre-contract information; the 14-day cancellation right (CRA 2022
  ss.112-113) and when it is lost — paid digital content only with prior express consent, an
  acknowledgement of loss and confirmation on a durable medium (s.111(e), s.109(3)); a digital
  service only once fully supplied (s.111(c)); missing cancellation information extends the
  period up to 12 months (s.114); refunds within 14 days (s.117); conformity, updates and
  remedies (Part 3); price shown inclusive of tax. Terms cannot remove statutory rights; draft
  them not to try.
- The seller is identified wherever the app is offered (S.I. 68/2003 reg. 7): name (and
  registered business name), geographic address, an email address, the register and number of
  any public register the seller is on (company or business-name register), the VAT number once
  registered, and any authorisation or professional body. Prices say whether they include tax
  and delivery.
- A sole trader selling under any name other than their own surname registers it with the CRO
  within one month of adopting it (RBNA 1963 ss.3, 6), and then puts their true name on business
  letters, circulars and catalogues carrying that name (s.18). Check the Act as amended before
  relying on s.18's wording.
- Paid apps sold to consumers: terms say whether and why the app may change; a change beyond
  keeping it working is announced in advance on a durable medium and, if it makes the app worse
  to use, lets the buyer terminate free of charge (CRA 2022 s.64). Security and conformity
  updates promised in the contract are supplied.

**Name**
- Before a name is used in public: identical and similar marks in the EUIPO and Irish registers
  (software and software-services classes, plus the app's own field), the companies and business
  names register, domains, app stores and package registries. Record queries, dates and hits.
  Registers an agent cannot query are listed for the owner with the exact query and URL; the
  name is not cleared until those rows are filled in.
  A hit is a fact for the owner; whether it is a conflict is a lawyer's call.
- A working name is recorded as one, and blocks tier `public` and above until cleared.

**EU AI Act**
- Cite the AI Act as 'Reg. (EU) 2024/1689 as amended by Reg. (EU) 2026/1744' and read the
  consolidated text on EUR-Lex (CELEX 02024R1689-<latest date>), not the 2024 original: articles
  4, 5, 6, 50(7), 111 and 113 were changed in 2026.
- State the role (provider or deployer) and the reasoning. Free of charge still counts
  (Art. 3(3)). A natural person using the app for purely personal, non-professional purposes has
  no deployer duties (Art. 2(10)); the owner using his own app for his business is a deployer.
  Screen against prohibited practices and the high-risk list; anything arguable is a lawyer
  trigger.
- From 2 Dec 2026 (Art. 5(1)(ba), (bb), (1a)): a system that can generate realistic intimate or
  sexually explicit imagery, video or audio of an identifiable person without explicit consent,
  or child sexual abuse material, is prohibited if that output is reasonably foreseeable and
  reproducible and the system lacks adequate technical safeguards. For any app that generates
  images, video or voice, record the safeguards (provider content filters kept on, prompt
  refusals, no face or likeness upload without consent) with file:line, and treat a gap as a
  lawyer trigger.
- A free and open-source licence exempts an AI system from the Act except for Art. 5
  (prohibited), high-risk systems, and Art. 50 (Art. 2(12)). An open-source generative app still
  owes Art. 50.
- Transparency (Art. 50, applies from 2 Aug 2026). Provider duties: 50(1) people interacting
  directly with the system are told it is AI unless obvious; 50(2) every synthetic audio, image,
  video or text output of the system is marked in a machine-readable, detectable way (exception:
  assistive standard editing, or output that does not substantially alter the input). Deployer
  duties: 50(4) disclose deep fakes (for evidently artistic, creative, satirical or fictional
  work, in a way that does not hamper it), and disclose AI-generated text published to inform
  the public on matters of public interest unless a person reviewed it and holds editorial
  responsibility. 50(5): give the information clearly at the first interaction or exposure.
  Record the marking mechanism per output type (metadata field, C2PA manifest, provider
  watermark kept on) and test that the app does not strip it.
- Art. 111(4) gives providers of systems already on the market before 2 Aug 2026 until 2 Dec
  2026 to meet Art. 50(2); a system first placed on the market on or after 2 Aug 2026 has no
  grace. Art. 50(1) and 50(4) are not deferred.
- Read the Commission's Guidelines on transparency obligations (20 July 2026) and the Code of
  Practice on transparency of AI-generated content (final 10 June 2026) before choosing a
  marking mechanism; record which measures of the code the app follows.
- Keep the upstream model provider's documentation and usage terms with the pack.
- Model-provider terms: read each provider's usage policy at every audit and record its
  effective date. Anthropic's (effective 2026-11-12) requires, for a personalised
  buy/sell/hold recommendation on specific securities or digital assets, review by a qualified
  person before delivery and telling the person AI was used; and an AI-disclosure at the start
  of every consumer-facing chat. OpenAI's (effective 2026-11-20) prohibits 'real money
  gambling' and tools giving 'tailored advice that requires a license' without a licensed
  professional. A feature that falls under one of these is a finding, even when the law does
  not reach it.

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
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-legal.md`, owner-accepted rows A-L1, A-L2, A-L3, A-L4, A-L5, A-L6, A-L9, A-L10, A-L11, A-L12, A-L13, A-L14, A-L17, B-L1, B-L3, B-L4, B-L5, B-L6, B-L7, B-L8, B-L9, B-L10. P3 rows (A-L7, A-L8, A-L15, A-L16, A-L18, B-L11) not applied.
