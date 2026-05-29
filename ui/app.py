
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
Главное окно приложения.
"""
import json
import os
import re
import sys
import logging
import threading
from queue import Empty
from tkinter import messagebox

import customtkinter as ctk

from core import (
    Place,
    get_current_session,
    get_accounts_list,
    save_account_profile,
    get_export_parallel_chats,
    get_api_id,
    get_api_hash,
    get_api_config,
    load_config,
    load_api_config,
    get_project_root,
)
from ui.queues import request_queue, response_queue, log_queue, scan_paused, scan_stop_requested
from ui.theme import PAD, PAD_SM, SIDEBAR_WIDTH, font, set_theme
from ui.logging_config import setup_file_logging
from ui.cache_export import load_places_from_cache, save_places_to_cache, get_cache_mtime_str, clear_cache
from ui.places_frame import PlacesFrame
from ui.posts_frame import PostsFrame
from ui.export_frame import ExportFrame
from ui.sidebar_frame import SidebarFrame
from ui.settings_frame import SettingsFrame
from ui.worker import worker_loop
from ui.tray import TrayIcon
from ui.messages import (
    WorkerMsg, LogMsg, MeMsg, SwitchAccountDoneMsg,
    ScanProgressMsg, ScanPlaceMsg, ScanDoneMsg,
    DeleteOpStatusMsg, DeleteDoneMsg, DeleteAllExceptDoneMsg,
    DeleteAllNoScanDoneMsg, DeleteBatchProgressMsg, DeleteBatchDoneMsg,
    ExportProgressMsg, ExportDoneMsg,
    ExportDialogsProgressMsg, ExportDialogsBatchMsg, ExportDialogsDoneMsg,
    ErrorMsg, FloodWaitMsg, ConnectionStatusMsg,
)

log = logging.getLogger("tg_deleter")
_PROJECT_ROOT = get_project_root()
_MAX_LOG_LINES = 1000
_MAX_MSGS_PER_CYCLE = 200


def resource_path(*parts: str) -> str:
    """Absolute path to a bundled resource, working both from source and a frozen .exe."""
    base = getattr(sys, "_MEIPASS", None) or _PROJECT_ROOT
    return os.path.join(base, *parts)


class QueueLogHandler(logging.Handler):
    """Отправляет записи лога в log_queue для вывода в GUI."""
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass


class App:
    def __init__(self):
        load_api_config()
        load_config()
        set_theme(get_api_config().get("theme") or "dark")
        self.root = ctk.CTk()
        self.root.title("TG Deleter — удаление своих сообщений")
        self.root.minsize(720, 500)
        self.root.configure(fg_color=("gray95", "#121212"))
        self._set_window_icon()

        self.me = None
        self.places: list = []
        self._worker_started = False
        self._worker_thread = None
        self._closing = False
        self._operation_running = False
        self._pending_switch_session = None
        self._tray_hint_shown = False

        # System-tray icon for background mode (closing the window hides it here).
        self._tray = TrayIcon(
            resource_path("assets", "icon.png"),
            on_show=lambda: self.root.after(0, self._show_window),
            on_quit=lambda: self.root.after(0, self._quit_app),
            title="TG Deleter",
        )

        self._load_window_geometry()

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True)

        self.sidebar = SidebarFrame(
            main,
            width=SIDEBAR_WIDTH,
            on_quit=self._quit_app,
            on_switch_account=self._on_switch_account,
            on_show_chats=self._show_places,
            on_show_export=self._show_export,
            on_show_settings=self._show_settings,
            on_clear_cache=self._on_clear_cache,
            on_logout=self._on_logout,
            on_show_log=self._toggle_log,
        )
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)

        content_holder = ctk.CTkFrame(main, fg_color="transparent")
        content_holder.pack(side="left", fill="both", expand=True)

        content = ctk.CTkFrame(content_holder, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        has_api = get_api_id() and get_api_hash()
        self.settings_frame = SettingsFrame(content, on_saved=self._on_settings_saved, is_initial_setup=not has_api)
        self.places_frame = PlacesFrame(
            content,
            on_open_place=self._open_place,
            on_start_scan=self._on_start_scan,
            on_refresh_cache=self._refresh_cache,
            on_export_places=self._on_export_places,
        )
        self.posts_frame = PostsFrame(content, on_back=self._show_places, all_places_getter=lambda: self.places)
        self.export_frame = ExportFrame(
            content,
            on_load_dialogs=self._on_load_export_dialogs,
            on_export_places=self._on_export_places,
        )

        self._log_visible = False
        self.log_frame = ctk.CTkFrame(content_holder, fg_color=("gray90", "gray15"), height=160)
        self.log_frame.pack_propagate(False)
        log_inner = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_inner.pack(fill="both", expand=True, padx=PAD_SM, pady=PAD_SM)
        ctk.CTkLabel(log_inner, text="Лог", font=font(12, "bold")).pack(anchor="w")
        self.log_text = ctk.CTkTextbox(log_inner, height=120, font=ctk.CTkFont(size=12), wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "Здесь выводятся сообщения авторизации и работы приложения.\n")
        self.log_text.see("end")

        self._log_handler = QueueLogHandler()
        self._log_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(self._log_handler)

        self._msg_handlers = {
            # Typed message class names
            "LogMsg": self._handle_log_message,
            "MeMsg": self._handle_me,
            "SwitchAccountDoneMsg": self._handle_switch_account_done,
            "ScanProgressMsg": self._handle_scan_progress,
            "ScanPlaceMsg": self._handle_scan_place,
            "ScanDoneMsg": self._handle_scan_done,
            "DeleteOpStatusMsg": self._handle_delete_op_status,
            "DeleteDoneMsg": self._handle_delete_done,
            "DeleteAllExceptDoneMsg": self._handle_delete_all_except_done,
            "DeleteAllNoScanDoneMsg": self._handle_delete_all_no_scan_done,
            "DeleteBatchProgressMsg": self._handle_delete_batch_progress,
            "DeleteBatchDoneMsg": self._handle_delete_batch_done,
            "ExportProgressMsg": self._handle_export_progress,
            "ExportDoneMsg": self._handle_export_done,
            "ExportDialogsProgressMsg": self._handle_export_dialogs_progress,
            "ExportDialogsBatchMsg": self._handle_export_dialogs_batch,
            "ExportDialogsDoneMsg": self._handle_export_dialogs_done,
            "ErrorMsg": self._handle_error,
            "FloodWaitMsg": self._handle_flood_wait,
            "ConnectionStatusMsg": self._handle_connection_status,
            # Backward compat with tuple messages
            "log_message": self._handle_log_message,
            "me": self._handle_me,
            "switch_account_done": self._handle_switch_account_done,
            "scan_progress": self._handle_scan_progress,
            "scan_place": self._handle_scan_place,
            "scan_done": self._handle_scan_done,
            "delete_op_status": self._handle_delete_op_status,
            "delete_done": self._handle_delete_done,
            "delete_all_except_done": self._handle_delete_all_except_done,
            "delete_all_no_scan_done": self._handle_delete_all_no_scan_done,
            "delete_batch_progress": self._handle_delete_batch_progress,
            "delete_batch_done": self._handle_delete_batch_done,
            "export_progress": self._handle_export_progress,
            "export_done": self._handle_export_done,
            "export_dialogs_progress": self._handle_export_dialogs_progress,
            "export_dialogs_batch": self._handle_export_dialogs_batch,
            "export_dialogs_done": self._handle_export_dialogs_done,
            "error": self._handle_error,
            "flood_wait": self._handle_flood_wait,
        }

        if not has_api:
            self.sidebar.set_active_section("settings")
            self.settings_frame.pack(fill="both", expand=True)
        else:
            self.sidebar.set_active_section("chats")
            self.places_frame.pack(fill="both", expand=True)
            self._load_and_show_cache()
            self._start_worker()
            if not get_accounts_list():
                self.sidebar.update_profile(None, None)

        self.root.bind("<Control-s>", lambda e: self._on_start_scan_hotkey())
        self.root.bind("<Escape>", lambda e: self._on_escape())
        self.root.bind("<F5>", lambda e: self._refresh_cache())

        self.root.after(100, self._check_queue)

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def _start_worker(self):
        if self._worker_started:
            return
        self._worker_started = True
        self._worker_thread = threading.Thread(target=worker_loop, daemon=True)
        self._worker_thread.start()

    # ------------------------------------------------------------------
    # Cache loading (deduplicated)
    # ------------------------------------------------------------------

    def _load_and_show_cache(self, session: str | None = None):
        """Load cache for session and update places_frame. Returns True if cache existed."""
        if session is None:
            session = get_current_session()
        cached = load_places_from_cache(session)
        if cached:
            self.places = cached
            self.places_frame.set_places(self.places)
            mtime = get_cache_mtime_str(session)
            if mtime:
                self.places_frame.status_label.configure(
                    text=f"Кэш от {mtime}. Чатов: {len(self.places)}. Сканировать или обновить из кэша."
                )
            return True
        self.places_frame.status_label.configure(
            text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать», чтобы найти их."
        )
        return False

    # ------------------------------------------------------------------
    # Window geometry persistence
    # ------------------------------------------------------------------

    def _geometry_config_path(self):
        return os.path.join(_PROJECT_ROOT, "window_state.json")

    def _geometry_on_screen(self, geo: str) -> bool:
        """True if a saved geometry string keeps the window title bar reachable."""
        m = re.fullmatch(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", (geo or "").strip())
        if not m:
            return False
        w, h = int(m.group(1)), int(m.group(2))
        if w < 200 or h < 200:
            return False
        if m.group(3) is None:
            return True
        x, y = int(m.group(3)), int(m.group(4))
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if x < -w + 100 or x > screen_w - 100:
            return False
        if y < 0 or y > screen_h - 100:
            return False
        return True

    def _load_window_geometry(self):
        path = self._geometry_config_path()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                geo = data.get("geometry", "")
                if isinstance(geo, str) and self._geometry_on_screen(geo):
                    self.root.geometry(geo)
                    return
            except Exception:
                pass
        self.root.geometry("960x600")

    def _save_window_geometry(self):
        try:
            with open(self._geometry_config_path(), "w", encoding="utf-8") as f:
                json.dump({"geometry": self.root.geometry()}, f)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_settings_saved(self):
        """После сохранения настроек: если раньше не было API — показать основной экран и запустить воркер."""
        self.settings_frame.pack_forget()
        self.sidebar.set_active_section("chats")
        self.places_frame.pack(fill="both", expand=True)
        self._load_and_show_cache()
        self._start_worker()

    def _show_settings(self):
        self.places_frame.pack_forget()
        self.posts_frame.pack_forget()
        self.export_frame.pack_forget()
        self.sidebar.set_active_section("settings")
        self.settings_frame.set_initial_setup(False)
        self.settings_frame.refresh_from_config()
        self.settings_frame.pack(fill="both", expand=True)

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log_frame.pack(side="bottom", fill="x", padx=0, pady=0)
            self.log_text.see("end")
        else:
            self.log_frame.pack_forget()

    def _show_places(self):
        self.settings_frame.pack_forget()
        self.posts_frame.pack_forget()
        self.export_frame.pack_forget()
        self.sidebar.set_active_section("chats")
        self.places_frame.pack(fill="both", expand=True)

    def _show_export(self):
        self.settings_frame.pack_forget()
        self.posts_frame.pack_forget()
        self.places_frame.pack_forget()
        self.sidebar.set_active_section("export")
        self.export_frame.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def _on_switch_account(self, session_name):
        session_name = (session_name or "").strip()
        if not session_name:
            return
        self._pending_switch_session = session_name
        if self._operation_running or getattr(self.places_frame, "_scanning", False):
            scan_stop_requested.set()
            scan_paused.clear()
            self.places_frame.status_label.configure(text=f"Останавливаю текущую операцию и переключаюсь на {session_name}...")
            self.export_frame.status_label.configure(text=f"Останавливаю текущую операцию и переключаюсь на {session_name}...")
        else:
            self.places_frame.status_label.configure(text=f"Переключаюсь на {session_name}...")
            self.export_frame.status_label.configure(text=f"Переключаюсь на {session_name}...")
        request_queue.put(("switch_account", session_name))

    def _on_clear_cache(self):
        clear_cache(get_current_session())
        self.places = []
        self.places_frame.set_places(self.places)
        self.places_frame.status_label.configure(text="Кэш сброшен. Нажмите «Сканировать».")

    def _on_logout(self):
        if not messagebox.askyesno("Выйти из аккаунта", "Выйти из аккаунта?"):
            return
        accounts = get_accounts_list()
        if len(accounts) > 1:
            current = get_current_session()
            others = [a for a in accounts if a != current]
            if others:
                request_queue.put(("switch_account", others[0]))
                return
        self._quit_app()

    def _refresh_cache(self):
        session = get_current_session()
        if not self._load_and_show_cache(session):
            self.places_frame.status_label.configure(text="Кэш не найден или пуст.")
        else:
            mtime = get_cache_mtime_str(session)
            self.places_frame.status_label.configure(text=f"Загружено из кэша ({mtime}). Чатов: {len(self.places)}.")
            log.debug("refresh_cache: loaded %s places", len(self.places))

    # ------------------------------------------------------------------
    # Scan / Export triggers
    # ------------------------------------------------------------------

    def _on_start_scan(self):
        self._operation_running = True
        self._pending_switch_session = None
        self.places = []
        self.places_frame.set_places(self.places)

    def _on_load_export_dialogs(self, include_groups, include_channels, include_private):
        if not get_current_session():
            messagebox.showwarning("Экспорт", "Сначала добавьте аккаунт.")
            self.export_frame.set_loading(False)
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        self._operation_running = True
        self._pending_switch_session = None
        request_queue.put((
            "list_export_dialogs",
            include_groups,
            include_channels,
            include_private,
            scan_paused,
            scan_stop_requested,
        ))

    def _on_export_places(self, output_dir, chat_ids, export_options=None):
        if not chat_ids:
            messagebox.showinfo("Экспорт", "Отметьте один или несколько чатов для экспорта.")
            return
        if not get_current_session():
            messagebox.showwarning("Экспорт", "Сначала добавьте аккаунт.")
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        self._operation_running = True
        self._pending_switch_session = None
        parallel_chats = get_export_parallel_chats()
        self.places_frame.set_scanning(True, label="Экспортирую")
        self.export_frame.start_export_progress(len(chat_ids), parallel_chats)
        self.places_frame.status_label.configure(text=f"Бекап выбранных чатов: {len(chat_ids)}, параллельно: {parallel_chats}...")
        self.export_frame.status_label.configure(text=f"Бекап выбранных чатов: {len(chat_ids)}, параллельно: {parallel_chats}...")
        request_queue.put(("export_chats", output_dir, chat_ids, export_options or {}))

    def _open_place(self, place: Place):
        self.places_frame.pack_forget()
        self.posts_frame.pack(fill="both", expand=True)
        self.posts_frame.set_place(place)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _append_log(self, text):
        try:
            self.log_text.insert("end", str(text).strip() + "\n")
            line_count = int(self.log_text.index("end-1c").split(".")[0])
            if line_count > _MAX_LOG_LINES:
                self.log_text.delete("1.0", f"{line_count - _MAX_LOG_LINES}.0")
            self.log_text.see("end")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Queue dispatch
    # ------------------------------------------------------------------

    def _check_queue(self):
        if self._closing:
            return
        try:
            try:
                while True:
                    self._append_log(log_queue.get_nowait())
            except Empty:
                pass
            processed = 0
            while processed < _MAX_MSGS_PER_CYCLE:
                msg = response_queue.get_nowait()
                processed += 1
                if self._closing:
                    break
                try:
                    if isinstance(msg, tuple):
                        key = msg[0]
                    else:
                        key = type(msg).__name__
                    handler = self._msg_handlers.get(key)
                    if handler:
                        handler(msg)
                    else:
                        log.warning("Unknown message: %s", key)
                except Exception as e:
                    log.exception("check_queue handler: %s", e)
        except Empty:
            pass
        if not self._closing:
            self.root.after(100, self._check_queue)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _handle_log_message(self, msg):
        if isinstance(msg, LogMsg):
            self._append_log(msg.text)
        else:
            self._append_log(msg[1] if len(msg) > 1 else "")

    def _handle_me(self, msg):
        if isinstance(msg, MeMsg):
            me, session = msg.me_dict, msg.session
        else:
            me = msg[1]
            session = msg[2] if len(msg) > 2 else None
        log.debug("Got me")
        if session and session != get_current_session():
            return
        self.me = me
        if session and self.me:
            first = (self.me.get("first_name") or "").strip()
            last = (self.me.get("last_name") or "").strip()
            display_name = f"{first} {last}".strip() or self.me.get("username") or "Без имени"
            save_account_profile(session, {
                "display_name": display_name,
                "username": self.me.get("username"),
                "avatar_path": self.me.get("avatar_path"),
            })
        self.sidebar.update_profile(self.me, session)

    def _handle_switch_account_done(self, msg):
        session = msg.session if isinstance(msg, SwitchAccountDoneMsg) else msg[1]
        log.debug("Got switch_account_done: %s", session)
        self._pending_switch_session = None
        self._operation_running = False
        self.places_frame.set_scanning(False)
        self.export_frame.set_loading(False)
        self.places = []
        self.places_frame.set_places(self.places)
        self.export_frame.set_dialogs([])
        if not self._load_and_show_cache(session):
            self.places_frame.status_label.configure(
                text="Аккаунт: %s. Нажмите «Сканировать» или «Обновить из кэша»." % (get_current_session() or "—")
            )
        self.sidebar.set_account(session)

    def _handle_scan_progress(self, msg):
        log.debug("Got scan_progress")
        if isinstance(msg, ScanProgressMsg):
            n, title, count = msg.n, msg.title, msg.count
        else:
            n, title = msg[1], msg[2]
            count = msg[3] if len(msg) > 3 else None
        short = (title[:30] + "…") if len(title) > 30 else title
        if count is not None:
            if count == 0:
                status = f"Проверено диалогов: {n}. Текущий: {short} (0 сообщений)"
            else:
                status = f"Проверено диалогов: {n}. Текущий: {short} ({count} сообщ.)"
        else:
            status = f"Проверено диалогов: {n}. Текущий: {short}"
        self.places_frame.status_label.configure(text=status)

    def _handle_scan_place(self, msg):
        log.debug("Got scan_place")
        place = msg.place if isinstance(msg, ScanPlaceMsg) else msg[1]
        self.places.append(place)
        self.places_frame.append_place(place)
        self.places_frame.status_label.configure(text=f"Найдено чатов: {len(self.places)}…")

    def _handle_scan_done(self, msg):
        log.debug("Got scan_done")
        if isinstance(msg, ScanDoneMsg):
            self.places = msg.places
            stopped = msg.stopped
            session = msg.session
        else:
            self.places = msg[1]
            stopped = msg[2] if len(msg) > 2 else False
            session = msg[3] if len(msg) > 3 else get_current_session()
        mtime = get_cache_mtime_str(session)
        self._operation_running = False
        if self._pending_switch_session and session != self._pending_switch_session:
            self.places_frame.set_scanning(False)
            self.places_frame.status_label.configure(text="Операция остановлена. Переключаю аккаунт...")
            return
        if not stopped:
            save_places_to_cache(self.places, session)
            mtime = get_cache_mtime_str(session)
        self.places_frame.set_places(self.places)
        self.places_frame.set_scanning(False)
        if stopped:
            self.places_frame.status_label.configure(
                text=f"Скан остановлен. Найдено чатов: {len(self.places)}. Кэш не обновлялся."
            )
        elif len(self.places) == 0:
            self.places_frame.status_label.configure(
                text="Скан завершён. Чатов с вашими сообщениями не найдено. Кэш обновлён (%s)." % (mtime or "")
            )
        else:
            self.places_frame.status_label.configure(
                text="Кэш обновлён (%s). Чатов: %s. Выберите чат и нажмите «Открыть»." % (mtime or "", len(self.places))
            )

    def _handle_delete_op_status(self, msg):
        self._operation_running = True
        text = msg.text if isinstance(msg, DeleteOpStatusMsg) else (msg[1] if len(msg) > 1 else "")
        self.places_frame.status_label.configure(text=text)
        self.places_frame.set_scanning(True, label="Удаляю")

    def _handle_delete_done(self, msg):
        log.debug("Got delete_done")
        if isinstance(msg, DeleteDoneMsg):
            cid, deleted_ids, stopped = msg.chat_id, msg.deleted_ids, msg.stopped
        else:
            cid, deleted_ids = msg[1], msg[2]
            stopped = msg[3] if len(msg) > 3 else False
        self._operation_running = False
        self.places_frame.set_scanning(False)
        deleted_set = set(deleted_ids)
        self.posts_frame.remove_deleted_ids(deleted_ids)
        for p in self.places:
            if p.chat_id == cid:
                p.messages = [(m[0], m[1], m[2]) for m in p.messages if m[0] not in deleted_set]
                break
        self.places = [p for p in self.places if p.messages]
        self.places_frame.set_places(self.places)
        title = "Остановлено" if stopped else "Готово"
        messagebox.showinfo(title, "Удалено сообщений: %s" % len(deleted_ids))

    def _handle_delete_all_except_done(self, msg):
        log.debug("Got delete_all_except_done")
        if isinstance(msg, DeleteAllExceptDoneMsg):
            deleted_map, stopped = msg.deleted_map, msg.stopped
        else:
            deleted_map = msg[1] if len(msg) > 1 else {}
            stopped = msg[2] if len(msg) > 2 else False
        self._operation_running = False
        self.places_frame.set_scanning(False)
        except_cid = self.posts_frame.current_place.chat_id if self.posts_frame.current_place else None
        total_deleted = sum(len(v) for v in deleted_map.values()) if deleted_map else 0
        for p in self.places:
            if p.chat_id != except_cid:
                del_ids = deleted_map.get(p.chat_id, [])
                if del_ids:
                    del_set = set(del_ids)
                    p.messages = [(m[0], m[1], m[2]) for m in p.messages if m[0] not in del_set]
        self.places = [p for p in self.places if p.messages]
        self.places_frame.set_places(self.places)
        messagebox.showinfo("Остановлено" if stopped else "Готово", "Удалено сообщений: %s" % total_deleted)

    def _handle_delete_all_no_scan_done(self, msg):
        log.debug("Got delete_all_no_scan_done")
        if isinstance(msg, DeleteAllNoScanDoneMsg):
            cid, count, stopped = msg.chat_id, msg.count, msg.stopped
        else:
            cid, count = msg[1], msg[2]
            stopped = msg[3] if len(msg) > 3 else False
        self._operation_running = False
        self.places_frame.set_scanning(False)
        for p in self.places:
            if p.chat_id == cid:
                p.messages = []
                break
        self.places = [p for p in self.places if p.messages]
        self.places_frame.set_places(self.places)
        if self.posts_frame.current_place and self.posts_frame.current_place.chat_id == cid:
            self.posts_frame.current_place.messages = []
            self.posts_frame.set_place(self.posts_frame.current_place)
        messagebox.showinfo("Остановлено" if stopped else "Готово", "Удалено сообщений: %s" % count)

    def _handle_delete_batch_progress(self, msg):
        if isinstance(msg, DeleteBatchProgressMsg):
            i, total, cid = msg.current, msg.total, msg.chat_id
        else:
            i, total, cid = msg[1], msg[2], msg[3]
        self.places_frame.status_label.configure(text="Удаление в чатах: %s из %s…" % (i, total))

    def _handle_delete_batch_done(self, msg):
        if isinstance(msg, DeleteBatchDoneMsg):
            total_deleted, chat_ids, stopped = msg.total_deleted, msg.chat_ids, msg.stopped
        else:
            total_deleted, chat_ids = msg[1], msg[2]
            stopped = msg[3] if len(msg) > 3 else False
        self._operation_running = False
        self.places_frame.set_scanning(False)
        for cid in chat_ids:
            for p in self.places:
                if p.chat_id == cid:
                    p.messages = []
                    break
        self.places = [p for p in self.places if p.messages]
        self.places_frame.set_places(self.places)
        if self.posts_frame.current_place and self.posts_frame.current_place.chat_id in chat_ids:
            self.posts_frame.current_place.messages = []
            self.posts_frame.set_place(self.posts_frame.current_place)
        self.places_frame.status_label.configure(text="Выберите чат и нажмите «Открыть» или дважды щёлкните по карточке.")
        messagebox.showinfo("Остановлено" if stopped else "Готово", "Удалено сообщений: %s в %s чатах." % (total_deleted, len(chat_ids)))

    def _handle_export_progress(self, msg):
        if isinstance(msg, ExportProgressMsg):
            kind, payload = msg.kind, msg.payload
        else:
            kind = msg[1]
            payload = msg[2] if len(msg) > 2 else {}
        current_title = payload.get("title")
        if kind in ("overall_start", "overall_progress", "chat_start", "chat_progress", "chat_done"):
            if kind == "overall_start":
                self.export_frame.start_export_progress(payload.get("total_chats", 0), payload.get("parallel_chats"))
            self.export_frame.update_export_progress(payload, current_title=current_title)
        if kind == "overall_start":
            self.places_frame.status_label.configure(
                text="Бекап: чаты 0/%s, параллельно: %s..." % (
                    payload.get("total_chats", 0),
                    payload.get("parallel_chats", get_export_parallel_chats()),
                )
            )
            self.export_frame.status_label.configure(text="Считаю объём истории перед бекапом...")
        elif kind == "overall_progress":
            if payload.get("total_messages") is not None:
                status = "Бекап: чаты %s/%s, сообщения %s/%s" % (
                    payload.get("done_chats", 0),
                    payload.get("total_chats", 0),
                    payload.get("done_messages", 0),
                    payload.get("total_messages", 0),
                )
            else:
                status = "Бекап: чаты %s/%s, сообщения %s" % (
                    payload.get("done_chats", 0),
                    payload.get("total_chats", 0),
                    payload.get("done_messages", 0),
                )
            self.places_frame.status_label.configure(text=status)
            self.export_frame.status_label.configure(text=status)
        elif kind == "chat_start":
            self.places_frame.status_label.configure(text="Бекап: %s..." % payload.get("title", payload.get("chat_id", "")))
            self.export_frame.status_label.configure(text="Бекап: %s..." % payload.get("title", payload.get("chat_id", "")))
        elif kind == "chat_progress":
            chat_total = payload.get("chat_total_messages")
            messages = payload.get("messages", 0)
            msg_part = f"{messages}/{chat_total}" if chat_total is not None else str(messages)
            status = "Бекап: %s, сообщений: %s, медиа: %s" % (
                payload.get("title", ""),
                msg_part,
                payload.get("media", 0),
            )
            self.places_frame.status_label.configure(text=status)
            self.export_frame.status_label.configure(text=status)
        elif kind == "chat_done":
            status = "Готов чат: %s, сообщений: %s" % (payload.get("title", ""), payload.get("messages", 0))
            self.places_frame.status_label.configure(text=status)
            self.export_frame.status_label.configure(text=status)

    def _handle_export_done(self, msg):
        if isinstance(msg, ExportDoneMsg):
            root, manifest, stopped = msg.root, msg.manifest, msg.stopped
        else:
            root, manifest = msg[1], msg[2]
            stopped = msg[3] if len(msg) > 3 else False
        self._operation_running = False
        self.places_frame.set_scanning(False)
        self.export_frame.finish_export_progress(stopped)
        total_messages = manifest.get("total_messages", 0)
        total_media = manifest.get("total_media", 0)
        self.places_frame.status_label.configure(text=f"Экспорт готов: {root}")
        self.export_frame.status_label.configure(text=f"Экспорт готов: {root}")
        messagebox.showinfo(
            "Остановлено" if stopped else "Экспорт готов",
            "Папка: %s\nСообщений: %s\nМедиа: %s" % (root, total_messages, total_media),
        )

    def _handle_export_dialogs_progress(self, msg):
        if isinstance(msg, ExportDialogsProgressMsg):
            n, title = msg.n, msg.title
        else:
            n, title = msg[1], msg[2]
        short = (title[:40] + "…") if len(title) > 40 else title
        self.export_frame.status_label.configure(text=f"Загружено диалогов: {n}. Текущий: {short}")

    def _handle_export_dialogs_batch(self, msg):
        batch = msg.batch if isinstance(msg, ExportDialogsBatchMsg) else msg[1]
        self.export_frame.append_dialogs(batch)

    def _handle_export_dialogs_done(self, msg):
        if isinstance(msg, ExportDialogsDoneMsg):
            dialogs, stopped = msg.dialogs, msg.stopped
        else:
            dialogs = msg[1]
            stopped = msg[2] if len(msg) > 2 else False
        self._operation_running = False
        self.export_frame.set_loading(False)
        self.export_frame.dialogs = list(dialogs)
        self.export_frame.status_label.configure(
            text=("Список остановлен." if stopped else "Список загружен.") + f" Диалогов: {len(dialogs)}."
        )

    def _handle_error(self, msg):
        if isinstance(msg, ErrorMsg):
            op, err = msg.operation, msg.error
        else:
            op = msg[1] if len(msg) > 1 else ""
            err = msg[2] if len(msg) > 2 else (msg[1] if len(msg) > 1 else "Неизвестная ошибка")
        log.debug("Got error in %s: %s", op, err)
        if op == "scan":
            self.places_frame.set_scanning(False)
            self.places_frame.status_label.configure(text="Ошибка сканирования")
        if op == "export_chats":
            self.places_frame.set_scanning(False)
            self.export_frame.finish_export_progress(stopped=True)
            self.places_frame.status_label.configure(text="Ошибка экспорта")
            self.export_frame.status_label.configure(text="Ошибка экспорта")
        if op == "list_export_dialogs":
            self.export_frame.set_loading(False)
            self.export_frame.status_label.configure(text="Ошибка загрузки списка")
        self._operation_running = False
        messagebox.showerror("Ошибка", err)

    def _handle_connection_status(self, msg):
        connected = msg.connected if isinstance(msg, ConnectionStatusMsg) else bool(msg[1])
        self.sidebar.set_connection_status(connected)

    def _handle_flood_wait(self, msg):
        if isinstance(msg, FloodWaitMsg):
            seconds, operation = msg.seconds, msg.operation
        else:
            seconds = msg[1] if len(msg) > 1 else 0
            operation = msg[2] if len(msg) > 2 else ""
        self.places_frame.status_label.configure(
            text=f"Telegram просит подождать: {seconds} сек... ({operation})"
        )
        self.export_frame.status_label.configure(
            text=f"Telegram просит подождать: {seconds} сек..."
        )

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def _on_start_scan_hotkey(self):
        if not self._operation_running and hasattr(self.places_frame, '_start_scan'):
            self.places_frame._start_scan()

    def _on_escape(self):
        if self._operation_running:
            scan_stop_requested.set()
            scan_paused.clear()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _set_window_icon(self):
        """Set the taskbar / title-bar icon (best-effort, cross-platform)."""
        ico = resource_path("assets", "icon.ico")
        png = resource_path("assets", "icon.png")
        try:
            if os.path.isfile(ico):
                self.root.iconbitmap(ico)
                return
        except Exception:
            pass
        try:
            if os.path.isfile(png):
                import tkinter as tk
                self._icon_image = tk.PhotoImage(file=png)
                self.root.iconphoto(True, self._icon_image)
        except Exception:
            pass

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        if self._tray.available:
            self._tray.start()
        self.root.mainloop()

    def _on_window_close(self):
        """X button: hide to the system tray and keep running in the background."""
        if self._closing:
            return
        if self._tray.available:
            self._save_window_geometry()
            self.root.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._tray.notify(
                    "Приложение свёрнуто в трей и продолжает работать в фоне. "
                    "«Открыть» — вернуть окно, «Выход» — закрыть полностью.",
                    "TG Deleter",
                )
            log.debug("window minimized to tray")
            return
        # No tray available — fall back to a full quit.
        self._quit_app()

    def _show_window(self):
        """Restore the window from the tray."""
        if self._closing:
            return
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as e:
            log.debug("show_window failed: %s", e)

    def _quit_app(self):
        if self._closing:
            return
        self._closing = True
        log.removeHandler(self._log_handler)
        scan_stop_requested.set()
        scan_paused.clear()
        try:
            self._save_window_geometry()
        except Exception:
            pass
        request_queue.put(("quit",))
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.root.title("TG Deleter — закрываюсь…")
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
            if self._worker_thread.is_alive():
                log.warning("Worker thread did not stop in time")
        self._tray.stop()
        self.root.destroy()


def run_gui():
    try:
        log.setLevel(logging.DEBUG)
        log_path = setup_file_logging(_PROJECT_ROOT)
        log.debug("file logging enabled: %s", log_path)
    except Exception:
        pass
    a = App()
    a.run()
