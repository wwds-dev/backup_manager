<!-- Owner: enable GitHub's private vulnerability reporting for wwds-dev/backup_manager (Settings > Code security > Private vulnerability reporting); the form linked below does not work until then. Delete this comment afterwards. -->

# Security

Backup Control Center is free, open-source software maintained by one person. It holds OAuth tokens for your cloud accounts in the macOS Keychain and runs a backup job over your files,
so security reports are welcome.

## Report privately

Use GitHub's private report form: **Security > Report a vulnerability** on
<https://github.com/wwds-dev/backup_manager/security/advisories/new>. Please do not open a public issue for a vulnerability.

Include the version in the window title, what you did, and what happened. Leave out real keys, tokens and personal data:
describe them instead.

## What to expect

- **Acknowledgement within 7 days.**
- **A first assessment within 14 days**, and a fix or a written reason within 90 days.
- No bounty, and no service-level promise beyond this: one person keeps this project, in
  their own time. If a deadline slips, the report gets a reply saying so.
- Credit in the CHANGELOG if you want it.

## Supported versions

Only the latest commit on `main` is supported. There are no binary releases; Backup Control Center is
distributed as source.

## Scope

In scope: this repository.
Out of scope: vulnerabilities in rsync, Google Drive, Dropbox, Time Machine, Qt, PySide6 or Python (report those upstream), and problems that need an attacker who already controls your Mac.
