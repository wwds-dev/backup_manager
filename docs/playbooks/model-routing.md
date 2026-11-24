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
- **Which local model, if any: ask the advisor** (Foundry HQ: `tools/local_advise.py`, rules in
  `tools/local_rules.toml`, this machine in the private `local_profile.toml` from
  `tools/local_profile.py`). Verdicts: Recommended, Possible with notes or Not recommended, each with
  reasons from a fixed rule table: model + KV cache must fit the memory the GPU may use; speed is
  about bandwidth / bytes read per token until a 30-second benchmark measures it; the kind of work
  sets the smallest acceptable model, quantisation and context; work no rule names stays on a cloud
  model. The workspace shows the verdict next to each `@local` item.
- **Uncensored and abliterated models** get no quality bonus, rank below an equal plain model and
  carry a warning; they are never used for gate-like work. No routing exists to get round a
  model's safeguards. When a cloud model over-refuses code for the owner's own security tooling,
  the owner may tag that one TODO line `local:owner-ok`. That allows a local draft; the security
  review still runs as usual. No tool sets the tag.
- **Overnight queue** (HQ: `tools/local_queue.py`). It drafts the Recommended `@local` items in one
  batch through `local_model.py`. Drafts go to the HQ's private `local-drafts/<date>/`, never into
  an app or onto main, and `MORNING.md` is the review list. Each draft gets an automatic local
  check. A Haiku screen is opt-in and never runs for `client` apps. The owner's `mark` is recorded
  in `local_quality.jsonl`, and the advisor uses that record to learn which kinds of work local
  handles well. The steps are in `docs/local-models-guide.md`.
- **Cost saved** is shown against the cloud fallback for local work (`[cost]` in the rule table)
  at the list price in `dashboard/model_prices.json`. With no price it says "not recorded".
- **Count everything.** Local calls are counted at zero cost in `docs/foundry/model_use.jsonl`;
  paid eval runs are counted with their cost against the plan's `eval_budget_usd`; agent sessions
  are measured from Claude Code's transcripts by the Foundry workspace.
- **Effort** follows the same test: low for simple or conversational work, medium for normal
  work, high only where careful multi-step reasoning or checking pays.

## Recommending a switch to local (every session, every project)
When the work in hand fits local and a cloud model would cost more than it adds, the agent says so
**once, before starting**, in a short block the owner can act on. It does not start the local work
itself and does not switch models on its own.

Recommend local when all of these hold: the task is one module with clear inputs and outputs; tests,
ruff or a gate can check most of it; a wrong draft is caught by those checks; it is volume work
(tests, wrappers, exports, changelog and docstring drafts, triage), or a cloud model has refused the
owner's own security tooling (`local:owner-ok`). Do not recommend it for small or subtle changes (the
cloud model writes them in about the cost of a review), for gates and judgement, or when the owner
has already declined it in this chat.

Before recommending, run a **preflight** on this Mac (skip it only when the session cannot run
commands there, and say so):
1. `python3 tools/local_advise.py --live "<task>"`: the model that fits the GPU limit, and a `Live:`
   line for steps 2 and 3.
2. Free memory now (what `--live` reads): `memory_pressure | tail -3` and `vm_stat` (free + inactive +
   speculative pages x 16 KB). Heavy apps: `ps -Aco rss,comm | sort -rn | head -8`. The estimate is
   conservative: macOS can compress active memory, so a model may still load when it says short.
3. Decide, and say which in the block:
   - **Fits now:** recommend the model and context the advisor gives.
   - **Tight (free memory below model + KV cache + about 3 GB for macOS):** name the apps to close
     (browsers, Docker, other models loaded in LM Studio or Ollama), then re-check; or pick the
     smaller context or the smaller model.
   - **Does not fit even after closing apps:** do not recommend it interactively. Offer the
     overnight queue (`local_queue.py plan`, then `run`), logged as `@local` items in `TODO.md`, and
     carry on with other work on a cloud model meanwhile.
   - **Long or low-priority batch (several drafts, or a dense 27B at a few tokens per second):**
     prefer the overnight queue over waiting; the owner reviews `MORNING.md` next day.

