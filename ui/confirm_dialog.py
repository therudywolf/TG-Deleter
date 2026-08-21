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
Подтверждение операции, которая затрагивает других людей.

Обычное «вы уверены?» скрывает, что именно произойдёт. Здесь видно список
чатов целиком, а для необратимых действий кнопка разблокируется только после
явной отметки — случайным двойным Enter такое не проскочит.
"""
import customtkinter as ctk

from ui.theme import (
    PAD,
    PAD_SM,
    RADIUS,
    BTN_RADIUS,
    ACCENT,
    ACCENT_HOVER,
    BTN_SECONDARY,
    SCROLL_FRAME_BG,
    TEXT_MUTED,
    DANGER,
    DANGER_HOVER,
    font,
)

ITEMS_SHOWN = 200


class ConfirmDialog(ctk.CTkToplevel):
    """Модальное окно: что именно произойдёт и с чем."""

    def __init__(self, parent, title, summary, items=(), note="", danger=False,
                 ack_text=None, confirm_text="Продолжить"):
        super().__init__(parent)
        self.result = False
        self._ack_text = ack_text

        self.title(title)
        self.minsize(460, 240)
        self.transient(parent)
        self.resizable(True, True)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=PAD, pady=(PAD, PAD_SM))
        ctk.CTkLabel(body, text=summary, anchor="w", justify="left", font=font(14),
                     wraplength=640).pack(fill="x")
        if note:
            ctk.CTkLabel(body, text=note, anchor="w", justify="left", font=font(12),
                         text_color=TEXT_MUTED, wraplength=640).pack(fill="x", pady=(PAD_SM, 0))

        items = list(items)
        if items:
            ctk.CTkLabel(body, text="Затронет %s чат(ов):" % len(items), anchor="w",
                         font=font(12, "bold"), text_color=TEXT_MUTED).pack(fill="x", pady=(PAD_SM, 2))
            self.scroll = ctk.CTkScrollableFrame(body, fg_color=SCROLL_FRAME_BG, corner_radius=RADIUS,
                                                 height=180)
            self.scroll.pack(fill="both", expand=True)
            for title_text in items[:ITEMS_SHOWN]:
                ctk.CTkLabel(self.scroll, text="• %s" % title_text, anchor="w",
                             font=font(12)).pack(fill="x", padx=PAD_SM, pady=1)
            if len(items) > ITEMS_SHOWN:
                ctk.CTkLabel(self.scroll, text="…и ещё %s" % (len(items) - ITEMS_SHOWN), anchor="w",
                             font=font(12), text_color=TEXT_MUTED).pack(fill="x", padx=PAD_SM, pady=1)
        else:
            self.scroll = None

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=PAD, pady=(0, PAD))

        self.ack_var = ctk.BooleanVar(value=not ack_text)
        if ack_text:
            self.ack_check = ctk.CTkCheckBox(
                bottom, text=ack_text, variable=self.ack_var, command=self._sync,
                font=font(12),
            )
            self.ack_check.pack(fill="x", pady=(0, PAD_SM))
        else:
            self.ack_check = None

        buttons = ctk.CTkFrame(bottom, fg_color="transparent")
        buttons.pack(fill="x")
        self.confirm_btn = ctk.CTkButton(
            buttons, text=confirm_text, command=self._confirm, corner_radius=BTN_RADIUS,
            width=190, height=36,
            fg_color=DANGER if danger else ACCENT,
            hover_color=DANGER_HOVER if danger else ACCENT_HOVER,
        )
        self.confirm_btn.pack(side="right")
        ctk.CTkButton(
            buttons, text="Отмена", command=self._cancel, corner_radius=BTN_RADIUS,
            width=120, height=36, fg_color=BTN_SECONDARY,
        ).pack(side="right", padx=(0, PAD_SM))

        self._sync()
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _sync(self):
        self.confirm_btn.configure(state="normal" if self.ack_var.get() else "disabled")

    def _confirm(self):
        if not self.ack_var.get():
            return
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()

    def ask(self) -> bool:
        """Показать модально и вернуть решение пользователя."""
        try:
            self.grab_set()
        except Exception:
            pass
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass
        self.wait_window()
        return self.result


def confirm_action(parent, title, summary, items=(), note="", danger=False,
                   ack_text=None, confirm_text="Продолжить") -> bool:
    """Спросить подтверждение. True — пользователь согласился."""
    return ConfirmDialog(
        parent, title, summary, items=items, note=note, danger=danger,
        ack_text=ack_text, confirm_text=confirm_text,
    ).ask()
