"""
Левая панель: аккаунты (список с аватаркой и именем), профиль, навигация, кнопки выхода и кэша.
"""
import os
import customtkinter as ctk
from tkinter import messagebox, simpledialog
from PIL import Image

from core import get_current_session, get_accounts_list, add_account, remove_account, get_account_profile, get_project_root, set_current_session, get_api_id, get_api_hash
from ui.login_dialog import LoginDialog
from ui.theme import PAD, PAD_SM, BTN_RADIUS, RADIUS, SIDEBAR_WIDTH, ACCENT, ACCENT_HOVER, SIDEBAR_BG, SIDEBAR_BORDER, font

_PROJECT_ROOT = get_project_root()
AVATAR_SIZE_SMALL = 36


def _avatar_image(path, size):
    img = Image.open(path)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class SidebarFrame(ctk.CTkFrame):
    """Левая панель: меню аккаунтов с аватарками, профиль, Чаты, Сбросить кэш, Выйти из аккаунта, Удалить аккаунт, Выход."""

    def __init__(self, parent, on_quit=None, on_switch_account=None, on_show_chats=None, on_show_export=None, on_show_settings=None, on_show_log=None, on_clear_cache=None, on_logout=None, **kw):
        kw.pop("width", None)
        super().__init__(parent, width=SIDEBAR_WIDTH, fg_color=SIDEBAR_BG, corner_radius=0,
                         border_width=1, border_color=SIDEBAR_BORDER, **kw)
        self.pack_propagate(False)
        self.on_quit = on_quit
        self.on_switch_account = on_switch_account
        self.on_show_chats = on_show_chats
        self.on_show_export = on_show_export
        self.on_show_settings = on_show_settings
        self.on_show_log = on_show_log
        self.on_clear_cache = on_clear_cache
        self.on_logout = on_logout
        self._updating_account = False

        ctk.CTkLabel(self, text="Аккаунты", font=font(12, "bold"), anchor="w").pack(fill="x", padx=PAD, pady=(PAD, PAD_SM))
        self.accounts_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", height=160)
        self.accounts_scroll.pack(fill="x", padx=PAD_SM, pady=(0, PAD_SM))
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=PAD_SM)
        ctk.CTkButton(btn_row, text="Добавить", command=self._add_account, corner_radius=BTN_RADIUS, height=32, fg_color=ACCENT, hover_color=ACCENT_HOVER, width=100).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Удалить", command=self._remove_selected_account, corner_radius=BTN_RADIUS, height=32, fg_color=("gray55", "gray40"), width=70).pack(side="left")
        self._refresh_accounts_list()
        sep1 = ctk.CTkFrame(self, height=1, fg_color=("gray70", "gray35"))
        sep1.pack(fill="x", padx=PAD, pady=PAD_SM)
        self.avatar_frame = ctk.CTkFrame(self, width=64, height=64, corner_radius=32, fg_color=("gray75", "gray30"))
        self.avatar_frame.pack_propagate(False)
        self.avatar_frame.pack(pady=(PAD_SM, PAD_SM))
        self.avatar_placeholder = ctk.CTkLabel(self.avatar_frame, text="?", font=font(24))
        self.avatar_placeholder.pack(expand=True)
        self.name_label = ctk.CTkLabel(self, text="Загрузка…", font=font(14, "bold"), wraplength=SIDEBAR_WIDTH - PAD * 2)
        self.name_label.pack(fill="x", padx=PAD, pady=(0, 2))
        self.username_label = ctk.CTkLabel(self, text="", font=font(12), text_color="gray", wraplength=SIDEBAR_WIDTH - PAD * 2)
        self.username_label.pack(fill="x", padx=PAD, pady=(0, 2))
        self.phone_label = ctk.CTkLabel(self, text="", font=font(11), text_color="gray", wraplength=SIDEBAR_WIDTH - PAD * 2)
        self.phone_label.pack(fill="x", padx=PAD, pady=(0, PAD))
        sep = ctk.CTkFrame(self, height=1, fg_color=("gray70", "gray35"))
        sep.pack(fill="x", padx=PAD, pady=PAD_SM)
        ctk.CTkLabel(self, text="Разделы", font=font(12, "bold"), anchor="w").pack(fill="x", padx=PAD, pady=(0, PAD_SM))
        self.btn_chats = ctk.CTkButton(
            self, text="Чаты", command=self._on_chats_click, corner_radius=BTN_RADIUS, height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, anchor="w"
        )
        self.btn_chats.pack(fill="x", padx=PAD_SM, pady=2)
        if self.on_show_export:
            ctk.CTkButton(
                self, text="Экспорт", command=self.on_show_export, corner_radius=BTN_RADIUS, height=36,
                fg_color=("gray70", "gray30"), hover_color=("gray65", "gray35"), anchor="w"
            ).pack(fill="x", padx=PAD_SM, pady=2)
        if self.on_show_settings:
            ctk.CTkButton(
                self, text="Настройки", command=self.on_show_settings, corner_radius=BTN_RADIUS, height=36,
                fg_color=("gray70", "gray30"), hover_color=("gray65", "gray35"), anchor="w"
            ).pack(fill="x", padx=PAD_SM, pady=2)
        if self.on_show_log:
            ctk.CTkButton(
                self, text="Лог", command=self.on_show_log, corner_radius=BTN_RADIUS, height=36,
                fg_color=("gray70", "gray30"), hover_color=("gray65", "gray35"), anchor="w"
            ).pack(fill="x", padx=PAD_SM, pady=2)
        spacer = ctk.CTkFrame(self, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=PAD_SM, pady=PAD_SM)
        if self.on_clear_cache:
            ctk.CTkButton(bottom, text="Сбросить кэш", command=self.on_clear_cache, corner_radius=BTN_RADIUS, height=32, fg_color=("gray60", "gray35"), hover_color=("gray50", "gray40")).pack(fill="x", pady=2)
        if self.on_logout:
            ctk.CTkButton(bottom, text="Выйти из аккаунта", command=self.on_logout, corner_radius=BTN_RADIUS, height=32, fg_color=("gray60", "gray35"), hover_color=("gray50", "gray40")).pack(fill="x", pady=2)
        ctk.CTkButton(bottom, text="Удалить аккаунт", command=self._remove_current_account, corner_radius=BTN_RADIUS, height=32, fg_color=("gray55", "gray40")).pack(fill="x", pady=2)
        if self.on_quit:
            ctk.CTkButton(bottom, text="Выход", command=self.on_quit, corner_radius=BTN_RADIUS, height=36, fg_color=("gray60", "gray35"), hover_color=("gray50", "gray40")).pack(fill="x", pady=(4, 0))

    def _on_chats_click(self):
        if self.on_show_chats:
            self.on_show_chats()

    def _refresh_accounts_list(self):
        for w in self.accounts_scroll.winfo_children():
            w.destroy()
        current = get_current_session()
        for session_name in get_accounts_list():
            profile = get_account_profile(session_name)
            display_name = (profile.get("display_name") or "").strip() or (profile.get("username") and f"@{profile.get('username')}") or session_name[:20] + ("…" if len(session_name) > 20 else "")
            avatar_path = profile.get("avatar_path")
            if avatar_path and not os.path.isabs(avatar_path):
                avatar_path = os.path.join(_PROJECT_ROOT, avatar_path)
            is_current = session_name == current
            row = ctk.CTkFrame(self.accounts_scroll, fg_color=(ACCENT, ACCENT) if is_current else ("gray78", "gray28"), corner_radius=RADIUS, height=AVATAR_SIZE_SMALL + 8, cursor="hand2")
            row.pack_propagate(False)
            row.pack(fill="x", pady=2)
            avatar_canvas = ctk.CTkFrame(row, width=AVATAR_SIZE_SMALL, height=AVATAR_SIZE_SMALL, corner_radius=AVATAR_SIZE_SMALL // 2, fg_color=("gray70", "gray35"))
            avatar_canvas.pack_propagate(False)
            avatar_canvas.pack(side="left", padx=PAD_SM, pady=4)
            if avatar_path and os.path.isfile(avatar_path):
                try:
                    img = _avatar_image(avatar_path, AVATAR_SIZE_SMALL)
                    lbl = ctk.CTkLabel(avatar_canvas, text="", image=img)
                    lbl.image = img
                    lbl.pack(expand=True)
                except Exception:
                    pl = ctk.CTkLabel(avatar_canvas, text=(display_name[0].upper() if display_name and display_name != "?" else "?"), font=font(14))
                    pl.pack(expand=True)
            else:
                pl = ctk.CTkLabel(avatar_canvas, text=(display_name[0].upper() if display_name and display_name != "?" else "?"), font=font(14))
                pl.pack(expand=True)
            text_label = ctk.CTkLabel(row, text=display_name[:24] + ("…" if len(display_name) > 24 else ""), anchor="w", font=font(12))
            text_label.pack(side="left", fill="x", expand=True, padx=(0, PAD_SM))
            row.bind("<Button-1>", lambda e, n=session_name: self._on_account_click(n))
            text_label.bind("<Button-1>", lambda e, n=session_name: self._on_account_click(n))
            del_btn = ctk.CTkButton(row, text="×", width=28, height=28, corner_radius=BTN_RADIUS, command=lambda n=session_name: self._remove_account(n), fg_color=("gray60", "gray40"))
            del_btn.pack(side="right", padx=2, pady=4)
            del_btn.bind("<Button-1>", lambda e: "break")
            row.session_name = session_name

    def _remove_current_account(self):
        """Удалить текущий аккаунт из списка (с подтверждением по display_name)."""
        current = get_current_session()
        if not current:
            messagebox.showinfo("Аккаунты", "Нет выбранного аккаунта.")
            return
        profile = get_account_profile(current)
        display_name = (profile.get("display_name") or "").strip() or current
        if not messagebox.askyesno("Удалить аккаунт", f'Удалить аккаунт «{display_name}» из списка? Файл сессии не удаляется.'):
            return
        self._remove_account(current)

    def _on_account_click(self, session_name):
        if self._updating_account or not self.on_switch_account:
            return
        if (session_name or "").strip() != get_current_session():
            self.on_switch_account((session_name or "").strip())

    def _add_account(self):
        api_id = get_api_id()
        api_hash = get_api_hash()
        if not api_id or not api_hash:
            messagebox.showwarning("Аккаунт", "Сначала введите API ID и API Hash в разделе Настройки.", parent=self.winfo_toplevel())
            return
        LoginDialog(
            self.winfo_toplevel(),
            api_id=api_id,
            api_hash=api_hash,
            on_success=self._on_login_success,
        )

    def _on_login_success(self, session_name: str):
        """Вызывается из LoginDialog после успешной авторизации."""
        add_account(session_name)
        set_current_session(session_name)
        self._refresh_accounts_list()
        if self.on_switch_account:
            self.on_switch_account(session_name)

    def _remove_selected_account(self):
        accounts = get_accounts_list()
        if len(accounts) == 0:
            messagebox.showinfo("Аккаунты", "Нет аккаунтов для удаления.")
            return
        name = simpledialog.askstring("Удалить аккаунт", "Имя сессии для удаления из списка:", initialvalue=get_current_session() or (accounts[0] if accounts else ""), parent=self.winfo_toplevel())
        if name and name.strip():
            self._remove_account(name.strip())

    def _remove_account(self, session_name):
        if session_name not in get_accounts_list():
            return
        was_current = get_current_session() == session_name
        remove_account(session_name)
        if was_current:
            next_list = get_accounts_list()
            next_session = next_list[0] if next_list else None
            set_current_session(next_session)
        self._refresh_accounts_list()
        if not get_accounts_list():
            self.update_profile(None, None)
        elif was_current and self.on_switch_account:
            self.on_switch_account(get_current_session())

    def set_account(self, session_name):
        self._updating_account = True
        try:
            self._refresh_accounts_list()
        finally:
            self._updating_account = False

    def update_profile(self, me_dict, session=None):
        """Обновить блок профиля из словаря get_me."""
        if session is not None:
            self.set_account(session)
        for w in self.avatar_frame.winfo_children():
            w.destroy()
        avatar_path = (me_dict or {}).get("avatar_path") if me_dict else None
        if avatar_path and os.path.isfile(avatar_path):
            try:
                img = _avatar_image(avatar_path, 64)
                lbl = ctk.CTkLabel(self.avatar_frame, text="", image=img)
                lbl.image = img
                lbl.pack(expand=True)
            except Exception:
                self.avatar_placeholder = ctk.CTkLabel(self.avatar_frame, text="?", font=font(24))
                self.avatar_placeholder.pack(expand=True)
        else:
            self.avatar_placeholder = ctk.CTkLabel(self.avatar_frame, text="?", font=font(24))
            self.avatar_placeholder.pack(expand=True)
        if not me_dict:
            self.name_label.configure(
                text="Добавьте аккаунт" if not get_accounts_list() else "Не в сети"
            )
            self.username_label.configure(text="")
            self.phone_label.configure(text="")
            return
        first = (me_dict.get("first_name") or "").strip()
        last = (me_dict.get("last_name") or "").strip()
        name = f"{first} {last}".strip() or "Без имени"
        self.name_label.configure(text=name)
        username = me_dict.get("username")
        self.username_label.configure(text=f"@{username}" if username else "")
        phone = me_dict.get("phone_number")
        self.phone_label.configure(text=phone or "")
