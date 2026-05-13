
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

"""Navigation controller for switching between content frames."""
import customtkinter as ctk


class Navigator:
    """Manages frame visibility — only one frame is shown at a time."""

    def __init__(self, container: ctk.CTkFrame):
        self._container = container
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._current_key: str | None = None

    def register(self, key: str, frame: ctk.CTkFrame):
        self._frames[key] = frame

    @property
    def current(self) -> str | None:
        return self._current_key

    def show(self, key: str):
        if self._current_key == key:
            return
        if self._current_key and self._current_key in self._frames:
            self._frames[self._current_key].pack_forget()
        frame = self._frames.get(key)
        if frame:
            frame.pack(fill="both", expand=True)
            self._current_key = key

    def hide_all(self):
        for frame in self._frames.values():
            frame.pack_forget()
        self._current_key = None
