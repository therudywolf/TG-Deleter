# Changelog

All notable changes to TG Deleter are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Capped chat message-list rendering to keep the UI responsive on very large histories
- Login dialog disconnects a stale client before retrying, preventing session-file locks
- Cancelled export tasks are awaited after Stop, removing pending-task warnings
- Added an inter-delete delay in the per-message fallback path to reduce cascading FloodWait
- Bounded the per-cycle GUI event drain so fast scans no longer stall the window
- Saved appearance theme is now applied on startup, not only within the session
- Worker reconnect uses exponential backoff (5→60 s) instead of a fixed 5 s retry
- Sidebar connection indicator clears when the worker loses its session
- Window geometry is validated against the current screen before being restored
- Bot chats are now reachable under the "Личка" section filter

### Changed
- Version scheme aligned to `0.7.0-beta.1` across `VERSION`, `core.py`, and `pyproject.toml`
- `TgCrypto` offered as an optional `performance` extra for faster Telegram crypto

### Removed
- Dead `export_media_types_filter` config key and the stale `FINAL_STATUS.txt` artifact

## [0.7.0-beta.1] — 2026-05-12

### Added
- Parallel streaming export for selected chats/channels with per-chat message limits
- Per-account export folders with `messages.jsonl`, `messages.html`, optional media, and `manifest.json`
- Dedicated exporter mode in the sidebar without requiring message history scan
- Per-run media type selection for backups (photos, videos, files, audio/voice, stickers/GIFs, other attachments)
- Determinate backup progress indicators
- Export settings persistence (parallel chat count, media download toggle)
- Connection status indicator in sidebar
- 24-hour avatar cache for Pyrogram 2.x compatibility
- Hotkey support (`Ctrl+S` scan, `Escape` stop, `F5` refresh cache)
- Window geometry persistence
- Log rotation (1000 lines) with dedicated `ui/logging_config.py`
- 47 comprehensive unit tests for `core.py`
- `pyproject.toml` with `[project.scripts]` entry point
- AGPL-3.0-only license headers in all source files
- `.gitattributes` for consistent line endings across platforms
- Live progress indicators with FloodWait countdown in status bar

### Changed
- **Core refactoring**: Thread-safe `AppState` replaces module-level globals; batch deletion (100 msgs/request)
- **Worker separation**: Extracted to `ui/worker.py` with typed dataclass messages (`ui/messages.py`)
- **Config system**: Read-only config view via `MappingProxyType` for safer access patterns
- **UI dispatch**: Message dispatch table in `_check_queue` for cleaner event handling
- **Search debounce**: Increased to 300 ms for improved performance
- **Phone validation**: Enforces 7-15 digit format
- **Avatar rendering**: Now loads through Pillow for better compatibility
- **Type annotations**: Full type hints across all modules for better IDE support

### Fixed
- Fixed avatar download for Pyrogram 2.x (`get_profile_photos` API changes)
- Fixed `--login` creating two redundant Pyrogram clients
- Fixed fire-and-forget avatar task leaking unhandled exceptions
- Fixed O(N²) performance in `remove_deleted_ids` (list → set)
- Fixed tooltip `after`-callback leak on rapid hover
- Fixed worker spamming "session not authorized" every 2 seconds
- Fixed double client disconnect in `LoginDialog`
- Fixed UI flicker from unnecessary `pack` / `pack_forget` at init
- Fixed account identity leakage between switched accounts
- Fixed scan cache reads/writes to use explicit session keys
- Fixed mass-delete operations cancellable by account switch/close

### Security
- No hardcoded credentials in source code; all API keys loaded from config files
- All git history verified clean of sensitive data
- Session files and API configs properly excluded via `.gitignore`
- Improved path traversal protection in session name validation

### Documentation
- Enhanced README with Docker examples, privacy policy, and development setup
- Added CONTRIBUTING.md with privacy rules and development guidelines
- Added SECURITY.md for responsible disclosure procedures
- Added RELEASE_NOTES.md and CHANGELOG.md for version history
- Added comprehensive inline documentation with docstrings
- Added type hints for better code discoverability

## [0.1.0] — Initial Release

### Added
- Multi-account support with Pyrogram session switching
- Smart chat scan with filters (groups, channels, private chats)
- Selective message deletion with batch API calls
- Parallel export to JSON and HTML formats
- Dark/Light/System theming via CustomTkinter
- CLI mode for headless operations
- Docker support for containerized deployments
- Windows executable build support via PyInstaller

---

**Security Notice**: If you believe you have committed a real Telegram API hash, session file, or personal data to a public fork of this repository, please revoke or rotate the affected credentials immediately and contact the maintainers.
