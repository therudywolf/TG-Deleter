
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

"""Общие фикстуры: изоляция от рабочей папки и одно окно Tk на прогон."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GUI_SESSION = "test_session"


@pytest.fixture(autouse=True, scope="session")
def isolated_project_root(tmp_path_factory):
    """
    Никаких конфигов, сессий и кэшей в репозитории.

    core.get_project_root — единая точка, через которую считаются пути к
    api_config.json, config.json и файлам сессий, поэтому подменяем её на
    временную папку сразу для всего прогона.
    """
    import core

    workdir = str(tmp_path_factory.mktemp("tg_deleter_home"))
    original = core.get_project_root
    core.get_project_root = lambda: workdir
    core._api_config_cache = None
    core._app_config_cache = None

    patched_modules = []
    for name in ("ui.cache_export", "ui.app", "ui.worker"):
        try:
            module = __import__(name, fromlist=["_PROJECT_ROOT"])
        except Exception:
            continue
        if hasattr(module, "_PROJECT_ROOT"):
            patched_modules.append((module, module._PROJECT_ROOT))
            module._PROJECT_ROOT = workdir
    try:
        yield workdir
    finally:
        core.get_project_root = original
        core._api_config_cache = None
        core._app_config_cache = None
        for module, value in patched_modules:
            module._PROJECT_ROOT = value


class FakeMessagebox:
    """Диалоги не открываем: тесту нужен только факт вызова и ответ «да»."""

    def __init__(self, answer=True):
        self.calls = []
        self.answer = answer

    def showinfo(self, *a, **k):
        self.calls.append(("info",) + a)

    def showwarning(self, *a, **k):
        self.calls.append(("warning",) + a)

    def showerror(self, *a, **k):
        self.calls.append(("error",) + a)

    def askyesno(self, *a, **k):
        self.calls.append(("ask",) + a)
        return self.answer

    def kinds(self):
        return [c[0] for c in self.calls]


@pytest.fixture(scope="session")
def gui_app(isolated_project_root):
    """
    Единственное окно Tk на весь прогон.

    Пересоздавать интерпретатор Tcl между тестами ненадёжно: после destroy
    следующий ctk.CTk() падает, поэтому все GUI-тесты живут в одном окне.
    Воркер не запускаем — Telegram в тестах не нужен.
    """
    pytest.importorskip("customtkinter", reason="GUI-тесты требуют customtkinter")
    import ui.app as uiapp
    import ui.members_frame as members_frame

    saved = {
        "start_worker": uiapp.App._start_worker,
        "session": uiapp.get_current_session,
        "box_app": uiapp.messagebox,
        "box_frame": members_frame.messagebox,
    }
    uiapp.App._start_worker = lambda self: None
    uiapp.get_current_session = lambda: GUI_SESSION
    box = FakeMessagebox()
    uiapp.messagebox = box
    members_frame.messagebox = box

    try:
        application = uiapp.App()
    except Exception as exc:  # pragma: no cover - зависит от окружения
        uiapp.App._start_worker = saved["start_worker"]
        uiapp.get_current_session = saved["session"]
        uiapp.messagebox = saved["box_app"]
        members_frame.messagebox = saved["box_frame"]
        pytest.skip("Нет доступного дисплея для Tk: %s" % exc)
    application.box = box
    application.root.geometry("1100x700")
    application._show_members()
    application.root.update()
    try:
        yield application
    finally:
        application._closing = True
        application.root.destroy()
        uiapp.App._start_worker = saved["start_worker"]
        uiapp.get_current_session = saved["session"]
        uiapp.messagebox = saved["box_app"]
        members_frame.messagebox = saved["box_frame"]


@pytest.fixture(scope="session")
def gui_root(gui_app):
    """Корневое окно для отдельно собираемых виджетов."""
    return gui_app.root
