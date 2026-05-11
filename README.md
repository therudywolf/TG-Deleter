# TG Deleter

Desktop utility for managing your Telegram messages across multiple accounts.
Scan dialogs for your own messages, delete them selectively or in bulk,
and export entire chats with media to a local archive.

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
python script.py login --session my_account --phone +71234567890
```

## Export

1. Open **Экспорт** in the left sidebar.
2. Click **Загрузить список** to fetch all available dialogs (no history scan needed).
3. Select media types to download: photos, videos, files, audio/voice, stickers/GIFs, or other attachments.
4. Filter / search the list and check one or more chats.
5. Click **Запустить бекап выбранных** and choose an output folder.

A timestamped `TG_Deleter_export_*` folder is created with `messages.jsonl`, `messages.html`, optional `media/`, and `manifest.json` per chat.

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

## Privacy

The following local files contain account data and **must not** be committed:

- `api_config.json`, `config.json`, `accounts_profiles.json`
- `*.session`, `scan_cache_*.json`
- export folders (`TG_Deleter_export_*`, `exports/`)

All patterns are covered by `.gitignore`.

## License

[MIT](LICENSE)
