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

        self.status_label = ctk.CTkLabel(self, text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать» или «Обновить из кэша».", text_color="gray")
        self.status_label.pack(fill="x", pady=(0, PAD_SM))

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
        self.search_var.trace_add("write", lambda *a: self._apply_sort_filter())
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
        # Сохранить выбранные фильтры как умолчание на следующий раз
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
        self._update_section_buttons()
        self._apply_sort_filter()

    def _build_place_card(self, place: Place):
        """Создать карточку чата в self.scroll и вернуть её."""
        card = ctk.CTkFrame(self.scroll, corner_radius=RADIUS, fg_color=CARD_BG, cursor="hand2")
        card.pack(fill="x", pady=4, padx=2)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=PAD_SM)
        var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="", variable=var, width=24, height=24).pack(side="left", padx=(0, PAD_SM))
        title_short = (place.title[:50] + "…") if len(place.title) > 50 else place.title
        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)
        label_text = f"{title_short}  ·  {place.type_str}  ·  {len(place.messages)} сообщ."
        lbl = ctk.CTkLabel(text_col, text=label_text, anchor="w", font=font(14, "bold"))
        lbl.pack(fill="x", anchor="w")
        if place.messages:
            mid, preview, date_str = place.messages[0]
            preview = (preview or "").replace("\n", " ")
            preview_short = preview[:90] + "…" if len(preview) > 90 else preview
            sub = ctk.CTkLabel(
                text_col,
                text=f"{date_str} · #{mid} · {preview_short}",
                anchor="w",
                font=font(12),
                text_color="gray",
                wraplength=560,
            )
            sub.pack(fill="x", anchor="w", pady=(2, 0))
        card.place_data = place
        card.place_var = var
        card.bind("<Double-1>", lambda e, pl=place: self.on_open_place(pl))
        lbl.bind("<Double-1>", lambda e, pl=place: self.on_open_place(pl))
        card.bind("<Button-1>", self._select_card)
        lbl.bind("<Button-1>", self._select_card)
        text_col.bind("<Button-1>", self._select_card)
        return card

    def append_place(self, place: Place):
        """Добавить один чат в конец списка и одну карточку (потоковый вывод)."""
        self.places.append(place)
        if getattr(self, "current_section", "all") == "channels" and place.type_str != "Канал":
            return
        if self.current_section == "groups" and place.type_str not in ("Группа", "Супергруппа"):
            return
        if self.current_section == "private" and place.type_str != "Личный":
            return
        for widget in self.scroll.winfo_children():
            if not getattr(widget, "place_data", None):
                widget.destroy()
        self._build_place_card(place)

    def _apply_sort_filter(self):
        """Перестроить список с учётом раздела, сортировки и поиска."""
        if getattr(self, "current_section", None) == "channels":
            base = [p for p in self.places if p.type_str == "Канал"]
        elif self.current_section == "groups":
            base = [p for p in self.places if p.type_str in ("Группа", "Супергруппа")]
        elif self.current_section == "private":
            base = [p for p in self.places if p.type_str == "Личный"]
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
        if not items:
            self._show_empty_places()
            self._selected_place = None
            return
        for p in items:
            self._build_place_card(p)
        self._selected_place = None

    def _show_empty_places(self):
        """Показать пустое состояние в списке чатов."""
        empty = ctk.CTkFrame(self.scroll, fg_color="transparent")
        empty.pack(fill="both", expand=True, pady=PAD * 3)
        msg = "Чатов с вашими сообщениями не найдено.\nНажмите «Сканировать» или «Обновить из кэша»."
        if self.places:
            msg = "По выбранным фильтрам чатов не найдено.\nИзмените раздел или поиск."
        ctk.CTkLabel(empty, text=msg, font=font(14), text_color="gray", justify="center").pack(expand=True)

    def _delete_in_selected_places(self):
        selected = self._selected_chat_ids()
        if not selected:
            messagebox.showinfo("Удаление", "Отметьте чаты для удаления (галочка на карточке).")
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить все ваши сообщения в {len(selected)} выбранных чатах? (обход по ходу, без предварительного списка). Продолжить?"):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_in_places", selected))

    def _selected_chat_ids(self):
        selected = []
        for card in self.scroll.winfo_children():
            if getattr(card, "place_data", None) and getattr(card, "place_var", None) and card.place_var.get():
                selected.append(card.place_data.chat_id)
        return selected

    def _export_selected_places(self):
        selected = self._selected_chat_ids()
        if not selected:
            messagebox.showinfo("Экспорт", "Отметьте чаты для экспорта (галочка на карточке).")
            return
        if not self.on_export_places:
            return
        folder = filedialog.askdirectory(title="Папка для экспорта")
        if folder:
            self.on_export_places(folder, selected)

    def _select_card(self, event):
        w = event.widget
        while w and not getattr(w, "place_data", None):
            w = w.master if hasattr(w, "master") else None
        if w is not None:
            if getattr(self, "_selected_card", None) is not None and self._selected_card.winfo_exists():
                self._selected_card.configure(fg_color=CARD_BG)
            w.configure(fg_color=("gray75", "gray28"))
            self._selected_card = w
            self._selected_place = w.place_data

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
