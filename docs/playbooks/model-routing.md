---
role: model-routing
last-reviewed: 2026-11-11
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
---

# Playbook: model routing

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval. Read by the orchestrator when it
hands work to an agent or a local model, by `qa-engineer` for live evals, and by
`business-finance` when it budgets model use.

## Scope
Which model does which kind of work in the development process (the studio's own agents and
local model), and which model an app's live eval suite runs on. It does not choose the models an
app ships with: that is a product decision in the spec, recorded in app-context's `## Models used`.

## The rule
**The cheapest model within reach of the best for that kind of work.** Within reach means a
result a reviewer would not tell apart for this task, judged on the kind of work, not on the
newest release. A bigger model is used only where it buys a noticeably better result, and a
missed result is expensive (a gate, a hard bug, a long-lived decision).

## Current practices
_Baseline: seeded 2026-11-11 with Foundry v9; not yet verified by a radar run. Model names and
prices change: read them from the provider's own model and pricing pages at the time of use,
with the date, and never write a price from memory. A missing or zero price is unknown, never
free._

| Kind of work | Default | Never |
|---|---|---|
| Mechanical drafts a gate checks anyway: changelog and docstring drafts, test scaffolds, fixtures, renames, formatting | local model (`local_model.py`), else Haiku | |
| Material with client or personal data that must not leave the machine: summaries, redaction, classification | local model only; if it is not good enough, the owner decides | any cloud model without a DPA naming it |
| Cheap first passes a stronger model or a person reviews next: triage, a first outline, search over the repo | local model or Haiku | |
| Everyday engineering: normal fixes, tests, docs, copy, QA plans | Sonnet | local |
| Gates and judgement: code review, QA verdicts, security and legal findings, architecture and ADRs, the business case | Sonnet; Opus for hard or wide-reaching changes | local; Haiku |
| Hard, clearly scoped work: tricky debugging, complex features, an audit's fix list | Opus | local |
| Rare high-stakes reasoning where a miss is expensive: a full readiness audit, a bug Opus failed on twice, a long-lived architecture decision | Fable for one focused pass, then back to Opus or Sonnet | |
| An app's live eval suite (qa-engineer) | the cheapest model the app's own spec accepts for that task; local when the app runs locally | a bigger model than the app uses in production |

- **Security-heavy and model-research work** (VPN, proxy, anonymity tooling; agent and model
  internals): Opus at high effort is the usual ceiling; providers' stronger models may carry
  extra safeguards there. Say so instead of escalating.
- **A local model drafts, never decides.** Its output is accepted only after the same checks as
  any other work; the backlog item carries `@local`. Nothing a person signs is drafted locally
  without the person reading it.
- **Local fails closed.** When the local server is off, the work waits or the owner chooses a
  cloud model; `local_model.py` never falls back by itself, and client or personal data never
  falls back at all.
- **Count everything.** Local calls are counted at zero cost in `docs/foundry/model_use.jsonl`;
  paid eval runs are counted with their cost against the plan's `eval_budget_usd`; agent sessions
  are measured from Claude Code's transcripts by the Foundry workspace.
- **Effort** follows the same test: low for simple or conversational work, medium for normal
  work, high only where careful multi-step reasoning or checking pays.

## Watch list
The model and pricing pages of every provider the studio or an app uses (Anthropic, OpenAI,
Google, ElevenLabs, ...); LM Studio's release notes and docs (endpoints, defaults, auth); public
benchmark and arena leaderboards per kind of work (as a prompt, not a verdict); provider data-use
and retention terms for API traffic. _The radar source row for this playbook is not added yet:
left for the radar session's owner review (Foundry TODO)._

## Change log
- 2026-11-11: seeded (baseline) with Foundry v9.
