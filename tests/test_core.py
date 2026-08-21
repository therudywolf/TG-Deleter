
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

"""Unit tests for core.py pure functions."""
import json
import os
import tempfile
import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSafeFilename:
    """Tests for _safe_filename."""

    def test_normal_name(self):
        from core import _safe_filename
        assert _safe_filename("hello_world") == "hello_world"

    def test_special_chars(self):
        from core import _safe_filename
        result = _safe_filename('file<>:"/\\|?*name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result

    def test_empty_string(self):
        from core import _safe_filename
        assert _safe_filename("") == "chat"
        assert _safe_filename("", fallback="default") == "default"

    def test_none(self):
        from core import _safe_filename
        assert _safe_filename(None) == "chat"

    def test_max_length(self):
        from core import _safe_filename
        long = "a" * 200
        result = _safe_filename(long, max_len=80)
        assert len(result) <= 80

    def test_trailing_dots(self):
        from core import _safe_filename
        result = _safe_filename("test...")
        assert not result.endswith(".")

    def test_whitespace(self):
        from core import _safe_filename
        result = _safe_filename("  hello   world  ")
        assert result == "hello world"

    def test_control_chars(self):
        from core import _safe_filename
        result = _safe_filename("hello\x00\x01world")
        assert "\x00" not in result


class TestMakePreview:
    """Tests for make_preview."""

    def test_text_message(self):
        from core import make_preview

        class FakeMsg:
            text = "Hello world"
            caption = None
        assert make_preview(FakeMsg()) == "Hello world"

    def test_long_text(self):
        from core import make_preview

        class FakeMsg:
            text = "x" * 100
            caption = None
        result = make_preview(FakeMsg(), max_len=50)
        assert len(result) == 53  # 50 + "..."
        assert result.endswith("...")

    def test_media_message(self):
        from core import make_preview

        class FakeMsg:
            text = None
            caption = None
        assert make_preview(FakeMsg()) == "[Медиа/Файл/Стикер]"

    def test_caption(self):
        from core import make_preview

        class FakeMsg:
            text = None
            caption = "Photo caption"
        assert make_preview(FakeMsg()) == "Photo caption"

    def test_empty_text(self):
        from core import make_preview

        class FakeMsg:
            text = ""
            caption = None
        assert make_preview(FakeMsg()) == "[Медиа/Файл/Стикер]"


class TestMessageDateStr:
    """Tests for _message_date_str."""

    def test_with_date(self):
        from core import _message_date_str
        from datetime import datetime

        class FakeMsg:
            date = datetime(2024, 3, 15, 10, 30)
        assert _message_date_str(FakeMsg()) == "2024-03-15 10:30"

    def test_none_date(self):
        from core import _message_date_str

        class FakeMsg:
            date = None
        assert _message_date_str(FakeMsg()) == ""


class TestChatTitle:
    """Tests for _chat_title."""

    def test_with_title(self):
        from core import _chat_title

        class FakeChat:
            title = "My Group"
            first_name = None
            id = 123
        assert _chat_title(FakeChat()) == "My Group"

    def test_with_first_name(self):
        from core import _chat_title

        class FakeChat:
            title = None
            first_name = "John"
            id = 123
        assert _chat_title(FakeChat()) == "John"

    def test_fallback_to_id(self):
        from core import _chat_title

        class FakeChat:
            title = None
            first_name = None
            id = 12345
        assert _chat_title(FakeChat()) == "12345"


class TestChatTypeStr:
    """Tests for _chat_type_str."""

    def test_private(self):
        from core import _chat_type_str
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.PRIVATE
        assert _chat_type_str(FakeChat()) == "Личный"

    def test_group(self):
        from core import _chat_type_str
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.GROUP
        assert _chat_type_str(FakeChat()) == "Группа"

    def test_channel(self):
        from core import _chat_type_str
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.CHANNEL
        assert _chat_type_str(FakeChat()) == "Канал"

    def test_supergroup(self):
        from core import _chat_type_str
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.SUPERGROUP
        assert _chat_type_str(FakeChat()) == "Супергруппа"

    def test_bot(self):
        from core import _chat_type_str
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.BOT
        assert _chat_type_str(FakeChat()) == "Бот"


class TestChatTypeClassifiers:
    """Tests for the scan/export section filters."""

    def test_bot_counts_as_private(self):
        from core import _is_private_chat_type, _is_group_chat_type, _is_channel_chat_type
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.BOT
        assert _is_private_chat_type(FakeChat()) is True
        assert _is_group_chat_type(FakeChat()) is False
        assert _is_channel_chat_type(FakeChat()) is False

    def test_private_is_private(self):
        from core import _is_private_chat_type
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.PRIVATE
        assert _is_private_chat_type(FakeChat()) is True

    def test_supergroup_is_group(self):
        from core import _is_group_chat_type, _is_private_chat_type
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.SUPERGROUP
        assert _is_group_chat_type(FakeChat()) is True
        assert _is_private_chat_type(FakeChat()) is False

    def test_channel_is_channel(self):
        from core import _is_channel_chat_type, _is_group_chat_type
        from pyrogram.enums import ChatType

        class FakeChat:
            type = ChatType.CHANNEL
        assert _is_channel_chat_type(FakeChat()) is True
        assert _is_group_chat_type(FakeChat()) is False


class TestIntFloat:
    """Tests for _int and _float helpers."""

    def test_int_valid(self):
        from core import _int
        assert _int("42") == 42
        assert _int(42) == 42

    def test_int_none(self):
        from core import _int
        assert _int(None) is None
        assert _int(None, 10) == 10

    def test_int_empty(self):
        from core import _int
        assert _int("") is None

    def test_int_invalid(self):
        from core import _int
        assert _int("abc") is None
        assert _int("abc", 5) == 5

    def test_float_valid(self):
        from core import _float
        assert _float("3.14") == pytest.approx(3.14)
        assert _float(2.5) == pytest.approx(2.5)

    def test_float_none(self):
        from core import _float
        assert _float(None) == pytest.approx(0.2)

    def test_float_empty(self):
        from core import _float
        assert _float("") == pytest.approx(0.2)

    def test_float_invalid(self):
        from core import _float
        assert _float("abc") == pytest.approx(0.2)


class TestMessageMediaKind:
    """Tests for _message_media_kind."""

    def test_photo(self):
        from core import _message_media_kind

        class FakeMsg:
            photo = True
            video = None
            video_note = None
            document = None
            audio = None
            voice = None
            sticker = None
            animation = None
            media = True
        assert _message_media_kind(FakeMsg()) == "photos"

    def test_video(self):
        from core import _message_media_kind

        class FakeMsg:
            photo = None
            video = True
            video_note = None
            document = None
            audio = None
            voice = None
            sticker = None
            animation = None
            media = True
        assert _message_media_kind(FakeMsg()) == "videos"

    def test_audio(self):
        from core import _message_media_kind

        class FakeMsg:
            photo = None
            video = None
            video_note = None
            document = None
            audio = None
            voice = True
            sticker = None
            animation = None
            media = True
        assert _message_media_kind(FakeMsg()) == "audio"

    def test_sticker(self):
        from core import _message_media_kind

        class FakeMsg:
            photo = None
            video = None
            video_note = None
            document = None
            audio = None
            voice = None
            sticker = True
            animation = None
            media = True
        assert _message_media_kind(FakeMsg()) == "stickers"

    def test_no_media(self):
        from core import _message_media_kind

        class FakeMsg:
            photo = None
            video = None
            video_note = None
            document = None
            audio = None
            voice = None
            sticker = None
            animation = None
            media = None
        assert _message_media_kind(FakeMsg()) is None


class TestShouldExportMedia:
    """Tests for _should_export_media gating."""

    class _PhotoMsg:
        photo = True
        video = None
        video_note = None
        document = None
        audio = None
        voice = None
        sticker = None
        animation = None
        media = True

    class _PlainMsg:
        photo = None
        video = None
        video_note = None
        document = None
        audio = None
        voice = None
        sticker = None
        animation = None
        media = None

    def test_enabled_type(self):
        from core import _should_export_media, _normalize_media_types
        assert _should_export_media(self._PhotoMsg(), _normalize_media_types({"photos": True})) is True

    def test_disabled_type(self):
        from core import _should_export_media, _normalize_media_types
        assert _should_export_media(self._PhotoMsg(), _normalize_media_types({"photos": False})) is False

    def test_non_media_message(self):
        from core import _should_export_media, _normalize_media_types
        assert _should_export_media(self._PlainMsg(), _normalize_media_types(None)) is False


class TestNormalizeMediaTypes:
    """Tests for _normalize_media_types."""

    def test_defaults(self):
        from core import _normalize_media_types
        result = _normalize_media_types(None)
        assert result["photos"] is True
        assert result["videos"] is True

    def test_override(self):
        from core import _normalize_media_types
        result = _normalize_media_types({"photos": False, "videos": True})
        assert result["photos"] is False
        assert result["videos"] is True
        assert result["documents"] is True  # default


class TestHtmlGeneration:
    """Tests for HTML export functions."""

    def test_html_header(self):
        from core import _html_header
        result = _html_header("Test Chat")
        assert "Test Chat" in result
        assert "<!doctype html>" in result
        assert "<style>" in result

    def test_html_header_escaping(self):
        from core import _html_header
        result = _html_header("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_message(self):
        from core import _html_message
        record = {
            "id": 123,
            "date": "2024-01-15T10:30:00",
            "sender": "John",
            "text": "Hello",
            "media": None,
        }
        result = _html_message(record)
        assert "Hello" in result
        assert "John" in result
        assert "123" in result


class TestMessageRecord:
    """Tests for _message_record."""

    def test_basic(self):
        from core import _message_record
        from datetime import datetime

        class FakeMsg:
            id = 42
            date = datetime(2024, 1, 15, 10, 30)
            text = "Hello"
            caption = None
            media = None
            service = None
            from_user = None
            sender_chat = None
            out = True
            outgoing = True
        record = _message_record(123, FakeMsg())
        assert record["id"] == 42
        assert record["chat_id"] == 123
        assert record["text"] == "Hello"
        assert record["outgoing"] is True


class TestConfigHelpers:
    """Tests for config load/save."""

    def test_api_config_roundtrip(self):
        from core import save_api_config, load_api_config, _api_config_path, _API_DEFAULTS
        import tempfile
        pass

    def test_place_dataclass(self):
        from core import Place
        p = Place(chat_id=123, title="Test", type_str="Группа", messages=[(1, "hi", "2024-01-01")])
        assert p.chat_id == 123
        assert len(p.messages) == 1

    def test_export_options_dataclass(self):
        from core import ExportOptions
        opts = ExportOptions(output_dir="/tmp", chat_ids=[1, 2, 3])
        assert opts.parallel_chats == 2
        assert opts.include_media is True


class TestMessageSenderName:
    """Tests for _message_sender_name."""

    def test_from_user_with_name(self):
        from core import _message_sender_name

        class FakeUser:
            first_name = "John"
            last_name = "Doe"
            username = "johndoe"
            id = 123

        class FakeMsg:
            from_user = FakeUser()
            sender_chat = None
        assert "John Doe" in _message_sender_name(FakeMsg())
        assert "@johndoe" in _message_sender_name(FakeMsg())

    def test_no_sender(self):
        from core import _message_sender_name

        class FakeMsg:
            from_user = None
            sender_chat = None
        assert _message_sender_name(FakeMsg()) == ""


class TestMessageText:
    """Tests for _message_text."""

    def test_text(self):
        from core import _message_text

        class FakeMsg:
            text = "Hello"
            caption = None
            media = None
            service = None
        assert _message_text(FakeMsg()) == "Hello"

    def test_caption(self):
        from core import _message_text

        class FakeMsg:
            text = None
            caption = "Cap"
            media = None
            service = None
        assert _message_text(FakeMsg()) == "Cap"

    def test_empty(self):
        from core import _message_text

        class FakeMsg:
            text = None
            caption = None
            media = None
            service = None
        assert _message_text(FakeMsg()) == ""

    def test_media_renders_enum_value(self):
        from core import _message_text

        class FakeEnum:
            value = "photo"

            def __str__(self):
                return "MessageMediaType.PHOTO"

        class FakeMsg:
            text = None
            caption = None
            media = FakeEnum()
            service = None
        # Should use the enum's .value, not its repr/str.
        assert _message_text(FakeMsg()) == "[photo]"


class TestSessionNames:
    """Tests for shared session name validation."""

    def test_valid_session_name(self):
        from core import normalize_session_name
        assert normalize_session_name("account_1-test") == "account_1-test"

    def test_rejects_path_traversal(self):
        from core import normalize_session_name
        assert normalize_session_name("../account") is None
        assert normalize_session_name("nested/account") is None

    def test_rejects_too_short(self):
        from core import normalize_session_name
        assert normalize_session_name("a") is None


class TestOwnershipSafety:
    """Tests for conservative ownership checks used before deletion."""

    @pytest.mark.asyncio
    async def test_author_signature_is_not_ownership(self):
        from core import check_if_mine, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "alice", "first_name": "Alice", "last_name": "Admin"})

        class FakeMsg:
            out = False
            outgoing = False
            from_user = None
            author_signature = "Alice"

        assert await check_if_mine(FakeMsg()) is False

    @pytest.mark.asyncio
    async def test_sender_chat_is_not_ownership(self):
        from core import check_if_mine, set_my_channels

        set_my_channels({123})

        class FakeSenderChat:
            id = 123

        class FakeMsg:
            out = False
            outgoing = False
            from_user = None
            sender_chat = FakeSenderChat()

        assert await check_if_mine(FakeMsg()) is False

    @pytest.mark.asyncio
    async def test_delete_rechecks_message_ownership(self):
        from core import delete_message_ids, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "alice"})

        class FakeUser:
            def __init__(self, user_id):
                self.id = user_id
                self.username = None

        class FakeMsg:
            out = False
            outgoing = False

            def __init__(self, message_id, user_id):
                self.id = message_id
                self.from_user = FakeUser(user_id)

        class FakeClient:
            def __init__(self):
                self.deleted = []

            async def get_messages(self, cid, message_ids):
                return [FakeMsg(message_ids[0], 1), FakeMsg(message_ids[1], 2)]

            async def delete_messages(self, cid, message_ids):
                self.deleted.extend(message_ids if isinstance(message_ids, list) else [message_ids])

        client = FakeClient()
        set_app(client)
        deleted = await delete_message_ids(100, [10, 20])

        assert deleted == [10]
        assert client.deleted == [10]
        set_app(None)


