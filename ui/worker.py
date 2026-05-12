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
    fetch_and_set_my_channels,
    list_export_dialogs,
    scan_all_dialogs,
    delete_message_ids,
    delete_all_my_in_chat_no_scan,
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
    SwitchAccountDoneMsg, LogMsg, ErrorMsg, FloodWaitMsg,
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
                        response_queue.put(MeMsg(me_dict=me_dict, session=session))

                        async def download_avatar():
                            avatar_path = None
                            try:
                                photos = await app.get_profile_photos(me.id, limit=1)
                                if photos:
                                    photo = photos[0]
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
                                await ensure_channels_ready()
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
                                await ensure_channels_ready()
                                cid = req[1]
                                response_queue.put(DeleteOpStatusMsg(text=f"Удаление в чате {cid}..."))
                                count = await delete_all_my_in_chat_no_scan(cid, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(DeleteAllNoScanDoneMsg(chat_id=cid, count=count, stopped=scan_stop_requested.is_set()))
                                log.debug("worker: put delete_all_no_scan_done")
                            elif req[0] == "delete_here":
                                await ensure_channels_ready()
                                cid, ids = req[1], req[2]
                                response_queue.put(DeleteOpStatusMsg(text=f"Удаляю {len(ids)} сообщений в чате {cid}..."))
                                deleted_ids = await delete_message_ids(cid, ids, pause_event=scan_paused, stop_event=scan_stop_requested)
                                response_queue.put(DeleteDoneMsg(chat_id=cid, deleted_ids=deleted_ids, stopped=scan_stop_requested.is_set()))
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
                                await ensure_channels_ready()
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
                log.exception("worker reconnect loop error for session=%s: %s", session, e)
                response_queue.put(LogMsg(text=f"Проблема соединения для сессии «{session}». Повтор через 5 сек."))
                await asyncio.sleep(5)

    asyncio.run(_run())
    log.debug("worker_loop finished")
