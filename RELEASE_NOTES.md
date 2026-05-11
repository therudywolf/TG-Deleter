# Release Notes

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