The block always carries:
- **Why.** What a cloud model would cost for this task against a local draft plus the cloud review
  (the advisor's "cost saved" line, or an honest estimate marked as one); the risk (quality gap,
  what the checks will and will not catch, privacy gain); the duration (measured tokens per second
  from `local_profile.toml`; a dense 27B is several times slower than the 30B-A3B MoE).
- **How.** Which model (`tools/local_advise.py` names it), then: start LM Studio's server on
  loopback, load the model with the context the advisor gives (`lms load <model> --context-length
  <n>`), close heavy apps, and either paste the prepared prompt into Bionic or run
  `tools/local_queue.py` / `local_model.py`. Give the prompt ready to paste.
- **When to come back.** The draft goes through the task's checks first; then the cloud review the
  tier needs (Tier C: Opus audit of the changed parts). Return to a cloud model when the draft fails
  its checks twice, a reviewer would rewrite more than about a third of it, the model will not load
  within the GPU memory limit, or the work turns out to need judgement. Say so as soon as it is
  noticed, so the owner can step back up early.

Afterwards the agent records the result with `tools/local_queue.py mark` (pass or fail) so the
advisor learns which kinds of work local handles well here.

## One flow: now, tonight, or a draft in the queue
A piece of work that fits local gets **one** suggestion, before it is started, naming one of three
places. The agent picks the place; the owner says yes or no; a no is not repeated in that chat.

| Place | When | On the owner's yes |
|---|---|---|
| **Nightshift** (code changed in a worktree overnight, `docs/nightshift.md`) | It changes code; it is small (within the type's file cap, its files under 60% of the context); one module; tests name its files; it can wait until morning; nothing in its title is `[never]` | `tools/nightshift.py add` (below). Arming stays the owner's |
| **Local now** ("Recommending a switch to local" above) | It is wanted today and the preflight says it fits now | The owner switches; the agent prepares the prompt |
| **Draft queue** (`@local` in `TODO.md`, `tools/local_queue.py`) | A Markdown draft, not a code change (docs, triage, a test plan), or a batch too slow to wait for | The agent writes the `@local` line |

For Nightshift the suggestion carries the type (`rename`, `docs`, `logic`, `tests`), the files (allow
globs), the test commands, an estimate in minutes, and the verdict of
`python3 tools/nightshift.py fit --app <app> --type <t> --title "<title>" --allow <glob> --test "<cmd>"`
(run in the HQ; it reads files and git only, never memory, and loads nothing). Suggest only when it
says FITS or NEEDS OWNER_OK; say which and why. On the owner's yes in chat:
`python3 tools/nightshift.py add <the same arguments> --prompt-file <file> --estimate <min>
--words "<the owner's yes, quoted verbatim>"`. That writes the task file approved, with the words,
the date and `approved_via = "chat"` (owner's choice, 2026-11-24). `--draft` writes it unapproved when
the owner asks for that. `add` never sets `owner_ok` (sensitive work stays blocked until the owner sets
it by hand), never overwrites a task and never arms: arming is `nightshift.py arm`, run by the owner.
Do not suggest Nightshift for work already started, for a subtle change, or for a task whose type is
daytime only (`fit` says so).

## Watch list
The model and pricing pages of every provider the studio or an app uses (Anthropic, OpenAI,
Google, ElevenLabs, ...); LM Studio's release notes and docs (endpoints, defaults, auth); public
benchmark and arena leaderboards per kind of work (as a prompt, not a verdict); provider data-use
and retention terms for API traffic. _The radar source row for this playbook is not added yet:
left for the radar session's owner review (Foundry TODO)._ The local-model rule table has its own
row ("local models" in `radar/sources.md`).

## Change log
- 2026-11-11: seeded (baseline) with Foundry v9.
- 2026-11-24: "One flow" added (owner request): Nightshift as the third place, suggested once with the
  `fit` result and added with `nightshift.py add` on the owner's yes, which approves it (owner's choice).
- 2026-11-21: preflight steps 1–3 automated by `local_advise.py --live` (Fits now / Close these apps /
  Use the overnight queue; model + KV + runtime + `macos_reserve_gb` 3 GB in `local_rules.toml`).
- 2026-11-21: "Recommending a switch to local" added (owner request): the proactive, once-per-task
  recommendation with cost, risk, duration, how and when to return.
- 2026-11-17: local-model advisor, profile, overnight queue, quality record and cost-saved line
  (Foundry v12, owner-approved plan). The rule table carries its own review date.
