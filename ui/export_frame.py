"""
Экран экспортера: быстрый список всех диалогов и потоковый экспорт выбранных.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core import Place, get_export_include_media, get_scan_include_groups, get_scan_include_channels, get_scan_include_private
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
    PANEL_BG,
    BORDER,
    TEXT_MUTED,
    font,
)
from ui.queues import scan_paused, scan_stop_requested

VISIBLE_LIMIT = 500


class ExportFrame(ctk.CTkFrame):
    """Отдельный режим экспортера: список всех диалогов без скана истории."""

    def __init__(self, parent, on_load_dialogs, on_export_places, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_load_dialogs = on_load_dialogs
        self.on_export_places = on_export_places
        self.dialogs: list[Place] = []
        self.selected_ids: set[int] = set()
        self._loading = False
        self._paused = False
        self._selected_card = None
        self._export_total_chats = 0
        self._export_done_chats = 0
        self._export_total_messages = None
        self._export_done_messages = 0

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(head, text="Экспорт", font=font(20, "bold")).pack(side="left")
        self.counter_label = ctk.CTkLabel(head, text="", text_color=TEXT_MUTED, font=font(12))
        self.counter_label.pack(side="right")

        controls = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=RADIUS, border_width=1, border_color=BORDER)
        controls.pack(fill="x", pady=(0, PAD_SM))
        inner = ctk.CTkFrame(controls, fg_color="transparent")
        inner.pack(fill="x", padx=PAD, pady=PAD_SM)

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Показать:").pack(side="left", padx=(0, PAD_SM))
        self.check_groups = ctk.BooleanVar(value=get_scan_include_groups())
        ctk.CTkCheckBox(row, text="Группы", variable=self.check_groups).pack(side="left", padx=PAD_SM)
        self.check_channels = ctk.BooleanVar(value=get_scan_include_channels())
        ctk.CTkCheckBox(row, text="Каналы", variable=self.check_channels).pack(side="left", padx=PAD_SM)
        self.check_private = ctk.BooleanVar(value=get_scan_include_private())
        ctk.CTkCheckBox(row, text="Личку", variable=self.check_private).pack(side="left", padx=PAD_SM)

        media_block = ctk.CTkFrame(inner, fg_color="transparent")
        media_block.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(media_block, text="Бекап медиа:").pack(anchor="w")
        self.include_media_var = ctk.BooleanVar(value=get_export_include_media())
        ctk.CTkCheckBox(
            media_block,
            text="Скачивать вложения",
            variable=self.include_media_var,
            command=self._toggle_media_options,
        ).pack(anchor="w", pady=(PAD_SM, 0))
        self.media_type_vars = {
            "photos": ctk.BooleanVar(value=True),
            "videos": ctk.BooleanVar(value=True),
            "documents": ctk.BooleanVar(value=True),
            "audio": ctk.BooleanVar(value=True),
            "stickers": ctk.BooleanVar(value=True),
            "other": ctk.BooleanVar(value=True),
        }
        self.media_type_checks = []
        type_grid = ctk.CTkFrame(media_block, fg_color="transparent")
        type_grid.pack(fill="x", pady=(PAD_SM, 0))
        for idx, (key, label) in enumerate((
            ("photos", "Фото"),
            ("videos", "Видео"),
            ("documents", "Файлы"),
            ("audio", "Аудио/voice"),
            ("stickers", "Стикеры/GIF"),
            ("other", "Прочее"),
        )):
            cb = ctk.CTkCheckBox(type_grid, text=label, variable=self.media_type_vars[key], width=150)
            cb.grid(row=idx // 3, column=idx % 3, sticky="w", padx=(0, PAD), pady=2)
            self.media_type_checks.append(cb)
        self._toggle_media_options()

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", pady=(0, PAD_SM))
        self.load_btn = ctk.CTkButton(
            actions,
            text="Загрузить список",
            command=self._load_dialogs,
            corner_radius=BTN_RADIUS,
            width=150,
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        )
        self.load_btn.pack(side="right", padx=PAD_SM)
        self.export_btn = ctk.CTkButton(
            actions,
            text="Запустить бекап выбранных",
            command=self._export_selected,
            corner_radius=BTN_RADIUS,
            width=210,
            height=36,
            fg_color=BTN_SECONDARY,
            state="disabled",
        )
        self.export_btn.pack(side="right", padx=PAD_SM)
        self.pause_btn = ctk.CTkButton(
            actions,
            text="Пауза",
            command=self._toggle_pause,
            corner_radius=BTN_RADIUS,
            width=100,
            height=36,
            state="disabled",
        )
        self.pause_btn.pack(side="right", padx=PAD_SM)
        self.stop_btn = ctk.CTkButton(
            actions,
            text="Стоп",
            command=self._stop,
            corner_radius=BTN_RADIUS,
            width=80,
            height=36,
            state="disabled",
            fg_color=("gray60", "gray35"),
            hover_color=("gray50", "gray40"),
        )
        self.stop_btn.pack(side="right", padx=PAD_SM)
        ctk.CTkButton(
            actions,
            text="Выбрать видимые",
            command=lambda: self._set_visible_checks(True),
            corner_radius=BTN_RADIUS,
            width=140,
            height=36,
            fg_color=BTN_SECONDARY,
        ).pack(side="left", padx=PAD_SM)
        ctk.CTkButton(
            actions,
            text="Снять",
            command=lambda: self._set_visible_checks(False),
            corner_radius=BTN_RADIUS,
            width=80,
            height=36,
            fg_color=BTN_SECONDARY,
        ).pack(side="left", padx=PAD_SM)

        self.status_label = ctk.CTkLabel(self, text="Загрузите список диалогов, отметьте чаты и экспортируйте.", text_color="gray")
        self.status_label.pack(fill="x", pady=(0, PAD_SM))

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(tools, text="Раздел:").pack(side="left", padx=(0, PAD_SM))
        self.section_var = ctk.StringVar(value="Все")
        self.section_combo = ctk.CTkComboBox(
            tools,
            values=["Все", "Каналы", "Группы", "Личка"],
            variable=self.section_var,
            width=140,
            command=lambda _v: self._apply_filter(),
        )
        self.section_combo.pack(side="left", padx=(0, PAD))
        ctk.CTkLabel(tools, text="Поиск:").pack(side="left", padx=(0, PAD_SM))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_a: self._apply_filter())
        ctk.CTkEntry(tools, placeholder_text="Название чата...", width=260, textvariable=self.search_var).pack(side="left")

        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=4)
        self.progress.pack(fill="x", pady=(0, PAD))
        self.progress.pack_forget()
        self.export_progress = ctk.CTkProgressBar(self, mode="determinate", height=8)
        self.export_progress.set(0)
        self.export_progress.pack(fill="x", pady=(0, PAD_SM))
        self.export_progress.pack_forget()
        self.progress_detail_label = ctk.CTkLabel(self, text="", text_color=TEXT_MUTED, font=font(12), anchor="w")
        self.progress_detail_label.pack(fill="x", pady=(0, PAD_SM))
        self.progress_detail_label.pack_forget()

        header = ctk.CTkFrame(self, fg_color=("gray85", "gray16"), corner_radius=0, height=28)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="", width=42).pack(side="left")
        ctk.CTkLabel(header, text="Диалог", anchor="w", font=font(12, "bold"), text_color=TEXT_MUTED).pack(side="left", fill="x", expand=True, padx=(0, PAD_SM))
        ctk.CTkLabel(header, text="Тип", width=130, anchor="w", font=font(12, "bold"), text_color=TEXT_MUTED).pack(side="right", padx=(0, PAD_SM))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=0)
        self.scroll.pack(fill="both", expand=True)
        self._update_counters()

    def _load_dialogs(self):
        scan_paused.clear()
        scan_stop_requested.clear()
        self.dialogs = []
        self.selected_ids.clear()
        self._hide_export_progress()
        self._apply_filter()
        self.set_loading(True, "Загружаю")
        self.status_label.configure(text="Загружаю список диалогов...")
        self.on_load_dialogs(self.check_groups.get(), self.check_channels.get(), self.check_private.get())

    def _toggle_media_options(self):
        state = "normal" if self.include_media_var.get() else "disabled"
        for cb in getattr(self, "media_type_checks", []):
            cb.configure(state=state)

    def get_export_options(self):
        return {
            "include_media": bool(self.include_media_var.get()),
            "media_types": {key: bool(var.get()) for key, var in self.media_type_vars.items()},
        }

    def _hide_export_progress(self):
        self._export_total_chats = 0
        self._export_done_chats = 0
        self._export_total_messages = None
        self._export_done_messages = 0
        self.export_progress.set(0)
        self.export_progress.pack_forget()
        self.progress_detail_label.configure(text="")
        self.progress_detail_label.pack_forget()

    def start_export_progress(self, total_chats, parallel_chats=None):
        self._loading = True
        self._paused = False
        self._export_total_chats = int(total_chats or 0)
        self._export_done_chats = 0
        self._export_total_messages = None
        self._export_done_messages = 0
        self.load_btn.configure(state="disabled", text="Бекап")
        self.export_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="Пауза")
        self.stop_btn.configure(state="normal")
        self.progress.stop()
        self.progress.pack_forget()
        self.export_progress.pack(fill="x", pady=(0, PAD_SM))
        self.export_progress.set(0)
        self.progress_detail_label.pack(fill="x", pady=(0, PAD_SM))
        parallel_text = f", параллельно: {parallel_chats}" if parallel_chats else ""
        self.progress_detail_label.configure(text=f"Чаты: 0/{self._export_total_chats}{parallel_text}. Сообщения: 0.")

    def update_export_progress(self, payload, current_title=None):
        total_chats = payload.get("total_chats")
        done_chats = payload.get("done_chats")
        done_messages = payload.get("done_messages")
        total_messages = payload.get("total_messages")
        total_messages_known = bool(payload.get("total_messages_known"))
        if total_chats is not None:
            self._export_total_chats = int(total_chats or 0)
        if done_chats is not None:
            self._export_done_chats = int(done_chats or 0)
        if done_messages is not None:
            self._export_done_messages = int(done_messages or 0)
        self._export_total_messages = int(total_messages) if total_messages is not None else None

        if self._export_total_messages:
            ratio = self._export_done_messages / max(1, self._export_total_messages)
        elif self._export_total_chats:
            ratio = self._export_done_chats / max(1, self._export_total_chats)
        else:
            ratio = 0
        self.export_progress.set(max(0, min(1, ratio)))

        parts = [f"Чаты: {self._export_done_chats}/{self._export_total_chats or 0}"]
        if self._export_total_messages is not None:
            left = max(0, self._export_total_messages - self._export_done_messages)
            suffix = "" if total_messages_known else "+"
            parts.append(f"Сообщения: {self._export_done_messages}/{self._export_total_messages}{suffix}, осталось: {left}{suffix}")
        else:
            parts.append(f"Сообщения: {self._export_done_messages}")
        if current_title:
            short = (str(current_title)[:48] + "…") if len(str(current_title)) > 48 else str(current_title)
            parts.append(f"Сейчас: {short}")
        self.progress_detail_label.configure(text=" · ".join(parts))

    def finish_export_progress(self, stopped=False):
        if not stopped:
            self.export_progress.set(1)
        self.set_loading(False)

    def set_loading(self, loading: bool, label: str | None = None):
        self._loading = loading
        self._paused = False
        if loading:
            self.load_btn.configure(state="disabled", text=label or "Выполняется")
            self.export_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text="Пауза")
            self.stop_btn.configure(state="normal")
            self.progress.pack(fill="x", pady=(0, PAD))
            self.progress.start()
        else:
            scan_paused.clear()
            self.load_btn.configure(state="normal", text="Загрузить список")
            self.export_btn.configure(state="normal" if self.selected_ids else "disabled")
            self.pause_btn.configure(state="disabled", text="Пауза")
            self.stop_btn.configure(state="disabled")
            self.progress.stop()
            self.progress.pack_forget()

    def _toggle_pause(self):
        if not self._loading:
            return
        if self._paused:
            scan_paused.clear()
            self._paused = False
            self.pause_btn.configure(text="Пауза")
            self.status_label.configure(text="Продолжаю...")
        else:
            scan_paused.set()
            self._paused = True
            self.pause_btn.configure(text="Продолжить")
            self.status_label.configure(text="Пауза.")

    def _stop(self):
        if not self._loading:
            return
        scan_stop_requested.set()
        scan_paused.clear()
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="Останавливаю...")

    def set_dialogs(self, dialogs):
        self.dialogs = list(dialogs)
        existing = {p.chat_id for p in self.dialogs}
        self.selected_ids.intersection_update(existing)
        self._apply_filter()

    def append_dialogs(self, dialogs):
        self.dialogs.extend(dialogs)
        if any(not getattr(w, "place_data", None) for w in self.scroll.winfo_children()):
            for widget in self.scroll.winfo_children():
                if not getattr(widget, "place_data", None):
                    widget.destroy()
        rendered_count = len([w for w in self.scroll.winfo_children() if getattr(w, "place_data", None)])
        for place in dialogs:
            if self._matches(place):
                if rendered_count < VISIBLE_LIMIT:
                    self._build_card(place)
                    rendered_count += 1
        self._update_counters()

    def _matches(self, place: Place):
        section = self.section_var.get()
        if section == "Каналы" and place.type_str != "Канал":
            return False
        if section == "Группы" and place.type_str not in ("Группа", "Супергруппа"):
            return False
        if section == "Личка" and place.type_str != "Личный":
            return False
        search = (self.search_var.get() or "").strip().lower()
        return not search or search in (place.title or "").lower()

    def _apply_filter(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
        items = [p for p in self.dialogs if self._matches(p)]
        items.sort(key=lambda p: (p.title or "").lower())
        if not items:
            empty = ctk.CTkFrame(self.scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=PAD * 3)
            ctk.CTkLabel(empty, text="Список пуст.", font=font(14), text_color="gray").pack(expand=True)
            self._update_counters(visible=0)
            return
        rendered = items[:VISIBLE_LIMIT]
        for place in rendered:
            self._build_card(place)
        if len(items) > VISIBLE_LIMIT:
            more = ctk.CTkFrame(self.scroll, fg_color="transparent")
            more.pack(fill="x", pady=PAD_SM)
            ctk.CTkLabel(
                more,
                text=f"Показаны первые {VISIBLE_LIMIT} из {len(items)}. Уточните поиск или раздел.",
                font=font(12),
                text_color=TEXT_MUTED,
            ).pack(anchor="center")
        self._update_counters(visible=len(items))

    def _build_card(self, place: Place):
        card = ctk.CTkFrame(self.scroll, corner_radius=0, fg_color=CARD_BG, cursor="hand2", height=38)
        card.pack(fill="x", pady=(0, 1), padx=0)
        card.pack_propagate(False)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=PAD_SM)
        var = ctk.BooleanVar(value=place.chat_id in self.selected_ids)
        cb = ctk.CTkCheckBox(
            row,
            text="",
            variable=var,
            width=24,
            height=24,
            command=lambda cid=place.chat_id, v=var: self._on_check(cid, v.get()),
        )
        cb.pack(side="left", padx=(0, PAD_SM))
        title_short = (place.title[:72] + "…") if len(place.title) > 72 else place.title
        ctk.CTkLabel(row, text=title_short, anchor="w", font=font(13)).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(row, text=place.type_str, width=130, anchor="w", font=font(12), text_color=TEXT_MUTED).pack(side="right")
        card.place_data = place
        card.place_var = var
        card.bind("<Button-1>", self._select_card)
        row.bind("<Button-1>", self._select_card)
        return card

    def _select_card(self, event):
        widget = event.widget
        while widget and not getattr(widget, "place_data", None):
            widget = widget.master if hasattr(widget, "master") else None
        if widget is None:
            return
        if self._selected_card is not None and self._selected_card.winfo_exists():
            self._selected_card.configure(fg_color=CARD_BG)
        widget.configure(fg_color=ROW_HOVER)
        self._selected_card = widget

    def _set_visible_checks(self, value: bool):
        for card in self.scroll.winfo_children():
            if getattr(card, "place_var", None) and getattr(card, "place_data", None):
                card.place_var.set(value)
                if value:
                    self.selected_ids.add(card.place_data.chat_id)
                else:
                    self.selected_ids.discard(card.place_data.chat_id)
        self._update_counters()

    def _selected_chat_ids(self):
        return list(self.selected_ids)

    def _on_check(self, chat_id, checked):
        if checked:
            self.selected_ids.add(chat_id)
        else:
            self.selected_ids.discard(chat_id)
        self._update_counters()

    def _update_counters(self, visible=None):
        if visible is None:
            visible = len([p for p in self.dialogs if self._matches(p)])
        selected = len(self.selected_ids)
        total = len(self.dialogs)
        self.counter_label.configure(text=f"Всего: {total} · видно: {visible} · выбрано: {selected}")
        if not self._loading:
            self.export_btn.configure(state="normal" if selected else "disabled")

    def _export_selected(self):
        selected = self._selected_chat_ids()
        if not selected:
            messagebox.showinfo("Экспорт", "Отметьте один или несколько чатов.")
            return
        if self.include_media_var.get() and not any(var.get() for var in self.media_type_vars.values()):
            messagebox.showwarning("Экспорт", "Выберите хотя бы один тип медиа или отключите скачивание вложений.")
            return
        folder = filedialog.askdirectory(title="Папка для экспорта")
        if folder:
            self.on_export_places(folder, selected, self.get_export_options())
