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
    Place,
    create_client,
    get_current_session,
    set_current_session,
    set_app,
    get_accounts_list,
    set_me_from_dict,
    fetch_and_set_my_channels,
    save_account_profile,
    scan_all_dialogs,
    delete_message_ids,
    delete_all_my_in_chat_no_scan,
    get_scan_delay_between_chats,
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
        while True:
            session = get_current_session() or (get_accounts_list() or [None])[0]
            if not session:
                await asyncio.sleep(2)
                continue
            session_file = os.path.join(_PROJECT_ROOT, session + ".session")
            if not os.path.isfile(session_file):
                response_queue.put(("log_message", "Сессия «%s» не авторизована. Добавьте аккаунт через кнопку «Добавить» в левой панели." % session))
                await asyncio.sleep(2)
                continue
            try:
                app = create_client(session)
                async with app:
                    set_app(app)
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
                        try:
                            await fetch_and_set_my_channels(app)
                        except Exception as ch_err:
                            log.warning("worker: fetch_and_set_my_channels skip: %s", ch_err)
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
                            me_dict["avatar_path"] = avatar_path
                        response_queue.put(("me", me_dict, session))
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
                            log.debug("worker_loop quit")
                            set_app(None)
                            return
                        if req[0] == "switch_account":
                            new_session = req[1]
                            set_current_session(new_session)
                            set_app(None)
                            response_queue.put(("switch_account_done", new_session))
                            log.debug("worker: switch to %s", new_session)
                            break
                        log.debug("worker: request %s", req[0])
                        try:
                            if req[0] == "scan":
                                include_groups = req[1]
                                include_channels = req[2]
                                include_private = req[3]
                                pause_ev = req[4]
                                max_my_messages_per_chat = req[5] if len(req) > 5 else None
                                stop_ev = req[6] if len(req) > 6 else None
                                scan_paused.clear()
                                scan_stop_requested.clear()
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
                                response_queue.put(("scan_done", places, stopped))
                                log.debug("worker: put scan_done, places=%s stopped=%s", len(places), stopped)
                            elif req[0] == "delete_all_no_scan":
                                cid = req[1]
                                response_queue.put(("delete_op_status", f"Удаление в чате {cid}..."))
                                count = await delete_all_my_in_chat_no_scan(cid)
                                response_queue.put(("delete_all_no_scan_done", cid, count))
                                log.debug("worker: put delete_all_no_scan_done")
                            elif req[0] == "delete_here":
                                cid, ids = req[1], req[2]
                                response_queue.put(("delete_op_status", f"Удаляю {len(ids)} сообщений в чате {cid}..."))
                                deleted_ids = await delete_message_ids(cid, ids)
                                response_queue.put(("delete_done", cid, deleted_ids))
                                log.debug("worker: put delete_done")
                            elif req[0] == "delete_all_except":
                                except_cid = req[1]
                                places_list = req[2]
                                deleted_map = {}
                                targets = [p for p in places_list if p.chat_id != except_cid and p.messages]
                                total_targets = len(targets)
                                for i, place in enumerate(targets):
                                    response_queue.put(("delete_op_status", f"Удаление в чатах: {i + 1} из {total_targets}..."))
                                    ids = [m[0] for m in place.messages]
                                    if ids:
                                        deleted_ids = await delete_message_ids(place.chat_id, ids)
                                        if deleted_ids:
                                            deleted_map[place.chat_id] = deleted_ids
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(("delete_all_except_done", deleted_map))
                                log.debug("worker: put delete_all_except_done")
                            elif req[0] == "delete_in_places":
                                chat_ids = req[1]
                                total_deleted = 0
                                for i, cid in enumerate(chat_ids):
                                    response_queue.put(("delete_batch_progress", i + 1, len(chat_ids), cid))
                                    n = await delete_all_my_in_chat_no_scan(cid)
                                    total_deleted += n
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(("delete_batch_done", total_deleted, chat_ids))
                                log.debug("worker: put delete_batch_done, deleted=%s", total_deleted)
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

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True)

        self.sidebar = SidebarFrame(
            main,
            width=SIDEBAR_WIDTH,
            on_quit=self._on_close,
            on_switch_account=self._on_switch_account,
            on_show_chats=self._show_places,
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
        )
        self.posts_frame = PostsFrame(content, on_back=self._show_places, all_places_getter=lambda: self.places)

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
            self.settings_frame.pack(fill="both", expand=True)
        else:
            self.places_frame.pack(fill="both", expand=True)
            self.posts_frame.pack(fill="both", expand=True)
            self.posts_frame.pack_forget()
            cached = load_places_from_cache()
            if cached:
                self.places = cached
                self.places_frame.set_places(self.places)
                mtime = get_cache_mtime_str()
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
        self.places_frame.pack(fill="both", expand=True)
        self.posts_frame.pack(fill="both", expand=True)
        self.posts_frame.pack_forget()
        cached = load_places_from_cache()
        if cached:
            self.places = cached
            self.places_frame.set_places(self.places)
            mtime = get_cache_mtime_str()
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
        self.places_frame.pack(fill="both", expand=True)

    def _on_switch_account(self, session_name):
        request_queue.put(("switch_account", session_name))

    def _on_clear_cache(self):
        clear_cache()
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
        cached = load_places_from_cache()
        if cached is None:
            self.places_frame.status_label.configure(text="Кэш не найден или пуст.")
            return
        self.places = cached
        self.places_frame.set_places(self.places)
        mtime = get_cache_mtime_str()
        self.places_frame.status_label.configure(text=f"Загружено из кэша ({mtime}). Чатов: {len(self.places)}.")
        log.debug("refresh_cache: loaded %s places", len(self.places))

    def _on_start_scan(self):
        self.places = []
        self.places_frame.set_places(self.places)

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
                        self.me = msg[1]
                        session = msg[2] if len(msg) > 2 else None
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
                        self.places = []
                        self.places_frame.set_places(self.places)
                        cached = load_places_from_cache()
                        if cached:
                            self.places = cached
                            self.places_frame.set_places(self.places)
                            mtime = get_cache_mtime_str()
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
                        self.places_frame.set_places(self.places)
                        self.places_frame.set_scanning(False)
                        save_places_to_cache(self.places)
                        mtime = get_cache_mtime_str()
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
                        self.places_frame.status_label.configure(text=msg[1])
                    elif msg[0] == "delete_done":
                        log.debug("Got delete_done")
                        cid, deleted_ids = msg[1], msg[2]
                        deleted_set = set(deleted_ids)
                        self.posts_frame.remove_deleted_ids(deleted_ids)
                        for p in self.places:
                            if p.chat_id == cid:
                                p.messages = [(m[0], m[1], m[2]) for m in p.messages if m[0] not in deleted_set]
                                break
                        self.places = [p for p in self.places if p.messages]
                        self.places_frame.set_places(self.places)
                        messagebox.showinfo("Готово", "Удалено сообщений: %s" % len(deleted_ids))
                    elif msg[0] == "delete_all_except_done":
                        log.debug("Got delete_all_except_done")
                        deleted_map = msg[1] if len(msg) > 1 else {}
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
                        messagebox.showinfo("Готово", "Удалено сообщений: %s" % total_deleted)
                    elif msg[0] == "delete_all_no_scan_done":
                        log.debug("Got delete_all_no_scan_done")
                        cid, count = msg[1], msg[2]
                        for p in self.places:
                            if p.chat_id == cid:
                                p.messages = []
                                break
                        self.places = [p for p in self.places if p.messages]
                        self.places_frame.set_places(self.places)
                        if self.posts_frame.current_place and self.posts_frame.current_place.chat_id == cid:
                            self.posts_frame.current_place.messages = []
                            self.posts_frame.set_place(self.posts_frame.current_place)
                        messagebox.showinfo("Готово", "Удалено сообщений: %s" % count)
                    elif msg[0] == "delete_batch_progress":
                        i, total, cid = msg[1], msg[2], msg[3]
                        self.places_frame.status_label.configure(text="Удаление в чатах: %s из %s…" % (i, total))
                    elif msg[0] == "delete_batch_done":
                        total_deleted, chat_ids = msg[1], msg[2]
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
                        messagebox.showinfo("Готово", "Удалено сообщений: %s в %s чатах." % (total_deleted, len(chat_ids)))
                    elif msg[0] == "error":
                        op = msg[1] if len(msg) > 1 else ""
                        err = msg[2] if len(msg) > 2 else (msg[1] if len(msg) > 1 else "Неизвестная ошибка")
                        log.debug("Got error in %s: %s", op, err)
                        if op == "scan":
                            self.places_frame.set_scanning(False)
                            self.places_frame.status_label.configure(text="Ошибка сканирования")
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
        request_queue.put(("quit",))
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self.root.destroy()


def run_gui():
    a = App()
    a.run()
