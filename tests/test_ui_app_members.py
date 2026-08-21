
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
Тесты главного окна в части экрана «Участники»: маршрутизация сообщений
воркера и формирование запросов к нему.

Требуют customtkinter и рабочий дисплей, поэтому в headless-CI пропускаются.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("customtkinter", reason="GUI-тесты требуют customtkinter")

from core import MemberActionResult, MemberChat, Place, TargetUser, _fill_member_note  # noqa: E402
from ui.members_frame import MODE_ADD, MODE_REMOVE  # noqa: E402
from ui.messages import (  # noqa: E402
    ErrorMsg,
    FloodWaitMsg,
    MemberActionDoneMsg,
    MemberActionProgressMsg,
    AdminsProgressMsg,
    AdminFoundMsg,
    AdminsDoneMsg,
    MemberChatFoundMsg,
    MemberChatsDoneMsg,
    MemberChatsProgressMsg,
    MemberDialogsBatchMsg,
    MemberDialogsDoneMsg,
    MemberDialogsProgressMsg,
    SwitchAccountDoneMsg,
    UserResolvedMsg,
)
from ui.queues import request_queue  # noqa: E402

SESSION = "test_session"
TARGET = TargetUser(user_id=777, username="spammer", first_name="Иван", last_name="Петров")


def chat(chat_id, title, can_manage=True):
    return _fill_member_note(
        MemberChat(chat_id=chat_id, title=title, type_str="Супергруппа",
                   my_status="owner" if can_manage else "member",
                   target_status="member", can_manage=can_manage)
    )


def drain():
    out = []
    while not request_queue.empty():
        out.append(request_queue.get_nowait())
    return out


@pytest.fixture(scope="module")
def app(gui_app):
    """Главное окно из общей сессионной фикстуры."""
    return gui_app


@pytest.fixture(autouse=True)
def clean(app):
    """Чистое состояние между тестами: пустая очередь, сброшенный экран, пустой лог диалогов."""
    drain()
    app.box.calls.clear()
    app.members_frame.reset()
    app._operation_running = False
    app.root.update()
    yield
    drain()


class TestNavigation:
    """Переходы между экранами."""

    def test_members_screen_is_reachable_and_exclusive(self, app):
        app._show_members()
        app.root.update()
        assert app.members_frame.winfo_ismapped()
        assert not app.export_frame.winfo_ismapped()
        assert not app.places_frame.winfo_ismapped()

    def test_other_screens_hide_members(self, app):
        app._show_members()
        app.root.update()
        for show in (app._show_places, app._show_export, app._show_settings):
            show()
            app.root.update()
            assert not app.members_frame.winfo_ismapped()
        app._show_members()
        app.root.update()


class TestDispatchTable:
    """Каждое новое сообщение воркера должно иметь обработчик."""

    @pytest.mark.parametrize("name", [
        "UserResolvedMsg", "MemberChatsProgressMsg", "MemberChatFoundMsg", "MemberChatsDoneMsg",
        "MemberDialogsProgressMsg", "MemberDialogsBatchMsg", "MemberDialogsDoneMsg",
        "MemberActionProgressMsg", "MemberActionDoneMsg",
    ])
    def test_handler_is_registered(self, app, name):
        assert name in app._msg_handlers

    def test_messages_route_without_errors(self, app):
        messages = [
            UserResolvedMsg(user=TARGET),
            MemberChatsProgressMsg(n=1, title="Чат", total=3),
            MemberChatFoundMsg(chat=chat(-1001, "Группа")),
            MemberChatsDoneMsg(chats=[chat(-1001, "Группа")], stopped=False, session=SESSION),
            MemberDialogsProgressMsg(n=2, title="Канал"),
            MemberDialogsBatchMsg(batch=[Place(chat_id=-2001, title="Канал", type_str="Канал")]),
            MemberDialogsDoneMsg(dialogs=[Place(chat_id=-2001, title="Канал", type_str="Канал")],
                                 stopped=False, session=SESSION),
        ]
        for msg in messages:
            app._msg_handlers[type(msg).__name__](msg)
            app.root.update()
        assert app.members_frame.target is TARGET


