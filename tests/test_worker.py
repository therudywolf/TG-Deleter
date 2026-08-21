
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
Тесты фонового воркера: протокол «запрос → ответ» целиком.

Именно здесь раньше молча терялись запросы — ветка есть, имя не совпало,
и операция уходила в пустоту без единой строчки в логе.
"""
import ast
import os
import re
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
from ui.messages import (  # noqa: E402
    AdminsDoneMsg,
    ConnectionStatusMsg,
    ErrorMsg,
    ExportDialogsDoneMsg,
    MeMsg,
    MemberActionDoneMsg,
    MemberChatsDoneMsg,
    MemberDialogsDoneMsg,
    ScanDoneMsg,
    SwitchAccountDoneMsg,
    UserResolvedMsg,
)
from ui.queues import request_queue, response_queue, scan_paused, scan_stop_requested  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION = "workersession"


# ---------------------------------------------------------------------------
# Статическая проверка: каждый запрос из главного окна должен иметь обработчик
# ---------------------------------------------------------------------------

UI_PRODUCERS = ("app.py", "places_frame.py", "posts_frame.py", "export_frame.py", "members_frame.py")


def _request_names_from_ui():
    """Имена запросов, которые экраны кладут в очередь воркера."""
    names = set()
    for module in UI_PRODUCERS:
        with open(os.path.join(ROOT, "ui", module), encoding="utf-8") as f:
            names |= _put_literals(ast.parse(f.read()))
    return names


def _put_literals(tree):
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "put"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "request_queue"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Tuple) or not node.args[0].elts:
            continue
        first = node.args[0].elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
    return names


def _names_handled_by_worker():
    """Имена, на которые воркер реально реагирует."""
    with open(os.path.join(ROOT, "ui", "worker.py"), encoding="utf-8") as f:
        source = f.read()
    names = set(re.findall(r'req\[0\]\s*==\s*"([a-z_]+)"', source))
    for group in re.findall(r'req\[0\]\s+in\s+\(([^)]*)\)', source):
        names.update(re.findall(r'"([a-z_]+)"', group))
    return names


class TestRequestProtocol:
    """Статический контракт между окном и воркером."""

    def test_every_request_has_a_branch(self):
        # «quit» и «switch_account» разбирает handle_control_request, а не цепочка elif.
        control = {"quit", "switch_account"}
        missing = _request_names_from_ui() - _names_handled_by_worker() - control
        assert not missing, "Воркер молча проигнорирует: %s" % sorted(missing)

    def test_the_parser_actually_finds_requests(self):
        # Страховка от того, что разбор сломался и тест выше стал пустым.
        names = _request_names_from_ui()
        assert {"scan", "resolve_user", "find_user_chats", "find_chat_admins",
                "delete_here", "export_chats"} <= names

    def test_worker_handles_more_than_a_couple_of_names(self):
        assert len(_names_handled_by_worker()) >= 10


# ---------------------------------------------------------------------------
# Живой прогон воркера на поддельном Telegram
# ---------------------------------------------------------------------------

class FakeUser:
    def __init__(self, uid, first="Имя", last="", username=None, is_bot=False):
        self.id = uid
        self.first_name = first
        self.last_name = last
        self.username = username
        self.phone_number = None
        self.is_bot = is_bot
        self.is_deleted = False


class FakeChat:
    def __init__(self, chat_id, title, chat_type):
        self.id = chat_id
        self.title = title
        self.type = chat_type


class FakeDialog:
    def __init__(self, chat):
        self.chat = chat


class FakeStatus:
    def __init__(self, name):
        self.name = name


class FakePrivileges:
    def __init__(self, can_restrict=True):
        self.can_restrict_members = can_restrict


class FakeMember:
    def __init__(self, status, user=None, can_restrict=True):
        self.status = FakeStatus(status)
        self.privileges = FakePrivileges(can_restrict)
        self.user = user
        self.invited_by = None


class FakeMessage:
    def __init__(self, mid, out=True):
        self.id = mid
        self.out = out
        self.outgoing = out
        self.from_user = FakeUser(1)
        self.text = "текст %s" % mid
        self.caption = None
        self.date = None


class FakeClient:
    """Ровно столько Telegram, сколько трогают ветки воркера."""

    SUPERGROUP = -1001111111111
    CHANNEL = -1002222222222

    def __init__(self):
        self.banned = []
        self.unbanned = []
        self.added = []
        self.deleted = []
        self.entered = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_me(self):
        return FakeUser(1, "Я", "Сам", "me")

    def get_chat_photos(self, chat_id, limit=0):
        async def gen():
            return
            yield  # pragma: no cover - аватарки в тестах нет

        return gen()

    def get_dialogs(self):
        from pyrogram.enums import ChatType

        async def gen():
            yield FakeDialog(FakeChat(self.SUPERGROUP, "Супергруппа", ChatType.SUPERGROUP))
            yield FakeDialog(FakeChat(self.CHANNEL, "Канал", ChatType.CHANNEL))
            yield FakeDialog(FakeChat(555, "Личка", ChatType.PRIVATE))

        return gen()

    def get_chat_history(self, chat_id, **kw):
        async def gen():
            yield FakeMessage(10)
            yield FakeMessage(11)

        return gen()

    async def get_messages(self, chat_id, message_ids):
        return [FakeMessage(mid) for mid in message_ids]

    async def delete_messages(self, chat_id, message_ids):
        ids = message_ids if isinstance(message_ids, list) else [message_ids]
        self.deleted.extend(ids)

    async def get_users(self, user_id):
        return FakeUser(777, "Цель", "", "target")

    async def get_common_chats(self, user_id):
        from pyrogram.enums import ChatType

        return [FakeChat(self.SUPERGROUP, "Супергруппа", ChatType.SUPERGROUP)]

    async def get_chat_member(self, chat_id, user_id):
        if user_id == "me":
            return FakeMember("OWNER", FakeUser(1))
        return FakeMember("MEMBER", FakeUser(777))

    def get_chat_members(self, chat_id, filter=None):
        async def gen():
            yield FakeMember("ADMINISTRATOR", FakeUser(100, "Босс", "", "boss"))

        return gen()

    async def ban_chat_member(self, chat_id, user_id):
        self.banned.append((chat_id, user_id))

    async def unban_chat_member(self, chat_id, user_id):
        self.unbanned.append((chat_id, user_id))

    async def add_chat_members(self, chat_id, user_ids):
        self.added.append((chat_id, user_ids))


class WorkerHarness:
    """Запускает воркер в потоке и умеет ждать нужный ответ."""

    def __init__(self, client):
        self.client = client
        self.seen = []

    def send(self, *req):
        request_queue.put(tuple(req))

    def wait_for(self, msg_type, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = response_queue.get(timeout=0.2)
            except Exception:
                continue
            self.seen.append(msg)
            if isinstance(msg, msg_type):
                return msg
        raise AssertionError(
            "Не дождались %s. Пришло: %s" % (msg_type.__name__, [type(m).__name__ for m in self.seen])
        )

    def drain(self):
        while not response_queue.empty():
            self.seen.append(response_queue.get_nowait())


def _clear_queues():
    while not request_queue.empty():
        request_queue.get_nowait()
    while not response_queue.empty():
        response_queue.get_nowait()


@pytest.fixture
def worker(tmp_path, monkeypatch):
    """Воркер в потоке, подключённый к поддельному Telegram."""
    import ui.worker as worker_module

    _clear_queues()
    scan_paused.clear()
    scan_stop_requested.clear()

    (tmp_path / (SESSION + ".session")).write_text("", encoding="utf-8")
    client = FakeClient()
    monkeypatch.setattr(worker_module, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(worker_module, "get_current_session", lambda: SESSION)
    monkeypatch.setattr(worker_module, "get_accounts_list", lambda: [SESSION])
    monkeypatch.setattr(worker_module, "create_client", lambda name: client)
    monkeypatch.setattr(core, "get_delay_sec", lambda: 0)
    monkeypatch.setattr(core, "get_scan_delay_between_chats", lambda: 0)
    monkeypatch.setattr(core, "_MEMBER_PROBE_DELAY_MIN", 0)
    monkeypatch.setattr(core, "_MEMBER_REMOVE_DELAY_MIN", 0)
    monkeypatch.setattr(core, "_MEMBER_ADD_DELAY_MIN", 0)

    harness = WorkerHarness(client)
    thread = threading.Thread(target=worker_module.worker_loop, daemon=True)
    thread.start()
    # Ждём, пока воркер подключится и представится.
    harness.wait_for(MeMsg)
    try:
        yield harness
    finally:
        scan_stop_requested.set()
        scan_paused.clear()
        request_queue.put(("quit",))
        thread.join(timeout=6)
        scan_stop_requested.clear()
        core.set_app(None)
        _clear_queues()


class TestWorkerStartup:
    """Подключение и представление."""

    def test_reports_connection_and_identity(self, worker):
        assert worker.client.entered == 1
        me = [m for m in worker.seen if isinstance(m, MeMsg)][0]
        assert me.me_dict["id"] == 1
        assert me.session == SESSION
        assert any(isinstance(m, ConnectionStatusMsg) and m.connected for m in worker.seen)

    def test_unknown_request_is_ignored_without_dying(self, worker):
        worker.send("такой ветки нет", 1, 2)
        worker.send("resolve_user", "@target")
        # Воркер должен пережить мусор и обработать следующий запрос.
        assert worker.wait_for(UserResolvedMsg).user.user_id == 777


class TestMemberBranches:
    """Ветки экрана «Участники»."""

    def test_resolve_user(self, worker):
        worker.send("resolve_user", "@target")
        msg = worker.wait_for(UserResolvedMsg)
        assert msg.user.username == "target"

    def test_resolve_user_error_is_reported(self, worker):
        worker.send("resolve_user", "не имя!")
        msg = worker.wait_for(ErrorMsg)
        assert msg.operation == "resolve_user"

    def test_find_user_chats(self, worker):
        worker.send("find_user_chats", 777, False, True, True, scan_paused, scan_stop_requested)
        msg = worker.wait_for(MemberChatsDoneMsg)
        assert [c.chat_id for c in msg.chats] == [FakeClient.SUPERGROUP]
        assert msg.chats[0].can_manage is True
        assert msg.session == SESSION

    def test_list_member_chats_skips_private(self, worker):
        worker.send("list_member_chats", True, True, scan_paused, scan_stop_requested)
        msg = worker.wait_for(MemberDialogsDoneMsg)
        assert sorted(p.chat_id for p in msg.dialogs) == sorted([FakeClient.SUPERGROUP, FakeClient.CHANNEL])

    def test_remove_user_from_chats(self, worker):
        worker.send("remove_user_from_chats", 777, [(FakeClient.SUPERGROUP, "Супергруппа")], True)
        msg = worker.wait_for(MemberActionDoneMsg)
        assert msg.action == "remove"
        assert worker.client.banned == [(FakeClient.SUPERGROUP, 777)]
        assert worker.client.unbanned == []
        assert msg.results[0].ok is True

    def test_kick_without_ban_unbans_afterwards(self, worker):
        worker.send("remove_user_from_chats", 777, [(FakeClient.SUPERGROUP, "Супергруппа")], False)
        worker.wait_for(MemberActionDoneMsg)
        assert worker.client.unbanned == [(FakeClient.SUPERGROUP, 777)]

    def test_add_user_to_chats(self, worker):
        worker.send("add_user_to_chats", 777, [(FakeClient.CHANNEL, "Канал")])
        msg = worker.wait_for(MemberActionDoneMsg)
        assert msg.action == "add"
        assert worker.client.added == [(FakeClient.CHANNEL, 777)]

    def test_unban_user_in_chats(self, worker):
        worker.send("unban_user_in_chats", 777, [(FakeClient.SUPERGROUP, "Супергруппа")])
        msg = worker.wait_for(MemberActionDoneMsg)
        assert msg.action == "unban"
        assert worker.client.unbanned == [(FakeClient.SUPERGROUP, 777)]
        assert msg.results[0].note == "Бан снят"

    def test_unban_failure_is_reported_and_closed(self, worker):
        worker.send("unban_user_in_chats", 777, [])
        err = worker.wait_for(ErrorMsg)
        assert err.operation == "unban_user_in_chats"
        assert worker.wait_for(MemberActionDoneMsg).results == []

    def test_find_chat_admins(self, worker):
        worker.send("find_chat_admins", [(FakeClient.SUPERGROUP, "Супергруппа")], 777,
                    scan_paused, scan_stop_requested)
        msg = worker.wait_for(AdminsDoneMsg)
        assert [a.user_id for a in msg.admins] == [100]
        assert msg.admins[0].chats == [(FakeClient.SUPERGROUP, "Супергруппа")]

    def test_failed_action_reports_and_closes(self, worker):
        # Пустой список чатов — ValueError внутри операции.
        worker.send("remove_user_from_chats", 777, [], True)
        err = worker.wait_for(ErrorMsg)
        assert err.operation == "remove_user_from_chats"
        # И всё равно закрываем операцию, иначе экран останется заблокированным.
        done = worker.wait_for(MemberActionDoneMsg)
        assert done.results == []


class TestOtherBranches:
    """Старые ветки — раньше они не были покрыты вовсе."""

    def test_scan(self, worker):
        worker.send("scan", True, True, True, scan_paused, None, scan_stop_requested)
        msg = worker.wait_for(ScanDoneMsg)
        assert msg.session == SESSION
        assert {p.chat_id for p in msg.places} == {FakeClient.SUPERGROUP, FakeClient.CHANNEL, 555}

    def test_list_export_dialogs(self, worker):
        worker.send("list_export_dialogs", True, True, True, scan_paused, scan_stop_requested)
        msg = worker.wait_for(ExportDialogsDoneMsg)
        assert len(msg.dialogs) == 3

    def test_delete_here(self, worker):
        worker.send("delete_here", FakeClient.SUPERGROUP, [10, 11])
        from ui.messages import DeleteDoneMsg

        msg = worker.wait_for(DeleteDoneMsg)
        assert sorted(msg.deleted_ids) == [10, 11]
        assert sorted(worker.client.deleted) == [10, 11]

    def test_switch_account(self, worker):
        worker.send("switch_account", "another")
        msg = worker.wait_for(SwitchAccountDoneMsg)
        assert msg.session == "another"
