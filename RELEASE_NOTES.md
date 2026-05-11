# Release Notes

## 1.1.0 — 2026-05-12

### Bug Fixes
- Fixed avatar download for Pyrogram 2.x (`get_profile_photos` API change).
- Fixed `--login` creating two redundant Pyrogram clients.
- Fixed fire-and-forget avatar task leaking unhandled exceptions.
- Fixed O(N²) performance in `remove_deleted_ids` (list → set).
- Fixed tooltip `after`-callback leak on rapid hover.
- Fixed worker spamming "session not authorized" every 2 seconds.
- Fixed redundant conditions in `get_current_session()`.
- Fixed double client disconnect in `LoginDialog`.
- Fixed UI flicker from unnecessary `pack` / `pack_forget` at init.

### Improvements
- **Core**: Thread-safe `AppState` replaces module-level globals; batch deletion (100 msgs/request); full type annotations; read-only config view via `MappingProxyType`.
- **Worker**: Extracted to `ui/worker.py` with typed dataclass messages (`ui/messages.py`).
- **App**: Dispatch-table `_check_queue`; log rotation (1000 lines); 5-second close timeout; FloodWait countdown in status bar; delete progress indicator; window geometry persistence; hotkeys (`Ctrl+S`, `Escape`, `F5`).
- **UI frames**: Reusable `ChatCard` widget; `Navigator` controller; 300 ms search debounce; bulk select/deselect; improved empty state; responsive button grid in posts frame; mass-delete confirmation lists affected chats.
- **Sidebar**: Connection status indicator; 24-hour avatar cache; log button navigation state.
- **Settings**: Live Dark / Light / System theme switcher; export media filter persistence.
- **Login**: Phone number validation (digits-only, 7-15 length).
- **Tooltip**: Off-screen clamping.
- **Infrastructure**: `pyproject.toml` with `[project.scripts]` entry point; `RotatingFileHandler` via `ui/logging_config.py`; 47 unit tests for `core.py`.
- **CLI**: `argparse`-based subcommands (`cli`, `login`) with `--version` flag.

## 2026-05-10

- Added parallel streaming export for selected chats/channels.
- Added per-account export folders with `messages.html`, `messages.jsonl`, optional media, and `manifest.json`.
- Made scan pause/stop responsive inside chat history traversal.
- Made long delete operations cancellable by account switch/close.
- Fixed account identity leakage between switched accounts.
- Fixed scan cache reads/writes to use explicit session keys.
- Improved chat cards with latest found message preview and selected-card highlighting.
- Added export settings: parallel chat count, media download toggle, and per-chat export limit.
- Fixed avatar rendering by loading images through Pillow.
- Removed tracked local profile/test-output artifacts and expanded `.gitignore`.
- Added `.gitattributes`, README, and release notes for cleaner releases.

## 2026-05-11

- Added a dedicated exporter mode in the sidebar.
- Exporter now loads all available dialogs without scanning message history for "my messages".
- Added per-run media type selection for exporter backups: photos, videos, files, audio/voice, stickers/GIFs, and other attachments.
- Added determinate backup progress with selected chats done/total and processed messages done/total when Telegram exposes history counts.
- Made multi-chat backup explicit in the exporter UI with `Запустить бекап выбранных`.
- Moved expensive channel-rights discovery out of account switching; it now runs only before scan/delete operations that need ownership detection.
- Reduced empty-state artifacts while streaming scan/export lists into the UI.
- Added persistent export selection, counters, active sidebar sections, and render limits for large dialog lists.
- Disabled Pyrogram updates for the app client to reduce account-switch overhead.
