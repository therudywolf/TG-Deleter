# Changelog

All notable changes to TG Deleter are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0-beta.1] — 2026-08-21

### Added
- **Участники screen**: find a person by `@username`, numeric ID, phone, or `t.me`
  link, then act on their chat membership in bulk
- **Remove from all chats**: discovers every chat you share with that person —
  fast via Telegram's common-chats list, or a full dialog sweep — checks your
  admin rights in each, and kicks or bans them from the ones you tick. Rows that
  you cannot act on (no admin rights, target is an admin or the owner) are
  labelled with the reason and left unchecked
- **Add to selected chats**: loads all your groups, supergroups, and channels with
  checkboxes and title search, then invites the person into everything you tick
- Per-chat result reporting for both operations: successes and Telegram's refusal
  reasons (privacy settings, missing rights, member limits) in plain Russian,
  mirrored into the log panel
- Pause / Stop, FloodWait countdowns, and inter-chat delays on member operations,
  matching the scan and export screens
- Tooltips on the search-scope selector, the ban checkbox, and every chat row
  (the row tip spells out both sides' status)
- 100 new tests: core coverage for user-query parsing, error descriptions, rights
  detection, ban vs. kick semantics and per-chat failure isolation, plus the
  project's first GUI tests — the Участники screen and the main window's worker
  message dispatch (166 tests total, up from 66)
- `tests/conftest.py` redirects `core.get_project_root` to a temporary directory
  for the whole run, so tests can no longer drop `api_config.json` or caches into
  the working tree, and hosts the single shared Tk window the GUI tests reuse
- CI installs customtkinter and runs the suite under `xvfb-run`, so the GUI tests
  execute on Linux too; they skip themselves when no display is available

### Fixed
- Sidebar account avatars never loaded: the worker called `get_profile_photos`,
  which Pyrogram 2.x renamed to `get_chat_photos` *and* turned into an async
  generator. The resulting `AttributeError` was swallowed by a blanket
  `except Exception`, leaving only a DEBUG line. Fixed the call, and
  `AttributeError`/`TypeError` now log at exception level so the next API move
  is loud instead of silent
- Added a contract test asserting the Pyrogram `Client` methods the worker calls
  by name still exist, so a future rename fails in CI
- Chat rows no longer overflow the status column into the type column; long
  titles and statuses are ellipsised with the full text in a tooltip
- Column headers line up with the values under them

### Changed
- Version aligned to `0.9.0-beta.1` across `VERSION`, `core.py`, `ui/__init__.py`, and `pyproject.toml`

## [0.8.0-beta.1] — 2026-05-29

### Added
- **Background mode**: closing the window now minimizes TG Deleter to the system
  tray (pystray) and keeps the worker connected; restore or quit from the tray
  menu, or quit fully from the sidebar
- Branded app icon (`assets/`) embedded in the window, taskbar, and `.exe`, with a
  reproducible generator (`assets/make_icon.py`)
- Auto-builder: `build.ps1` bootstraps a venv, installs dependencies + PyInstaller,
  and produces a single windowed `TGDeleter.exe` with the icon and tray bundled
- Persistent rotating file logging (`tg_deleter.log`, 5 MB × 3) wired up at GUI
  startup — previously the rotating handler existed but was never enabled, so the
  windowed `.exe` produced no diagnostics
- Continuous-integration workflow running the test suite on Python 3.10 and 3.13
- Unit tests for chat-type classification (incl. bots), media-export gating, and
  enum rendering in exported text (64 tests total)

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
- Version aligned to `0.8.0-beta.1` across `VERSION`, `core.py`, `ui/__init__.py`, and `pyproject.toml`
- README rewritten in the active RudyWolf project style; added `pystray` runtime dependency
- `TgCrypto` offered as an optional `performance` extra for faster Telegram crypto

### Removed
- Dead `export_media_types_filter` config key and the stale `FINAL_STATUS.txt` artifact
- Unused `ui/navigator.py` module (navigation is handled directly in `ui/app.py`)
- Stray debug output dumps (`cli_*.txt`, `gui_*.txt`) from the working tree

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
