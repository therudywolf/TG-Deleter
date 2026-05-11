# TG Deleter

Desktop utility for Telegram accounts. It scans dialogs for your own messages, lets you delete them selectively, and exports multiple selected chats/channels in parallel.

## Features

- Multiple Telegram accounts via Pyrogram sessions.
- Per-account scan cache.
- Scan filters for groups, channels, and private chats.
- Responsive pause/stop for long scans and export jobs.
- Selective deletion by chat/message, including no-scan deletion mode.
- Parallel streaming export for selected chats:
  - `messages.jsonl` for machine processing;
  - `messages.html` for readable local preview;
  - `media/` attachments when enabled;
  - `manifest.json` with totals and chat statuses.

## Setup

1. Install Python 3.10+.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `api_config.example.json` to `api_config.json` or enter API settings in the app.
4. Get `api_id` and `api_hash` from https://my.telegram.org/apps.
5. Start the GUI:

```bash
python script.py
```

On Windows, `run_project.bat` creates/uses `venv` and starts the GUI.

## Export

1. Open `Экспорт` in the left sidebar.
2. Click `Загрузить список` to fetch all available dialogs without scanning message history.
3. Filter/search the list and mark chats with checkboxes.
4. Click `Экспорт выбранных`.
5. Pick an output folder.

The app creates a timestamped `TG_Deleter_export_*` folder. Export is intentionally streamed to disk so large chats do not have to fit in memory.

## Build

Windows executable:

```powershell
.\build.ps1
```

The build writes `TGDeleter.exe` locally. Build artifacts, sessions, configs, caches, profiles, and exports are ignored by Git.

## Privacy

Do not commit local files containing account data:

- `api_config.json`
- `config.json`
- `accounts_profiles.json`
- `*.session`
- `scan_cache_*.json`
- export folders

These patterns are covered by `.gitignore`.
