
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
GUI-тесты экрана «Участники».

Требуют customtkinter и рабочий дисплей, поэтому в headless-CI пропускаются.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ctk = pytest.importorskip("customtkinter", reason="GUI-тесты требуют customtkinter")

from core import MemberActionResult, MemberChat, Place, TargetUser, _fill_member_note  # noqa: E402
from ui.members_frame import (  # noqa: E402
    MODE_ADD,
    MODE_REMOVE,
    OK_COLOR,
    FAIL_COLOR,
    SCOPE_DEEP,
    MemberRow,
    MembersFrame,
    _shorten,
)
from ui.theme import TEXT_MUTED  # noqa: E402
from tests.conftest import FakeMessagebox  # noqa: E402


class Recorder:
    """Ловит вызовы колбэков экрана вместо похода в воркер."""

    def __init__(self):
        self.resolve = []
        self.find = []
        self.load = []
        self.remove = []
        self.add = []


def make_chat(chat_id, title, type_str="Супергруппа", my="owner", target="member", can_manage=True):
    return _fill_member_note(
        MemberChat(
            chat_id=chat_id, title=title, type_str=type_str,
            my_status=my, target_status=target, can_manage=can_manage,
        )
    )


TARGET = TargetUser(user_id=777, username="spammer", first_name="Иван", last_name="Петров")


@pytest.fixture
def frame(gui_root, monkeypatch):
    """Свежий экран «Участники» на каждый тест."""
    import ui.members_frame as members_frame
    from ui.queues import scan_paused, scan_stop_requested

    scan_paused.clear()
    scan_stop_requested.clear()
    box = FakeMessagebox()
    monkeypatch.setattr(members_frame, "messagebox", box)
    rec = Recorder()
    f = MembersFrame(
        gui_root,
        on_resolve_user=lambda q: rec.resolve.append(q),
        on_find_chats=lambda *a: rec.find.append(a),
        on_load_chats=lambda *a: rec.load.append(a),
        on_remove=lambda *a: rec.remove.append(a),
        on_add=lambda *a: rec.add.append(a),
    )
    f.pack(fill="both", expand=True)
    gui_root.update()
    f.rec = rec
    f.box = box
    try:
        yield f
    finally:
        # Отложенный перерисовщик поиска не должен стрелять по уничтоженному экрану.
        if f._search_job is not None:
            try:
                f.after_cancel(f._search_job)
            except Exception:
                pass
        scan_paused.clear()
        scan_stop_requested.clear()
        f.destroy()


class TestShorten:
    """Tests for _shorten."""

    def test_short_text_is_untouched(self):
        assert _shorten("можно удалить", 30) == "можно удалить"

    def test_long_text_gets_ellipsis(self):
        result = _shorten("a" * 50, 30)
        assert len(result) == 30
        assert result.endswith("…")

    def test_none_becomes_empty(self):
        assert _shorten(None, 10) == ""

    def test_non_string_is_coerced(self):
        assert _shorten(-1001234, 30) == "-1001234"


class TestMemberRow:
    """Tests for MemberRow."""

    def test_checkbox_reports_state(self, frame):
        seen = []
        row = MemberRow(
            frame.scroll, chat_id=-1, title="Чат", type_str="Группа",
            status="можно удалить", selected=True, on_check=lambda cid, v: seen.append((cid, v)),
        )
        row.pack()
        frame.update()
        assert row.is_checked is True
        row.set_checked(False)
        assert row.is_checked is False