class TestNormalizeUserQuery:
    """Tests for normalize_user_query."""

    def test_username_with_at(self):
        from core import normalize_user_query
        assert normalize_user_query("@durov") == "durov"

    def test_bare_username(self):
        from core import normalize_user_query
        assert normalize_user_query("durov") == "durov"

    def test_tme_link(self):
        from core import normalize_user_query
        assert normalize_user_query("https://t.me/durov") == "durov"
        assert normalize_user_query("t.me/@durov") == "durov"

    def test_numeric_id(self):
        from core import normalize_user_query
        assert normalize_user_query(" 123456789 ") == 123456789

    def test_phone(self):
        from core import normalize_user_query
        assert normalize_user_query("+7 (999) 123-45-67") == "+79991234567"

    def test_chat_id_rejected(self):
        from core import normalize_user_query
        with pytest.raises(ValueError):
            normalize_user_query("-1001234567890")

    def test_empty_rejected(self):
        from core import normalize_user_query
        with pytest.raises(ValueError):
            normalize_user_query("   ")

    def test_garbage_rejected(self):
        from core import normalize_user_query
        with pytest.raises(ValueError):
            normalize_user_query("не имя!")


class TestDescribeTelegramError:
    """Tests for describe_telegram_error."""

    def test_known_error_name(self):
        from core import describe_telegram_error

        class ChatAdminRequired(Exception):
            pass

        assert describe_telegram_error(ChatAdminRequired("[400 ...]")) == "Нужны права администратора"

    def test_unknown_error_keeps_text(self):
        from core import describe_telegram_error
        text = describe_telegram_error(ValueError("что-то пошло не так"))
        assert text.startswith("ValueError: ")
        assert "что-то пошло не так" in text

    def test_long_text_is_trimmed(self):
        from core import describe_telegram_error, _MAX_ERROR_TEXT
        text = describe_telegram_error(RuntimeError("x" * 500))
        assert len(text) <= _MAX_ERROR_TEXT + len("RuntimeError: ")


