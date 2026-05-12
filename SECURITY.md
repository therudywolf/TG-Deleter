# Security Policy

## Reporting

Please report security issues privately through GitHub Security Advisories when available, or by opening a minimal issue that does not include secrets, tokens, session files, exported chats, or personal Telegram data.

## Sensitive Local Files

TG Deleter stores Telegram credentials, session databases, caches, and exports locally. These files are intentionally ignored by git. Never attach them to issues or pull requests.

If a Telegram API hash, `.session` file, account profile, or chat export was exposed publicly, revoke or rotate the affected credential/session before continuing to use it.
