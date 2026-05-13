
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
