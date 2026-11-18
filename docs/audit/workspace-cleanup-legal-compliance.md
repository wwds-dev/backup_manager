# Legal check: workspace cleanup, slice 1 (Worktrees dialog)

Status: DRAFT (legal-compliance agent, not a lawyer), 2026-11-18. Phase: Comply for slice 1 of
`docs/specs/workspace-cleanup.md` (built in `e77a6f0`, tests `b716dca`). Tier `public`. Playbook
`last-reviewed: 2026-11-11`, `status: current`. The pack is in the private HQ (`docs/legal` link);
this file is the clearance report the Comply phase asks for. It does not sign anything and says
nothing about the pack as a whole beyond what the Worktrees feature touches.

## What the feature does (evidence)
- Lists git worktrees under the lab and, per row, offers removal only when all gates pass; removal
  is `git -C <repo> worktree remove -- <path>`, never `--force`, branch kept (`workspace.py`,
  spec sections 10-12; README `README.md:198-207`).
- Writes a restore record `worktree_records/<id>.json` (repo path, path, branch, HEAD, size, time,
  the `git worktree add` command) in the app-support folder: file mode 0600, folder 0700
  (`workspace.py:269-291`).
- Network: none. `grep -n "requests\|urllib\|socket\|urlopen\|http" workspace.py`, 2026-11-18: no
  hit; the only subprocess calls are local `git` and `lsof` (`workspace.py:13,39-43,91,115,194,249,299,329`).
- New dependencies: none (`requirements.txt` last changed in `d30c07a`, before this feature;
  `workspace.py` imports the standard library and `lab_health`).
- Models/AI: none (`app-context.md` `## Models used`: none).

## Regimes touched
| Regime | Touched? | Reasoning and evidence |
|---|---|---|
| GDPR / DPA 2018 | No new processing | The record holds repo and folder paths and a branch name on the user's own Mac, never sent anywhere. Branch and folder names are other agents' input, not personal data about identifiable persons as far as the code shows (a branch could name a person; not checked). No change to the data map in `privacy.md` beyond adding the record row (done). DPIA: not indicated. |
| ePrivacy | No | No cookies, no network. |
| Consumer / product liability | Unchanged (free, non-commercial) | Data loss from a deleting feature is the exposure; see finding F1. Row 9 of the register applies unchanged. |
| Licences | No change | No dependency added. `git` and `lsof` are run as the user's own system tools, not bundled. |
| Name / AI / CRA / EAA / DSA / gambling | No | No change from `register.md`. |
| Third-party terms | No | No Google/Dropbox call. |

## Findings
**No P0 or P1 from the legal side.**

- **F1 (P2): copy does not say that removal also deletes known git-ignored cache folders inside
  the worktree, and that "restore" recreates the checkout only.** The spec records it as a known
  limit (`docs/specs/workspace-cleanup.md` section 11: "`git worktree remove` ignores git-ignored
  caches, so those are deleted with the worktree"); the restore command is `git worktree add`
  (`workspace.py:276-281`), which does not bring back ignored files or caches. README line 198-207
  says "never forced" and "the branch stays" but not this. Who is exposed: the user (or the owner
  himself) who reads "restore record" as an undo. Fix: one sentence in the README, and the
  confirmation dialog if the engineer agrees; the `terms.md` disclaimer already says the tool "can
  delete or move files". Rule: a disclaimer describes the product and does not replace accurate
  copy (playbook, Terms). Not a legal opinion.
- **F2 (P3): the 14-day default is described in the README as a fact but the code keeps it as a
  constant, not a setting** (spec section 11, "not yet a setting"). Accuracy only; README says
  "untouched for 14 days", which matches the constant. No action unless it becomes a setting.
- **F3 (P3): restore-record names and the Worktrees list can reveal folder or branch names
  (including other people's) in a local file.** Local only, mode 0600 in a 0700 folder
  (`workspace.py:290-291`); no retention or pruning of records (privacy.md data map). Owner may want
  a prune rule; not a legal requirement on this evidence.
- **F4 (P3, process): `docs/foundry/app-context.md` Stack, Commands and Security surface are still
  the unfilled template** (spec section 12 (e)). The legal playbook reads `## Models used` and
  `## Distribution` only, which are filled in; flagging for the owner because other roles read the
  rest.

## Claims this feature adds to public copy
`README.md:198-207`: "offers one only when every gate passes", "never forced", "nothing is ticked",
"if `lsof` fails, nothing is offered". Supported by the spec's Verify log (196 tests, mutation
checks; `docs/specs/workspace-cleanup.md` sections 11-13) and by `claims.md` C10. Not re-run by this
agent; the QA agent had not re-run on the added tests (spec section 13). No new claim is made about
privacy or security.

## Lawyer triggers from this change
None. The open trigger in `register.md` (name) is unrelated to this feature.

## What the owner must decide
Nothing new for the legal pack from this feature. F1 is a copy change if he wants it. The pack
as a whole still needs the owner's licence decision and his sign-off (`register.md`).
