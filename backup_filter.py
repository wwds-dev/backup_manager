"""The rsync filter for the Google Drive copy, shared by every path that sends files there.

The scheduled backup (`_Admin/backup/backup_to_gdrive.sh`) is the source of truth: its
`RSYNC_OPTS` let `*.example`, `*.sample` and `*.template` through first, then exclude
`gdrive_backup_excludes.txt` (junk) and `secret_name_patterns.txt` (secrets, which go to
the Proton vault instead). The app's one-folder "Back up now" and the Excludes
"Preview matches" read the filter from that script through `rsync_filter_args()`, and
fail closed: if the secret list is missing or empty, or the script's filter is not the
one this module expects, nothing is sent (readiness audit B1).

Qt-free; matching reads file names only, never file contents.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

KEEP_INCLUDES = ("*.example", "*.sample", "*.template")
EXCLUDES_NAME = "gdrive_backup_excludes.txt"
SECRETS_NAME = "secret_name_patterns.txt"
SCRIPT_NAME = "backup_to_gdrive.sh"


class FilterError(RuntimeError):
    """The secret-safe filter could not be built; do not run rsync."""


def expected_filter_args(backup_dir: Path) -> list[str]:
    """The include/exclude arguments, in rsync's first-match order."""
    return ([f"--include={p}" for p in KEEP_INCLUDES]
            + [f"--exclude-from={backup_dir / EXCLUDES_NAME}",
               f"--exclude-from={backup_dir / SECRETS_NAME}"])


def read_patterns(path: Path) -> list[str]:
    """Pattern lines of an rsync exclude file (blank, '#' and ';' lines dropped)."""
    return read_patterns_text(path.read_text())


def read_patterns_text(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith(("#", ";")):
            out.append(line)
    return out


def script_filter_args(script: Path, backup_dir: Path) -> list[str]:
    """The `--include=` / `--exclude-from=` arguments of the script's RSYNC_OPTS, in order,
    with `$SCRIPT_DIR` and `$EXCLUDES` resolved. Raises FilterError if it cannot tell."""
    try:
        text = script.read_text()
    except OSError as e:
        raise FilterError(f"cannot read {script.name}: {e}") from e
    m = re.search(r"^RSYNC_OPTS=\($(.*?)^\)", text, re.M | re.S)
    if not m:
        raise FilterError(f"no RSYNC_OPTS block in {script.name}")
    variables = {"SCRIPT_DIR": str(backup_dir)}
    em = re.search(r"^EXCLUDES=(.+)$", text, re.M)
    if em:
        variables["EXCLUDES"] = _expand(shlex.split(em.group(1), comments=True)[0], variables)
    args = []
    for line in m.group(1).splitlines():
        for tok in shlex.split(line, comments=True):
            if tok.startswith(("--include", "--exclude", "--filter", "-f")):
                args.append(_expand(tok, variables))
    return args


def _expand(token: str, variables: dict) -> str:
    def sub(mm):
        name = mm.group(1) or mm.group(2)
        if name not in variables:
            raise FilterError(f"unknown variable ${name} in the backup script's filter")
        return variables[name]
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", sub, token)


def rsync_filter_args(backup_dir: Path) -> list[str]:
    """The filter for any rsync to Google Drive. Raises FilterError instead of
    returning a filter that could let a secret-named file through."""
    secrets = backup_dir / SECRETS_NAME
    try:
        if not read_patterns(secrets):
            raise FilterError(f"{SECRETS_NAME} has no patterns")
    except OSError as e:
        raise FilterError(f"cannot read {SECRETS_NAME}: {e}") from e
    if not (backup_dir / EXCLUDES_NAME).is_file():
        raise FilterError(f"{EXCLUDES_NAME} is missing")
    expected = expected_filter_args(backup_dir)
    actual = script_filter_args(backup_dir / SCRIPT_NAME, backup_dir)
    if actual != expected:
        raise FilterError(
            f"{SCRIPT_NAME} filters differently from this app; update backup_filter.py "
            f"before using the one-folder backup.\n  script: {actual}\n  app:    {expected}")
    return expected


# ----------------------------------------------------------------------------
# Preview: which names the filter keeps out, without running rsync.
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    pattern: str
    include: bool
    secret: bool = False

    def matches(self, rel: str, is_dir: bool) -> bool:
        pat = self.pattern
        if pat.endswith("/"):
            if not is_dir:
                return False
            pat = pat.rstrip("/")
        if pat.startswith("/"):
            return fnmatch.fnmatchcase(rel, pat[1:])
        if "/" in pat:
            parts = rel.split("/")
            depth = pat.count("/") + 1
            return any(fnmatch.fnmatchcase("/".join(parts[i:]), pat)
                       for i in range(max(0, len(parts) - depth), len(parts)))
        return fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], pat)


def preview_rules(exclude_patterns: list[str], secret_patterns: list[str]) -> list[Rule]:
    """Rules in the order rsync applies them: keep-includes, junk excludes, secrets."""
    rules = [Rule(p, include=True) for p in KEEP_INCLUDES]
    for p in exclude_patterns:
        if p.startswith("+ "):
            rules.append(Rule(p[2:].strip(), include=True))
        else:
            rules.append(Rule(p[2:].strip() if p.startswith("- ") else p, include=False))
    rules += [Rule(p, include=False, secret=True) for p in secret_patterns]
    return rules


def first_match(rules: list[Rule], rel: str, is_dir: bool) -> Rule | None:
    for r in rules:
        if r.matches(rel, is_dir):
            return r
    return None


def excluded_paths(root: Path, rules: list[Rule], max_depth: int = 6,
                   limit: int = 200, max_entries: int = 50_000) -> list[tuple[str, bool]]:
    """(relative path, is_secret) for each name the rules keep out under root.

    Like rsync, an excluded folder is listed once and not walked into. Stops after
    `limit` matches or `max_entries` names looked at.
    """
    out: list[tuple[str, bool]] = []
    seen = 0
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir
        depth = 0 if not rel_dir else rel_dir.count(os.sep) + 1
        keep_dirs = []
        for names, is_dir in ((sorted(dirnames), True), (sorted(filenames), False)):
            for name in names:
                seen += 1
                rel = f"{rel_dir}/{name}" if rel_dir else name
                rule = first_match(rules, rel, is_dir)
                if rule is not None and not rule.include:
                    out.append((rel + ("/" if is_dir else ""), rule.secret))
                    if len(out) >= limit:
                        return out
                elif is_dir and depth + 1 < max_depth:
                    keep_dirs.append(name)
                if seen >= max_entries:
                    return out
        dirnames[:] = keep_dirs
    return out
