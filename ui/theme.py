"""
Единые константы темы и шрифты для TG Deleter UI.
"""
import sys
import customtkinter as ctk

# Тема: тёмная, акцент в стиле Telegram Desktop
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

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