class FakeChatMember:
    """Минимальный аналог pyrogram.types.ChatMember."""

    class _Status:
        def __init__(self, name):
            self.name = name

    class _Privileges:
        def __init__(self, can_restrict_members):
            self.can_restrict_members = can_restrict_members

    def __init__(self, status, can_restrict=False):
        self.status = self._Status(status)
        self.privileges = self._Privileges(can_restrict)


class UserNotParticipant(Exception):
    """Одноимённая ошибка Pyrogram — код смотрит на имя класса."""


class ChatAdminRequired(Exception):
    pass


class UserPrivacyRestricted(Exception):
    pass


class UserAlreadyParticipant(Exception):
    pass


@pytest.fixture
def no_member_delays(monkeypatch):
    """Убираем паузы между чатами, чтобы тесты не спали секундами."""
    import core
    monkeypatch.setattr(core, "_MEMBER_PROBE_DELAY_MIN", 0)
    monkeypatch.setattr(core, "_MEMBER_REMOVE_DELAY_MIN", 0)
    monkeypatch.setattr(core, "_MEMBER_ADD_DELAY_MIN", 0)
    monkeypatch.setattr(core, "get_delay_sec", lambda: 0)


class TestRemoveUserFromChats:
    """Tests for remove_user_from_chats."""

    @pytest.mark.asyncio
    async def test_bans_every_selected_chat(self, no_member_delays):
        from core import remove_user_from_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeClient:
            def __init__(self):
                self.banned = []
                self.unbanned = []

            async def ban_chat_member(self, cid, uid):
                self.banned.append((cid, uid))

            async def unban_chat_member(self, cid, uid):
                self.unbanned.append((cid, uid))

        client = FakeClient()
        set_app(client)
        try:
            results = await remove_user_from_chats(777, [(-1001, "Первый"), (-1002, "Второй")], ban=True)
        finally:
            set_app(None)

        assert client.banned == [(-1001, 777), (-1002, 777)]
        assert client.unbanned == []
        assert [r.ok for r in results] == [True, True]
        assert results[0].note == "Удалён и забанен"

    @pytest.mark.asyncio
    async def test_kick_without_ban_unbans_only_channels(self, no_member_delays):
        from core import remove_user_from_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})
        supergroup = -1001234567890   # супергруппа/канал
        basic_group = -4321           # обычная группа: бана там нет

        class FakeClient:
            def __init__(self):
                self.unbanned = []

            async def ban_chat_member(self, cid, uid):
                pass

            async def unban_chat_member(self, cid, uid):
                self.unbanned.append(cid)

        client = FakeClient()
        set_app(client)
        try:
            results = await remove_user_from_chats(
                777, [(supergroup, "Супергруппа"), (basic_group, "Группа")], ban=False
            )
        finally:
            set_app(None)

        assert client.unbanned == [supergroup]
        assert all(r.ok for r in results)
        assert results[0].note == "Удалён"

    @pytest.mark.asyncio
    async def test_per_chat_error_does_not_stop_the_rest(self, no_member_delays):
        from core import remove_user_from_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeClient:
            def __init__(self):
                self.banned = []

            async def ban_chat_member(self, cid, uid):
                if cid == -1001:
                    raise ChatAdminRequired("[400 CHAT_ADMIN_REQUIRED]")
                self.banned.append(cid)

        client = FakeClient()
        set_app(client)
        try:
            results = await remove_user_from_chats(777, [(-1001, "Чужой"), (-1002, "Свой")], ban=True)
        finally:
            set_app(None)

        assert client.banned == [-1002]
        assert [r.ok for r in results] == [False, True]
        assert results[0].note == "Нужны права администратора"

    @pytest.mark.asyncio
    async def test_refuses_to_target_self(self, no_member_delays):
        from core import remove_user_from_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 555, "username": "me"})
        set_app(object())
        try:
            with pytest.raises(ValueError):
                await remove_user_from_chats(555, [(-1001, "Чат")])
        finally:
            set_app(None)

    @pytest.mark.asyncio
    async def test_stop_event_interrupts(self, no_member_delays):
        import threading
        from core import remove_user_from_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})
        stop = threading.Event()

        class FakeClient:
            def __init__(self):
                self.banned = []

            async def ban_chat_member(self, cid, uid):
                self.banned.append(cid)
                stop.set()

        client = FakeClient()
        set_app(client)
        try:
            results = await remove_user_from_chats(
                777, [(-1001, "Один"), (-1002, "Два"), (-1003, "Три")], stop_event=stop
            )
        finally:
            set_app(None)

        assert client.banned == [-1001]
        assert len(results) == 1


