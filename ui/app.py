"""
Главное окно приложения и фоновый воркер (Pyrogram).
"""
import os
import asyncio
import logging
import threading
from queue import Empty
from tkinter import messagebox

import customtkinter as ctk

from core import (
    ExportOptions,
    Place,
    clear_me,
    create_client,
    export_chats_streaming,
    get_current_session,
    set_current_session,
    set_app,
    get_accounts_list,
    set_me_from_dict,
    fetch_and_set_my_channels,
    save_account_profile,
    list_export_dialogs,
    scan_all_dialogs,
    delete_message_ids,
    delete_all_my_in_chat_no_scan,
    get_scan_delay_between_chats,
    get_export_parallel_chats,
    get_export_include_media,
    get_export_message_limit,
    get_api_id,
    get_api_hash,
    load_config,
    load_api_config,
    get_project_root,
)
from ui.queues import request_queue, response_queue, log_queue, scan_paused, scan_stop_requested
from ui.theme import PAD, PAD_SM, SIDEBAR_WIDTH, font
from ui.cache_export import load_places_from_cache, save_places_to_cache, get_cache_mtime_str, clear_cache
from ui.places_frame import PlacesFrame
from ui.posts_frame import PostsFrame
from ui.export_frame import ExportFrame
from ui.sidebar_frame import SidebarFrame
from ui.settings_frame import SettingsFrame

log = logging.getLogger("tg_deleter")
_PROJECT_ROOT = get_project_root()


class QueueLogHandler(logging.Handler):
    """Отправляет записи лога в log_queue для вывода в GUI."""
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put(msg)
        except Exception:
            pass


