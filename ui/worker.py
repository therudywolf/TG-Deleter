
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

"""Фоновый воркер: asyncio + Pyrogram."""
import os
import asyncio
import logging
from queue import Empty

from core import (
    ExportOptions,
    clear_me,
    create_client,
    export_chats_streaming,
    get_current_session,
    set_current_session,
    set_app,
    get_accounts_list,
    set_me_from_dict,
    list_export_dialogs,
    scan_all_dialogs,
    delete_message_ids,
    delete_all_my_in_chat_no_scan,
    resolve_target_user,
    find_chats_with_user,
    remove_user_from_chats,
    add_user_to_chats,
    find_chat_admins,
    unban_user_in_chats,
    get_scan_delay_between_chats,
    get_export_parallel_chats,
    get_export_include_media,
    get_export_message_limit,
    get_project_root,
)
from ui.queues import request_queue, response_queue, scan_paused, scan_stop_requested
from ui.messages import (
    MeMsg, ScanProgressMsg, ScanPlaceMsg, ScanDoneMsg,
    DeleteDoneMsg, DeleteAllNoScanDoneMsg, DeleteAllExceptDoneMsg,
    DeleteBatchProgressMsg, DeleteBatchDoneMsg, DeleteOpStatusMsg,
    ExportProgressMsg, ExportDoneMsg,
    ExportDialogsProgressMsg, ExportDialogsBatchMsg, ExportDialogsDoneMsg,
    UserResolvedMsg, MemberChatsProgressMsg, MemberChatFoundMsg, MemberChatsDoneMsg,
    MemberDialogsProgressMsg, MemberDialogsBatchMsg, MemberDialogsDoneMsg,
    MemberActionProgressMsg, MemberActionDoneMsg,
    AdminsProgressMsg, AdminFoundMsg, AdminsDoneMsg,
    SwitchAccountDoneMsg, LogMsg, ErrorMsg, FloodWaitMsg, ConnectionStatusMsg,
)

try:
    from pyrogram.errors import FloodWait
except ImportError:
    FloodWait = None

