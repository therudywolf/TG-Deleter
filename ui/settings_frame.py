"""
Экран настроек: API ID, API Hash, параметры скана, Сохранить и Сбросить настройки.
Данные из api_config.json. Режим «Первоначальная настройка» при первом запуске.
"""
import customtkinter as ctk
from tkinter import messagebox

from core import (
    load_api_config,
    save_api_config,
    reset_api_config,
    get_api_config,
)
from ui.theme import PAD, PAD_SM, RADIUS, BTN_RADIUS, ACCENT, ACCENT_HOVER, font


class SettingsFrame(ctk.CTkFrame):
    """Форма настроек API и скана (api_config.json)."""

    def __init__(self, parent, on_saved=None, is_initial_setup=False, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_saved = on_saved
        self.is_initial_setup = is_initial_setup

        title_text = "Первоначальная настройка" if is_initial_setup else "Настройки"
        self.title_label = ctk.CTkLabel(self, text=title_text, font=font(20, "bold"))
        self.title_label.pack(anchor="w", pady=(0, PAD_SM))
        hint = (
            "Введите API ID и API Hash с my.telegram.org, затем нажмите «Сохранить». "
            "После этого добавьте аккаунт в левой панели."
            if is_initial_setup
            else ""
        )
        if hint:
            ctk.CTkLabel(self, text=hint, font=font(12), text_color="gray", wraplength=500).pack(anchor="w", pady=(0, PAD))

        block = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=RADIUS, border_width=1, border_color=("gray85", "gray25"))
        block.pack(fill="x", pady=(0, PAD))
        inner = ctk.CTkFrame(block, fg_color="transparent")
        inner.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkLabel(inner, text="API Telegram (получить: https://my.telegram.org/apps)", font=font(12, "bold"), text_color="gray").pack(anchor="w")
        row1 = ctk.CTkFrame(inner, fg_color="transparent")
        row1.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(row1, text="API ID (число):", width=120, anchor="w").pack(side="left", padx=(0, PAD_SM))
        api_cfg = get_api_config()
        self.api_id_var = ctk.StringVar(value=str(api_cfg.get("api_id") or ""))
        self.api_id_entry = ctk.CTkEntry(row1, textvariable=self.api_id_var, width=200, placeholder_text="Например: 12345678")
        self.api_id_entry.pack(side="left")
        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(row2, text="API Hash:", width=120, anchor="w").pack(side="left", padx=(0, PAD_SM))
        self.api_hash_var = ctk.StringVar(value=api_cfg.get("api_hash") or "")
        self.api_hash_entry = ctk.CTkEntry(row2, textvariable=self.api_hash_var, width=280, placeholder_text="Строка из my.telegram.org", show="*")
        self.api_hash_entry.pack(side="left")

        ctk.CTkLabel(inner, text="Дополнительно", font=font(12, "bold"), text_color="gray").pack(anchor="w", pady=(PAD, 0))
        row3 = ctk.CTkFrame(inner, fg_color="transparent")
        row3.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(row3, text="Лимит скана (пусто = вся история):", width=220, anchor="w").pack(side="left", padx=(0, PAD_SM))
        self.scan_limit_var = ctk.StringVar(value=str(api_cfg.get("scan_limit") or ""))
        ctk.CTkEntry(row3, textvariable=self.scan_limit_var, width=100, placeholder_text="пусто").pack(side="left")
        row4 = ctk.CTkFrame(inner, fg_color="transparent")
        row4.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(row4, text="Задержка между удалениями (сек):", width=220, anchor="w").pack(side="left", padx=(0, PAD_SM))
        self.delay_sec_var = ctk.StringVar(value=str(api_cfg.get("delay_sec") or "0.2"))
        ctk.CTkEntry(row4, textvariable=self.delay_sec_var, width=80).pack(side="left")
        row5 = ctk.CTkFrame(inner, fg_color="transparent")
        row5.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(row5, text="Задержка между чатами при скане (сек):", width=220, anchor="w").pack(side="left", padx=(0, PAD_SM))
        self.scan_delay_var = ctk.StringVar(value=str(api_cfg.get("scan_delay_between_chats") or "2.0"))
        ctk.CTkEntry(row5, textvariable=self.scan_delay_var, width=80).pack(side="left")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", pady=PAD)
        ctk.CTkButton(btn_row, text="Сохранить", command=self._save, corner_radius=BTN_RADIUS, width=120, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(0, PAD_SM))
        ctk.CTkButton(btn_row, text="Сбросить настройки", command=self._reset, corner_radius=BTN_RADIUS, width=160, height=36, fg_color=("gray55", "gray40")).pack(side="left")
        self.status_label = ctk.CTkLabel(self, text="", text_color="gray")
        self.status_label.pack(anchor="w", pady=(PAD_SM, 0))

    def _save(self):
        api_id_str = (self.api_id_var.get() or "").strip()
        api_hash_str = (self.api_hash_var.get() or "").strip()
        if not api_id_str or not api_hash_str:
            messagebox.showwarning("Настройки", "Введите API ID и API Hash.")
            return
        try:
            api_id = int(api_id_str)
        except ValueError:
            messagebox.showwarning("Настройки", "API ID должен быть числом.")
            return
        try:
            delay_sec = float((self.delay_sec_var.get() or "0.2").strip() or "0.2")
        except ValueError:
            delay_sec = 0.2
        try:
            scan_delay = float((self.scan_delay_var.get() or "2").strip() or "2")
        except ValueError:
            scan_delay = 2.0
        scan_limit_str = (self.scan_limit_var.get() or "").strip()
        scan_limit = int(scan_limit_str) if scan_limit_str else None
        c = load_api_config()
        c["api_id"] = api_id
        c["api_hash"] = api_hash_str
        c["delay_sec"] = delay_sec
        c["scan_delay_between_chats"] = scan_delay
        c["scan_limit"] = scan_limit
        save_api_config(c)
        self.status_label.configure(text="Настройки сохранены.")
        if self.on_saved:
            self.on_saved()

    def _reset(self):
        if not messagebox.askyesno("Сбросить настройки", "Обнулить настройки API и скана? Потребуется снова ввести API ID и API Hash."):
            return
        reset_api_config()
        self.api_id_var.set("")
        self.api_hash_var.set("")
        self.scan_limit_var.set("")
        self.delay_sec_var.set("0.2")
        self.scan_delay_var.set("2.0")
        self.status_label.configure(text="Настройки сброшены. Введите API и нажмите «Сохранить».")

    def refresh_from_config(self):
        """Обновить поля из api_config."""
        api_cfg = get_api_config()
        self.api_id_var.set(str(api_cfg.get("api_id") or ""))
        self.api_hash_var.set(api_cfg.get("api_hash") or "")
        self.scan_limit_var.set(str(api_cfg.get("scan_limit") or ""))
        self.delay_sec_var.set(str(api_cfg.get("delay_sec") or "0.2"))
        self.scan_delay_var.set(str(api_cfg.get("scan_delay_between_chats") or "2.0"))

    def set_initial_setup(self, is_initial_setup):
        """Переключить заголовок между «Первоначальная настройка» и «Настройки»."""
        self.is_initial_setup = is_initial_setup
        self.title_label.configure(text="Первоначальная настройка" if is_initial_setup else "Настройки")
