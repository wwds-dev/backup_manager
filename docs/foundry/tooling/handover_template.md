# Handover: <app> for <client>

DRAFT: for the owner to review and hand over. Copied from Foundry's
`docs/foundry/tooling/handover_template.md` at Release (tier `client`). Each item names its
evidence (a file, a command and its output, a link). Tick it (`- [x]`) only with that evidence
beside it; mark one that does not apply `- [~] n/a: <reason>`. `order.py gate <id> done` in the
Foundry HQ fails while any `- [ ]` is left. Never write a password, key or token in this file:
name the credential and where the client now holds it.

Order: <id> · Release: <version> · Handover date: <date, as recorded with order.py handover>

## Source and licences
- [ ] Source repository transferred or access granted to the client's own account: <how, when>
- [ ] The app's own licence or ownership terms as the contract states them: <LICENSE / contract clause>
- [ ] Third-party components and their licences, with obligations met: <docs/legal/licences.md, date>
- [ ] Models, APIs, datasets, fonts and media and their terms: <docs/legal/licences.md, app-context ## Models used>

## Credentials and accounts the client must own
- [ ] Each account and credential listed by name, with the client's account that now holds it
      (domain, hosting, store, payment provider, model and API keys, email sender, analytics): <list>
- [ ] Studio access removed or agreed to stay, per account: <list>

## Deployment and operation
- [ ] Where it runs and how it is deployed, step by step: <docs/RUNBOOK.md or equivalent>
- [ ] Backups and restore, tested once: <command, date, result>
- [ ] Monitoring and alerts, and who receives them: <...>
- [ ] Running costs the client pays from now on (hosting, model and API use), with source and date: <...>

## Data and AI disclosures
- [ ] Personal data processed, where, for how long, and the signed DPA: <docs/legal/privacy.md, docs/legal/client/dpa.md>
- [ ] Sub-processors, including every model or API provider: <app-context ## Models used>
- [ ] That the software was built with AI assistance, and which AI features the app itself has
      (what the user is told, how output is marked): <docs/legal/ai-act.md>

## Support and warranty
- [ ] Support contact, channel and response target: <SUPPORT.md or the contract>
- [ ] What the warranty covers (defects against the accepted specs) and what it does not
      (new features, third-party outages, changes made by others): <acceptance-warranty terms, quote>
- [ ] Warranty period and end date: <from the quote; recorded with order.py handover>
- [ ] How to report a defect, and how one outside the warranty is priced (change request): <...>

## Acceptance
- [ ] Acceptance criteria from each accepted spec, checked against this release: <spec, evidence per criterion>
- [ ] The client's acceptance of the delivery, recorded in the HQ (order.py accept <id> delivery): <reference>
