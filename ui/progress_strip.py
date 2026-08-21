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
Полоса хода операции: этап, счётчик, время и прогресс в одном месте.

Пока total неизвестен, полоса бежит сама; как только он появился — становится
обычным прогрессом с процентами и оценкой остатка.
"""
import time

import customtkinter as ctk

from ui.theme import PAD_SM, RADIUS, BORDER, PANEL_BG, TEXT_MUTED, font

DETAIL_MAX = 46


def _shorten(text, limit=DETAIL_MAX):
    text = str(text or "")
    return (text[: limit - 1] + "…") if len(text) > limit else text


def format_duration(seconds) -> str:
    """Секунды в «мм:сс» или «чч:мм:сс»."""
    seconds = max(0, int(seconds or 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def estimate_remaining(done, total, elapsed):
    """Сколько ещё ждать, по средней скорости. None, пока считать не из чего."""
    if not total or not done or done <= 0 or elapsed <= 0 or done >= total:
        return None
    return elapsed / done * (total - done)


class ProgressStrip(ctk.CTkFrame):
    """Единая полоса хода для всех длинных операций экрана."""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=RADIUS,
                         border_width=1, border_color=BORDER, **kw)
        self._stage = ""
        self._done = 0
        self._total = None
        self._detail = ""
        self._started_at = None
        self._tick_job = None
        self._running = False

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="x", padx=PAD_SM, pady=(PAD_SM, 4))
        self.stage_label = ctk.CTkLabel(inner, text="", anchor="w", font=font(13, "bold"))
        self.stage_label.pack(side="left")
        self.timer_label = ctk.CTkLabel(inner, text="", anchor="e", font=font(12), text_color=TEXT_MUTED)
        self.timer_label.pack(side="right")
        self.counter_label = ctk.CTkLabel(inner, text="", anchor="e", font=font(12), text_color=TEXT_MUTED)
        self.counter_label.pack(side="right", padx=(0, PAD_SM))

        self.bar = ctk.CTkProgressBar(self, height=8)
        self.bar.pack(fill="x", padx=PAD_SM)
        self.detail_label = ctk.CTkLabel(self, text="", anchor="w", font=font(12), text_color=TEXT_MUTED)
        self.detail_label.pack(fill="x", padx=PAD_SM, pady=(2, PAD_SM))

    # ------------------------------------------------------------------
    # Управление
    # ------------------------------------------------------------------

    def start(self, stage: str, total=None, now=None):
        """Начать показ. total=None — пока считаем неизвестным."""
        self._stage = stage or "Выполняется"
        self._done = 0
        self._total = int(total) if total else None
        self._detail = ""
        self._started_at = now if now is not None else time.monotonic()
        self._running = True
        self._apply_mode()
        self._render()
        self._schedule_tick()

    def update_progress(self, done=None, total=None, detail=None, stage=None):
        """Обновить счётчик, общий объём и подпись. Любой аргумент можно опустить."""
        if stage is not None:
            self._stage = stage
        if total is not None:
            self._total = int(total) if total else None
            self._apply_mode()
        if done is not None:
            self._done = int(done)
        if detail is not None:
            self._detail = detail
        self._render()

    def finish(self, text: str = "", ok: bool = True):
        """Операция закончилась: полоса замирает на итоге."""
        self._running = False
        self._cancel_tick()
        self.bar.configure(mode="determinate")
        self.bar.stop()
        self.bar.set(1.0 if ok else self._ratio())
        self.stage_label.configure(text=text or "Готово")
        self.counter_label.configure(text=self._counter_text())
        self.detail_label.configure(text="")

    def hide(self):
        self._running = False
        self._cancel_tick()
        self.bar.stop()
        self.pack_forget()

    def destroy(self):
        self._cancel_tick()
        super().destroy()

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def _apply_mode(self):
        if self._total:
            self.bar.stop()
            self.bar.configure(mode="determinate")
            self.bar.set(self._ratio())
        else:
            self.bar.configure(mode="indeterminate")
            self.bar.start()

    def _ratio(self):
        if not self._total:
            return 0.0
        return max(0.0, min(1.0, self._done / self._total))

    def _counter_text(self):
        if self._total:
            return "%s / %s" % (self._done, self._total)
        return str(self._done) if self._done else ""

    def elapsed(self, now=None):
        if self._started_at is None:
            return 0.0
        return (now if now is not None else time.monotonic()) - self._started_at

    def timer_text(self, now=None):
        """«0:07» или «0:07 · осталось ~0:22», когда есть из чего оценить."""
        elapsed = self.elapsed(now)
        text = format_duration(elapsed)
        left = estimate_remaining(self._done, self._total, elapsed)
        if left is not None and left >= 1:
            text += " · осталось ~%s" % format_duration(left)
        return text

    def _render(self, now=None):
        self.stage_label.configure(text=self._stage)
        self.counter_label.configure(text=self._counter_text())
        self.timer_label.configure(text=self.timer_text(now))
        self.detail_label.configure(text=_shorten(self._detail))
        if self._total:
            self.bar.set(self._ratio())

    def _schedule_tick(self):
        self._cancel_tick()
        if not self._running:
            return
        try:
            self._tick_job = self.after(1000, self._tick)
        except Exception:
            self._tick_job = None

    def _tick(self):
        self._tick_job = None
        if not self._running or not self.winfo_exists():
            return
        self.timer_label.configure(text=self.timer_text())
        self._schedule_tick()

    def _cancel_tick(self):
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
