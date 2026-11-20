# Security

Backup Control Center is free software under the MIT licence, maintained by one person. It keeps OAuth tokens for your cloud accounts in a local file readable only by your user (`~/Library/Application Support/Backup Control Center/tokens.json`, mode 0600, in a folder only your user can open, mode 0700; the Google, Dropbox and OneDrive app credentials and the manual accounts file are also written mode 0600, atomically). Sign-in uses a `state` check, PKCE and a loopback-only listener (details in the README). The app also runs a backup job over your files,
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
