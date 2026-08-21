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
Экран «Участники»: убрать человека из чатов, добавить в выбранные
и откатить собственный бан по журналу операций.
"""
import logging

import customtkinter as ctk
from tkinter import messagebox

from core import (
    MY_STATUS_LABELS,
    TARGET_STATUS_LABELS,
    MemberChat,
    _peer_kind,
    pending_bans,
)
from ui.theme import (
    PAD,
    PAD_SM,
    RADIUS,
    BTN_RADIUS,
    ACCENT,
    ACCENT_HOVER,
    CARD_BG,
    SCROLL_FRAME_BG,
    BTN_SECONDARY,
    PANEL_BG,
    BORDER,
    TEXT_MUTED,
    DANGER,
    DANGER_HOVER,
    font,
)
from ui.queues import scan_paused, scan_stop_requested
from ui.tooltip import bind_tooltip
from ui.admins_dialog import AdminsDialog
from ui.confirm_dialog import confirm_action
from ui.progress_strip import ProgressStrip

log = logging.getLogger("tg_deleter")

VISIBLE_LIMIT = 500
MODE_REMOVE = "Удалить из чатов"
MODE_ADD = "Добавить в чаты"
MODE_UNBAN = "Снять бан"
MODES = (MODE_REMOVE, MODE_ADD, MODE_UNBAN)

SCOPE_QUICK = "Общие чаты (быстро)"
SCOPE_DEEP = "Все диалоги (долго)"

OK_COLOR = ("#1B7F3B", "#4CD07D")
FAIL_COLOR = ("#B3261E", "#FF8A80")

TITLE_MAX = 52
STATUS_MAX = 30
STATUS_WIDTH = 210
TYPE_WIDTH = 100

# С какого числа чатов операция считается массовой и требует явной отметки.
BULK_THRESHOLD = 5


def _shorten(text, limit):
    text = str(text or "")
    return (text[: limit - 1] + "…") if len(text) > limit else text


def _chat_kind_label(chat_id) -> str:
    kind = _peer_kind(chat_id)
    if kind == "channel":
        return "Супергруппа"
    if kind == "chat":
        return "Группа"
    return ""


def ban_entries_as_chats(entries, with_names=False):
    """Записи журнала → строки списка, чтобы переиспользовать всю таблицу."""
    items = []
    for entry in entries:
        note = "забанен %s" % entry.when
        if with_names:
            note = "%s · %s" % (entry.user_name, note)
        items.append(MemberChat(
            chat_id=entry.chat_id,
            title=entry.chat_title or str(entry.chat_id),
            type_str=_chat_kind_label(entry.chat_id),
            my_status="unknown",
            target_status="banned",
            can_manage=True,
            note=note,
        ))
    items.sort(key=lambda i: (i.title or "").lower())
    return items


class MemberRow(ctk.CTkFrame):
    """Строка списка: галочка, название чата, короткий статус и тип."""

    def __init__(
        self, parent, chat_id, title, type_str,
        status="", status_color=None, detail="", selected=False, on_check=None, **kw,
    ):
        super().__init__(parent, corner_radius=0, fg_color=CARD_BG, height=38, **kw)
        self.pack_propagate(False)
        self.chat_id = chat_id
        self._check_var = ctk.BooleanVar(value=selected)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=PAD_SM)

        ctk.CTkCheckBox(
            row, text="", variable=self._check_var, width=24, height=24,
            command=lambda: on_check(chat_id, self._check_var.get()) if on_check else None,
        ).pack(side="left", padx=(0, PAD_SM))

        title_label = ctk.CTkLabel(row, text=_shorten(title or chat_id, TITLE_MAX), anchor="w", font=font(13))
        title_label.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            row, text=type_str or "", width=TYPE_WIDTH, anchor="w", font=font(12), text_color=TEXT_MUTED,
        ).pack(side="right")
        status_label = ctk.CTkLabel(
            row, text=_shorten(status, STATUS_MAX), width=STATUS_WIDTH, anchor="w", font=font(12),
            text_color=status_color or TEXT_MUTED,
        )
        status_label.pack(side="right", padx=(0, PAD_SM))

        if detail:
            bind_tooltip(title_label, detail)
            bind_tooltip(status_label, detail)

    @property
    def is_checked(self) -> bool:
        return self._check_var.get()

    def set_checked(self, value: bool):
        self._check_var.set(value)


class MembersFrame(ctk.CTkFrame):
    """Поиск человека и массовые операции с его участием в чатах."""

    def __init__(self, parent, on_resolve_user, on_find_chats, on_load_chats, on_remove, on_add,
                 on_find_admins=None, on_unban=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_resolve_user = on_resolve_user
        self.on_find_chats = on_find_chats
        self.on_load_chats = on_load_chats
        self.on_remove = on_remove
        self.on_add = on_add
        self.on_find_admins = on_find_admins
        self.on_unban = on_unban

        self.target = None
        self.mode = MODE_REMOVE
        self._busy = False
        self._paused = False
        self._search_job = None
        self._admins_chats = 0
        # Свои списки и выбор для каждого режима, чтобы переключение их не сбрасывало.
        self._items = {mode: [] for mode in MODES}
        self._selected = {mode: set() for mode in MODES}
        self._results = {}

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(head, text="Участники", font=font(20, "bold")).pack(side="left")
        self.counter_label = ctk.CTkLabel(head, text="", text_color=TEXT_MUTED, font=font(12))
        self.counter_label.pack(side="right")

        # --- Кто ---------------------------------------------------------
        user_panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=RADIUS, border_width=1, border_color=BORDER)
        user_panel.pack(fill="x", pady=(0, PAD_SM))
        user_inner = ctk.CTkFrame(user_panel, fg_color="transparent")
        user_inner.pack(fill="x", padx=PAD, pady=PAD_SM)
        user_row = ctk.CTkFrame(user_inner, fg_color="transparent")
        user_row.pack(fill="x")
        ctk.CTkLabel(user_row, text="Кто:").pack(side="left", padx=(0, PAD_SM))
        self.user_var = ctk.StringVar()
        self.user_entry = ctk.CTkEntry(
            user_row, placeholder_text="@username, ID или +телефон", width=280, textvariable=self.user_var
        )
        self.user_entry.pack(side="left")
        self.user_entry.bind("<Return>", lambda _e: self._resolve_user())
        self.find_user_btn = ctk.CTkButton(
            user_row, text="Найти", command=self._resolve_user, corner_radius=BTN_RADIUS,
            width=100, height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        )
        self.find_user_btn.pack(side="left", padx=PAD_SM)
        self.user_label = ctk.CTkLabel(
            user_inner, text="Найдите человека по @username, ID, телефону или ссылке t.me.",
            anchor="w", font=font(12), text_color=TEXT_MUTED,
        )
        self.user_label.pack(fill="x", pady=(PAD_SM, 0))

        # --- Режим -------------------------------------------------------
        self.mode_switch = ctk.CTkSegmentedButton(
            self, values=list(MODES), command=self._on_mode_change,
        )
        self.mode_switch.set(MODE_REMOVE)
        self.mode_switch.pack(fill="x", pady=(0, PAD_SM))

        # --- Опции режима «удалить» --------------------------------------
        self.remove_options = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.remove_options, text="Искать:").pack(side="left", padx=(0, PAD_SM))
        self.scope_var = ctk.StringVar(value=SCOPE_QUICK)
        scope_combo = ctk.CTkComboBox(
            self.remove_options, values=[SCOPE_QUICK, SCOPE_DEEP], variable=self.scope_var,
            width=210, state="readonly",
        )
        scope_combo.pack(side="left", padx=(0, PAD))
        bind_tooltip(
            scope_combo,
            "Общие чаты — один запрос к Telegram, до 100 чатов.\n"
            "Все диалоги — проверка каждого чата по отдельности: полнее, но заметно дольше.",
        )
        self.ban_var = ctk.BooleanVar(value=True)
        ban_check = ctk.CTkCheckBox(
            self.remove_options, text="Забанить, чтобы не вернулся", variable=self.ban_var,
        )
        ban_check.pack(side="left")
        bind_tooltip(
            ban_check,
            "С галочкой человек не вернётся сам. Без неё — обычный кик: "
            "сможет зайти заново по ссылке-приглашению.",
        )

        # --- Опции режима «добавить» -------------------------------------
        self.add_options = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            self.add_options,
            text="Telegram может отказать из-за приватности человека, а массовые приглашения — "
                 "привести к ограничениям аккаунта.",
            anchor="w", font=font(12), text_color=TEXT_MUTED,
        ).pack(fill="x")

        # --- Опции режима «снять бан» ------------------------------------
        self.unban_options = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            self.unban_options,
            text="Список берётся из журнала: здесь только те баны, что поставили вы сами. "
                 "После снятия человек не вернётся сам — понадобится ссылка-приглашение.",
            anchor="w", font=font(12), text_color=TEXT_MUTED,
        ).pack(fill="x")

        # --- Кнопки операций ---------------------------------------------
        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.pack(fill="x", pady=(PAD_SM, 0))
        self.find_chats_btn = ctk.CTkButton(
            self.actions, text="Найти чаты", command=self._find_chats, corner_radius=BTN_RADIUS,
            width=150, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER, state="disabled",
        )
        self.remove_btn = ctk.CTkButton(
            self.actions, text="Удалить из выбранных", command=self._remove_selected, corner_radius=BTN_RADIUS,
            width=200, height=36, fg_color=DANGER, hover_color=DANGER_HOVER, state="disabled",
        )
        self.admins_btn = ctk.CTkButton(
            self.actions, text="Кто может удалить", command=self._find_admins, corner_radius=BTN_RADIUS,
            width=180, height=36, fg_color=BTN_SECONDARY, state="disabled",
        )
        bind_tooltip(
            self.admins_btn,
            "Соберёт администраторов тех чатов, где прав у вас нет, и покажет, "
            "кому написать. Один админ обычно закрывает сразу десятки чатов.",
        )
        self.load_chats_btn = ctk.CTkButton(
            self.actions, text="Загрузить чаты", command=self._load_chats, corner_radius=BTN_RADIUS,
            width=150, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        )
        self.add_btn = ctk.CTkButton(
            self.actions, text="Добавить в выбранные", command=self._add_selected, corner_radius=BTN_RADIUS,
            width=200, height=36, fg_color=BTN_SECONDARY, state="disabled",
        )
        self.load_bans_btn = ctk.CTkButton(
            self.actions, text="Показать баны", command=self.load_pending_bans, corner_radius=BTN_RADIUS,
            width=150, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        )
        bind_tooltip(
            self.load_bans_btn,
            "Читает журнал операций. Без выбранного человека покажет все ваши баны, "
            "с выбранным — только его.",
        )
        self.unban_btn = ctk.CTkButton(
            self.actions, text="Снять бан в выбранных", command=self._unban_selected, corner_radius=BTN_RADIUS,
            width=200, height=36, fg_color=BTN_SECONDARY, state="disabled",
        )
        self.pause_btn = ctk.CTkButton(
            self.actions, text="Пауза", command=self._toggle_pause, corner_radius=BTN_RADIUS,
            width=100, height=36, state="disabled",
        )
        self.stop_btn = ctk.CTkButton(
            self.actions, text="Стоп", command=self._stop, corner_radius=BTN_RADIUS, width=80, height=36,
            state="disabled", fg_color=("gray60", "gray35"), hover_color=("gray50", "gray40"),
        )

        self.status_label = ctk.CTkLabel(
            self, text="Укажите человека, затем найдите чаты.", text_color="gray", anchor="w",
        )
        self.status_label.pack(fill="x", pady=(PAD_SM, PAD_SM))

        self.progress = ProgressStrip(self)

        # --- Фильтры списка ----------------------------------------------
        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(tools, text="Раздел:").pack(side="left", padx=(0, PAD_SM))
        self.section_var = ctk.StringVar(value="Все")
        ctk.CTkComboBox(
            tools, values=["Все", "Группы", "Каналы"], variable=self.section_var, width=130,
            state="readonly", command=lambda _v: self._apply_filter(),
        ).pack(side="left", padx=(0, PAD))
        ctk.CTkLabel(tools, text="Поиск:").pack(side="left", padx=(0, PAD_SM))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_a: self._schedule_filter())
        ctk.CTkEntry(tools, placeholder_text="Название чата...", width=240, textvariable=self.search_var).pack(side="left")
        ctk.CTkButton(
            tools, text="Снять", command=lambda: self._set_visible_checks(False),
            corner_radius=BTN_RADIUS, width=80, height=28, fg_color=BTN_SECONDARY,
        ).pack(side="right", padx=(PAD_SM, 0))
        ctk.CTkButton(
            tools, text="Выбрать видимые", command=lambda: self._set_visible_checks(True),
            corner_radius=BTN_RADIUS, width=140, height=28, fg_color=BTN_SECONDARY,
        ).pack(side="right")

        header = ctk.CTkFrame(self, fg_color=("gray85", "gray16"), corner_radius=0, height=28)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="", width=42).pack(side="left")
        ctk.CTkLabel(header, text="Чат", anchor="w", font=font(12, "bold"), text_color=TEXT_MUTED).pack(
            side="left", fill="x", expand=True, padx=(0, PAD_SM)
        )
        # padx повторяет отступ строки списка, иначе заголовки уезжают от значений.
        ctk.CTkLabel(
            header, text="Тип", width=TYPE_WIDTH, anchor="w", font=font(12, "bold"), text_color=TEXT_MUTED,
        ).pack(side="right", padx=(0, PAD_SM))
        ctk.CTkLabel(
            header, text="Статус", width=STATUS_WIDTH, anchor="w", font=font(12, "bold"), text_color=TEXT_MUTED,
        ).pack(side="right", padx=(0, PAD_SM))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=0)
        self.scroll.pack(fill="both", expand=True)

        self._on_mode_change(MODE_REMOVE)

    # ------------------------------------------------------------------
    # Пользователь
    # ------------------------------------------------------------------

    def _resolve_user(self):
        if self._busy:
            return
        query = (self.user_var.get() or "").strip()
        if not query:
            messagebox.showinfo("Участники", "Введите @username, ID или телефон.")
            return
        self.user_label.configure(text="Ищу пользователя…", text_color=TEXT_MUTED)
        self.find_user_btn.configure(state="disabled")
        self.on_resolve_user(query)

    def set_user(self, target):
        """Показать найденного пользователя и разблокировать операции."""
        self.target = target
        self.find_user_btn.configure(state="normal")
        self.user_label.configure(text=target.summary, text_color=ACCENT)
        # Найденные ранее чаты относились к другому человеку.
        self._items[MODE_REMOVE] = []
        self._selected[MODE_REMOVE].clear()
        self._items[MODE_UNBAN] = []
        self._selected[MODE_UNBAN].clear()
        self._results = {}
        self._apply_filter()
        self.status_label.configure(
            text="Пользователь найден. «Найти чаты» — посмотреть, откуда его можно удалить."
        )
        self._sync_buttons()

    def set_user_error(self, text):
        self.target = None
        self.find_user_btn.configure(state="normal")
        self.user_label.configure(text=text, text_color=FAIL_COLOR)
        self._sync_buttons()

    # ------------------------------------------------------------------
    # Режимы
    # ------------------------------------------------------------------

    def _on_mode_change(self, value):
        self.mode = value
        for panel in (self.remove_options, self.add_options, self.unban_options):
            panel.pack_forget()
        options = {
            MODE_REMOVE: self.remove_options,
            MODE_ADD: self.add_options,
            MODE_UNBAN: self.unban_options,
        }[value]
        options.pack(fill="x", after=self.mode_switch)
        # Кнопки пакуются справа налево, поэтому порядок задаём заново на каждом переключении.
        for btn in (self.find_chats_btn, self.remove_btn, self.admins_btn, self.load_chats_btn,
                    self.add_btn, self.load_bans_btn, self.unban_btn, self.pause_btn, self.stop_btn):
            btn.pack_forget()
        order = {
            MODE_REMOVE: [self.find_chats_btn, self.remove_btn, self.admins_btn],
            MODE_ADD: [self.load_chats_btn, self.add_btn],
            MODE_UNBAN: [self.load_bans_btn, self.unban_btn],
        }[value]
        for btn in order + [self.pause_btn, self.stop_btn]:
            btn.pack(side="right", padx=PAD_SM)
        self._results = {}
        self._apply_filter()
        self._sync_buttons()

    def _sync_buttons(self):
        if self._busy:
            return
        has_user = self.target is not None
        selected = len(self._selected[self.mode])
        self.find_chats_btn.configure(state="normal" if has_user else "disabled")
        self.remove_btn.configure(state="normal" if has_user and selected else "disabled")
        self.add_btn.configure(state="normal" if has_user and selected else "disabled")
        self.admins_btn.configure(state="normal" if self._chats_without_rights() else "disabled")
        self.unban_btn.configure(state="normal" if selected and self.mode == MODE_UNBAN else "disabled")

    # ------------------------------------------------------------------
    # Запуск операций
    # ------------------------------------------------------------------

    def _find_chats(self):
        if self._busy or not self.target:
            return
        deep = self.scope_var.get() == SCOPE_DEEP
        if deep and not confirm_action(
            self.winfo_toplevel(),
            "Полный обход",
            "Проверить каждый диалог по отдельности?",
            note="Это может занять много минут, а Telegram — притормозить аккаунт. "
                 "Быстрый поиск по общим чатам обычно находит всё то же самое.",
            confirm_text="Обойти всё",
        ):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        self._items[MODE_REMOVE] = []
        self._selected[MODE_REMOVE].clear()
        self._results = {}
        self._apply_filter()
        self.set_busy(True, "Ищу чаты")
        self.status_label.configure(text="Ищу чаты, где состоит %s…" % self.target.display_name)
        # Ищем везде; «Раздел» ниже фильтрует только показ найденного.
        self.on_find_chats(self.target.user_id, deep, True, True)

    def _load_chats(self):
        if self._busy:
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        self._items[MODE_ADD] = []
        self._selected[MODE_ADD].clear()
        self._results = {}
        self._apply_filter()
        self.set_busy(True, "Загружаю чаты")
        self.status_label.configure(text="Загружаю список групп и каналов…")
        self.on_load_chats(True, True)

    def load_pending_bans(self):
        """Показать собственные баны из журнала: только их и можно откатить."""
        if self._busy:
            return
        user_id = self.target.user_id if self.target else None
        try:
            entries = pending_bans(user_id)
        except Exception as e:
            log.warning("Журнал не прочитан: %s", e)
            entries = []
        self._items[MODE_UNBAN] = ban_entries_as_chats(entries, with_names=user_id is None)
        self._selected[MODE_UNBAN] = {i.chat_id for i in self._items[MODE_UNBAN]}
        self._results = {}
        self._apply_filter()
        if not entries:
            whose = "у %s" % self.target.display_name if self.target else "в журнале"
            self.status_label.configure(text="Незакрытых банов %s нет." % whose)
        else:
            self.status_label.configure(
                text="Ваших банов в силе: %s. Отметьте, какие снять." % len(entries)
            )

    def _selected_pairs(self):
        selected = self._selected[self.mode]
        return [(item.chat_id, item.title) for item in self._items[self.mode] if item.chat_id in selected]

    def _remove_selected(self):
        if self._busy or not self.target:
            return
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showinfo("Участники", "Отметьте хотя бы один чат.")
            return
        ban = bool(self.ban_var.get())
        summary = "%s %s из %s чат(ов)?" % (
            "Удалить и забанить" if ban else "Удалить", self.target.summary, len(pairs),
        )
        note = ("Забаненный не вернётся сам. Откатить можно на вкладке «Снять бан» — "
                "операция записывается в журнал."
                if ban else
                "Без бана человек сможет зайти заново по ссылке-приглашению.")
        ack = None
        if ban or len(pairs) > BULK_THRESHOLD:
            ack = "Понимаю, что это затронет других людей"
        if not confirm_action(
            self.winfo_toplevel(), "Удаление участника", summary,
            items=[t for _cid, t in pairs], note=note, danger=True,
            ack_text=ack, confirm_text="Удалить" if not ban else "Удалить и забанить",
        ):
            return
        self._start_action("Удаляю", len(pairs))
        self.on_remove(self.target.user_id, pairs, ban)

    def _add_selected(self):
        if self._busy or not self.target:
            return
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showinfo("Участники", "Отметьте хотя бы один чат.")
            return
        ack = "Понимаю риск ограничений за массовые приглашения" if len(pairs) > BULK_THRESHOLD else None
        if not confirm_action(
            self.winfo_toplevel(), "Добавление участника",
            "Добавить %s в %s чат(ов)?" % (self.target.summary, len(pairs)),
            items=[t for _cid, t in pairs],
            note="Telegram может отказать из-за настроек приватности человека, "
                 "а массовые приглашения — привести к ограничениям аккаунта.",
            ack_text=ack, confirm_text="Добавить",
        ):
            return
        self._start_action("Добавляю", len(pairs))
        self.on_add(self.target.user_id, pairs)

    def _unban_selected(self):
        if self._busy or not self.on_unban:
            return
        pairs = self._selected_pairs()
        if not pairs:
            messagebox.showinfo("Участники", "Отметьте хотя бы один чат.")
            return
        target_id = self.target.user_id if self.target else None
        if target_id is None:
            messagebox.showinfo(
                "Участники",
                "Сначала найдите человека — снимать бан нужно у конкретного пользователя.",
            )
            return
        whose = self.target.summary
        if not confirm_action(
            self.winfo_toplevel(), "Снятие бана",
            "Снять бан с %s в %s чат(ах)?" % (whose, len(pairs)),
            items=[t for _cid, t in pairs],
            note="Человек не вернётся сам: бан снимается, но зайти он должен по ссылке.",
            confirm_text="Снять бан",
        ):
            return
        self._start_action("Снимаю бан", len(pairs))
        self.on_unban(target_id, pairs)

    def _start_action(self, stage, total):
        scan_paused.clear()
        scan_stop_requested.clear()
        self._results = {}
        self.set_busy(True, stage, total=total)
        self.status_label.configure(text="%s: 0/%s…" % (stage, total))

    def _chats_without_rights(self):
        """Чаты, где удалить сами не можем, — именно там нужен чужой админ."""
        return [(c.chat_id, c.title) for c in self._items[MODE_REMOVE] if not c.can_manage]

    def _find_admins(self):
        if self._busy or not self.on_find_admins:
            return
        pairs = self._chats_without_rights()
        if not pairs:
            messagebox.showinfo(
                "Участники",
                "Нет чатов, где вам не хватает прав. Сначала нажмите «Найти чаты».",
            )
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        self._admins_chats = len(pairs)
        self.set_busy(True, "Ищу админов", total=len(pairs))
        self.status_label.configure(text="Собираю админов: 0/%s…" % len(pairs))
        self.on_find_admins(pairs, self.target.user_id if self.target else None)

    def update_admins_progress(self, n, total, title):
        self.progress.update_progress(done=n, total=total, detail=title)

    def finish_admins(self, admins, stopped):
        self.set_busy(False)
        prefix = "Поиск остановлен." if stopped else "Готово."
        self.progress.finish("Админы собраны" if not stopped else "Остановлено", ok=not stopped)
        self.status_label.configure(
            text="%s Людей, которые могут удалить: %s." % (prefix, len(admins))
        )
        AdminsDialog(
            self.winfo_toplevel(),
            admins,
            target_name=self.target.display_name if self.target else "",
            chats_count=getattr(self, "_admins_chats", 0),
            stopped=stopped,
        )

    # ------------------------------------------------------------------
    # Состояние выполнения
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool, label: str | None = None, total=None):
        self._busy = busy
        self._paused = False
        if busy:
            for btn in (self.find_user_btn, self.find_chats_btn, self.load_chats_btn, self.load_bans_btn,
                        self.remove_btn, self.add_btn, self.unban_btn, self.admins_btn):
                btn.configure(state="disabled")
            self.find_chats_btn.configure(text=label or "Выполняется")
            self.pause_btn.configure(state="normal", text="Пауза")
            self.stop_btn.configure(state="normal")
            self.progress.pack(fill="x", pady=(0, PAD_SM), before=self.status_label)
            self.progress.start(label or "Выполняется", total)
        else:
            scan_paused.clear()
            self.find_user_btn.configure(state="normal")
            self.find_chats_btn.configure(text="Найти чаты")
            self.load_chats_btn.configure(state="normal")
            self.load_bans_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled", text="Пауза")
            self.stop_btn.configure(state="disabled")
            self._sync_buttons()

    def _toggle_pause(self):
        if not self._busy:
            return
        if self._paused:
            scan_paused.clear()
            self._paused = False
            self.pause_btn.configure(text="Пауза")
            self.status_label.configure(text="Продолжаю…")
        else:
            scan_paused.set()
            self._paused = True
            self.pause_btn.configure(text="Продолжить")
            self.status_label.configure(text="Пауза.")

    def _stop(self):
        if not self._busy:
            return
        scan_stop_requested.set()
        scan_paused.clear()
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="Останавливаю…")

    # ------------------------------------------------------------------
    # Приём данных от воркера
    # ------------------------------------------------------------------

    def update_search_progress(self, n, total, title):
        """Ход поиска чатов: n=0 — это этап, а не конкретный чат."""
        if not n:
            self.progress.update_progress(total=total, detail="", stage=title or "Ищу чаты")
            return
        self.progress.update_progress(done=n, total=total, detail=title)

    def add_found_chat(self, mc: MemberChat):
        self._items[MODE_REMOVE].append(mc)
        if mc.can_manage:
            self._selected[MODE_REMOVE].add(mc.chat_id)
        if self.mode == MODE_REMOVE and self._matches(mc) and self._rendered_count() < VISIBLE_LIMIT:
            self._drop_placeholder()
            self._build_row(mc)
        self._update_counters()

    def finish_find_chats(self, chats, stopped):
        self._items[MODE_REMOVE] = list(chats)
        self._selected[MODE_REMOVE] = {c.chat_id for c in chats if c.can_manage}
        self.set_busy(False)
        self._apply_filter()
        manageable = sum(1 for c in chats if c.can_manage)
        prefix = "Поиск остановлен." if stopped else "Поиск завершён."
        self.progress.finish("Остановлено" if stopped else "Поиск завершён", ok=not stopped)
        if not chats:
            self.status_label.configure(text=prefix + " Общих чатов с этим человеком не нашлось.")
        else:
            self.status_label.configure(
                text="%s Чатов: %s, удалить можно из %s." % (prefix, len(chats), manageable)
            )

    def update_dialogs_progress(self, n, title):
        self.progress.update_progress(done=n, detail=title)

    def append_dialogs(self, batch):
        self._items[MODE_ADD].extend(batch)
        if self.mode == MODE_ADD:
            for place in batch:
                if self._matches(place) and self._rendered_count() < VISIBLE_LIMIT:
                    self._drop_placeholder()
                    self._build_row(place)
        self._update_counters()

    def finish_load_chats(self, dialogs, stopped):
        self._items[MODE_ADD] = list(dialogs)
        self._selected[MODE_ADD].intersection_update({p.chat_id for p in dialogs})
        self.set_busy(False)
        self._apply_filter()
        prefix = "Список остановлен." if stopped else "Список загружен."
        self.progress.finish("Остановлено" if stopped else "Список загружен", ok=not stopped)
        self.status_label.configure(text="%s Чатов: %s. Отметьте нужные." % (prefix, len(dialogs)))

    def update_action_progress(self, action, current, total, result):
        self._results[result.chat_id] = result
        verb = {"remove": "Удаляю", "add": "Добавляю", "unban": "Снимаю бан"}.get(action, "Работаю")
        self.progress.update_progress(
            done=current, total=total, stage=verb,
            detail="%s — %s" % (_shorten(result.title, 28), result.note),
        )
        log.info("%s: %s — %s", verb, result.title, result.note)

    def finish_action(self, action, results, stopped):
        self.set_busy(False)
        for result in results:
            self._results[result.chat_id] = result
        if not results:
            # Причину уже показал обработчик ошибки — статус не затираем.
            self.progress.finish("Не выполнено", ok=False)
            return
        ok = sum(1 for r in results if r.ok)
        failed = len(results) - ok
        if action == "remove":
            done_ids = {r.chat_id for r in results if r.ok}
            self._items[MODE_REMOVE] = [c for c in self._items[MODE_REMOVE] if c.chat_id not in done_ids]
            self._selected[MODE_REMOVE].difference_update(done_ids)
        elif action == "unban":
            done_ids = {r.chat_id for r in results if r.ok}
            self._items[MODE_UNBAN] = [c for c in self._items[MODE_UNBAN] if c.chat_id not in done_ids]
            self._selected[MODE_UNBAN].difference_update(done_ids)
        else:
            self._selected[MODE_ADD].difference_update({r.chat_id for r in results if r.ok})
        self._apply_filter()
        title = "Остановлено" if stopped else "Готово"
        verb = {"remove": "Удалено", "add": "Добавлено", "unban": "Бан снят"}.get(action, "Обработано")
        summary = "%s: %s из %s чатов." % (verb, ok, len(results))
        self.progress.finish(title, ok=not stopped and not failed)
        self.status_label.configure(text=summary)
        details = "\n".join("• %s — %s" % (r.title, r.note) for r in results if not r.ok)
        if failed and details:
            summary += "\n\nНе получилось (%s):\n%s" % (failed, details[:1500])
        messagebox.showinfo(title, summary)

    def reset(self):
        """Сброс при смене аккаунта."""
        self.target = None
        self._items = {mode: [] for mode in MODES}
        self._selected = {mode: set() for mode in MODES}
        self._results = {}
        self._admins_chats = 0
        self.set_busy(False)
        self.progress.hide()
        self.user_label.configure(
            text="Найдите человека по @username, ID, телефону или ссылке t.me.", text_color=TEXT_MUTED
        )
        self._apply_filter()
        self.status_label.configure(text="Укажите человека, затем найдите чаты.")

    # ------------------------------------------------------------------
    # Список чатов
    # ------------------------------------------------------------------

    def _schedule_filter(self):
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(300, self._apply_filter)

    def _matches(self, item):
        section = self.section_var.get()
        type_str = getattr(item, "type_str", "")
        if section == "Каналы" and type_str != "Канал":
            return False
        if section == "Группы" and type_str not in ("Группа", "Супергруппа"):
            return False
        search = (self.search_var.get() or "").strip().lower()
        return not search or search in (getattr(item, "title", "") or "").lower()

    def _rendered_count(self):
        return len([w for w in self.scroll.winfo_children() if isinstance(w, MemberRow)])

    def _drop_placeholder(self):
        """Убрать «Список пуст», иначе он повиснет над приходящими строками."""
        for widget in self.scroll.winfo_children():
            if not isinstance(widget, MemberRow):
                widget.destroy()

    def _row_status(self, item):
        """Короткий статус, его цвет и подробности для подсказки."""
        result = self._results.get(item.chat_id)
        if result is not None:
            return result.note, (OK_COLOR if result.ok else FAIL_COLOR), "%s — %s" % (item.title, result.note)
        if not isinstance(item, MemberChat):
            return "", None, ""
        if self.mode == MODE_UNBAN:
            return item.note, None, "%s · %s" % (item.title, item.note)
        detail = " · ".join(p for p in (
            "Он: " + TARGET_STATUS_LABELS.get(item.target_status, item.target_status),
            MY_STATUS_LABELS.get(item.my_status, "ваш статус неизвестен").capitalize(),
            item.note,
        ) if p)
        return item.note, (None if item.can_manage else TEXT_MUTED), detail

    def _build_row(self, item):
        status, color, detail = self._row_status(item)
        row = MemberRow(
            self.scroll,
            chat_id=item.chat_id,
            title=item.title,
            type_str=item.type_str,
            status=status,
            status_color=color,
            detail=detail,
            selected=item.chat_id in self._selected[self.mode],
            on_check=self._on_check,
        )
        row.pack(fill="x", pady=(0, 1))
        return row

    def _empty_hint(self):
        return {
            MODE_REMOVE: "Нажмите «Найти чаты».",
            MODE_ADD: "Нажмите «Загрузить чаты».",
            MODE_UNBAN: "Нажмите «Показать баны».",
        }[self.mode]

    def _apply_filter(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
        items = [i for i in self._items[self.mode] if self._matches(i)]
        items.sort(key=lambda i: ((not getattr(i, "can_manage", True)), (i.title or "").lower()))
        if not items:
            empty = ctk.CTkFrame(self.scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=PAD * 3)
            ctk.CTkLabel(empty, text="Список пуст. " + self._empty_hint(),
                         font=font(14), text_color="gray").pack(expand=True)
            self._update_counters(visible=0)
            return
        for item in items[:VISIBLE_LIMIT]:
            self._build_row(item)
        if len(items) > VISIBLE_LIMIT:
            more = ctk.CTkFrame(self.scroll, fg_color="transparent")
            more.pack(fill="x", pady=PAD_SM)
            ctk.CTkLabel(
                more,
                text="Показаны первые %s из %s. Уточните поиск или раздел." % (VISIBLE_LIMIT, len(items)),
                font=font(12), text_color=TEXT_MUTED,
            ).pack(anchor="center")
        self._update_counters(visible=len(items))

    def _on_check(self, chat_id, checked):
        if checked:
            self._selected[self.mode].add(chat_id)
        else:
            self._selected[self.mode].discard(chat_id)
        self._update_counters()

    def _set_visible_checks(self, value: bool):
        for row in self.scroll.winfo_children():
            if isinstance(row, MemberRow):
                row.set_checked(value)
                if value:
                    self._selected[self.mode].add(row.chat_id)
                else:
                    self._selected[self.mode].discard(row.chat_id)
        self._update_counters()

    def _update_counters(self, visible=None):
        items = self._items[self.mode]
        if visible is None:
            visible = len([i for i in items if self._matches(i)])
        self.counter_label.configure(
            text="Всего: %s · видно: %s · выбрано: %s" % (len(items), visible, len(self._selected[self.mode]))
        )
        self._sync_buttons()
