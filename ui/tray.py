
# SPDX-License-Identifier: AGPL-3.0-only
# TG Deleter - Desktop utility for managing Telegram messages
# Copyright (C) 2024-2026 TG Deleter Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
System-tray icon for background mode.

Wraps pystray so the rest of the app can run a tray icon without caring whether
pystray is installed or which backend it uses. All menu callbacks are forwarded
verbatim — the caller is responsible for marshalling them onto the Tk main
thread (e.g. via ``root.after``).
"""
import logging
import os

log = logging.getLogger("tg_deleter")

try:
    import pystray
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency / headless env
    pystray = None
    Image = None


class TrayIcon:
    """A minimal system-tray icon: «Открыть» (default) and «Выход»."""

    def __init__(self, icon_path, on_show, on_quit, title="TG Deleter"):
        self._on_show = on_show
        self._on_quit = on_quit
        self._title = title
        self._icon = None
        self._image = None
        if pystray is None or Image is None:
            log.debug("tray: pystray/Pillow unavailable, background mode disabled")
            return
        try:
            if icon_path and os.path.isfile(icon_path):
                self._image = Image.open(icon_path)
                self._image.load()
            else:
                self._image = self._fallback_image()
        except Exception as e:
            log.debug("tray: icon load failed (%s), using fallback", e)
            self._image = self._fallback_image()

    @property
    def available(self) -> bool:
        return pystray is not None and self._image is not None

    @staticmethod
    def _fallback_image():
        if Image is None:
            return None
        return Image.new("RGB", (64, 64), (42, 171, 238))

    def start(self) -> bool:
        """Start the tray icon on its own backend thread. Returns True on success."""
        if not self.available or self._icon is not None:
            return False
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda icon, item: self._safe(self._on_show), default=True),
            pystray.MenuItem("Выход", lambda icon, item: self._safe(self._on_quit)),
        )
        self._icon = pystray.Icon("tg_deleter", self._image, self._title, menu)
        try:
            # run_detached spins up its own thread; fall back to a manual thread.
            self._icon.run_detached()
        except Exception:
            import threading
            threading.Thread(target=self._icon.run, daemon=True).start()
        log.debug("tray: started")
        return True

    @staticmethod
    def _safe(callback):
        try:
            if callback:
                callback()
        except Exception as e:
            log.debug("tray: callback error: %s", e)

    def notify(self, message: str, title: str | None = None) -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, title or self._title)
            except Exception as e:
                log.debug("tray: notify failed: %s", e)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as e:
                log.debug("tray: stop failed: %s", e)
            self._icon = None
