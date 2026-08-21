
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
Тесты окна «Кто может удалить».

Требуют customtkinter и рабочий дисплей, поэтому в headless-CI пропускаются.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("customtkinter", reason="GUI-тесты требуют customtkinter")

from core import AdminContact  # noqa: E402
import ui.admins_dialog as admins_dialog  # noqa: E402
from ui.admins_dialog import AdminRow, AdminsDialog, admins_as_text, open_telegram_link  # noqa: E402


def contact(uid, first="Имя", last="Фамилия", username=None, chats=None, owner_of=0, is_bot=False):
    a = AdminContact(user_id=uid, first_name=first, last_name=last, username=username,
                     is_bot=is_bot, owner_of=owner_of)
    a.chats = list(chats or [(-1001, "Чат")])
    return a


@pytest.fixture
def dialog(gui_root):
    """Окно создаётся под тест и закрывается после него."""
    made = []

    def make(admins, **kw):
        dlg = AdminsDialog(gui_root, admins, **kw)
        made.append(dlg)
        gui_root.update()
        return dlg

    yield make
    for dlg in made:
        try:
            dlg.destroy()
        except Exception:
            pass
    gui_root.update()


class TestAdminsAsText:
    """Список, который уходит в буфер обмена."""

    def test_includes_the_target_and_every_chat(self):
        text = admins_as_text(
            [contact(1, "Наталья", "Шипова", "NDShe", [(-1, "Первый"), (-2, "Второй")])],
            target_name="Майя Саакова",
        )
        assert text.startswith("Кто может удалить Майя Саакова:")
        assert "Наталья Шипова (@NDShe)" in text
        assert "чатов: 2" in text
        assert "– Первый" in text and "– Второй" in text

    def test_user_without_username_shows_the_id(self):
        text = admins_as_text([contact(603708602, username=None)])
        assert "id 603708602" in text

    def test_no_target_no_header(self):
        text = admins_as_text([contact(1, username="a")])
        assert not text.startswith("Кто может удалить")

    def test_empty_list_is_empty_text(self):
        assert admins_as_text([]) == ""


class TestOpenTelegramLink:
    """Открытие ссылки: путь зависит от платформы, но пустая ссылка не открывается."""

    def test_empty_url_is_refused(self):
        assert open_telegram_link("") is False
        assert open_telegram_link(None) is False

    def test_windows_uses_startfile(self, monkeypatch):
        calls = []
        monkeypatch.setattr(admins_dialog.sys, "platform", "win32")
        monkeypatch.setattr(admins_dialog.os, "startfile", lambda u: calls.append(u), raising=False)
        assert open_telegram_link("https://t.me/NDShe") is True
        assert calls == ["https://t.me/NDShe"]

    def test_other_platforms_use_the_browser(self, monkeypatch):
        calls = []
        monkeypatch.setattr(admins_dialog.sys, "platform", "linux")
        monkeypatch.setattr(admins_dialog.webbrowser, "open", lambda u: calls.append(u) or True)
        assert open_telegram_link("tg://user?id=7") is True
        assert calls == ["tg://user?id=7"]

    def test_failure_is_reported_not_raised(self, monkeypatch):
        def boom(_u):
            raise OSError("нет обработчика")

        monkeypatch.setattr(admins_dialog.sys, "platform", "linux")
        monkeypatch.setattr(admins_dialog.webbrowser, "open", boom)
        assert open_telegram_link("https://t.me/x") is False


class TestAdminsDialog:
    """Содержимое окна."""

    @staticmethod
    def _rows(dlg):
        return [w for w in dlg.scroll.winfo_children() if isinstance(w, AdminRow)]

    def test_one_row_per_admin(self, dialog):
        dlg = dialog([contact(1, username="a"), contact(2, username="b")], target_name="Цель")
        assert len(self._rows(dlg)) == 2

    def test_title_names_the_target(self, dialog):
        dlg = dialog([contact(1, username="a")], target_name="Майя Саакова")
        assert "Майя Саакова" in dlg.winfo_children()[0].winfo_children()[0].cget("text")

    def test_empty_result_says_so_and_has_no_rows(self, dialog):
        dlg = dialog([], target_name="Цель")
        assert self._rows(dlg) == []

    def test_stopped_search_is_labelled(self, dialog):
        dlg = dialog([contact(1, username="a")], target_name="Цель", stopped=True)
        subtitle = dlg.winfo_children()[0].winfo_children()[1].cget("text")
        assert "остановлен" in subtitle

    def test_copy_puts_the_list_on_the_clipboard(self, dialog, gui_root):
        dlg = dialog([contact(1, "Наталья", "Шипова", "NDShe")], target_name="Цель")
        text = dlg._copy()
        gui_root.update()
        assert "Наталья Шипова" in text
        assert gui_root.clipboard_get() == text
        assert dlg.copy_btn.cget("text") == "Скопировано"

    def test_row_click_opens_the_link(self, dialog, monkeypatch):
        opened = []
        monkeypatch.setattr(admins_dialog, "open_telegram_link", lambda u: opened.append(u) or True)
        dlg = dialog([contact(1, username="NDShe")], target_name="Цель")
        self._rows(dlg)[0]._open()
        assert opened == ["https://t.me/NDShe"]

    def test_row_reports_a_failed_open(self, dialog, monkeypatch):
        monkeypatch.setattr(admins_dialog, "open_telegram_link", lambda u: False)
        dlg = dialog([contact(1, username="NDShe")], target_name="Цель")
        row = self._rows(dlg)[0]
        row._open()
        assert row.write_btn.cget("text") == "Не открылось"
