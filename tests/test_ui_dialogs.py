
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
Тесты подтверждения операции и полосы хода.

Требуют customtkinter и рабочий дисплей, поэтому в headless-CI пропускаются.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("customtkinter", reason="GUI-тесты требуют customtkinter")

from ui.confirm_dialog import ConfirmDialog  # noqa: E402
from ui.progress_strip import ProgressStrip, estimate_remaining, format_duration  # noqa: E402


@pytest.fixture
def dialog(gui_root):
    made = []

    def make(**kw):
        kw.setdefault("title", "Проверка")
        kw.setdefault("summary", "Точно?")
        dlg = ConfirmDialog(gui_root, **kw)
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


@pytest.fixture
def strip(gui_root):
    widget = ProgressStrip(gui_root)
    widget.pack(fill="x")
    gui_root.update()
    try:
        yield widget
    finally:
        widget.destroy()
        gui_root.update()


class TestConfirmDialog:
    """Подтверждение должно показывать, что произойдёт, и не проскакивать случайно."""

    def test_defaults_to_no(self, dialog):
        dlg = dialog()
        assert dlg.result is False

    def test_confirm_sets_the_result(self, dialog):
        dlg = dialog()
        dlg._confirm()
        assert dlg.result is True

    def test_cancel_keeps_no(self, dialog):
        dlg = dialog()
        dlg._cancel()
        assert dlg.result is False

    def test_without_ack_the_button_is_live(self, dialog):
        dlg = dialog()
        assert dlg.confirm_btn.cget("state") == "normal"
        assert dlg.ack_check is None

    def test_ack_gates_the_button(self, dialog):
        dlg = dialog(ack_text="Понимаю последствия")
        assert dlg.confirm_btn.cget("state") == "disabled"
        dlg.ack_var.set(True)
        dlg._sync()
        assert dlg.confirm_btn.cget("state") == "normal"

    def test_confirm_is_ignored_until_acknowledged(self, dialog):
        dlg = dialog(ack_text="Понимаю последствия")
        dlg._confirm()
        assert dlg.result is False
        dlg.ack_var.set(True)
        dlg._confirm()
        assert dlg.result is True

    def test_items_are_listed(self, dialog):
        dlg = dialog(items=["Первый", "Второй", "Третий"])
        texts = [w.cget("text") for w in dlg.scroll.winfo_children()]
        assert texts == ["• Первый", "• Второй", "• Третий"]

    def test_long_lists_are_truncated_with_a_tail(self, dialog):
        import ui.confirm_dialog as module

        dlg = dialog(items=["Чат %s" % i for i in range(module.ITEMS_SHOWN + 5)])
        texts = [w.cget("text") for w in dlg.scroll.winfo_children()]
        assert len(texts) == module.ITEMS_SHOWN + 1
        assert texts[-1] == "…и ещё 5"

    def test_no_items_no_list(self, dialog):
        assert dialog().scroll is None


class TestDurationHelpers:
    """Форматирование времени и оценка остатка."""

    @pytest.mark.parametrize("seconds,expected", [
        (0, "0:00"), (7, "0:07"), (65, "1:05"), (600, "10:00"), (3661, "1:01:01"),
    ])
    def test_format(self, seconds, expected):
        assert format_duration(seconds) == expected

    def test_negative_and_none_are_zero(self):
        assert format_duration(-5) == "0:00"
        assert format_duration(None) == "0:00"

    def test_estimate_is_linear(self):
        # 10 из 40 за 10 секунд — на остальные 30 нужно ещё 30.
        assert estimate_remaining(10, 40, 10) == pytest.approx(30)

    def test_estimate_needs_something_to_go_on(self):
        assert estimate_remaining(0, 40, 5) is None
        assert estimate_remaining(10, None, 5) is None
        assert estimate_remaining(10, 40, 0) is None
        assert estimate_remaining(40, 40, 10) is None


class TestProgressStrip:
    """Полоса хода: этап, счётчик, время."""

    def test_unknown_total_runs_indeterminate(self, strip):
        strip.start("Ищу чаты")
        assert strip.bar.cget("mode") == "indeterminate"
        assert strip.stage_label.cget("text") == "Ищу чаты"
        assert strip.counter_label.cget("text") == ""

    def test_known_total_switches_to_a_real_bar(self, strip):
        strip.start("Удаляю", total=4)
        assert strip.bar.cget("mode") == "determinate"
        strip.update_progress(done=1)
        assert strip.bar.get() == pytest.approx(0.25)
        assert strip.counter_label.cget("text") == "1 / 4"

    def test_total_can_arrive_later(self, strip):
        strip.start("Ищу чаты")
        strip.update_progress(total=10, done=5)
        assert strip.bar.cget("mode") == "determinate"
        assert strip.bar.get() == pytest.approx(0.5)

    def test_stage_and_detail_update(self, strip):
        strip.start("Ищу чаты")
        strip.update_progress(stage="Проверяю права", detail="ДИТ. WAF - КППМ")
        assert strip.stage_label.cget("text") == "Проверяю права"
        assert "КППМ" in strip.detail_label.cget("text")

    def test_long_detail_is_shortened(self, strip):
        strip.start("Ищу")
        strip.update_progress(detail="ы" * 200)
        assert len(strip.detail_label.cget("text")) <= 46

    def test_timer_counts_from_the_start(self, strip):
        strip.start("Ищу чаты", now=100.0)
        assert strip.timer_text(now=107.0).startswith("0:07")

    def test_timer_adds_an_estimate_once_it_can(self, strip):
        strip.start("Удаляю", total=40, now=0.0)
        strip.update_progress(done=10)
        assert "осталось ~0:30" in strip.timer_text(now=10.0)

    def test_finish_fills_the_bar(self, strip):
        strip.start("Удаляю", total=4)
        strip.update_progress(done=2)
        strip.finish("Готово")
        assert strip.bar.get() == pytest.approx(1.0)
        assert strip.stage_label.cget("text") == "Готово"
        assert strip.is_running is False

    def test_finish_after_a_stop_keeps_the_real_ratio(self, strip):
        strip.start("Удаляю", total=4)
        strip.update_progress(done=1)
        strip.finish("Остановлено", ok=False)
        assert strip.bar.get() == pytest.approx(0.25)

    def test_hide_stops_the_ticker(self, strip):
        strip.start("Ищу чаты")
        strip.hide()
        assert strip.is_running is False
        assert strip._tick_job is None