class TestUserResolution:
    """Поиск человека и состояние кнопок вокруг него."""

    def test_starts_locked_until_a_user_is_found(self, frame):
        assert frame.target is None
        assert frame.find_chats_btn.cget("state") == "disabled"
        assert frame.remove_btn.cget("state") == "disabled"
        assert frame.add_btn.cget("state") == "disabled"

    def test_empty_query_does_not_reach_the_worker(self, frame):
        frame.user_var.set("   ")
        frame._resolve_user()
        assert frame.rec.resolve == []
        assert frame.box.kinds() == ["info"]

    def test_query_is_passed_through(self, frame):
        frame.user_var.set(" @spammer ")
        frame._resolve_user()
        assert frame.rec.resolve == ["@spammer"]

    def test_found_user_unlocks_search(self, frame):
        frame.set_user(TARGET)
        assert frame.target is TARGET
        assert frame.find_chats_btn.cget("state") == "normal"
        assert TARGET.summary in frame.user_label.cget("text")

    def test_error_clears_the_user(self, frame):
        frame.set_user(TARGET)
        frame.set_user_error("Такого @username не существует")
        assert frame.target is None
        assert frame.find_chats_btn.cget("state") == "disabled"
        assert frame.user_label.cget("text_color") == FAIL_COLOR

    def test_new_user_drops_previous_findings(self, frame):
        frame.set_user(TARGET)
        frame.add_found_chat(make_chat(-1001, "Чат"))
        assert frame._items[MODE_REMOVE]
        frame.set_user(TargetUser(user_id=888, username="other", first_name="Другой"))
        assert frame._items[MODE_REMOVE] == []
        assert frame._selected[MODE_REMOVE] == set()