class TestAddUserToChats:
    """Tests for add_user_to_chats."""

    @pytest.mark.asyncio
    async def test_adds_to_every_chat(self, no_member_delays):
        from core import add_user_to_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeClient:
            def __init__(self):
                self.added = []

            async def add_chat_members(self, cid, uid):
                self.added.append((cid, uid))

        client = FakeClient()
        set_app(client)
        try:
            results = await add_user_to_chats(777, [(-1001, "Первый"), (-1002, "Второй")])
        finally:
            set_app(None)

        assert client.added == [(-1001, 777), (-1002, 777)]
        assert all(r.ok for r in results)
        assert results[0].note == "Добавлен"

    @pytest.mark.asyncio
    async def test_already_participant_counts_as_success(self, no_member_delays):
        from core import add_user_to_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeClient:
            async def add_chat_members(self, cid, uid):
                raise UserAlreadyParticipant("[400 USER_ALREADY_PARTICIPANT]")

        set_app(FakeClient())
        try:
            results = await add_user_to_chats(777, [(-1001, "Первый")])
        finally:
            set_app(None)

        assert results[0].ok is True
        assert results[0].note == "Уже в чате"

    @pytest.mark.asyncio
    async def test_privacy_error_is_reported(self, no_member_delays):
        from core import add_user_to_chats, set_app, set_me_from_dict

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeClient:
            async def add_chat_members(self, cid, uid):
                raise UserPrivacyRestricted("[403 USER_PRIVACY_RESTRICTED]")

        set_app(FakeClient())
        try:
            results = await add_user_to_chats(777, [(-1001, "Первый")])
        finally:
            set_app(None)

        assert results[0].ok is False
        assert results[0].note == "Настройки приватности не позволяют добавить"


