# 🐺 TG Deleter — Telegram Cleanup & Archive

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-2AABEE.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-6b7280.svg)](#)

Desktop tool to **find and delete your own Telegram messages** across multiple
accounts — and to **archive whole chats** (text + media) to disk before they're
gone. Scan dialogs, review what's yours, delete selectively or in bulk, or just
back everything up.

Everything runs **locally**. Your API credentials and session files never leave
your machine, and exported chats are written straight to a folder you pick.
Licensed under AGPL-3.0-only.

## Features

- **Multi-account** — switch between Pyrogram sessions on the fly; per-account avatar, profile, and scan cache.
- **Smart scan** — find only *your* messages across groups, channels, and private chats, with depth limits to keep the API happy.
- **Safe deletion** — ownership is re-checked right before every delete; batched up to 100 messages per request. Delete by message, by chat, "everything except this one", or skip-scan for huge histories.
- **Streaming export** — back up selected chats to `messages.jsonl` + `messages.html` + optional `media/`, with a `manifest.json` summary. Large chats never need to fit in memory.
- **Background mode** — close the window and TG Deleter keeps running in the **system tray**; reopen or quit from the tray menu. 🐺
- **Live control** — pause / stop any scan, delete, or export; FloodWait countdowns surface in the status bar.
- **Theming & hotkeys** — Dark / Light / System appearance; `Ctrl+S` scan, `Esc` stop, `F5` refresh cache.
- **CLI mode** — headless login and per-chat cleanup for scripts and Docker.

## Quick start (clone → one launcher)

**Requirements:** Python 3.10+ and Telegram API credentials (`api_id` / `api_hash`) from <https://my.telegram.org/apps>.

| **OS** | What to run |
|----|-------------|
| **Windows** | `run.bat` |
| **Linux / macOS** | `python script.py` (after the manual setup below) |

`run.bat` creates a virtual environment, installs dependencies, and launches the
GUI on first run. On launch, open **Настройки**, paste your `api_id` / `api_hash`,
then add an account from the left sidebar.

## Manual setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
cp api_config.example.json api_config.json
python script.py
```

Optional — much faster Telegram crypto (prebuilt wheel on most platforms):

```bash
pip install TgCrypto
```

## Background mode

Closing the window (the **×** button) doesn't quit — TG Deleter minimizes to the
system tray and the worker stays connected, so long scans, deletions, and
exports keep running. Right-click the tray icon for **Открыть** (restore the
window) or **Выход** (quit for real). The sidebar **Выход** button also quits
fully.

## Export

1. Open **Экспорт** in the left sidebar.
2. Click **Загрузить список** to fetch all dialogs (no history scan needed).
3. Pick which media to download: photos, videos, files, audio/voice, stickers/GIFs, or other.
4. Filter / search and check one or more chats.
5. Click **Запустить бекап выбранных** and choose an output folder.

A timestamped `TG_Deleter_export_*` folder is created per run, with
`messages.jsonl`, `messages.html`, optional `media/`, and `manifest.json` for
each chat. Exports can contain private data — don't drop them in the repo root.

## CLI mode

```bash
python script.py login my_account            # interactive phone + code login
python script.py cli --chat-id -1001234567890
```

## Docker (CLI only)

```bash
docker build -t tg-deleter .
docker run -it -v $(pwd):/app tg-deleter login my_account
docker run -it -v $(pwd):/app tg-deleter cli --chat-id -1001234567890
```

The volume mount preserves session files and configs between runs.

## Build a Windows .exe

```powershell
.\build.ps1
```

The auto-builder bootstraps a venv, installs dependencies and PyInstaller,
generates the app icon if needed, and produces a single windowed
`TGDeleter.exe` in the project root (with tray support and the bundled icon).
Build artifacts, sessions, configs, caches, and exports are all gitignored.

## Project structure

```
core.py            Telegram logic: config, scan, delete, streaming export
script.py          Entry point — GUI by default, `cli` / `login` subcommands
gui.py             Thin re-export of ui.app.run_gui
ui/                CustomTkinter GUI
  app.py           Main window, queue dispatch, tray / background mode
  worker.py        Background asyncio + Pyrogram thread
  tray.py          System-tray icon (pystray)
  *_frame.py       Screens: chats, posts, export, settings, sidebar
assets/            App icon + generator (make_icon.py)
tests/             pytest suite for core logic
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

CI runs the suite on Python 3.10 and 3.13 on every push and pull request.

## Privacy & security

TG Deleter stores credentials, session databases, caches, and exports **locally
only** — all are gitignored. Never attach them to issues or PRs. If an API hash
or `.session` file is ever exposed, rotate it. See [SECURITY.md](SECURITY.md).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). By contributing,
you agree your work is licensed under AGPL-3.0-only.

## License

[AGPL-3.0-only](LICENSE) © 2024–2026 TG Deleter contributors.