class TestFoundChats:
    """Список найденных чатов и автоотметка."""

    def test_only_manageable_chats_are_ticked(self, frame):
        frame.set_user(TARGET)
        frame.add_found_chat(make_chat(-1001, "Мой чат"))
        frame.add_found_chat(make_chat(-1002, "Чужой чат", my="member", can_manage=False))
        frame.update()
        assert frame._selected[MODE_REMOVE] == {-1001}
        assert frame._rendered_count() == 2

    def test_finish_reports_how_many_are_actionable(self, frame):
        frame.set_user(TARGET)
        chats = [make_chat(-1001, "Мой"), make_chat(-1002, "Чужой", my="member", can_manage=False)]
        frame.finish_find_chats(chats, stopped=False)
        frame.update()
        text = frame.status_label.cget("text")
        assert "Чатов: 2" in text and "удалить можно из 1" in text
        assert frame._selected[MODE_REMOVE] == {-1001}

    def test_empty_result_says_so(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([], stopped=False)
        assert "не нашлось" in frame.status_label.cget("text")

    def test_stopped_search_is_labelled(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Мой")], stopped=True)
        assert frame.status_label.cget("text").startswith("Поиск остановлен.")


class TestRowStatus:
    """Цвет и текст колонки «Статус»."""

    def test_actionable_row_keeps_default_color(self, frame):
        status, color, detail = frame._row_status(make_chat(-1, "Чат"))
        assert status == "можно удалить"
        assert color is None
        assert "Он: участник" in detail and "Вы владелец" in detail

    def test_blocked_row_is_muted_not_red(self, frame):
        status, color, _ = frame._row_status(make_chat(-1, "Чат", my="member", can_manage=False))
        assert status == "вы не админ"
        assert color == TEXT_MUTED

    def test_operation_success_is_green(self, frame):
        chat = make_chat(-1, "Чат")
        frame._results[-1] = MemberActionResult(-1, "Чат", True, "Удалён и забанен")
        status, color, _ = frame._row_status(chat)
        assert status == "Удалён и забанен"
        assert color == OK_COLOR

    def test_operation_failure_is_red(self, frame):
        chat = make_chat(-1, "Чат")
        frame._results[-1] = MemberActionResult(-1, "Чат", False, "Нужны права администратора")
        _, color, _ = frame._row_status(chat)
        assert color == FAIL_COLOR

    def test_plain_place_has_no_status(self, frame):
        status, color, detail = frame._row_status(Place(chat_id=-1, title="Чат", type_str="Канал"))
        assert (status, color, detail) == ("", None, "")


class TestFiltering:
    """Раздел и поиск по названию."""

    def _fill(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([
            make_chat(-1001, "Рабочий чат", "Супергруппа"),
            make_chat(-1002, "Новости компании", "Канал"),
            make_chat(-1003, "Старая группа", "Группа"),
        ], stopped=False)
        frame.update()

    def test_section_channels(self, frame):
        self._fill(frame)
        frame.section_var.set("Каналы")
        frame._apply_filter()
        frame.update()
        assert frame._rendered_count() == 1

    def test_section_groups_includes_supergroups(self, frame):
        self._fill(frame)
        frame.section_var.set("Группы")
        frame._apply_filter()
        frame.update()
        assert frame._rendered_count() == 2

    def test_search_is_case_insensitive(self, frame):
        self._fill(frame)
        frame.search_var.set("НОВОСТИ")
        frame._apply_filter()
        frame.update()
        assert frame._rendered_count() == 1

    def test_filter_does_not_drop_selection(self, frame):
        self._fill(frame)
        frame.search_var.set("новости")
        frame._apply_filter()
        frame.update()
        assert frame._selected[MODE_REMOVE] == {-1001, -1002, -1003}

    def test_select_visible_only_touches_shown_rows(self, frame):
        self._fill(frame)
        frame._set_visible_checks(False)
        frame.search_var.set("новости")
        frame._apply_filter()
        frame.update()
        frame._set_visible_checks(True)
        assert frame._selected[MODE_REMOVE] == {-1002}


class TestModes:
    """Переключение между удалением и добавлением."""

    def test_each_mode_keeps_its_own_selection(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Для удаления")], stopped=False)
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        frame.finish_load_chats([Place(chat_id=-2001, title="Для добавления", type_str="Канал")], stopped=False)
        frame._set_visible_checks(True)
        frame.update()
        assert frame._selected[MODE_ADD] == {-2001}
        frame.mode_switch.set(MODE_REMOVE)
        frame._on_mode_change(MODE_REMOVE)
        assert frame._selected[MODE_REMOVE] == {-1001}
        assert frame._rendered_count() == 1

    def test_add_mode_loads_chats(self, frame):
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        frame._load_chats()
        assert frame.rec.load == [(True, True)]

    def test_add_mode_button_order_puts_primary_last(self, frame):
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        packed = [w for w in frame.actions.pack_slaves()]
        assert frame.find_chats_btn not in packed and frame.remove_btn not in packed
        assert frame.load_chats_btn in packed and frame.add_btn in packed


class TestOperations:
    """Запуск операций и разбор результата."""

    def test_find_chats_passes_quick_scope(self, frame):
        frame.set_user(TARGET)
        frame._find_chats()
        assert frame.rec.find == [(777, False, True, True)]

    def test_deep_scope_asks_first(self, frame):
        frame.set_user(TARGET)
        frame.scope_var.set(SCOPE_DEEP)
        frame._find_chats()
        assert frame.box.kinds() == ["ask"]
        assert frame.rec.find == [(777, True, True, True)]

    def test_declined_deep_scope_does_nothing(self, frame):
        frame.box.answer = False
        frame.set_user(TARGET)
        frame.scope_var.set(SCOPE_DEEP)
        frame._find_chats()
        assert frame.rec.find == []

    def test_remove_sends_pairs_and_ban_flag(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Мой чат")], stopped=False)
        frame._remove_selected()
        assert frame.rec.remove == [(777, [(-1001, "Мой чат")], True)]

    def test_remove_without_ban(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Мой чат")], stopped=False)
        frame.ban_var.set(False)
        frame._remove_selected()
        assert frame.rec.remove[0][2] is False

    def test_remove_needs_confirmation(self, frame):
        frame.box.answer = False
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Мой чат")], stopped=False)
        frame._remove_selected()
        assert frame.rec.remove == []
        assert frame.box.kinds() == ["ask"]

    def test_remove_with_nothing_ticked_is_refused(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Чужой", my="member", can_manage=False)], stopped=False)
        frame._remove_selected()
        assert frame.rec.remove == []
        assert frame.box.kinds() == ["info"]

    def test_add_sends_pairs(self, frame):
        frame.set_user(TARGET)
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        frame.finish_load_chats([Place(chat_id=-2001, title="Канал", type_str="Канал")], stopped=False)
        frame._set_visible_checks(True)
        frame._add_selected()
        assert frame.rec.add == [(777, [(-2001, "Канал")])]

    def test_progress_updates_bar_and_status(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Мой чат")], stopped=False)
        frame.update_action_progress("remove", 1, 2, MemberActionResult(-1001, "Мой чат", True, "Удалён и забанен"))
        frame.update()
        assert frame.action_progress.get() == pytest.approx(0.5)
        assert "1/2" in frame.status_label.cget("text")

    def test_successful_removals_leave_the_list(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Ушёл"), make_chat(-1002, "Остался")], stopped=False)
        frame.finish_action("remove", [
            MemberActionResult(-1001, "Ушёл", True, "Удалён и забанен"),
            MemberActionResult(-1002, "Остался", False, "Нужны права администратора"),
        ], stopped=False)
        frame.update()
        assert [c.chat_id for c in frame._items[MODE_REMOVE]] == [-1002]
        # Неудачный чат остаётся отмеченным: права можно поправить и повторить.
        assert frame._selected[MODE_REMOVE] == {-1002}
        assert "Удалено: 1 из 2" in frame.status_label.cget("text")

    def test_failed_chats_are_listed_in_the_report(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1002, "Остался")], stopped=False)
        frame.finish_action("remove", [
            MemberActionResult(-1002, "Остался", False, "Нужны права администратора"),
        ], stopped=False)
        report = frame.box.calls[-1]
        assert report[0] == "info"
        assert "Не получилось (1)" in report[2] and "Остался" in report[2]

    def test_added_chats_only_lose_their_tick(self, frame):
        frame.set_user(TARGET)
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        frame.finish_load_chats([Place(chat_id=-2001, title="Канал", type_str="Канал")], stopped=False)
        frame._set_visible_checks(True)
        frame.finish_action("add", [MemberActionResult(-2001, "Канал", True, "Добавлен")], stopped=False)
        assert frame._selected[MODE_ADD] == set()
        assert len(frame._items[MODE_ADD]) == 1

    def test_empty_result_keeps_the_error_text(self, frame):
        frame.set_busy(True, "Удаляю")
        frame.status_label.configure(text="Ошибка: Нет подключения к Telegram.")
        frame.finish_action("remove", [], stopped=False)
        assert frame.status_label.cget("text") == "Ошибка: Нет подключения к Telegram."
        assert frame.box.kinds() == []


class TestBusyState:
    """Пауза, стоп и блокировка кнопок во время работы."""

    def test_busy_locks_actions_and_frees_controls(self, frame):
        frame.set_user(TARGET)
        frame.set_busy(True, "Ищу чаты")
        assert frame.find_chats_btn.cget("state") == "disabled"
        assert frame.find_user_btn.cget("state") == "disabled"
        assert frame.pause_btn.cget("state") == "normal"
        assert frame.stop_btn.cget("state") == "normal"

    def test_pause_toggles_the_shared_event(self, frame):
        from ui.queues import scan_paused

        frame.set_busy(True)
        frame._toggle_pause()
        assert scan_paused.is_set()
        assert frame.pause_btn.cget("text") == "Продолжить"
        frame._toggle_pause()
        assert not scan_paused.is_set()
        frame.set_busy(False)

    def test_stop_sets_the_shared_event(self, frame):
        from ui.queues import scan_paused, scan_stop_requested

        scan_stop_requested.clear()
        frame.set_busy(True)
        frame._stop()
        assert scan_stop_requested.is_set()
        assert not scan_paused.is_set()
        scan_stop_requested.clear()
        frame.set_busy(False)

    def test_idle_frame_ignores_pause_and_stop(self, frame):
        from ui.queues import scan_paused, scan_stop_requested

        scan_paused.clear()
        scan_stop_requested.clear()
        frame._toggle_pause()
        frame._stop()
        assert not scan_paused.is_set()
        assert not scan_stop_requested.is_set()

    def test_operations_refuse_to_start_while_busy(self, frame):
        frame.set_user(TARGET)
        frame.set_busy(True)
        frame._find_chats()
        frame._load_chats()
        frame._resolve_user()
        assert frame.rec.find == [] and frame.rec.load == [] and frame.rec.resolve == []
        frame.set_busy(False)


class TestReset:
    """Сброс при смене аккаунта."""

    def test_reset_clears_everything(self, frame):
        frame.set_user(TARGET)
        frame.finish_find_chats([make_chat(-1001, "Чат")], stopped=False)
        frame.mode_switch.set(MODE_ADD)
        frame._on_mode_change(MODE_ADD)
        frame.finish_load_chats([Place(chat_id=-2001, title="Канал", type_str="Канал")], stopped=False)
        frame.reset()
        frame.update()
        assert frame.target is None
        assert frame._items == {MODE_REMOVE: [], MODE_ADD: []}
        assert frame._selected == {MODE_REMOVE: set(), MODE_ADD: set()}
        assert frame._rendered_count() == 0
        assert frame.find_chats_btn.cget("state") == "disabled"
