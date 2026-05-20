
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
Экран «Чаты с вашими сообщениями»: скан, фильтры, пауза, карточки чатов, сортировка, поиск.
"""
import customtkinter as ctk
from tkinter import messagebox, filedialog

from core import Place, get_current_session, get_scan_include_groups, get_scan_include_channels, get_scan_include_private, get_api_config, save_api_config
from ui.theme import (
    PAD,
    PAD_SM,
    RADIUS,
    BTN_RADIUS,
    ACCENT,
    ACCENT_HOVER,
    DANGER,
    DANGER_HOVER,
    CARD_BG,
    SCROLL_FRAME_BG,
    BTN_SECONDARY,
    font,
)
from ui.queues import request_queue, scan_paused, scan_stop_requested
from ui.cache_export import export_places_to_csv, export_places_to_json
from ui.tooltip import bind_tooltip
from ui.chat_card import ChatCard

VISIBLE_LIMIT = 400


class PlacesFrame(ctk.CTkFrame):
    """Экран 1: Чаты с вашими сообщениями — скан, фильтры, пауза, карточки чатов, сортировка, поиск."""

    def __init__(self, parent, on_open_place, on_start_scan=None, on_refresh_cache=None, on_export_places=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_open_place = on_open_place
        self.on_start_scan = on_start_scan
        self.on_refresh_cache = on_refresh_cache
        self.on_export_places = on_export_places
        self.places: list = []
        self._scanning = False
        self._paused = False
        self._selected_chat_ids = set()
        self._selected_card = None
        self._selected_place = None
        self._search_job = None
        self._rendered_count = 0

        # Заголовок
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(head, text="Чаты с вашими сообщениями", font=font(20, "bold")).pack(side="left")

        # Блок «Настройки сканирования»
        scan_block = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=RADIUS, border_width=1, border_color=("gray85", "gray25"))
        scan_block.pack(fill="x", pady=(0, PAD_SM))
        scan_inner = ctk.CTkFrame(scan_block, fg_color="transparent")
        scan_inner.pack(fill="x", padx=PAD, pady=PAD_SM)
        ctk.CTkLabel(scan_inner, text="Настройки сканирования", font=font(12, "bold"), text_color="gray").pack(anchor="w")
        filters_row = ctk.CTkFrame(scan_inner, fg_color="transparent")
        filters_row.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(filters_row, text="Проверять:").pack(side="left", padx=(0, PAD_SM))
        self.check_groups = ctk.BooleanVar(value=get_scan_include_groups())
        ctk.CTkCheckBox(filters_row, text="Группы", variable=self.check_groups).pack(side="left", padx=PAD_SM)
        self.check_channels = ctk.BooleanVar(value=get_scan_include_channels())
        ctk.CTkCheckBox(filters_row, text="Каналы", variable=self.check_channels).pack(side="left", padx=PAD_SM)
        self.check_private = ctk.BooleanVar(value=get_scan_include_private())
        ctk.CTkCheckBox(filters_row, text="Личку", variable=self.check_private).pack(side="left", padx=PAD_SM)
        ctk.CTkLabel(filters_row, text="Глубина:").pack(side="left", padx=(PAD, PAD_SM))
        self.depth_options = [("10 моих на чат", 10), ("50 моих на чат", 50), ("Без ограничения", None)]
        cfg = get_api_config()
        depth_cfg = cfg.get("scan_depth_per_chat")
        depth_label_default = "10 моих на чат"
        for label, val in self.depth_options:
            if val == depth_cfg:
                depth_label_default = label
                break
        self.depth_var = ctk.StringVar(value=depth_label_default)
        self.depth_combo = ctk.CTkComboBox(
            filters_row,
            values=[t[0] for t in self.depth_options],
            variable=self.depth_var,
            width=160,
        )
        self.depth_combo.pack(side="left", padx=PAD_SM)
        self._depth_hint = ctk.CTkLabel(scan_inner, text="Макс. своих сообщений в одном чате (меньше — быстрее скан)", font=font(11), text_color="gray")
        self._depth_hint.pack(anchor="w", pady=(2, 0))
        bind_tooltip(self.depth_combo, "Максимум ваших сообщений в каждом чате. Меньше значение — быстрее скан и меньше нагрузка на API.")

        # Кнопки действий: основная + вторичные
        actions_row = ctk.CTkFrame(self, fg_color="transparent")
        actions_row.pack(fill="x", pady=(0, PAD_SM))
        self.scan_btn = ctk.CTkButton(
            actions_row, text="Сканировать", command=self._start_scan,
            corner_radius=BTN_RADIUS, width=120, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER
        )
        self.scan_btn.pack(side="right", padx=PAD_SM)
        self.pause_btn = ctk.CTkButton(
            actions_row, text="Пауза", command=self._toggle_pause,
            corner_radius=BTN_RADIUS, width=100, height=36, state="disabled"
        )
        self.pause_btn.pack(side="right", padx=PAD_SM)
        self.stop_btn = ctk.CTkButton(
            actions_row, text="Стоп", command=self._stop_scan,
            corner_radius=BTN_RADIUS, width=80, height=36, state="disabled",
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray40")
        )
        self.stop_btn.pack(side="right", padx=PAD_SM)
        if on_refresh_cache:
            ctk.CTkButton(
                actions_row, text="Обновить из кэша", command=on_refresh_cache,
                corner_radius=BTN_RADIUS, width=140, height=36, fg_color=BTN_SECONDARY
            ).pack(side="right", padx=PAD_SM)
        ctk.CTkButton(
            actions_row, text="Экспорт CSV", command=self._export_csv,
            corner_radius=BTN_RADIUS, width=100, height=36, fg_color=BTN_SECONDARY
        ).pack(side="right", padx=PAD_SM)
        ctk.CTkButton(
            actions_row, text="Экспорт JSON", command=self._export_json,
            corner_radius=BTN_RADIUS, width=100, height=36, fg_color=BTN_SECONDARY
        ).pack(side="right", padx=PAD_SM)
        self.export_chats_btn = ctk.CTkButton(
            actions_row, text="Экспорт выбранных", command=self._export_selected_places,
            corner_radius=BTN_RADIUS, width=150, height=36, fg_color=BTN_SECONDARY
        )
        self.export_chats_btn.pack(side="right", padx=PAD_SM)
        ctk.CTkButton(
            actions_row, text="Выбрать видимые", command=lambda: self._set_visible_checks(True),
            corner_radius=BTN_RADIUS, width=140, height=36, fg_color=BTN_SECONDARY
        ).pack(side="right", padx=PAD_SM)
        ctk.CTkButton(
            actions_row, text="Снять", command=lambda: self._set_visible_checks(False),
            corner_radius=BTN_RADIUS, width=80, height=36, fg_color=BTN_SECONDARY
        ).pack(side="right", padx=PAD_SM)

        self.status_label = ctk.CTkLabel(self, text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать» или «Обновить из кэша».", text_color="gray")
        self.status_label.pack(fill="x", pady=(0, PAD_SM))
        self.counter_label = ctk.CTkLabel(self, text="", text_color="gray", font=font(12))
        self.counter_label.pack(fill="x", pady=(0, PAD_SM))

        # Меню разделов
        self.current_section = "all"
        menu_row = ctk.CTkFrame(self, fg_color="transparent")
        menu_row.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(menu_row, text="Смотреть:", font=font(weight="bold")).pack(side="left", padx=(0, PAD_SM))
        def _section_btn(label, key):
            b = ctk.CTkButton(menu_row, text=label, command=lambda: self._set_section(key), corner_radius=BTN_RADIUS, width=90, height=32, fg_color=("gray75", "gray25"))
            b.pack(side="left", padx=2)
            return b
        self.btn_all = _section_btn("Все", "all")
        self.btn_channels = _section_btn("Каналы", "channels")
        self.btn_groups = _section_btn("Группы", "groups")
        self.btn_private = _section_btn("Личка", "private")

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=4)
        self.progress.pack(fill="x", pady=(0, PAD))
        self.progress.pack_forget()

        # Сортировка и поиск
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(toolbar, text="Сортировка:").pack(side="left", padx=(0, PAD_SM))
        self.sort_var = ctk.StringVar(value="По названию")
        self.sort_combo = ctk.CTkComboBox(
            toolbar, values=["По названию", "По количеству постов"],
            variable=self.sort_var, width=180, command=lambda v: self._apply_sort_filter()
        )
        self.sort_combo.pack(side="left", padx=(0, PAD))
        ctk.CTkLabel(toolbar, text="Поиск:").pack(side="left", padx=(0, PAD_SM))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._schedule_filter())
        self.search_entry = ctk.CTkEntry(toolbar, placeholder_text="Название чата...", width=200, textvariable=self.search_var)
        self.search_entry.pack(side="left")

        # Список чатов — карточки в скролле
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=RADIUS)
        self.scroll.pack(fill="both", expand=True, pady=(0, PAD))

        self.open_btn = ctk.CTkButton(
            self, text="Открыть", command=self._open_selected,
            corner_radius=BTN_RADIUS, width=120, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER
        )
        self.open_btn.pack(pady=PAD_SM)
        self.delete_batch_btn = ctk.CTkButton(
            self, text="Удалить в выбранных чатах", command=self._delete_in_selected_places,
            corner_radius=BTN_RADIUS, width=200, height=36, fg_color=DANGER, hover_color=DANGER_HOVER
        )
        self.delete_batch_btn.pack(pady=PAD_SM)

    def _schedule_filter(self):
        if not self.winfo_exists():
            return
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(300, self._apply_sort_filter)

    def _set_section(self, key):
        self.current_section = key
        self._update_section_buttons()
        self._apply_sort_filter()

    def _update_section_buttons(self):
        for btn, k in [(self.btn_all, "all"), (self.btn_channels, "channels"), (self.btn_groups, "groups"), (self.btn_private, "private")]:
            if btn.winfo_exists():
                btn.configure(fg_color=(ACCENT, ACCENT) if self.current_section == k else ("gray75", "gray25"))

    def _start_scan(self):
        if not get_current_session():
            messagebox.showwarning("Сканирование", "Сначала добавьте аккаунт в левой панели.")
            return
        if self.on_start_scan:
            self.on_start_scan()
        scan_paused.clear()
        scan_stop_requested.clear()
        self.set_scanning(True, label="Сканирую")
        self.status_label.configure(text="Сканирую диалоги…")
        depth_val = None
        for label, val in self.depth_options:
            if self.depth_var.get() == label:
                depth_val = val
                break
        try:
            c = get_api_config()
            c["scan_include_groups"] = self.check_groups.get()
            c["scan_include_channels"] = self.check_channels.get()
            c["scan_include_private"] = self.check_private.get()
            c["scan_depth_per_chat"] = depth_val
            save_api_config(c)
        except Exception:
            pass
        request_queue.put((
            "scan",
            self.check_groups.get(),
            self.check_channels.get(),
            self.check_private.get(),
            scan_paused,
            depth_val,
            scan_stop_requested,
        ))

    def _toggle_pause(self):
        if not self._scanning:
            return
        if self._paused:
            scan_paused.clear()
            self._paused = False
            self.pause_btn.configure(text="Пауза")
            self.status_label.configure(text="Продолжаю операцию...")
        else:
            scan_paused.set()
            self._paused = True
            self.pause_btn.configure(text="Продолжить")
            self.status_label.configure(text="Пауза. Нажмите «Продолжить» для возобновления.")

    def _stop_scan(self):
        if not self._scanning:
            return
        scan_stop_requested.set()
        scan_paused.clear()
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.status_label.configure(text="Останавливаю операцию...")

    def set_scanning(self, scanning: bool, label: str | None = None):
        self._scanning = scanning
        self._paused = False
        if scanning:
            self.scan_btn.configure(state="disabled", text=label or "Выполняется")
            self.pause_btn.configure(state="normal", text="Пауза")
            self.stop_btn.configure(state="normal")
            self.export_chats_btn.configure(state="disabled")
            self.delete_batch_btn.configure(state="disabled")
            self.progress.pack(fill="x", pady=(0, PAD))
            self.progress.start()
        else:
            scan_paused.clear()
            self.scan_btn.configure(state="normal", text="Сканировать")
            self.pause_btn.configure(state="disabled", text="Пауза")
            self.stop_btn.configure(state="disabled")
            self.export_chats_btn.configure(state="normal")
            self.delete_batch_btn.configure(state="normal")
            self.progress.stop()
            self.progress.pack_forget()

    def set_places(self, places):
        self.places = list(places)
        existing = {p.chat_id for p in self.places}
        self._selected_chat_ids.intersection_update(existing)
        self._update_section_buttons()
        self._apply_sort_filter()

    def _build_place_card(self, place: Place):
        """Создать карточку чата в self.scroll и вернуть её."""
        card = ChatCard(
            self.scroll, place,
            selected=place.chat_id in self._selected_chat_ids,
            compact=False,
            on_check=self._on_card_check,
            on_click=self._on_card_click,
            on_double_click=self.on_open_place,
        )
        card.pack(fill="x", pady=4, padx=2)
        return card

    def _on_card_click(self, card: ChatCard):
        if self._selected_card is not None and self._selected_card.winfo_exists():
            self._selected_card.configure(fg_color=CARD_BG)
        card.configure(fg_color=("gray75", "gray28"))
        self._selected_card = card
        self._selected_place = card.place

    def append_place(self, place: Place):
        """Добавить один чат в конец списка и одну карточку (потоковый вывод)."""
        self.places.append(place)
        if getattr(self, "current_section", "all") == "channels" and place.type_str != "Канал":
            return
        if self.current_section == "groups" and place.type_str not in ("Группа", "Супергруппа"):
            return
        if self.current_section == "private" and place.type_str not in ("Личный", "Бот"):
            return
        for widget in self.scroll.winfo_children():
            if not isinstance(widget, ChatCard):
                widget.destroy()
        if self._rendered_count < VISIBLE_LIMIT:
            self._build_place_card(place)
            self._rendered_count += 1
        self._update_counter()

    def _apply_sort_filter(self):
        """Перестроить список с учётом раздела, сортировки и поиска."""
        if getattr(self, "current_section", None) == "channels":
            base = [p for p in self.places if p.type_str == "Канал"]
        elif self.current_section == "groups":
            base = [p for p in self.places if p.type_str in ("Группа", "Супергруппа")]
        elif self.current_section == "private":
            base = [p for p in self.places if p.type_str in ("Личный", "Бот")]
        else:
            base = list(self.places)
        search = (self.search_var.get() or "").strip().lower()
        if search:
            base = [p for p in base if search in (p.title or "").lower()]
        sort_by = self.sort_var.get()
        if sort_by == "По количеству постов":
            items = sorted(base, key=lambda p: -len(p.messages))
        else:
            items = sorted(base, key=lambda p: (p.title or "").lower())
        for w in self.scroll.winfo_children():
            w.destroy()
        self._rendered_count = 0
        self._selected_card = None
        if not items:
            self._show_empty_places()
            self._selected_place = None
            return
        rendered = items[:VISIBLE_LIMIT]
        for p in rendered:
            self._build_place_card(p)
        self._rendered_count = len(rendered)
        if len(items) > VISIBLE_LIMIT:
            more = ctk.CTkFrame(self.scroll, fg_color="transparent")
            more.pack(fill="x", pady=PAD_SM)
            ctk.CTkLabel(
                more,
                text=f"Показаны первые {VISIBLE_LIMIT} из {len(items)}. Уточните поиск или раздел.",
                font=font(12),
                text_color="gray",
            ).pack(anchor="center")
        self._selected_place = None
        self._update_counter(visible=len(items))

    def _show_empty_places(self):
        """Показать пустое состояние в списке чатов."""
        empty = ctk.CTkFrame(self.scroll, fg_color="transparent")
        empty.pack(fill="both", expand=True, pady=PAD * 3)
        ctk.CTkLabel(empty, text="💬", font=font(36)).pack(pady=(0, PAD_SM))
        if self.places:
            msg = "По выбранным фильтрам чатов не найдено.\nИзмените раздел или поиск."
        else:
            msg = "Чатов с вашими сообщениями не найдено.\nНажмите «Сканировать» или «Обновить из кэша»."
        ctk.CTkLabel(empty, text=msg, font=font(14), text_color="gray", justify="center").pack(expand=True)
        self._update_counter(visible=0)

    def _set_visible_checks(self, value: bool):
        for card in self.scroll.winfo_children():
            if isinstance(card, ChatCard):
                card.set_checked(value)
                if value:
                    self._selected_chat_ids.add(card.place.chat_id)
                else:
                    self._selected_chat_ids.discard(card.place.chat_id)
        self._update_counter()

    def _delete_in_selected_places(self):
        selected = list(self._selected_chat_ids)
        if not selected:
            messagebox.showinfo("Удаление", "Отметьте чаты для удаления (галочка на карточке).")
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить все ваши сообщения в {len(selected)} выбранных чатах? (обход по ходу, без предварительного списка). Продолжить?"):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_in_places", selected))

    def _export_selected_places(self):
        selected = list(self._selected_chat_ids)
        if not selected:
            messagebox.showinfo("Экспорт", "Отметьте чаты для экспорта (галочка на карточке).")
            return
        if not self.on_export_places:
            return
        folder = filedialog.askdirectory(title="Папка для экспорта")
        if folder:
            self.on_export_places(folder, selected)

    def _on_card_check(self, chat_id, checked):
        if checked:
            self._selected_chat_ids.add(chat_id)
        else:
            self._selected_chat_ids.discard(chat_id)
        self._update_counter()

    def _update_counter(self, visible=None):
        if visible is None:
            visible = len([w for w in self.scroll.winfo_children() if isinstance(w, ChatCard)])
        self.counter_label.configure(
            text=f"Чатов: {len(self.places)} · видно: {visible} · выбрано: {len(self._selected_chat_ids)}"
        )

    def _open_selected(self):
        if hasattr(self, "_selected_place") and self._selected_place is not None:
            self.on_open_place(self._selected_place)
            return
        messagebox.showinfo("Выбор", "Выберите чат в списке (клик по карточке) и нажмите «Открыть» или дважды щёлкните по карточке.")

    def _export_csv(self):
        if not self.places:
            messagebox.showinfo("Экспорт", "Нет данных для экспорта. Выполните скан или загрузите кэш.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export_places_to_csv(self.places, path)
                messagebox.showinfo("Экспорт", f"Сохранено: {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def _export_json(self):
        if not self.places:
            messagebox.showinfo("Экспорт", "Нет данных для экспорта. Выполните скан или загрузите кэш.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                export_places_to_json(self.places, path)
                messagebox.showinfo("Экспорт", f"Сохранено: {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