log = logging.getLogger("tg_deleter")
_PROJECT_ROOT = get_project_root()


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
                response_queue.put(SwitchAccountDoneMsg(session=new_session))
                log.debug("worker: switch to %s", new_session)
                return "switch"
            response_queue.put(ErrorMsg(operation=req[0], error="Нет подключенной Telegram-сессии."))
            return "handled"

        _warned_no_session = None
        reconnect_delay = 5
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
                if _warned_no_session != session:
                    response_queue.put(LogMsg(
                        text="Сессия «%s» не авторизована. Добавьте аккаунт через кнопку «Добавить» в левой панели." % session
                    ))
                    _warned_no_session = session
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
                    reconnect_delay = 5
                    response_queue.put(ConnectionStatusMsg(connected=True))

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
                        response_queue.put(MeMsg(me_dict=me_dict, session=session))

                        async def download_avatar():
                            avatar_path = None
                            try:
                                # get_chat_photos — асинхронный генератор, не корутина со списком.
                                photo = None
                                async for item in app.get_chat_photos(me.id, limit=1):
                                    photo = item
                                    break
                                if photo:
                                    temp_dir = os.path.join(_PROJECT_ROOT, "temp")
                                    os.makedirs(temp_dir, exist_ok=True)
                                    avatar_path = os.path.join(temp_dir, f"avatar_{session}_{me.id}.jpg")
                                    await app.download_media(photo.file_id, file_name=avatar_path)
                                    if not os.path.isfile(avatar_path):
                                        avatar_path = None
                            except (AttributeError, TypeError):
                                # Так выглядит переезд API Pyrogram: это баг, а не «аватарки нет».
                                log.exception("worker: не удалось скачать аватар — метод Pyrogram не подошёл")
                            except Exception as av_err:
                                log.debug("worker: avatar download skip: %s", av_err)
                            if avatar_path:
                                updated = dict(me_dict)
                                updated["avatar_path"] = avatar_path
                                response_queue.put(MeMsg(me_dict=updated, session=session))

                        _avatar_task = asyncio.create_task(download_avatar())
                        _avatar_task.add_done_callback(lambda t: t.exception() if not t.cancelled() and t.exception() else None)
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
                                include_groups = req[1]
                                include_channels = req[2]
                                include_private = req[3]
                                pause_ev = req[4]
                                max_my_messages_per_chat = req[5] if len(req) > 5 else None
                                stop_ev = req[6] if len(req) > 6 else None

                                def on_place(p):
                                    response_queue.put(ScanPlaceMsg(place=p))
                                    log.debug("worker: put scan_place")

                                def on_dialog(n, title, count=None):
                                    response_queue.put(ScanProgressMsg(n=n, title=title, count=count))

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
                                response_queue.put(ScanDoneMsg(places=places, stopped=stopped, session=session))
                                log.debug("worker: put scan_done, places=%s stopped=%s", len(places), stopped)
                            elif req[0] == "delete_all_no_scan":
                                cid = req[1]
                                response_queue.put(DeleteOpStatusMsg(text=f"Удаление в чате {cid}..."))
                                count = await delete_all_my_in_chat_no_scan(cid, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(DeleteAllNoScanDoneMsg(chat_id=cid, count=count, stopped=scan_stop_requested.is_set()))
                                log.debug("worker: put delete_all_no_scan_done")
                            elif req[0] == "delete_here":
                                cid, ids = req[1], req[2]
                                response_queue.put(DeleteOpStatusMsg(text=f"Удаляю {len(ids)} сообщений в чате {cid}..."))
                                deleted_ids = await delete_message_ids(cid, ids, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(DeleteDoneMsg(chat_id=cid, deleted_ids=deleted_ids, stopped=scan_stop_requested.is_set()))
                                log.debug("worker: put delete_done")
                            elif req[0] == "delete_all_except":
                                except_cid = req[1]
                                places_list = req[2]
                                deleted_map = {}
                                targets = [p for p in places_list if p.chat_id != except_cid and p.messages]
                                total_targets = len(targets)
                                for i, place in enumerate(targets):
                                    if scan_stop_requested.is_set():
                                        break
                                    response_queue.put(DeleteOpStatusMsg(text=f"Удаление в чатах: {i + 1} из {total_targets}..."))
                                    ids = [m[0] for m in place.messages]
                                    if ids:
                                        deleted_ids = await delete_message_ids(place.chat_id, ids, pause_event=scan_paused, stop_event=scan_stop_requested)
                                        if deleted_ids:
                                            deleted_map[place.chat_id] = deleted_ids
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(DeleteAllExceptDoneMsg(deleted_map=deleted_map, stopped=scan_stop_requested.is_set()))
                                log.debug("worker: put delete_all_except_done")
                            elif req[0] == "delete_in_places":
                                chat_ids = req[1]
                                total_deleted = 0
                                for i, cid in enumerate(chat_ids):
                                    if scan_stop_requested.is_set():
                                        break
                                    response_queue.put(DeleteBatchProgressMsg(current=i + 1, total=len(chat_ids), chat_id=cid))
                                    n = await delete_all_my_in_chat_no_scan(cid, pause_event=scan_paused, stop_event=scan_stop_requested)
                                    total_deleted += n
                                    if get_scan_delay_between_chats() > 0:
                                        await asyncio.sleep(get_scan_delay_between_chats())
                                response_queue.put(DeleteBatchDoneMsg(total_deleted=total_deleted, chat_ids=chat_ids, stopped=scan_stop_requested.is_set()))
                                log.debug("worker: put delete_batch_done, deleted=%s", total_deleted)
                            elif req[0] == "export_chats":
                                output_dir = req[1]
                                chat_ids = req[2]
                                export_options = req[3] if len(req) > 3 and isinstance(req[3], dict) else {}
                                include_media = export_options.get("include_media", get_export_include_media())
                                options = ExportOptions(
                                    output_dir=output_dir,
                                    chat_ids=chat_ids,
                                    parallel_chats=get_export_parallel_chats(),
                                    include_media=include_media,
                                    media_types=export_options.get("media_types"),
                                    message_limit=get_export_message_limit(),
                                )

                                def on_export(kind, payload):
                                    response_queue.put(ExportProgressMsg(kind=kind, payload=payload))

                                root, manifest = await export_chats_streaming(
                                    options,
                                    pause_event=scan_paused,
                                    stop_event=scan_stop_requested,
                                    progress_callback=on_export,
                                )
                                response_queue.put(ExportDoneMsg(root=root, manifest=manifest, stopped=scan_stop_requested.is_set()))
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
                                        response_queue.put(ExportDialogsBatchMsg(batch=batch))
                                        batch = []

                                def on_dialog(place):
                                    batch.append(place)
                                    if len(batch) >= 50:
                                        flush_batch()

                                def on_progress(n, title):
                                    response_queue.put(ExportDialogsProgressMsg(n=n, title=title))

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
                                response_queue.put(ExportDialogsDoneMsg(dialogs=dialogs, stopped=scan_stop_requested.is_set(), session=session))
                                log.debug("worker: put export_dialogs_done, dialogs=%s", len(dialogs))
                            elif req[0] == "resolve_user":
                                target = await resolve_target_user(req[1])
                                response_queue.put(UserResolvedMsg(user=target))
                                log.debug("worker: put user_resolved id=%s", target.user_id)
                            elif req[0] == "find_user_chats":
                                user_id = req[1]
                                deep = bool(req[2])
                                include_groups = bool(req[3])
                                include_channels = bool(req[4])
                                pause_ev = req[5]
                                stop_ev = req[6]

                                def on_member_chat(mc):
                                    response_queue.put(MemberChatFoundMsg(chat=mc))

                                def on_member_progress(n, total, title):
                                    response_queue.put(MemberChatsProgressMsg(n=n, title=title, total=total))

                                def on_member_flood(seconds):
                                    response_queue.put(FloodWaitMsg(seconds=seconds, operation="find_user_chats"))

                                member_chats = await find_chats_with_user(
                                    user_id,
                                    deep=deep,
                                    include_groups=include_groups,
                                    include_channels=include_channels,
                                    pause_event=pause_ev,
                                    stop_event=stop_ev,
                                    progress_callback=on_member_chat,
                                    status_callback=on_member_progress,
                                    flood_callback=on_member_flood,
                                )
                                response_queue.put(MemberChatsDoneMsg(
                                    chats=member_chats,
                                    stopped=stop_ev is not None and stop_ev.is_set(),
                                    session=session,
                                ))
                                log.debug("worker: put member_chats_done, chats=%s", len(member_chats))
                            elif req[0] == "list_member_chats":
                                include_groups = req[1]
                                include_channels = req[2]
                                pause_ev = req[3]
                                stop_ev = req[4]
                                member_batch = []

                                def flush_member_batch():
                                    nonlocal member_batch
                                    if member_batch:
                                        response_queue.put(MemberDialogsBatchMsg(batch=member_batch))
                                        member_batch = []

                                def on_member_dialog(place):
                                    member_batch.append(place)
                                    if len(member_batch) >= 50:
                                        flush_member_batch()

                                def on_member_dialog_progress(n, title):
                                    response_queue.put(MemberDialogsProgressMsg(n=n, title=title))

                                dialogs = await list_export_dialogs(
                                    include_groups=include_groups,
                                    include_channels=include_channels,
                                    include_private=False,
                                    pause_event=pause_ev,
                                    stop_event=stop_ev,
                                    progress_callback=on_member_dialog,
                                    dialog_progress_callback=on_member_dialog_progress,
                                )
                                flush_member_batch()
                                response_queue.put(MemberDialogsDoneMsg(
                                    dialogs=dialogs,
                                    stopped=stop_ev is not None and stop_ev.is_set(),
                                    session=session,
                                ))
                                log.debug("worker: put member_dialogs_done, dialogs=%s", len(dialogs))
                            elif req[0] == "find_chat_admins":
                                chat_pairs = req[1]
                                admin_target_id = req[2]
                                pause_ev = req[3]
                                stop_ev = req[4]

                                def on_admin(contact):
                                    response_queue.put(AdminFoundMsg(admin=contact))

                                def on_admin_progress(n, total, title):
                                    response_queue.put(AdminsProgressMsg(n=n, total=total, title=title))

                                def on_admin_flood(seconds):
                                    response_queue.put(FloodWaitMsg(seconds=seconds, operation="find_chat_admins"))

                                admins = await find_chat_admins(
                                    chat_pairs,
                                    target_user_id=admin_target_id,
                                    pause_event=pause_ev,
                                    stop_event=stop_ev,
                                    progress_callback=on_admin,
                                    status_callback=on_admin_progress,
                                    flood_callback=on_admin_flood,
                                )
                                response_queue.put(AdminsDoneMsg(
                                    admins=admins,
                                    stopped=stop_ev is not None and stop_ev.is_set(),
                                ))
                                log.debug("worker: put admins_done, людей=%s", len(admins))
                            elif req[0] == "unban_user_in_chats":
                                user_id = req[1]
                                chat_pairs = req[2]

                                def on_unban_progress(i, total, result):
                                    response_queue.put(MemberActionProgressMsg(
                                        action="unban", current=i, total=total, result=result,
                                    ))

                                def on_unban_flood(seconds):
                                    response_queue.put(FloodWaitMsg(seconds=seconds, operation=req[0]))

                                try:
                                    unban_results = await unban_user_in_chats(
                                        user_id, chat_pairs,
                                        pause_event=scan_paused, stop_event=scan_stop_requested,
                                        progress_callback=on_unban_progress,
                                        flood_callback=on_unban_flood,
                                    )
                                except Exception as unban_err:
                                    log.exception("worker: unban failed: %s", unban_err)
                                    response_queue.put(ErrorMsg(operation=req[0], error=str(unban_err)))
                                    unban_results = []
                                response_queue.put(MemberActionDoneMsg(
                                    action="unban",
                                    results=unban_results,
                                    stopped=scan_stop_requested.is_set(),
                                ))
                                log.debug("worker: put member_action_done unban, chats=%s", len(unban_results))
                            elif req[0] in ("remove_user_from_chats", "add_user_to_chats"):
                                action = "remove" if req[0] == "remove_user_from_chats" else "add"
                                user_id = req[1]
                                chat_pairs = req[2]
                                ban = bool(req[3]) if len(req) > 3 else True

                                def on_action_progress(i, total, result):
                                    response_queue.put(MemberActionProgressMsg(
                                        action=action, current=i, total=total, result=result,
                                    ))

                                def on_action_flood(seconds):
                                    response_queue.put(FloodWaitMsg(seconds=seconds, operation=req[0]))

                                # Массовую правку участников нельзя повторять целиком после ошибки,
                                # поэтому обрабатываем её здесь, а не общим обработчиком ниже.
                                try:
                                    if action == "remove":
                                        action_results = await remove_user_from_chats(
                                            user_id, chat_pairs, ban=ban,
                                            pause_event=scan_paused, stop_event=scan_stop_requested,
                                            progress_callback=on_action_progress,
                                            flood_callback=on_action_flood,
                                        )
                                    else:
                                        action_results = await add_user_to_chats(
                                            user_id, chat_pairs,
                                            pause_event=scan_paused, stop_event=scan_stop_requested,
                                            progress_callback=on_action_progress,
                                            flood_callback=on_action_flood,
                                        )
                                except Exception as action_err:
                                    log.exception("worker: %s failed: %s", req[0], action_err)
                                    response_queue.put(ErrorMsg(operation=req[0], error=str(action_err)))
                                    action_results = []
                                response_queue.put(MemberActionDoneMsg(
                                    action=action,
                                    results=action_results,
                                    stopped=scan_stop_requested.is_set(),
                                ))
                                log.debug("worker: put member_action_done %s, chats=%s", action, len(action_results))
                        except Exception as e:
                            if FloodWait is not None and isinstance(e, FloodWait):
                                response_queue.put(FloodWaitMsg(seconds=e.value, operation=req[0]))
                                log.warning("FloodWait: waiting %s seconds for %s, will retry", e.value, req[0])
                                await asyncio.sleep(e.value)
                                request_queue.put(req)
                            else:
                                log.exception("worker error in %s: %s", req[0], e)
                                response_queue.put(ErrorMsg(operation=req[0], error=str(e)))
            except Exception as e:
                set_app(None)
                response_queue.put(ConnectionStatusMsg(connected=False))
                log.exception("worker reconnect loop error for session=%s: %s", session, e)
                response_queue.put(LogMsg(
                    text=f"Проблема соединения для сессии «{session}». Повтор через {reconnect_delay} сек."
                ))
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    asyncio.run(_run())
    log.debug("worker_loop finished")
