
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
Диалог авторизации Telegram: ввод телефона → код → (опционально) 2FA-пароль.
Использует отдельный asyncio event loop в фоновом потоке.
"""
import asyncio
import threading
import logging
from queue import Queue, Empty

import customtkinter as ctk
from tkinter import messagebox

from pyrogram import Client
from pyrogram.errors import (
    BadRequest,
    FloodWait,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)

from core import get_project_root
from ui.theme import PAD, PAD_SM, BTN_RADIUS, ACCENT, ACCENT_HOVER, font

log = logging.getLogger("tg_deleter")

_SESSION_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


class LoginDialog(ctk.CTkToplevel):
    """
    Пошаговый диалог авторизации:
      Шаг 1 — имя сессии + номер телефона
      Шаг 2 — код из Telegram
      Шаг 3 — облачный пароль 2FA (если включён)
    on_success(session_name) вызывается из главного потока после успешного входа.
    """

    def __init__(self, parent, api_id, api_hash, on_success=None):
        super().__init__(parent)
        self.title("Добавить аккаунт")
        self.resizable(False, False)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._api_id = api_id
        self._api_hash = api_hash
        self._on_success = on_success
        self._workdir = get_project_root()

        self._client = None
        self._phone: str = ""
        self._session_name: str = ""
        self._phone_code_hash: str = ""
        self._busy = False

        self._q: Queue = Queue()

        # Background asyncio loop
        self._loop = asyncio.new_event_loop()
        self._bg_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._bg_thread.start()

        self._build_ui()
        self._poll()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=PAD * 2, pady=PAD * 2)

        ctk.CTkLabel(wrap, text="Добавить аккаунт", font=font(16, "bold")).pack(pady=(0, PAD))

        # Контейнер с фиксированной позицией — шаги переключаются внутри него,
        # поэтому status_label всегда остаётся ниже, независимо от pack-порядка.
        self._steps_host = ctk.CTkFrame(wrap, fg_color="transparent")
        self._steps_host.pack(fill="x")

        # --- Step 1: session name + phone ---
        self._step1 = ctk.CTkFrame(self._steps_host, fg_color="transparent")

        ctk.CTkLabel(self._step1, text="Имя сессии (латиница, цифры, _ -):", anchor="w", font=font(12)).pack(fill="x", pady=(0, 2))
        self._name_var = ctk.StringVar()
        self._name_entry = ctk.CTkEntry(self._step1, textvariable=self._name_var, placeholder_text="my_account", width=300, font=font(13))
        self._name_entry.pack(fill="x", pady=(0, PAD_SM))

        ctk.CTkLabel(self._step1, text="Номер телефона (с кодом страны):", anchor="w", font=font(12)).pack(fill="x", pady=(0, 2))
        self._phone_var = ctk.StringVar()
        self._phone_entry = ctk.CTkEntry(self._step1, textvariable=self._phone_var, placeholder_text="+79001234567", width=300, font=font(13))
        self._phone_entry.pack(fill="x", pady=(0, PAD))
        self._phone_entry.bind("<Return>", lambda _e: self._on_send_code())

        self._btn_send = ctk.CTkButton(
            self._step1, text="Получить код", command=self._on_send_code,
            corner_radius=BTN_RADIUS, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=font(13),
        )
        self._btn_send.pack(fill="x")

        # --- Step 2: code ---
        self._step2 = ctk.CTkFrame(self._steps_host, fg_color="transparent")

        ctk.CTkLabel(self._step2, text="Код из Telegram:", anchor="w", font=font(12)).pack(fill="x", pady=(0, 2))
        self._code_var = ctk.StringVar()
        self._code_entry = ctk.CTkEntry(self._step2, textvariable=self._code_var, placeholder_text="12345", width=300, font=font(13))
        self._code_entry.pack(fill="x", pady=(0, PAD))
        self._code_entry.bind("<Return>", lambda _e: self._on_sign_in())

        self._btn_signin = ctk.CTkButton(
            self._step2, text="Подтвердить", command=self._on_sign_in,
            corner_radius=BTN_RADIUS, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=font(13),
        )
        self._btn_signin.pack(fill="x", pady=(0, PAD_SM))

        self._btn_resend = ctk.CTkButton(
            self._step2, text="← Изменить номер", command=self._back_to_step1,
            corner_radius=BTN_RADIUS, height=30,
            fg_color=("gray65", "gray30"), hover_color=("gray55", "gray40"), font=font(12),
        )
        self._btn_resend.pack(fill="x")

        # --- Step 3: 2FA ---
        self._step3 = ctk.CTkFrame(self._steps_host, fg_color="transparent")

        ctk.CTkLabel(self._step3, text="Облачный пароль (2FA):", anchor="w", font=font(12)).pack(fill="x", pady=(0, 2))
        self._pass_var = ctk.StringVar()
        self._pass_entry = ctk.CTkEntry(self._step3, textvariable=self._pass_var, show="*", placeholder_text="Пароль", width=300, font=font(13))
        self._pass_entry.pack(fill="x", pady=(0, PAD))
        self._pass_entry.bind("<Return>", lambda _e: self._on_check_password())

        self._btn_2fa = ctk.CTkButton(
            self._step3, text="Войти", command=self._on_check_password,
            corner_radius=BTN_RADIUS, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER, font=font(13),
        )
        self._btn_2fa.pack(fill="x")

        # --- Status label (shared) — всегда ниже steps_host ---
        self._status_var = ctk.StringVar(value="")
        self._status_label = ctk.CTkLabel(wrap, textvariable=self._status_var, font=font(12), text_color=("gray40", "gray70"), wraplength=300)
        self._status_label.pack(pady=(PAD_SM, 0))

        self._show_step(1)

    def _show_step(self, step: int):
        # Переключаем шаги внутри _steps_host — его позиция в wrap не меняется
        for frame in (self._step1, self._step2, self._step3):
            frame.pack_forget()
        if step == 1:
            self._step1.pack(fill="x", in_=self._steps_host)
            self.after(50, self._name_entry.focus_set)
        elif step == 2:
            self._step2.pack(fill="x", in_=self._steps_host)
            self.after(50, self._code_entry.focus_set)
        elif step == 3:
            self._step3.pack(fill="x", in_=self._steps_host)
            self.after(50, self._pass_entry.focus_set)
        self.after(10, lambda: self.geometry(""))  # авто-ресайз после перерисовки

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_send_code(self):
        if self._busy:
            return
        name = self._name_var.get().strip()
        phone = self._phone_var.get().strip()
        if not name:
            self._set_status("Введите имя сессии.", error=True)
            return
        if len(name) < 2:
            self._set_status("Имя сессии: минимум 2 символа.", error=True)
            return
        if not all(c in _SESSION_CHARS for c in name):
            self._set_status("Имя сессии: только буквы, цифры, _ и -.", error=True)
            return
        if not phone or not phone.startswith("+"):
            self._set_status("Введите номер с кодом страны, например +79001234567.", error=True)
            return
        digits = phone[1:]
        if not digits.isdigit():
            self._set_status("Номер должен содержать только цифры после +.", error=True)
            return
        if len(digits) < 7 or len(digits) > 15:
            self._set_status("Номер телефона: от 7 до 15 цифр.", error=True)
            return
        self._session_name = name
        self._phone = phone
        self._set_busy(True)
        self._set_status("Отправка кода…")
        asyncio.run_coroutine_threadsafe(self._async_send_code(), self._loop)

    def _on_sign_in(self):
        if self._busy:
            return
        code = self._code_var.get().strip()
        if not code:
            self._set_status("Введите код из Telegram.", error=True)
            return
        self._set_busy(True)
        self._set_status("Проверка кода…")
        asyncio.run_coroutine_threadsafe(self._async_sign_in(code), self._loop)

    def _on_check_password(self):
        if self._busy:
            return
        password = self._pass_var.get()
        if not password:
            self._set_status("Введите облачный пароль.", error=True)
            return
        self._set_busy(True)
        self._set_status("Проверка пароля…")
        asyncio.run_coroutine_threadsafe(self._async_check_password(password), self._loop)

    def _back_to_step1(self):
        if self._busy:
            return
        self._code_var.set("")
        self._set_status("")
        self._show_step(1)

    # ------------------------------------------------------------------
    # Async methods (run in background loop)
    # ------------------------------------------------------------------

    async def _async_send_code(self):
        try:
            self._client = Client(
                self._session_name,
                api_id=self._api_id,
                api_hash=self._api_hash,
                workdir=self._workdir,
                no_updates=True,
            )
            await self._client.connect()
            sent = await self._client.send_code(self._phone)
            self._phone_code_hash = sent.phone_code_hash
            self._q.put(("need_code", None))
        except PhoneNumberInvalid:
            self._q.put(("error", "Неверный номер телефона."))
        except FloodWait as e:
            self._q.put(("flood", e.value))
        except Exception as e:
            log.exception("LoginDialog send_code error: %s", e)
            self._q.put(("error", f"Ошибка: {e}"))

    async def _async_sign_in(self, code: str):
        try:
            await self._client.sign_in(self._phone, self._phone_code_hash, code)
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._q.put(("success", self._session_name))
        except SessionPasswordNeeded:
            self._q.put(("need_2fa", None))
        except PhoneCodeInvalid:
            self._q.put(("error", "Неверный код. Попробуйте ещё раз."))
        except PhoneCodeExpired:
            self._q.put(("error", "Код истёк. Запросите новый."))
        except FloodWait as e:
            self._q.put(("flood", e.value))
        except Exception as e:
            log.exception("LoginDialog sign_in error: %s", e)
            self._q.put(("error", f"Ошибка входа: {e}"))

    async def _async_check_password(self, password: str):
        try:
            await self._client.check_password(password)
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._q.put(("success", self._session_name))
        except BadRequest:
            self._q.put(("error", "Неверный облачный пароль."))
        except FloodWait as e:
            self._q.put(("flood", e.value))
        except Exception as e:
            log.exception("LoginDialog check_password error: %s", e)
            self._q.put(("error", f"Ошибка 2FA: {e}"))

    # ------------------------------------------------------------------
    # Queue polling
    # ------------------------------------------------------------------

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind == "need_code":
                    self._set_busy(False)
                    self._set_status(f"Код отправлен на {self._phone}.", error=False)
                    self._show_step(2)
                elif kind == "need_2fa":
                    self._set_busy(False)
                    self._set_status("Требуется облачный пароль (2FA).", error=False)
                    self._show_step(3)
                elif kind == "success":
                    session_name = msg[1]
                    self._set_busy(False)
                    self._cleanup_loop()
                    if self._on_success:
                        self._on_success(session_name)
                    self.destroy()
                    return
                elif kind == "error":
                    self._set_busy(False)
                    self._set_status(msg[1], error=True)
                elif kind == "flood":
                    secs = msg[1]
                    self._set_busy(False)
                    self._set_status(f"Слишком много попыток. Подождите {secs} сек.", error=True)
        except Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self._name_entry, self._phone_entry, self._btn_send,
            self._code_entry, self._btn_signin, self._btn_resend,
            self._pass_entry, self._btn_2fa,
        ):
            try:
                widget.configure(state=state)
            except Exception:
                pass

    def _set_status(self, text: str, error: bool = False):
        self._status_var.set(text)
        color = ("#C62828", "#FF6B6B") if error else ("gray40", "gray70")
        self._status_label.configure(text_color=color)

    def _cleanup_loop(self):
        """Безопасно останавливает фоновый loop и ждёт завершения потока."""
        if self._client is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(self._client.disconnect(), self._loop)
                future.result(timeout=3)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._bg_thread.is_alive():
            self._bg_thread.join(timeout=3)

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno("Закрыть?", "Авторизация в процессе. Прервать?", parent=self):
                return
        self._cleanup_loop()
        self.destroy()
