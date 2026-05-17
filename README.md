# 🐺 RudyWolf Archive: TG Deleter

> Desktop utility for managing your Telegram messages across multiple accounts.

![Version](https://img.shields.io/badge/version-archive-4c8bf5)
![Status](https://img.shields.io/badge/status-archive-6b7280)
[![License](https://img.shields.io/badge/license-AGPL--3.0--only-22c55e)](LICENSE)

Scan dialogs for your own messages, delete them selectively or in bulk,
and export entire chats with media to a local archive.

## Status

- Archive-only repository.
- Not intended for production use.
- License: [AGPL-3.0-only](LICENSE) — see [SECURITY.md](SECURITY.md).

## Secrets

- Telegram API credentials: copy `api_config.example.json` → `api_config.json` locally only.
- Session files (`*.session`), `config.json`, `accounts_profiles.json`, and export folders are gitignored — never commit them.
- Rotate API credentials if they were ever pushed to a public fork.

## Run

```bat
run.bat
```

Or manually:

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp api_config.example.json api_config.json
python script.py
```

## Features

- **Multi-account** — switch between Pyrogram sessions on the fly.
- **Smart scan** — filters for groups, channels, and private chats with per-account cache.
- **Selective deletion** — delete by chat, by message, or skip-scan mode; batch API calls (up to 100 per request).
- **Parallel export** — stream `messages.jsonl` + `messages.html` + selectable media types to disk; large chats never need to fit in memory.
- **Live progress** — responsive pause / stop for scans, deletes, and exports; FloodWait countdown in the UI.
- **Theming** — Dark / Light / System appearance via CustomTkinter.
- **Hotkeys** — `Ctrl+S` scan, `Escape` stop, `F5` refresh cache.
- **CLI mode** — `python script.py cli` for headless session login.

## Requirements

- Python 3.10+
- Telegram API credentials (`api_id` / `api_hash`) from <https://my.telegram.org/apps>

### CLI Login

```bash
python script.py login my_account
```

Pyrogram will interactively prompt for your phone number and the verification code.

## Export

1. Open **Экспорт** in the left sidebar.
2. Click **Загрузить список** to fetch all available dialogs (no history scan needed).
3. Select media types to download: photos, videos, files, audio/voice, stickers/GIFs, or other attachments.
4. Filter / search the list and check one or more chats.
5. Click **Запустить бекап выбранных** and choose an output folder.

A timestamped `TG_Deleter_export_*` folder is created with `messages.jsonl`, `messages.html`, optional `media/`, and `manifest.json` per chat.
Avoid saving ad hoc exports directly into the repository root unless you intentionally want to inspect them locally; exported chats can contain private Telegram data.

## Docker (CLI mode)

```bash
docker build -t tg-deleter .
docker run -it -v $(pwd):/app tg-deleter login my_account
docker run -it -v $(pwd):/app tg-deleter cli --chat-id -1001234567890
```

The volume mount preserves session files and configs between runs.

## Build

Windows executable:

```powershell
.\build.ps1
```

Produces `TGDeleter.exe` in the project root. Build artifacts, sessions, configs, caches, and exports are covered by `.gitignore`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Runtime dependencies are listed in `requirements.txt`. Build and test tooling is available through optional extras:

```bash
pip install -e ".[build,dev]"
```

## Publication Note

Before any push or reuse, check that no Telegram sessions, API hashes, exported chats, or account profiles are included in tracked files or history.
