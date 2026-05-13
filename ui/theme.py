
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
Единые константы темы и шрифты для TG Deleter UI.
"""
import sys
import customtkinter as ctk

# Тема: тёмная, акцент в стиле Telegram Desktop
ctk.set_default_color_theme("dark-blue")

_DEFAULT_APPEARANCE = "dark"


def set_theme(mode: str = "dark"):
    """Set appearance mode: 'dark', 'light', or 'system'."""
    valid = {"dark", "light", "system"}
    mode = mode.lower() if mode.lower() in valid else _DEFAULT_APPEARANCE
    ctk.set_appearance_mode(mode)


def get_current_theme() -> str:
    return ctk.get_appearance_mode().lower()


set_theme(_DEFAULT_APPEARANCE)

FONT_FAMILY = "Segoe UI Variable" if sys.platform == "win32" else None

# Отступы и скругления
PAD = 16
PAD_SM = 8
RADIUS = 8
BTN_RADIUS = 8
SIDEBAR_WIDTH = 260

# Акцент Telegram-синий
ACCENT = "#2AABEE"
ACCENT_HOVER = "#229ED9"
DANGER = ("#C62828", "#8B0000")
DANGER_HOVER = ("#E53935", "#B71C1C")

# Сайдбар: фон и граница (TG Desktop dark)
SIDEBAR_BG = ("#E8E8E8", "#182533")
SIDEBAR_BORDER = ("#DEDEDE", "#2B5278")

# Фон карточек и списков
CARD_BG = ("gray85", "gray20")
SCROLL_FRAME_BG = ("gray90", "gray17")
ROW_BG = ("gray92", "gray22")
ROW_HOVER = ("gray78", "gray27")
PANEL_BG = ("gray92", "gray18")
BORDER = ("gray82", "gray27")
TEXT_MUTED = ("gray40", "gray65")
ACTIVE_BG = ("#2AABEE", "#2AABEE")

# Вторичные кнопки
BTN_SECONDARY = ("gray65", "gray30")
BTN_SECONDARY_DANGER = ("gray60", "gray35")


def font(size: int = 14, weight: str = "normal"):
    """Шрифт с учётом Win11 (Segoe UI)."""
    if FONT_FAMILY:
        return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
    return ctk.CTkFont(size=size, weight=weight)