class TestFindChatsWithUser:
    """Tests for find_chats_with_user (быстрый режим по общим чатам)."""

    @pytest.mark.asyncio
    async def test_marks_chats_by_my_rights(self, no_member_delays):
        from core import find_chats_with_user, set_app, set_me_from_dict
        from pyrogram.enums import ChatType

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeChat:
            def __init__(self, chat_id, title, chat_type):
                self.id = chat_id
                self.title = title
                self.type = chat_type

        class FakeClient:
            async def get_common_chats(self, uid):
                return [
                    FakeChat(-1001, "Мой чат", ChatType.SUPERGROUP),
                    FakeChat(-1002, "Чужой чат", ChatType.SUPERGROUP),
                ]

            async def get_chat_member(self, cid, uid):
                if uid == "me":
                    return FakeChatMember("OWNER" if cid == -1001 else "MEMBER")
                return FakeChatMember("MEMBER")

        set_app(FakeClient())
        try:
            found = await find_chats_with_user(777, deep=False)
        finally:
            set_app(None)

        by_id = {c.chat_id: c for c in found}
        assert by_id[-1001].can_manage is True
        assert by_id[-1001].note == "можно удалить"
        assert by_id[-1002].can_manage is False
        assert by_id[-1002].note == "вы не админ"

    @pytest.mark.asyncio
    async def test_admin_target_is_not_removable(self, no_member_delays):
        from core import find_chats_with_user, set_app, set_me_from_dict
        from pyrogram.enums import ChatType

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeChat:
            id = -1001
            title = "Чат"
            type = ChatType.SUPERGROUP

        class FakeClient:
            async def get_common_chats(self, uid):
                return [FakeChat()]

            async def get_chat_member(self, cid, uid):
                if uid == "me":
                    return FakeChatMember("OWNER")
                return FakeChatMember("ADMINISTRATOR")

        set_app(FakeClient())
        try:
            found = await find_chats_with_user(777, deep=False)
        finally:
            set_app(None)

        assert len(found) == 1
        assert found[0].can_manage is False
        assert found[0].note == "админ — снимите права"

    @pytest.mark.asyncio
    async def test_deep_scan_skips_chats_without_the_user(self, no_member_delays):
        from core import find_chats_with_user, set_app, set_me_from_dict
        from pyrogram.enums import ChatType

        set_me_from_dict({"id": 1, "username": "me"})

        class FakeChat:
            def __init__(self, chat_id, title, chat_type):
                self.id = chat_id
                self.title = title
                self.type = chat_type

        class FakeDialog:
            def __init__(self, chat):
                self.chat = chat

        class FakeClient:
            async def get_dialogs(self):
                for chat in (
                    FakeChat(-1001, "С ним", ChatType.SUPERGROUP),
                    FakeChat(-1002, "Без него", ChatType.SUPERGROUP),
                    FakeChat(555, "Личка", ChatType.PRIVATE),
                ):
                    yield FakeDialog(chat)

            async def get_chat_member(self, cid, uid):
                if uid == "me":
                    return FakeChatMember("OWNER")
                if cid == -1002:
                    raise UserNotParticipant("[400 USER_NOT_PARTICIPANT]")
                return FakeChatMember("MEMBER")

        set_app(FakeClient())
        try:
            found = await find_chats_with_user(777, deep=True)
        finally:
            set_app(None)

        assert [c.chat_id for c in found] == [-1001]


class TestPyrogramApiContract:
    """Методы Pyrogram, которые воркер зовёт по имени: переименование должно падать здесь, а не молча в логе."""

    def test_client_exposes_methods_the_worker_calls(self):
        from pyrogram import Client

        # get_profile_photos переехал в get_chat_photos ещё в Pyrogram 2.x —
        # промах ловился общим except и оставлял сайдбар без аватарок.
        for name in ("get_chat_photos", "download_media", "get_dialogs", "get_chat_history",
                     "get_common_chats", "get_chat_member", "ban_chat_member",
                     "unban_chat_member", "add_chat_members"):
            assert hasattr(Client, name), f"Pyrogram больше не отдаёт Client.{name}"