class TestIncomingMessages:
    """Что именно сообщения делают с экраном."""

    def test_resolved_user_lands_on_the_screen(self, app):
        app._msg_handlers["UserResolvedMsg"](UserResolvedMsg(user=TARGET))
        assert app.members_frame.target is TARGET

    def test_progress_shows_counter_and_title(self, app):
        strip = app.members_frame.progress
        strip.start("Ищу чаты")
        app._msg_handlers["MemberChatsProgressMsg"](
            MemberChatsProgressMsg(n=2, title="Рабочий чат", total=7)
        )
        assert strip.counter_label.cget("text") == "2 / 7"
        assert "Рабочий чат" in strip.detail_label.cget("text")

    def test_progress_without_total_shows_plain_count(self, app):
        strip = app.members_frame.progress
        strip.start("Ищу чаты")
        app._msg_handlers["MemberChatsProgressMsg"](
            MemberChatsProgressMsg(n=5, title="Чат", total=None)
        )
        assert strip.counter_label.cget("text") == "5"

    def test_stage_message_becomes_the_stage(self, app):
        # n=0 — это этап поиска, а не конкретный чат: «Проверено чатов: 0» врало бы.
        strip = app.members_frame.progress
        strip.start("Ищу чаты")
        app._msg_handlers["MemberChatsProgressMsg"](
            MemberChatsProgressMsg(n=0, title="Спрашиваю Telegram про общие чаты…", total=None)
        )
        assert strip.stage_label.cget("text") == "Спрашиваю Telegram про общие чаты…"

    def test_stage_message_carries_the_total(self, app):
        strip = app.members_frame.progress
        strip.start("Ищу чаты")
        app._msg_handlers["MemberChatsProgressMsg"](
            MemberChatsProgressMsg(n=0, title="Общих чатов: 12. Проверяю права…", total=12)
        )
        assert strip.stage_label.cget("text") == "Общих чатов: 12. Проверяю права…"
        assert strip.counter_label.cget("text") == "0 / 12"

    def test_found_chat_is_appended(self, app):
        app._msg_handlers["UserResolvedMsg"](UserResolvedMsg(user=TARGET))
        app._msg_handlers["MemberChatFoundMsg"](MemberChatFoundMsg(chat=chat(-1001, "Группа")))
        app.root.update()
        assert [c.chat_id for c in app.members_frame._items[MODE_REMOVE]] == [-1001]

    def test_chats_done_clears_the_running_flag(self, app):
        app._operation_running = True
        app._msg_handlers["MemberChatsDoneMsg"](
            MemberChatsDoneMsg(chats=[chat(-1001, "Группа")], stopped=False, session=SESSION)
        )
        assert app._operation_running is False
        assert app.members_frame._selected[MODE_REMOVE] == {-1001}

    def test_dialogs_batch_fills_add_mode(self, app):
        app.members_frame.mode_switch.set(MODE_ADD)
        app.members_frame._on_mode_change(MODE_ADD)
        app._msg_handlers["MemberDialogsBatchMsg"](
            MemberDialogsBatchMsg(batch=[Place(chat_id=-2001, title="Канал", type_str="Канал")])
        )
        app.root.update()
        assert len(app.members_frame._items[MODE_ADD]) == 1
        app.members_frame.mode_switch.set(MODE_REMOVE)
        app.members_frame._on_mode_change(MODE_REMOVE)

    def test_action_progress_and_done(self, app):
        app._msg_handlers["UserResolvedMsg"](UserResolvedMsg(user=TARGET))
        app._msg_handlers["MemberChatsDoneMsg"](
            MemberChatsDoneMsg(chats=[chat(-1001, "Группа")], stopped=False, session=SESSION)
        )
        app._operation_running = True
        app._msg_handlers["MemberActionProgressMsg"](MemberActionProgressMsg(
            action="remove", current=1, total=1,
            result=MemberActionResult(-1001, "Группа", True, "Удалён и забанен"),
        ))
        app._msg_handlers["MemberActionDoneMsg"](MemberActionDoneMsg(
            action="remove",
            results=[MemberActionResult(-1001, "Группа", True, "Удалён и забанен")],
            stopped=False,
        ))
        app.root.update()
        assert app._operation_running is False
        assert app.members_frame._items[MODE_REMOVE] == []
        assert app.box.kinds()[-1] == "info"

    def test_switching_account_resets_the_screen(self, app):
        app._msg_handlers["UserResolvedMsg"](UserResolvedMsg(user=TARGET))
        app._msg_handlers["MemberChatFoundMsg"](MemberChatFoundMsg(chat=chat(-1001, "Группа")))
        app._msg_handlers["SwitchAccountDoneMsg"](SwitchAccountDoneMsg(session="other"))
        app.root.update()
        assert app.members_frame.target is None
        assert app.members_frame._items[MODE_REMOVE] == []

    def test_flood_wait_is_visible_on_the_screen(self, app):
        app._msg_handlers["FloodWaitMsg"](FloodWaitMsg(seconds=42, operation="find_user_chats"))
        assert "42" in app.members_frame.status_label.cget("text")


class TestErrors:
    """Ошибки операций с участниками."""

    def test_resolve_error_stays_inline(self, app):
        app._msg_handlers["UserResolvedMsg"](UserResolvedMsg(user=TARGET))
        app._msg_handlers["ErrorMsg"](
            ErrorMsg(operation="resolve_user", error="Такого @username не существует")
        )
        app.root.update()
        assert app.members_frame.target is None
        assert "Такого @username не существует" in app.members_frame.user_label.cget("text")
        assert app.box.kinds() == []

    @pytest.mark.parametrize("operation", [
        "find_user_chats", "list_member_chats", "remove_user_from_chats", "add_user_to_chats",
    ])
    def test_operation_error_unlocks_the_screen(self, app, operation):
        app.members_frame.set_busy(True, "Работаю")
        app._operation_running = True
        app._msg_handlers["ErrorMsg"](ErrorMsg(operation=operation, error="Нет подключения"))
        app.root.update()
        assert app.members_frame._busy is False
        assert app._operation_running is False
        assert "Нет подключения" in app.members_frame.status_label.cget("text")
        assert app.box.kinds() == ["error"]