def worker_loop():
    """Фоновый поток: asyncio + Pyrogram, поддержка переключения аккаунтов."""
    log.debug("worker_loop started")

    async def _run():
        def handle_control_request(req):
            if req[0] == "quit":
                log.debug("worker_loop quit")
                set_app(None)
                return "quit"
            if req[0] == "switch_account":
                new_session = req[1]
                clear_me()
                set_current_session(new_session)
                set_app(None)
                response_queue.put(("switch_account_done", new_session))
                log.debug("worker: switch to %s", new_session)
                return "switch"
            response_queue.put(("error", req[0], "Нет подключенной Telegram-сессии."))
            return "handled"

        while True:
            session = get_current_session() or (get_accounts_list() or [None])[0]
            if not session:
                try:
                    req = request_queue.get_nowait()
                    action = handle_control_request(req)
                    if action == "quit":
                        return
                except Empty:
                    pass
                await asyncio.sleep(2)
                continue
            session_file = os.path.join(_PROJECT_ROOT, session + ".session")
            if not os.path.isfile(session_file):
                response_queue.put(("log_message", "Сессия «%s» не авторизована. Добавьте аккаунт через кнопку «Добавить» в левой панели." % session))
                try:
                    req = request_queue.get_nowait()
                    action = handle_control_request(req)
                    if action == "quit":
                        return
                except Empty:
                    pass
                await asyncio.sleep(2)
                continue
            try:
                app = create_client(session)
                async with app:
                    set_app(app)
                    channels_ready = False
                    async def ensure_channels_ready():
                        nonlocal channels_ready
                        if channels_ready:
                            return
                        try:
                            await fetch_and_set_my_channels(app)
                        except Exception as ch_err:
                            log.warning("worker: fetch_and_set_my_channels skip: %s", ch_err)
                        channels_ready = True

                    try:
                        me = await app.get_me()
                        me_dict = {
                            "id": getattr(me, "id", None),
                            "first_name": getattr(me, "first_name", None) or "",
                            "last_name": getattr(me, "last_name", None) or "",
                            "username": (getattr(me, "username", None) or "").strip() or None,
                            "phone_number": getattr(me, "phone_number", None) or None,
                        }
                        set_me_from_dict(me_dict)
                        response_queue.put(("me", me_dict, session))
                        async def download_avatar():
                            avatar_path = None
                            try:
                                profile = await app.get_profile_photos(me.id, limit=1)
                                if profile and getattr(profile, "photos", None) and len(profile.photos) > 0 and len(profile.photos[0]) > 0:
                                    photo = profile.photos[0][-1]
                                    temp_dir = os.path.join(_PROJECT_ROOT, "temp")
                                    os.makedirs(temp_dir, exist_ok=True)
                                    avatar_path = os.path.join(temp_dir, f"avatar_{session}_{me.id}.jpg")
                                    await app.download_media(photo.file_id, file_name=avatar_path)
                                    if not os.path.isfile(avatar_path):
                                        avatar_path = None
                            except Exception as av_err:
                                log.debug("worker: avatar download skip: %s", av_err)
                            if avatar_path:
                                updated = dict(me_dict)
                                updated["avatar_path"] = avatar_path
                                response_queue.put(("me", updated, session))
                        asyncio.create_task(download_avatar())
                        log.debug("worker: sent me profile to GUI, session=%s", session)
                    except Exception as e:
                        log.warning("worker: get_me failed: %s", e)
                    while True:
                        try:
                            req = request_queue.get_nowait()
                        except Empty:
                            await asyncio.sleep(0.2)
                            continue
                        if req[0] == "quit":
                            handle_control_request(req)
                            return
                        if req[0] == "switch_account":
                            handle_control_request(req)
                            break
                        log.debug("worker: request %s", req[0])
                        try:
                            if req[0] == "scan":
                                await ensure_channels_ready()
                                include_groups = req[1]
                                include_channels = req[2]
                                include_private = req[3]
                                pause_ev = req[4]
                                max_my_messages_per_chat = req[5] if len(req) > 5 else None
                                stop_ev = req[6] if len(req) > 6 else None
                                def on_place(p):
                                    response_queue.put(("scan_place", p))
                                    log.debug("worker: put scan_place")
                                def on_dialog(n, title, count=None):
                                    response_queue.put(("scan_progress", n, title, count))
                                places = await scan_all_dialogs(
                                    include_groups=include_groups,
                                    include_channels=include_channels,
                                    include_private=include_private,
                                    pause_event=pause_ev,
                                    stop_event=stop_ev,
                                    progress_callback=on_place,
                                    dialog_progress_callback=on_dialog,
                                    max_my_messages_per_chat=max_my_messages_per_chat,
                                )
                                stopped = stop_ev is not None and stop_ev.is_set()
                                response_queue.put(("scan_done", places, stopped, session))
                                log.debug("worker: put scan_done, places=%s stopped=%s", len(places), stopped)
                            elif req[0] == "delete_all_no_scan":
                                await ensure_channels_ready()
                                cid = req[1]
                                response_queue.put(("delete_op_status", f"Удаление в чате {cid}..."))
                                count = await delete_all_my_in_chat_no_scan(cid, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(("delete_all_no_scan_done", cid, count, scan_stop_requested.is_set()))
                                log.debug("worker: put delete_all_no_scan_done")
                            elif req[0] == "delete_here":
                                await ensure_channels_ready()
                                cid, ids = req[1], req[2]
                                response_queue.put(("delete_op_status", f"Удаляю {len(ids)} сообщений в чате {cid}..."))
                                deleted_ids = await delete_message_ids(cid, ids, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(("delete_done", cid, deleted_ids, scan_stop_requested.is_set()))
                                log.debug("worker: put delete_done")
                            elif req[0] == "delete_all_except":
                                await ensure_channels_ready()
                                except_cid = req[1]
                                places_list = req[2]
                                deleted_map = {}
                                targets = [p for p in places_list if p.chat_id != except_cid and p.messages]
                                total_targets = len(targets)
                                for i, place in enumerate(targets):
                                    if scan_stop_requested.is_set():
                                        break
                                    response_queue.put(("delete_op_status", f"Удаление в чатах: {i + 1} из {total_targets}..."))
                                    ids = [m[0] for m in place.messages]
                                    if ids:
                                        deleted_ids = await delete_message_ids(place.chat_id, ids, pause_event=scan_paused, stop_event=scan_stop_requested)
                                        if deleted_ids:
                                            deleted_map[place.chat_id] = deleted_ids
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(("delete_all_except_done", deleted_map, scan_stop_requested.is_set()))
                                log.debug("worker: put delete_all_except_done")
                            elif req[0] == "delete_in_places":
                                await ensure_channels_ready()
                                chat_ids = req[1]
                                total_deleted = 0
                                for i, cid in enumerate(chat_ids):
                                    if scan_stop_requested.is_set():
                                        break
                                    response_queue.put(("delete_batch_progress", i + 1, len(chat_ids), cid))
                                    n = await delete_all_my_in_chat_no_scan(cid, pause_event=scan_paused, stop_event=scan_stop_requested)
                                    total_deleted += n
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(("delete_batch_done", total_deleted, chat_ids, scan_stop_requested.is_set()))
                                log.debug("worker: put delete_batch_done, deleted=%s", total_deleted)
                            elif req[0] == "export_chats":
                                output_dir = req[1]
                                chat_ids = req[2]
                                options = ExportOptions(
                                    output_dir=output_dir,
                                    chat_ids=chat_ids,
                                    parallel_chats=get_export_parallel_chats(),
                                    include_media=get_export_include_media(),
                                    message_limit=get_export_message_limit(),
                                )
                                def on_export(kind, payload):
                                    response_queue.put(("export_progress", kind, payload))
                                root, manifest = await export_chats_streaming(
                                    options,
                                    pause_event=scan_paused,
                                    stop_event=scan_stop_requested,
                                    progress_callback=on_export,
                                )
                                response_queue.put(("export_done", root, manifest, scan_stop_requested.is_set()))
                                log.debug("worker: put export_done, root=%s", root)
                            elif req[0] == "list_export_dialogs":
                                include_groups = req[1]
                                include_channels = req[2]
                                include_private = req[3]
                                pause_ev = req[4]
                                stop_ev = req[5]
                                batch = []
                                def flush_batch():
                                    nonlocal batch
                                    if batch:
                                        response_queue.put(("export_dialogs_batch", batch))
                                        batch = []
                                def on_dialog(place):
                                    batch.append(place)
                                    if len(batch) >= 50:
                                        flush_batch()
                                def on_progress(n, title):
                                    response_queue.put(("export_dialogs_progress", n, title))
                                dialogs = await list_export_dialogs(
                                    include_groups=include_groups,
                                    include_channels=include_channels,
                                    include_private=include_private,
                                    pause_event=pause_ev,
                                    stop_event=stop_ev,
                                    progress_callback=on_dialog,
                                    dialog_progress_callback=on_progress,
                                )
                                flush_batch()
                                response_queue.put(("export_dialogs_done", dialogs, scan_stop_requested.is_set(), session))
                                log.debug("worker: put export_dialogs_done, dialogs=%s", len(dialogs))
                        except Exception as e:
                            log.exception("worker error in %s: %s", req[0], e)
                            response_queue.put(("error", req[0], str(e)))
            except Exception as e:
                set_app(None)
                log.exception("worker reconnect loop error for session=%s: %s", session, e)
                response_queue.put(("log_message", f"Проблема соединения для сессии «{session}». Повтор через 5 сек."))
                await asyncio.sleep(5)
    asyncio.run(_run())
    log.debug("worker_loop finished")


class App:
    def __init__(self):
        load_api_config()
        load_config()
        self.root = ctk.CTk()
        self.root.title("TG Deleter — удаление своих сообщений")
        self.root.geometry("960x600")
        self.root.minsize(720, 500)
        self.root.configure(fg_color=("gray95", "#121212"))

        self.me = None
        self.places: list = []
        self._worker_started = False
        self._worker_thread = None
        self._closing = False
        self._operation_running = False
        self._pending_switch_session = None

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True)

        self.sidebar = SidebarFrame(
            main,
            width=SIDEBAR_WIDTH,
            on_quit=self._on_close,
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

        handler = QueueLogHandler()
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"))
        log.addHandler(handler)

        if not has_api:
            self.sidebar.set_active_section("settings")
            self.settings_frame.pack(fill="both", expand=True)
        else:
            self.sidebar.set_active_section("chats")
            self.places_frame.pack(fill="both", expand=True)
            self.posts_frame.pack(fill="both", expand=True)
            self.posts_frame.pack_forget()
            self.export_frame.pack(fill="both", expand=True)
            self.export_frame.pack_forget()
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
            else:
                self.places_frame.status_label.configure(
                    text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать», чтобы найти их."
                )
            self._start_worker()
            if not get_accounts_list():
                self.sidebar.update_profile(None, None)
        self.root.after(100, self._check_queue)

    def _start_worker(self):
        if self._worker_started:
            return
        self._worker_started = True
        self._worker_thread = threading.Thread(target=worker_loop, daemon=True)
        self._worker_thread.start()

    def _on_settings_saved(self):
        """После сохранения настроек: если раньше не было API — показать основной экран и запустить воркер."""
        self.settings_frame.pack_forget()
        self.sidebar.set_active_section("chats")
        self.places_frame.pack(fill="both", expand=True)
        self.posts_frame.pack(fill="both", expand=True)
        self.posts_frame.pack_forget()
        self.export_frame.pack(fill="both", expand=True)
        self.export_frame.pack_forget()
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
        else:
            self.places_frame.status_label.configure(
                text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать», чтобы найти их."
            )
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
        self._on_close()

    def _refresh_cache(self):
        session = get_current_session()
        cached = load_places_from_cache(session)
        if cached is None:
            self.places_frame.status_label.configure(text="Кэш не найден или пуст.")
            return
        self.places = cached
        self.places_frame.set_places(self.places)
        mtime = get_cache_mtime_str(session)
        self.places_frame.status_label.configure(text=f"Загружено из кэша ({mtime}). Чатов: {len(self.places)}.")
        log.debug("refresh_cache: loaded %s places", len(self.places))

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

    def _on_export_places(self, output_dir, chat_ids):
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
        self.places_frame.set_scanning(True, label="Экспортирую")
        self.export_frame.set_loading(True, label="Экспортирую")
        self.places_frame.status_label.configure(text=f"Экспорт выбранных чатов: {len(chat_ids)}...")
        self.export_frame.status_label.configure(text=f"Экспорт выбранных чатов: {len(chat_ids)}...")
        request_queue.put(("export_chats", output_dir, chat_ids))

    def _open_place(self, place: Place):
        self.places_frame.pack_forget()
        self.posts_frame.pack(fill="both", expand=True)
        self.posts_frame.set_place(place)

    def _append_log(self, text):
        try:
            self.log_text.insert("end", str(text).strip() + "\n")
            self.log_text.see("end")
        except Exception:
            pass

    def _check_queue(self):
        try:
            try:
                while True:
                    line = log_queue.get_nowait()
                    self._append_log(line)
            except Empty:
                pass
            while True:
                msg = response_queue.get_nowait()
                try:
                    if msg[0] == "log_message":
                        self._append_log(msg[1] if len(msg) > 1 else "")
                    elif msg[0] == "me":
                        log.debug("Got me")
                        me = msg[1]
                        session = msg[2] if len(msg) > 2 else None
                        if session and session != get_current_session():
                            continue
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
                    elif msg[0] == "switch_account_done":
                        log.debug("Got switch_account_done: %s", msg[1])
                        self._pending_switch_session = None
                        self._operation_running = False
                        self.places_frame.set_scanning(False)
                        self.export_frame.set_loading(False)
                        self.places = []
                        self.places_frame.set_places(self.places)
                        self.export_frame.set_dialogs([])
                        session = msg[1]
                        cached = load_places_from_cache(session)
                        if cached:
                            self.places = cached
                            self.places_frame.set_places(self.places)
                            mtime = get_cache_mtime_str(session)
                            if mtime:
                                self.places_frame.status_label.configure(
                                    text=f"Кэш от {mtime}. Чатов: {len(self.places)}. Сканировать или обновить из кэша."
                                )
                            else:
                                self.places_frame.status_label.configure(
                                    text="Здесь появятся чаты с вашими сообщениями. Нажмите «Сканировать» или «Обновить из кэша»."
                                )
                        else:
                            self.places_frame.status_label.configure(
                                text="Аккаунт: %s. Нажмите «Сканировать» или «Обновить из кэша»." % (get_current_session() or "—")
                            )
                        self.sidebar.set_account(msg[1])
                    elif msg[0] == "export_dialogs_progress":
                        n, title = msg[1], msg[2]
                        short = (title[:40] + "…") if len(title) > 40 else title
                        self.export_frame.status_label.configure(text=f"Загружено диалогов: {n}. Текущий: {short}")
                    elif msg[0] == "export_dialogs_batch":
                        batch = msg[1]
                        self.export_frame.append_dialogs(batch)
                    elif msg[0] == "export_dialogs_done":
                        dialogs = msg[1]
                        stopped = msg[2] if len(msg) > 2 else False
                        self._operation_running = False
                        self.export_frame.set_loading(False)
                        self.export_frame.dialogs = list(dialogs)
                        self.export_frame.status_label.configure(
                            text=("Список остановлен." if stopped else "Список загружен.") + f" Диалогов: {len(dialogs)}."
                        )
                    elif msg[0] == "scan_progress":
                        log.debug("Got scan_progress")
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
                        self.root.update_idletasks()
                    elif msg[0] == "scan_place":
                        log.debug("Got scan_place")
                        place = msg[1]
                        self.places.append(place)
                        self.places_frame.append_place(place)
                        self.places_frame.status_label.configure(text=f"Найдено чатов: {len(self.places)}…")
                    elif msg[0] == "scan_done":
                        log.debug("Got scan_done")
                        self.places = msg[1]
                        stopped = msg[2] if len(msg) > 2 else False
                        session = msg[3] if len(msg) > 3 else get_current_session()
                        save_places_to_cache(self.places, session)
                        mtime = get_cache_mtime_str(session)
                        self._operation_running = False
                        if self._pending_switch_session and session != self._pending_switch_session:
                            self.places_frame.set_scanning(False)
                            self.places_frame.status_label.configure(text="Операция остановлена. Переключаю аккаунт...")
                            continue
                        self.places_frame.set_places(self.places)
                        self.places_frame.set_scanning(False)
                        if stopped:
                            self.places_frame.status_label.configure(
                                text=f"Скан остановлен. Найдено чатов: {len(self.places)}. Кэш обновлён ({mtime})."
                            )
                        elif len(self.places) == 0:
                            self.places_frame.status_label.configure(
                                text="Скан завершён. Чатов с вашими сообщениями не найдено. Кэш обновлён (%s)." % (mtime or "")
                            )
                        else:
                            self.places_frame.status_label.configure(
                                text="Кэш обновлён (%s). Чатов: %s. Выберите чат и нажмите «Открыть»." % (mtime or "", len(self.places))
                            )
                    elif msg[0] == "delete_op_status":
                        self._operation_running = True
                        self.places_frame.status_label.configure(text=msg[1])
                    elif msg[0] == "delete_done":
                        log.debug("Got delete_done")
                        cid, deleted_ids = msg[1], msg[2]
                        stopped = msg[3] if len(msg) > 3 else False
                        self._operation_running = False
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
                    elif msg[0] == "delete_all_except_done":
                        log.debug("Got delete_all_except_done")
                        deleted_map = msg[1] if len(msg) > 1 else {}
                        stopped = msg[2] if len(msg) > 2 else False
                        self._operation_running = False
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
                    elif msg[0] == "delete_all_no_scan_done":
                        log.debug("Got delete_all_no_scan_done")
                        cid, count = msg[1], msg[2]
                        stopped = msg[3] if len(msg) > 3 else False
                        self._operation_running = False
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
                    elif msg[0] == "delete_batch_progress":
                        i, total, cid = msg[1], msg[2], msg[3]
                        self.places_frame.status_label.configure(text="Удаление в чатах: %s из %s…" % (i, total))
                    elif msg[0] == "delete_batch_done":
                        total_deleted, chat_ids = msg[1], msg[2]
                        stopped = msg[3] if len(msg) > 3 else False
                        self._operation_running = False
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
                    elif msg[0] == "export_progress":
                        kind = msg[1]
                        payload = msg[2] if len(msg) > 2 else {}
                        if kind == "chat_start":
                            self.places_frame.status_label.configure(text="Экспорт: %s..." % payload.get("title", payload.get("chat_id", "")))
                            self.export_frame.status_label.configure(text="Экспорт: %s..." % payload.get("title", payload.get("chat_id", "")))
                        elif kind == "chat_progress":
                            status = "Экспорт: %s, сообщений: %s, медиа: %s" % (
                                payload.get("title", ""),
                                payload.get("messages", 0),
                                payload.get("media", 0),
                            )
                            self.places_frame.status_label.configure(text=status)
                            self.export_frame.status_label.configure(text=status)
                        elif kind == "chat_done":
                            status = "Готов чат: %s, сообщений: %s" % (payload.get("title", ""), payload.get("messages", 0))
                            self.places_frame.status_label.configure(text=status)
                            self.export_frame.status_label.configure(text=status)
                    elif msg[0] == "export_done":
                        root, manifest = msg[1], msg[2]
                        stopped = msg[3] if len(msg) > 3 else False
                        self._operation_running = False
                        self.places_frame.set_scanning(False)
                        self.export_frame.set_loading(False)
                        total_messages = manifest.get("total_messages", 0)
                        total_media = manifest.get("total_media", 0)
                        self.places_frame.status_label.configure(text=f"Экспорт готов: {root}")
                        self.export_frame.status_label.configure(text=f"Экспорт готов: {root}")
                        messagebox.showinfo(
                            "Остановлено" if stopped else "Экспорт готов",
                            "Папка: %s\nСообщений: %s\nМедиа: %s" % (root, total_messages, total_media),
                        )
                    elif msg[0] == "error":
                        op = msg[1] if len(msg) > 1 else ""
                        err = msg[2] if len(msg) > 2 else (msg[1] if len(msg) > 1 else "Неизвестная ошибка")
                        log.debug("Got error in %s: %s", op, err)
                        if op == "scan":
                            self.places_frame.set_scanning(False)
                            self.places_frame.status_label.configure(text="Ошибка сканирования")
                        if op == "export_chats":
                            self.places_frame.set_scanning(False)
                            self.export_frame.set_loading(False)
                            self.places_frame.status_label.configure(text="Ошибка экспорта")
                            self.export_frame.status_label.configure(text="Ошибка экспорта")
                        if op == "list_export_dialogs":
                            self.export_frame.set_loading(False)
                            self.export_frame.status_label.configure(text="Ошибка загрузки списка")
                        self._operation_running = False
                        messagebox.showerror("Ошибка", err)
                except Exception as e:
                    import traceback
                    log.exception("check_queue handler: %s", e)
                    traceback.print_exc()
        except Empty:
            pass
        self.root.after(100, self._check_queue)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        scan_stop_requested.set()
        request_queue.put(("quit",))
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self.root.destroy()


def run_gui():
    a = App()
    a.run()
