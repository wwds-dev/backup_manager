# App context

The only app-specific file the company agents read. Fill it in once; keep it short and
true. Agents treat the **Invariants** as hard rules.

## Product
<one paragraph: what it is, who it is for, what it must never claim or do>

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

## Domain specialist
None. For a regulated or expert domain (money, insurance, health, law, ...), name the key
(`finance`, `insurance-compliance`, ...) and list: the domain, the rules and standards that apply
(with jurisdiction), what the reviewer must check, and the claims this app must never make.
`/new-app` and `/adopt-app` propose it; `install.sh --with domain-<key>` installs the reviewer.

## Optional roles installed
<model-validator? other?>
