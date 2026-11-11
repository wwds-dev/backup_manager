---
role: ux-designer
last-reviewed: 2026-11-11
status: current
---

# Playbook: ux-designer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Information hierarchy, plain language, states, accessibility

## Current practices
Sources and dates are in `radar/reports/2026-11-11-rest.md`; the rules in `AGENTS.md` and the agent prompt still apply.

- The accessibility bar is WCAG 2.2 level AA, applied to desktop apps by analogy: text contrast
  at least 4.5:1 (3:1 for large text), and 3:1 for focus rings, control borders, chart marks and
  state indicators against what they sit on (1.4.11). Every control is reachable and operable by
  keyboard with a visible focus that is never hidden behind another element (2.4.11); anything
  done by dragging has a click alternative (2.5.7); click targets are at least 24×24 px (2.5.8).
  Do not design to WCAG 3 or APCA until WCAG 3 is a Recommendation.
- Contrast is a test, not a review comment: each app with a theme has a test that computes the
  WCAG relative-luminance ratio for every text colour token against every background it is used
  on, and fails below 4.5:1 (3:1 for non-text indicators). `git_autosync/tests/test_header_fit.py`
  is the reference pattern.
- Every icon-only control and custom-painted widget sets `setAccessibleName` (and
  `setAccessibleDescription` where the name is not enough). A UX audit includes a five-minute
  VoiceOver pass (Cmd-F5) over each screen and lists what is unnamed or unreachable.

## Watch list
WCAG, platform HIG, UI-toolkit guidance, dark-mode and HiDPI practice

## Change log
- 2026-10-10: seeded (baseline).
- 2026-11-11: first radar review (current), from `radar/reports/2026-11-11-rest.md`, owner-accepted rows U1, U2, U4. P3 rows (U3, U5) not applied.
