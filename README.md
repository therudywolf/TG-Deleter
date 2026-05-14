# 🐺 TG Deleter

AGPL-licensed desktop utility for managing your Telegram messages across multiple accounts.
Scan dialogs for your own messages, delete them selectively or in bulk,
and export entire chats with media to a local archive.

AGPL v3 Copyleft applies to reuse, modification, and network deployment of derived versions.

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

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/therudywolf/TG-Deleter.git
cd TG-Deleter

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the config template and fill in your API credentials
cp api_config.example.json api_config.json

# 5. Launch the GUI
python script.py
```

On Windows you can also run `run.bat` — it creates/uses `venv` automatically.

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

## Privacy

The following local files contain account data and **must not** be committed:

- `api_config.json`, `config.json`, `accounts_profiles.json`
- `*.session`, `scan_cache_*.json`
- export folders (`TG_Deleter_export_*`, `exports/`)

All patterns are covered by `.gitignore`.

The repository history has been cleaned of local account profile files. If you ever committed a real Telegram API hash, session file, exported chat, or account profile to a public fork, revoke or rotate the affected credentials and sessions.

## License

TG Deleter is free software licensed under the [GNU Affero General Public License v3.0 only](LICENSE).