class TestOutgoingRequests:
    """Формат запросов, которые экран кладёт в очередь воркера."""

    def test_resolve_user(self, app):
        app._on_resolve_user("@spammer")
        assert drain() == [("resolve_user", "@spammer")]

    def test_find_user_chats(self, app):
        from ui.queues import scan_paused, scan_stop_requested

        app._on_find_user_chats(777, True, True, False)
        sent = drain()
        assert len(sent) == 1
        assert sent[0][:5] == ("find_user_chats", 777, True, True, False)
        assert sent[0][5] is scan_paused and sent[0][6] is scan_stop_requested
        assert app._operation_running is True

    def test_list_member_chats(self, app):
        app._on_load_member_chats(True, True)
        sent = drain()
        assert sent[0][:3] == ("list_member_chats", True, True)

    def test_remove_request_carries_pairs_and_ban(self, app):
        app._on_remove_user_from_chats(777, [(-1001, "Группа")], True)
        assert drain() == [("remove_user_from_chats", 777, [(-1001, "Группа")], True)]

    def test_add_request_carries_pairs(self, app):
        app._on_add_user_to_chats(777, [(-2001, "Канал")])
        assert drain() == [("add_user_to_chats", 777, [(-2001, "Канал")])]

    def test_requests_are_refused_without_an_account(self, app, monkeypatch):
        import ui.app as uiapp

        monkeypatch.setattr(uiapp, "get_current_session", lambda: None)
        app._on_resolve_user("@spammer")
        app._on_find_user_chats(777, False, True, True)
        app._on_load_member_chats(True, True)
        app._on_remove_user_from_chats(777, [(-1001, "Группа")], True)
        app._on_add_user_to_chats(777, [(-2001, "Канал")])
        assert drain() == []
        assert app.box.kinds() == ["warning"] * 5


class TestAdminLookupWiring:
    """Поиск админов: сообщения воркера и запрос к нему."""

    def test_handlers_are_registered(self, app):
        for name in ("AdminsProgressMsg", "AdminFoundMsg", "AdminsDoneMsg"):
            assert name in app._msg_handlers

    def test_progress_reaches_the_screen(self, app):
        strip = app.members_frame.progress
        strip.start("Ищу админов", total=40)
        app._msg_handlers["AdminsProgressMsg"](
            AdminsProgressMsg(n=7, total=40, title="ДИТ. WAF - КППМ")
        )
        assert strip.counter_label.cget("text") == "7 / 40"
        assert "КППМ" in strip.detail_label.cget("text")

    def test_found_admin_is_only_logged(self, app):
        from core import AdminContact

        # Промежуточные находки не трогают экран — итог показывает окно.
        before = app.members_frame.progress.detail_label.cget("text")
        app._msg_handlers["AdminFoundMsg"](AdminFoundMsg(admin=AdminContact(user_id=5, username="x")))
        assert app.members_frame.progress.detail_label.cget("text") == before

    def test_done_opens_the_dialog(self, app, monkeypatch):
        import ui.members_frame as members_frame
        from core import AdminContact

        opened = {}

        class FakeDialog:
            def __init__(self, parent, admins, target_name="", chats_count=0, stopped=False):
                opened.update(admins=admins, stopped=stopped)

        monkeypatch.setattr(members_frame, "AdminsDialog", FakeDialog)
        app._operation_running = True
        admins = [AdminContact(user_id=5, username="boss")]
        app._msg_handlers["AdminsDoneMsg"](AdminsDoneMsg(admins=admins, stopped=False))
        app.root.update()
        assert opened["admins"] is admins
        assert app._operation_running is False

    def test_request_carries_pairs_and_target(self, app):
        from ui.queues import scan_paused, scan_stop_requested

        app._on_find_chat_admins([(-1002, "Чужой чат")], 777)
        sent = drain()
        assert len(sent) == 1
        assert sent[0][:3] == ("find_chat_admins", [(-1002, "Чужой чат")], 777)
        assert sent[0][3] is scan_paused and sent[0][4] is scan_stop_requested

    def test_error_unlocks_the_screen(self, app):
        app.members_frame.set_busy(True, "Ищу админов")
        app._operation_running = True
        app._msg_handlers["ErrorMsg"](ErrorMsg(operation="find_chat_admins", error="Нет подключения"))
        app.root.update()
        assert app.members_frame._busy is False
        assert "Нет подключения" in app.members_frame.status_label.cget("text")
