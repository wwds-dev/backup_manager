# Support

Backup Control Center is a macOS app that monitors cloud storage and manages one rsync backup into Google Drive, maintained by one person in their own time. There is no paid
support and no guaranteed response time.

## Where to ask

| You want | Go to |
|---|---|
| Help running it, or a question about how it works | the README first, then a [GitHub issue](https://github.com/wwds-dev/backup_manager/issues) |
| To report a bug | a GitHub issue with the version in the window title, your macOS version, what you did, what you expected and what happened. Do not paste OAuth tokens, `tokens.json`, the Key/Secret from a provider's console, file or folder lists you would not publish, or log excerpts that show them |
| To report a security problem | [SECURITY.md](SECURITY.md), privately, never in a public issue |
| To suggest a feature | a GitHub issue; `SUGGESTIONS.md` lists what is already considered |

## What to expect

Issues are read **about once a week**; a reply within 7 days is the target, not a promise.
Fixes land when the maintainer has time.

## What Backup Control Center is not

- A guarantee that a backup is complete or restorable: it runs and monitors the rsync job and reports what the logs say. Test a restore.
- A way to reconfigure iCloud, Google Drive, Dropbox or Proton sync: it links to them and shows what it can read.

## Known limits

- macOS only (developed on Apple Silicon); published as source, with no binary release.
- Quotas need you to connect each account once (OAuth); an expired token shows as disconnected until you reconnect it.
