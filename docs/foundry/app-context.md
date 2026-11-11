# App context

The only app-specific file the Foundry agents read. Fill it in once; keep it short and
true. Agents treat the **Invariants** as hard rules.

## Product
<one paragraph: what it is, who it is for, what it must never claim or do>

## Distribution
tier: public

Status: tier confirmed by the owner on 2026-11-11 ("confirm all nine tiers"). An agent proposed it
the same day from the evidence below; raising it later goes through Comply first.

Evidence: the repo `wwds-dev/backup_manager` is public (checked 2026-11-11); it has no
`LICENSE`, no GitHub release, no download page and no store listing. Nobody pays and it takes no
payment. Personal data: the owner's own backup folder list and Google Drive / Dropbox OAuth
tokens (Keychain), nobody else's. `public` is proposed only because the source is published; if
nobody else is meant to use it, making the repo private and setting `internal` removes the
LICENSE, privacy note, name check and sign-off.

## Stack
<languages, frameworks, with versions; the radar reads this to know what to watch>

## Commands
- Install deps: `<cmd>`
- Run tests (list every mode that must pass): `<cmd>`
- Lint / types: `<cmd>`
- Build / package: `<cmd>`
- Release smoke test checklist: <launch, core action, quit, relaunch with state intact, ...>

## Docs and process files
<README, CHANGELOG, versioning doc, backlog file, user docs, UI entry points, design conventions>

## Architecture hot spots
<locks, threads, state files, module boundaries, nested repos, external providers>

## Security surface
<entry points, secrets and where they live, untrusted input paths, dependency manifests, packaging>

## Test bar
<coverage target, test layout, what counts as flaky>

## Invariants
<things agents must never do or imply, e.g. "no real money", "no network calls", copy rules>
- Start every background `QThread` with `start_thread()` (or `replace_worker()`) in `main.py`, never bare `.start()`: the keeper holds it until `finished`, so no owner (a tile deleted by refresh, a closed dialog) can destroy it mid-run. Never `QThread.terminate()`. Guarded by `tests/test_thread_lifetime.py`.

## Domain specialist
None. For a regulated or expert domain (money, insurance, health, law, ...), name the key
(`finance`, `insurance-compliance`, ...) and list: the domain, the rules and standards that apply
(with jurisdiction), what the reviewer must check, and the claims this app must never make.
`/new-app` and `/adopt-app` propose it; `install.sh --with domain-<key>` installs the reviewer.

## Optional roles installed
<model-validator? other?>
