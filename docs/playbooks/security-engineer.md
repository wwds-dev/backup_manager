---
role: security-engineer
last-reviewed: 2026-11-11
status: current
---

# Playbook: security-engineer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Secrets, network surfaces, untrusted input, dependencies, packaging

## Current practices
Sources and dates are in `radar/reports/2026-10-12-security.md` and `2026-11-11-security.md`.

### Dependencies
- Every Secure phase and every release runs a dependency audit on the **installed** set, not on the
  manifest: `pip-audit` (or the OSV querybatch API, https://api.osv.dev/v1/querybatch, with
  name==version pairs read from the venv's `*.dist-info`) for each Python venv, including nested
  ones (`engine/.venv`, `agents/*/.venv`), and `npm audit --omit=dev` for each Node lockfile, with
  the full `npm audit` reported separately for build tooling. Audit every
  `lib/python3.*/site-packages` in a venv; a venv with more than one is rebuilt, not patched.
- An open CRITICAL or HIGH advisory in a runtime dependency blocks release unless the owner defers it
  in writing with a reachability note (which code path, which input, network-facing or not).
  A CRITICAL with a demonstrated path from network or untrusted-file input is P0: fix before any
  other work in that app.
- A dependency bump is not done until the venv (or `node_modules`) is resynced
  (`uv pip sync`/`uv pip install -r`, `npm ci`) and the audit re-run shows the fixed version
  installed. A launcher app that links the venv's interpreter is re-installed afterwards.
- Unpinned or ranged requirements are audited at the version actually installed, and the report
  says so. Secondary manifests (Dockerfiles, `cloud/requirements.txt`, vendored copies) are audited
  too and kept at or above the desktop pins.
- Tooling inside a venv (pip, setuptools) is kept current when the venv is rebuilt; advisories in
  it are reported but do not block release.

### Standards to review against
- Threat-model and audit against OWASP Top 10:2025 (A01-A10). Treat A03 Software Supply Chain
  Failures as covered by the dependency rules above, and A10 Mishandling of Exceptional Conditions
  as a required review question: does every error path fail closed and avoid leaking secrets or
  stack traces?
- Apps that call an LLM: review against the OWASP Top 10 for LLM Applications 2026 (the 2025 list,
  LLM01-LLM10, until the 2026 document has been read and its IDs recorded here). Apps whose agents
  call tools, run code, act on accounts or keep memory: also review against the OWASP Top 10 for
  Agentic Applications 2026 (ASI01 Agent Goal Hijack ... ASI10 Rogue Agents). Model output, fetched
  web content, files and images from outside are untrusted input; agent actions go through a guard
  that fails closed.

### Secrets
- Secrets live only in the macOS Keychain (via `keyring`, with explicit `--hidden-import` of its
  backends in frozen builds) or in an untracked `.env` outside any bundle; never in source,
  config committed to git, logs, URLs or test fixtures. Identity values (handles, chat IDs) come
  from git-ignored config.
- Every repo is pushed only through the gitleaks gate (staged changes and history). A finding
  blocks the repo until resolved; an allowlist entry needs a one-line reason, and
  `.gitleaks.toml`/`.gitleaksignore` changes are reviewed and pushed by hand. After any history
  rewrite, re-pin `.gitleaksignore` and re-run the history scan.
- A secret that reached git history is treated as leaked: rotate it first, then rewrite or retire
  the repo. Never publish a repo whose history held a live key.

### Packaging and distribution (macOS)
- Bundles meant for anyone else: sign every executable with a Developer ID certificate,
  `--options runtime --timestamp`, no `get-task-allow` entitlement, notarize with
  `xcrun notarytool`, staple with `xcrun stapler`, read the notary log, then check with
  `spctl --assess`. Local-only builds say "unsigned/ad-hoc, not notarized" in their release notes.
  Launcher bundles that run a checkout's venv are local-only by construction.
- A frozen app writes config and data to `~/Library/Application Support/<App>/`, never inside the
  bundle, and scrubs inherited `QT_*`, `DYLD_*`, `PYTHON*` variables before launching a child.

### Inputs for the radar
- The Stack section of `docs/foundry/app-context.md` lists every runtime dependency manager and
  lockfile (venv paths, `package-lock.json`, `uv.lock`, Dockerfiles), so the radar can audit what
  the app actually ships.

## Watch list
OWASP Top 10:2025; OWASP Top 10 for LLM Applications 2026 (record its IDs once read); OWASP Top 10
for Agentic Applications 2026 (ASI01-ASI10) and the OWASP Agent Control Standard; GitHub Advisory
Database and OSV for every installed dependency (fastest movers: pillow, pypdf, next,
react-server-dom-*, undici, urllib3, certifi); certifi/CA-store removals; Apple notarization and
Upcoming Requirements; gitleaks releases and rule changes; Qt/PySide6 security notes (bundled Qt is
not covered by OSV PyPI).

## Change log
- 2026-10-10: seeded (baseline).
- 2026-11-11: first review (current). Current practices and Watch list replaced from `radar/reports/2026-11-11-security.md` (findings #1-#9, consolidated block and watch list), accepted by the owner; #10 (sources) not applied.
