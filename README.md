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
- **Member management** — remove a person from every chat where you have the rights, or add them to the chats you tick. Find them by `@username`, ID, phone, or `t.me` link. Where your rights fall short, the app finds the admins who *can* remove them and links straight to their DMs.
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

## Members — remove from chats / add to chats

Open **Участники** in the left sidebar and find the person by `@username`, numeric
ID, `+phone`, or a `t.me/...` link.

**Удалить из чатов.** Pick how to search:

| Mode | What it does |
|----|-------------|
| **Общие чаты (быстро)** | asks Telegram for your chats in common with that person — one request, up to 100 chats |
| **Все диалоги (долго)** | walks every dialog and checks membership one by one — thorough, but slow and FloodWait-prone |

Every chat found gets a row with the person's status, your status, and whether the
removal is possible. Chats where you can act are ticked automatically; the rest
show the reason (no admin rights, target is an admin or the owner) and stay
unticked — you can still tick them by hand to let Telegram have the final word.
**Забанить, чтобы не вернулся** is on by default; untick it to kick without a ban,
so the person can rejoin via an invite link.

**Кто может удалить.** Rights you do not have are not a dead end. Press
**Кто может удалить** and the app walks the chats you cannot act in, collects
their administrators (Telegram shows admin lists to plain members too), and
reports *people* rather than chats — one admin typically covers dozens of them.
Every row opens a private chat with that person in one click, and
**Копировать список** puts the whole thing on the clipboard as text you can
paste straight into a message.

**Добавить в чаты.** Click **Загрузить чаты** for all your groups, supergroups, and
channels, filter or search by title, tick the ones you want, and press **Добавить в
выбранные**.

Both operations run one chat at a time with a delay, honour Pause / Stop, wait out
FloodWait, and finish with a per-chat report — including Telegram's reason for
every chat it refused. Note that adding people is subject to *their* privacy
settings, and mass invites can get an account limited by Telegram's anti-spam.

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
  *_frame.py       Screens: chats, posts, export, members, settings, sidebar
  admins_dialog.py Who-can-remove window with one-click links to their DMs
assets/            App icon + generator (make_icon.py)
tests/             pytest suite: core logic + GUI (conftest.py isolates the data dir)
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite covers `core.py` logic plus the GUI: the Участники screen and the main
window's worker-message dispatch. GUI tests need `customtkinter` and a display —
without either they skip themselves. Nothing in the suite writes to the working
tree; `tests/conftest.py` points the app's data directory at a temporary folder.

CI runs the suite on Python 3.10 and 3.13 on every push and pull request, under
`xvfb-run` so the GUI tests execute on Linux too.

## Privacy & security

TG Deleter stores credentials, session databases, caches, and exports **locally
only** — all are gitignored. Never attach them to issues or PRs. If an API hash
or `.session` file is ever exposed, rotate it. See [SECURITY.md](SECURITY.md).

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). By contributing,
you agree your work is licensed under AGPL-3.0-only.

## License

[AGPL-3.0-only](LICENSE) © 2024–2026 TG Deleter contributors.
