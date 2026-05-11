"""
Экран экспортера: быстрый список всех диалогов и потоковый экспорт выбранных.
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox

from core import Place, get_scan_include_groups, get_scan_include_channels, get_scan_include_private
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
    font,
)
from ui.queues import scan_paused, scan_stop_requested


class ExportFrame(ctk.CTkFrame):
    """Отдельный режим экспортера: список всех диалогов без скана истории."""

    def __init__(self, parent, on_load_dialogs, on_export_places, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_load_dialogs = on_load_dialogs
        self.on_export_places = on_export_places
        self.dialogs: list[Place] = []
        self._loading = False
        self._paused = False
        self._selected_card = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))
        ctk.CTkLabel(head, text="Экспорт", font=font(20, "bold")).pack(side="left")

        controls = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=RADIUS, border_width=1, border_color=("gray85", "gray25"))
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
            text="Экспорт выбранных",
            command=self._export_selected,
            corner_radius=BTN_RADIUS,
            width=160,
            height=36,
            fg_color=BTN_SECONDARY,
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

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=RADIUS)
        self.scroll.pack(fill="both", expand=True)

    def _load_dialogs(self):
        scan_paused.clear()
        scan_stop_requested.clear()
        self.dialogs = []
        self._apply_filter()
        self.set_loading(True, "Загружаю")
        self.status_label.configure(text="Загружаю список диалогов...")
        self.on_load_dialogs(self.check_groups.get(), self.check_channels.get(), self.check_private.get())

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
            self.export_btn.configure(state="normal")
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
        self._apply_filter()

    def append_dialogs(self, dialogs):
        self.dialogs.extend(dialogs)
        if any(not getattr(w, "place_data", None) for w in self.scroll.winfo_children()):
            for widget in self.scroll.winfo_children():
                if not getattr(widget, "place_data", None):
                    widget.destroy()
        for place in dialogs:
            if self._matches(place):
                self._build_card(place)

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
            return
        for place in items:
            self._build_card(place)

    def _build_card(self, place: Place):
        card = ctk.CTkFrame(self.scroll, corner_radius=RADIUS, fg_color=CARD_BG, cursor="hand2")
        card.pack(fill="x", pady=3, padx=2)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=PAD, pady=PAD_SM)
        var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="", variable=var, width=24, height=24).pack(side="left", padx=(0, PAD_SM))
        title_short = (place.title[:72] + "…") if len(place.title) > 72 else place.title
        ctk.CTkLabel(row, text=title_short, anchor="w", font=font(13, "bold")).pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(row, text=place.type_str, anchor="e", font=font(12), text_color="gray").pack(side="right", padx=PAD_SM)
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
        widget.configure(fg_color=("gray75", "gray28"))
        self._selected_card = widget

    def _set_visible_checks(self, value: bool):
        for card in self.scroll.winfo_children():
            if getattr(card, "place_var", None):
                card.place_var.set(value)

    def _selected_chat_ids(self):
        return [
            card.place_data.chat_id
            for card in self.scroll.winfo_children()
            if getattr(card, "place_data", None) and getattr(card, "place_var", None) and card.place_var.get()
        ]

    def _export_selected(self):
        selected = self._selected_chat_ids()
        if not selected:
            messagebox.showinfo("Экспорт", "Отметьте один или несколько чатов.")
            return
        folder = filedialog.askdirectory(title="Папка для экспорта")
        if folder:
            self.on_export_places(folder, selected)
