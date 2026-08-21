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
Окно «Кто может удалить»: администраторы чатов, где прав у нас нет.
Клик по строке открывает личку с человеком.
"""
import logging
import os
import sys
import webbrowser

import customtkinter as ctk

from ui.theme import (
    PAD,
    PAD_SM,
    RADIUS,
    BTN_RADIUS,
    ACCENT,
    ACCENT_HOVER,
    CARD_BG,
    ROW_HOVER,
    SCROLL_FRAME_BG,
    BTN_SECONDARY,
    TEXT_MUTED,
    font,
)
from ui.tooltip import bind_tooltip

log = logging.getLogger("tg_deleter")

NAME_MAX = 34
CHATS_PREVIEW_MAX = 78
CHATS_TOOLTIP_MAX = 40


def open_telegram_link(url: str) -> bool:
    """Открыть ссылку в Telegram или браузере. True, если получилось."""
    if not url:
        return False
    try:
        if sys.platform == "win32":
            # startfile понимает и https://, и схему tg://
            os.startfile(url)  # noqa: S606 - ссылку формируем сами, не из внешних данных
            return True
        return bool(webbrowser.open(url))
    except Exception as e:
        log.warning("Не удалось открыть ссылку %s: %s", url, e)
        try:
            return bool(webbrowser.open(url))
        except Exception:
            return False


def _shorten(text, limit):
    text = str(text or "")
    return (text[: limit - 1] + "…") if len(text) > limit else text


def admins_as_text(admins, target_name: str = "") -> str:
    """Список для копирования в мессенджер."""
    lines = []
    if target_name:
        lines.append("Кто может удалить %s:" % target_name)
    for admin in admins:
        handle = "@%s" % admin.username if admin.username else "id %s" % admin.user_id
        lines.append("• %s (%s) — %s, чатов: %s" % (
            admin.display_name, handle, admin.role, len(admin.chats),
        ))
        for _cid, title in admin.chats:
            lines.append("    – %s" % title)
    return "\n".join(lines)


class AdminRow(ctk.CTkFrame):
    """Строка с администратором: имя, роль, чаты и кнопка «Написать»."""

    def __init__(self, parent, admin, **kw):
        super().__init__(parent, corner_radius=RADIUS, fg_color=CARD_BG, cursor="hand2", **kw)
        self.admin = admin

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="x", padx=PAD_SM, pady=PAD_SM)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        name = ctk.CTkLabel(top, text=_shorten(admin.display_name, NAME_MAX), anchor="w", font=font(14, "bold"))
        name.pack(side="left")
        handle = "@%s" % admin.username if admin.username else "id %s" % admin.user_id
        ctk.CTkLabel(top, text=handle, anchor="w", font=font(12), text_color=ACCENT).pack(side="left", padx=(PAD_SM, 0))
        badge = admin.role + (" · бот" if admin.is_bot else "")
        ctk.CTkLabel(top, text=badge, anchor="w", font=font(12), text_color=TEXT_MUTED).pack(side="left", padx=(PAD_SM, 0))

        self.write_btn = ctk.CTkButton(
            top, text="Написать", width=110, height=28, corner_radius=BTN_RADIUS,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._open,
        )
        self.write_btn.pack(side="right")
        ctk.CTkLabel(
            top, text="чатов: %s" % len(admin.chats), anchor="e", font=font(12), text_color=TEXT_MUTED,
        ).pack(side="right", padx=(0, PAD_SM))

        titles = [t for _cid, t in admin.chats]
        preview = ", ".join(titles)
        chats_label = ctk.CTkLabel(
            inner, text=_shorten(preview, CHATS_PREVIEW_MAX), anchor="w",
            font=font(12), text_color=TEXT_MUTED,
        )
        chats_label.pack(fill="x", pady=(2, 0))

        tip = "\n".join("• %s" % t for t in titles[:CHATS_TOOLTIP_MAX])
        if len(titles) > CHATS_TOOLTIP_MAX:
            tip += "\n… и ещё %s" % (len(titles) - CHATS_TOOLTIP_MAX)
        bind_tooltip(chats_label, tip)
        bind_tooltip(name, admin.link)

        for widget in (self, inner, top, name, chats_label):
            widget.bind("<Button-1>", lambda _e: self._open())
            widget.bind("<Enter>", lambda _e: self.configure(fg_color=ROW_HOVER))
            widget.bind("<Leave>", lambda _e: self.configure(fg_color=CARD_BG))

    def _open(self):
        if not open_telegram_link(self.admin.link):
            self.write_btn.configure(text="Не открылось")


class AdminsDialog(ctk.CTkToplevel):
    """Отдельное окно со списком тех, кого можно попросить."""

    def __init__(self, parent, admins, target_name="", chats_count=0, stopped=False):
        super().__init__(parent)
        self.title("Кто может удалить")
        self.geometry("760x560")
        self.minsize(560, 360)
        self.transient(parent)
        self._admins = list(admins)
        self._target_name = target_name or ""

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=PAD, pady=(PAD, PAD_SM))
        title = "Кто может удалить: %s" % target_name if target_name else "Кто может удалить"
        ctk.CTkLabel(head, text=title, font=font(18, "bold"), anchor="w").pack(fill="x")
        if stopped:
            subtitle = "Поиск остановлен, список неполный."
        elif self._admins:
            subtitle = ("Прав у вас нет в %s чат(ах). Напишите этим людям — "
                        "клик по строке откроет личку." % chats_count)
        else:
            subtitle = "Администраторов с правом удалять найти не удалось."
        ctk.CTkLabel(head, text=subtitle, font=font(12), text_color=TEXT_MUTED, anchor="w").pack(fill="x", pady=(2, 0))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=RADIUS)
        self.scroll.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD_SM))
        if self._admins:
            for admin in self._admins:
                AdminRow(self.scroll, admin).pack(fill="x", pady=(0, PAD_SM), padx=PAD_SM)
        else:
            ctk.CTkLabel(
                self.scroll,
                text="Список админов этих чатов Telegram не отдал.",
                font=font(14), text_color="gray",
            ).pack(expand=True, pady=PAD * 3)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=PAD, pady=(0, PAD))
        self.copy_btn = ctk.CTkButton(
            bottom, text="Копировать список", command=self._copy, corner_radius=BTN_RADIUS,
            width=170, height=32, fg_color=BTN_SECONDARY,
        )
        self.copy_btn.pack(side="left")
        ctk.CTkButton(
            bottom, text="Закрыть", command=self.destroy, corner_radius=BTN_RADIUS,
            width=110, height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        ).pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        # Перед подъёмом даём окну отрисоваться, иначе на Windows оно мигает пустым.
        self.after(120, self._raise)

    def _raise(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _copy(self):
        text = admins_as_text(self._admins, self._target_name)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.copy_btn.configure(text="Скопировано")
            self.after(1500, lambda: self.copy_btn.winfo_exists() and self.copy_btn.configure(text="Копировать список"))
        except Exception as e:
            log.warning("Копирование не удалось: %s", e)
            self.copy_btn.configure(text="Не вышло")
        return text
