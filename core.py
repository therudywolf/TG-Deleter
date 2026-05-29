
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
Ядро TG Deleter: api_config.json (API и скан), config.json (аккаунты/сессия), Pyrogram-клиент.
"""
__version__ = "0.8.0-beta.1"

import os
import sys
import json
import logging
import asyncio
import math
import re
import html
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatType

log = logging.getLogger("tg_deleter")

# Дефолты для api_config.json (API Telegram + параметры скана)
_API_DEFAULTS = {
    "api_id": None,
    "api_hash": "",
    "scan_limit": None,
    "delay_sec": 0.2,
    "scan_delay_between_chats": 2.0,
    "chat_id_cli": None,
    "scan_include_groups": True,
    "scan_include_channels": True,
    "scan_include_private": True,
    "scan_depth_per_chat": 10,
    "export_parallel_chats": 2,
    "export_include_media": True,
    "export_message_limit": None,
}
# Дефолты для config.json (только приложение: сессии и аккаунты)
_APP_DEFAULTS = {
    "session_name": "session",
    "accounts": [],
    "current_session": None,
}
_api_config_cache = None
_app_config_cache = None
_config_lock = threading.Lock()
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")


class AppState:
    """Thread-safe container for current user identity and Pyrogram client."""

    def __init__(self):
        self._lock = threading.Lock()
        self.user_id: int | None = None
        self.username: str | None = None
        self.first_name: str | None = None
        self.last_name: str | None = None
        self.channel_ids: set[int] = set()
        self.client: Client | None = None

    def set_me(self, me_dict: dict | None) -> None:
        with self._lock:
            if me_dict:
                self.user_id = me_dict.get("id")
                self.username = (me_dict.get("username") or "").strip() or None
                self.first_name = (me_dict.get("first_name") or "").strip() or None
                self.last_name = (me_dict.get("last_name") or "").strip() or None

    def clear(self) -> None:
        with self._lock:
            self.user_id = None
            self.username = None
            self.first_name = None
            self.last_name = None
            self.channel_ids = set()
            self.client = None

    def set_channels(self, ids: set[int]) -> None:
        with self._lock:
            self.channel_ids = set(ids)

    def set_client(self, client: Client | None) -> None:
        with self._lock:
            self.client = client

    def get_client(self) -> Client | None:
        with self._lock:
            return self.client

    def get_user_id(self) -> int | None:
        with self._lock:
            return self.user_id


state = AppState()


def get_project_root() -> str:
    """Папка с конфигами и сессиями: при запуске из .exe — папка с exe, иначе — папка core.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _int(val, default=None):
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (TypeError, ValueError, OverflowError):
        return default

def _float(val, default=0.2):
    if val is None or val == "":
        return default
    try:
        result = float(val)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _api_config_path():
    return os.path.join(get_project_root(), "api_config.json")


def _app_config_path():
    return os.path.join(get_project_root(), "config.json")


def _migrate_to_api_config():
    """Один раз: старый config.json или .env → api_config.json."""
    api_path = _api_config_path()
    if os.path.isfile(api_path):
        return
    data = dict(_API_DEFAULTS)
    app_path = _app_config_path()
    if os.path.isfile(app_path):
        try:
            with open(app_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, dict):
                for k in _API_DEFAULTS:
                    if k in old and old[k] is not None:
                        data[k] = old[k]
        except Exception as e:
            log.debug("migrate api from config: %s", e)
    if not data.get("api_id") or not data.get("api_hash"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_id = _int(os.environ.get("API_ID"))
            api_hash = (os.environ.get("API_HASH") or "").strip()
            if api_id and api_hash:
                data["api_id"] = api_id
                data["api_hash"] = api_hash
                data["scan_limit"] = _int(os.environ.get("SCAN_LIMIT"))
                data["delay_sec"] = _float(os.environ.get("DELAY_SEC"), 0.2)
                data["scan_delay_between_chats"] = _float(os.environ.get("SCAN_DELAY_BETWEEN_CHATS"), 2.0)
                data["chat_id_cli"] = _int(os.environ.get("CHAT_ID_CLI"))
        except Exception:
            pass
    try:
        with open(api_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.debug("migrated to api_config.json")
        if os.path.isfile(app_path):
            try:
                with open(app_path, "r", encoding="utf-8") as f:
                    app_data = json.load(f)
                if isinstance(app_data, dict):
                    for k in _API_DEFAULTS:
                        app_data.pop(k, None)
                    with open(app_path, "w", encoding="utf-8") as f:
                        json.dump(app_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
    except Exception as e:
        log.warning("save api_config failed: %s", e)


def _migrate_app_config_from_legacy():
    """Один раз: accounts.json, current_account.json → config.json (только если в config нет accounts)."""
    app_path = _app_config_path()
    data = dict(_APP_DEFAULTS)
    if os.path.isfile(app_path):
        try:
            with open(app_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if k in _APP_DEFAULTS})
        except Exception:
            pass
    base = get_project_root()
    if not data.get("accounts"):
        accounts_path = os.path.join(base, "accounts.json")
        if os.path.isfile(accounts_path):
            try:
                with open(accounts_path, "r", encoding="utf-8") as f:
                    L = json.load(f)
                if isinstance(L, list) and L:
                    data["accounts"] = [str(x).strip() for x in L if str(x).strip()]
            except Exception:
                pass
    if not data.get("current_session"):
        current_path = os.path.join(base, "current_account.json")
        if os.path.isfile(current_path):
            try:
                with open(current_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                name = (d.get("session") or "").strip()
                if name:
                    data["current_session"] = name
            except Exception:
                pass
    try:
        with open(app_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("save app config failed: %s", e)


# ---------- API config (api_config.json) ----------

def load_api_config() -> dict:
    global _api_config_cache
    _migrate_to_api_config()
    path = _api_config_path()
    data = dict(_API_DEFAULTS)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if k in _API_DEFAULTS or k == "theme"})
        except Exception as e:
            log.warning("load_api_config failed: %s", e)
    with _config_lock:
        _api_config_cache = data
    return data


def save_api_config(data: dict) -> None:
    global _api_config_cache
    path = _api_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        with _config_lock:
            _api_config_cache = dict(data)
    except Exception as e:
        log.warning("save_api_config failed: %s", e)


def get_api_config() -> dict:
    global _api_config_cache
    with _config_lock:
        if _api_config_cache is not None:
            return dict(_api_config_cache)
    load_api_config()
    with _config_lock:
        return dict(_api_config_cache)


def get_api_config_readonly() -> MappingProxyType:
    """Read-only view, no copy overhead."""
    global _api_config_cache
    with _config_lock:
        if _api_config_cache is not None:
            return MappingProxyType(_api_config_cache)
    load_api_config()
    with _config_lock:
        return MappingProxyType(_api_config_cache)


def reset_api_config() -> None:
    save_api_config(dict(_API_DEFAULTS))


def get_api_id() -> int | None:
    return _int(get_api_config_readonly().get("api_id"))


def get_api_hash() -> str:
    return (get_api_config_readonly().get("api_hash") or "").strip()


def get_scan_limit() -> int | None:
    return _int(get_api_config_readonly().get("scan_limit"))


def get_delay_sec() -> float:
    return _float(get_api_config_readonly().get("delay_sec"), 0.2)


def get_scan_delay_between_chats() -> float:
    return _float(get_api_config_readonly().get("scan_delay_between_chats"), 2.0)


def get_chat_id_cli() -> int | None:
    return _int(get_api_config_readonly().get("chat_id_cli"))


def get_scan_include_groups() -> bool:
    v = get_api_config_readonly().get("scan_include_groups")
    return v if isinstance(v, bool) else True


def get_scan_include_channels() -> bool:
    v = get_api_config_readonly().get("scan_include_channels")
    return v if isinstance(v, bool) else True


def get_scan_include_private() -> bool:
    v = get_api_config_readonly().get("scan_include_private")
    return v if isinstance(v, bool) else True


def get_export_parallel_chats() -> int:
    return max(1, min(6, _int(get_api_config_readonly().get("export_parallel_chats"), 2)))


def get_export_include_media() -> bool:
    v = get_api_config_readonly().get("export_include_media")
    return v if isinstance(v, bool) else True


def get_export_message_limit() -> int | None:
    return _int(get_api_config_readonly().get("export_message_limit"))


# ---------- App config (config.json): session_name, accounts, current_session ----------

def load_config() -> dict:
    global _app_config_cache
    _migrate_app_config_from_legacy()
    path = _app_config_path()
    data = dict(_APP_DEFAULTS)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update({k: loaded[k] for k in _APP_DEFAULTS if k in loaded})
        except Exception as e:
            log.warning("load_config failed: %s", e)
    with _config_lock:
        _app_config_cache = data
    return data


def save_config(data: dict) -> None:
    global _app_config_cache
    path = _app_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        with _config_lock:
            _app_config_cache = dict(data)
    except Exception as e:
        log.warning("save_config failed: %s", e)


def get_config() -> dict:
    global _app_config_cache
    with _config_lock:
        if _app_config_cache is not None:
            return dict(_app_config_cache)
    load_config()
    with _config_lock:
        return dict(_app_config_cache)


def get_config_value(key: str):
    return get_config().get(key, _APP_DEFAULTS.get(key))


def set_config_value(key: str, value) -> None:
    c = get_config()
    c[key] = value
    save_config(c)


def reset_config() -> None:
    save_config(dict(_APP_DEFAULTS))

def set_my_channels(channel_ids: set[int]) -> None:
    """Сохранить ID каналов, где пользователь является admin/creator."""
    state.set_channels(channel_ids)
    log.debug("set_my_channels: %d каналов", len(channel_ids))


async def fetch_and_set_my_channels(client: Client) -> None:
    """Обходит диалоги один раз и собирает ID каналов где пользователь — admin или creator."""
    ids: set[int] = set()
    try:
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            if getattr(chat, "type", None) == ChatType.CHANNEL:
                if getattr(chat, "creator", False) or getattr(chat, "admin_rights", None) is not None:
                    ids.add(chat.id)
    except Exception as e:
        log.warning("fetch_and_set_my_channels failed: %s", e)
    set_my_channels(ids)

def _accounts_profiles_path():
    """Путь к файлу с профилями аккаунтов (display_name, username, avatar_path)."""
    return os.path.join(get_project_root(), "accounts_profiles.json")


def get_account_profile(session_name: str) -> dict:
    """Профиль для отображения: {"display_name": str, "username": str|None, "avatar_path": str|None}. Пустой dict если нет данных."""
    path = _accounts_profiles_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return dict(data.get(session_name, {}) or {})
    except Exception:
        return {}


def save_account_profile(session_name: str, profile: dict) -> None:
    """Сохранить профиль для сессии. profile: dict с ключами display_name, username, avatar_path."""
    path = _accounts_profiles_path()
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    data[session_name] = {
        "display_name": (profile.get("display_name") or "").strip() or "Без имени",
        "username": (profile.get("username") or "").strip() or None,
        "avatar_path": profile.get("avatar_path") or None,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
        log.debug("save_account_profile: %s", session_name)
    except Exception as e:
        log.warning("save_account_profile failed: %s", e)


def get_accounts_list() -> list[str]:
    """Список имён сессий из config.json. Может быть пустым."""
    acc = get_config_value("accounts")
    if isinstance(acc, list):
        return [name for x in acc if (name := normalize_session_name(str(x).strip()))]
    return []


def save_accounts_list(accounts: list[str]) -> None:
    """Сохранить список аккаунтов в config."""
    set_config_value("accounts", list(accounts))


def add_account(session_name: str) -> bool:
    """Добавить аккаунт (сессию) в список. Не дублирует."""
    name = normalize_session_name(session_name)
    if not name:
        return False
    accounts = get_accounts_list()
    if name in accounts:
        return True
    accounts.append(name)
    save_accounts_list(accounts)
    return True


def remove_account(session_name: str) -> bool:
    """Удалить аккаунт из списка. Файл сессии не удаляется."""
    name = normalize_session_name(session_name)
    if not name:
        return False
    accounts = get_accounts_list()
    if name not in accounts:
        return False
    accounts = [a for a in accounts if a != name]
    save_accounts_list(accounts)
    return True


def get_current_session() -> str | None:
    """Текущая выбранная сессия или первая из списка. None если аккаунтов нет."""
    name = get_config_value("current_session")
    accounts = get_accounts_list()
    if name and name.strip() in accounts:
        return name.strip()
    return accounts[0] if accounts else None


def get_cache_session_key() -> str:
    """Ключ сессии для имени файла кэша: текущая сессия или имя по умолчанию, если аккаунтов нет."""
    return get_current_session() or normalize_session_name(get_config_value("session_name")) or "session"


def set_current_session(session_name: str | None) -> None:
    """Сохранить выбранную сессию в config."""
    if session_name is None:
        set_config_value("current_session", None)
        return
    name = normalize_session_name(session_name)
    if not name:
        raise ValueError("Имя сессии: 2-64 символа, только буквы, цифры, _ и -.")
    set_config_value("current_session", name)


def normalize_session_name(session_name: str | None) -> str | None:
    """Return a safe Pyrogram session name or None if it can escape the app directory."""
    name = (session_name or "").strip()
    if not _SESSION_NAME_RE.fullmatch(name):
        return None
    return name


def create_client(session_name: str) -> Client:
    """Создать Pyrogram Client для указанной сессии."""
    session_name = normalize_session_name(session_name)
    if not session_name:
        raise ValueError("Имя сессии: 2-64 символа, только буквы, цифры, _ и -.")
    api_id = get_api_id()
    api_hash = get_api_hash()
    if not api_id or not api_hash:
        raise ValueError("Введите API ID и API Hash в настройках приложения.")
    return Client(session_name, api_id=api_id, api_hash=api_hash, workdir=get_project_root(), no_updates=True)


def set_app(client: Client | None) -> None:
    """Установить текущий клиент (вызывает воркер после подключения)."""
    state.set_client(client)


def get_app() -> Client | None:
    """Текущий активный клиент (None до подключения воркера)."""
    return state.get_client()


def clear_me() -> None:
    """Сбросить данные текущего пользователя перед переключением аккаунта."""
    state.clear()


def set_me_from_dict(me_dict: dict | None) -> None:
    """Обновить данные текущего пользователя из результата get_me (для check_if_mine)."""
    state.set_me(me_dict)
    log.debug("set_me_from_dict: user_id=%s username=%s", state.user_id, state.username)


@dataclass
class Place:
    """Место (чат/группа/канал) с списком своих сообщений."""
    chat_id: int
    title: str
    type_str: str
    messages: list = field(default_factory=list)  # [(message_id, preview, date_str), ...]


_EXPORT_MEDIA_TYPE_DEFAULTS = {
    "photos": True,
    "videos": True,
    "documents": True,
    "audio": True,
    "stickers": True,
    "other": True,
}


@dataclass
class ExportOptions:
    """Параметры потокового экспорта выбранных чатов."""
    output_dir: str
    chat_ids: list
    parallel_chats: int = 2
    include_media: bool = True
    media_types: dict | None = None
    message_limit: int | None = None
    export_format: str = "html_jsonl"


async def _sleep_responsive(seconds, pause_event=None, stop_event=None, step=0.2):
    """Сон, который реагирует на паузу и остановку."""
    end = time.monotonic() + max(0, float(seconds or 0))
    while time.monotonic() < end:
        if stop_event is not None and stop_event.is_set():
            return False
        if pause_event is not None and pause_event.is_set():
            ok = await _wait_if_paused(pause_event, stop_event)
            if not ok:
                return False
        await asyncio.sleep(min(step, max(0, end - time.monotonic())))
    return stop_event is None or not stop_event.is_set()


async def _wait_if_paused(pause_event=None, stop_event=None):
    """Ждать снятия паузы. Возвращает False, если во время паузы запросили остановку."""
    while pause_event is not None and pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return False
        await asyncio.sleep(0.2)
    return stop_event is None or not stop_event.is_set()


def _is_stopped(stop_event=None):
    return stop_event is not None and stop_event.is_set()


def _chat_title(chat) -> str:
    """Название чата для отображения. Безопасно при ошибках кодировки."""
    try:
        if getattr(chat, "title", None) and chat.title:
            s = str(chat.title)
            if s:
                return s
        if getattr(chat, "first_name", None) and chat.first_name:
            s = str(chat.first_name)
            if s:
                return s
        return str(chat.id)
    except (UnicodeDecodeError, UnicodeEncodeError, TypeError, ValueError):
        return f"Чат {getattr(chat, 'id', '?')}"


def _chat_type_str(chat) -> str:
    """Тип чата для отображения."""
    t = getattr(chat, "type", None)
    # В некоторых случаях pyrogram может вернуть строку вместо Enum.
    t_str = str(t).lower() if t is not None else ""
    if t == ChatType.PRIVATE or t_str == "private":
        return "Личный"
    if t == ChatType.BOT or t_str == "bot":
        return "Бот"
    if t == ChatType.GROUP or t_str == "group":
        return "Группа"
    if t == ChatType.SUPERGROUP or t_str == "supergroup" or t_str == "megagroup":
        return "Супергруппа"
    if t == ChatType.CHANNEL or t_str == "channel":
        return "Канал"
    return "Чат"


def _chat_type_key(chat) -> str:
    t = getattr(chat, "type", None)
    return str(t).lower() if t is not None else ""


def _is_private_chat_type(chat) -> bool:
    t = getattr(chat, "type", None)
    key = _chat_type_key(chat)
    return t in (ChatType.PRIVATE, ChatType.BOT) or key in ("private", "bot") or key.endswith(".private") or key.endswith(".bot")


def _is_group_chat_type(chat) -> bool:
    t = getattr(chat, "type", None)
    key = _chat_type_key(chat)
    return t in (ChatType.GROUP, ChatType.SUPERGROUP) or key in ("group", "supergroup", "megagroup") or key.endswith(".group") or key.endswith(".supergroup")


def _is_channel_chat_type(chat) -> bool:
    t = getattr(chat, "type", None)
    key = _chat_type_key(chat)
    return t == ChatType.CHANNEL or key == "channel" or key.endswith(".channel")


async def check_if_mine(message) -> bool:
    try:
        if getattr(message, "out", None) is True or getattr(message, "outgoing", None) is True:
            return True
        if message.from_user:
            uid = message.from_user.id
            my_uid = state.get_user_id()
            if my_uid is not None and uid == my_uid:
                return True
        return False
    except (UnicodeDecodeError, UnicodeEncodeError, TypeError, ValueError, AttributeError):
        return False


def make_preview(message, max_len: int = 50) -> str:
    """Текст или подпись, обрезка по длине. Безопасно при ошибках кодировки."""
    try:
        raw = getattr(message, "text", None) or getattr(message, "caption", None)
        if raw is None:
            return "[Медиа/Файл/Стикер]"
        if isinstance(raw, str):
            text = raw
        else:
            text = str(raw)
        if not text:
            return "[Медиа/Файл/Стикер]"
    except (UnicodeDecodeError, UnicodeEncodeError, TypeError, ValueError, AttributeError):
        return "[Медиа/Файл/Стикер]"
    return text[:max_len] + "..." if len(text) > max_len else text


def _message_date_str(message) -> str:
    """Дата сообщения для отображения."""
    d = getattr(message, "date", None)
    if d is None:
        return ""
    try:
        return d.strftime("%Y-%m-%d %H:%M")
    except (AttributeError, TypeError, ValueError):
        return ""


async def delete_message_ids(cid: int, message_ids, pause_event=None, stop_event=None, progress_callback=None) -> list[int]:
    """
    Удаляет сообщения в чате cid по списку ID батчами (до 100 за вызов).
    Возвращает список успешно удалённых message_id.
    """
    if not message_ids:
        return []
    log.debug("delete_message_ids: chat_id=%s count=%s", cid, len(message_ids))
    client = get_app()
    if not client:
        return []
    deleted_ids: list[int] = []
    total = len(message_ids)
    BATCH_SIZE = 100

    for batch_start in range(0, total, BATCH_SIZE):
        if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
            break
        batch = message_ids[batch_start:batch_start + BATCH_SIZE]
        batch_int = [int(mid) for mid in batch]
        batch_int = await _filter_owned_message_ids(client, cid, batch_int, pause_event, stop_event)
        if not batch_int:
            continue
        while True:
            try:
                await client.delete_messages(cid, batch_int)
                deleted_ids.extend(batch_int)
                if progress_callback:
                    try:
                        progress_callback(len(deleted_ids), total, cid)
                    except Exception:
                        pass
                if not await _sleep_responsive(get_delay_sec(), pause_event, stop_event):
                    break
                break
            except FloodWait as e:
                log.warning("FloodWait: waiting %s sec", e.value)
                if not await _sleep_responsive(e.value, pause_event, stop_event):
                    break
            except Exception:
                for mid in batch_int:
                    if _is_stopped(stop_event):
                        break
                    try:
                        await client.delete_messages(cid, mid)
                        deleted_ids.append(mid)
                        if not await _sleep_responsive(get_delay_sec(), pause_event, stop_event):
                            break
                    except FloodWait as e2:
                        await _sleep_responsive(e2.value, pause_event, stop_event)
                    except Exception:
                        pass
                    if progress_callback:
                        try:
                            progress_callback(len(deleted_ids), total, cid)
                        except Exception:
                            pass
                break

    log.debug("delete_message_ids done: chat_id=%s deleted=%s", cid, len(deleted_ids))
    return deleted_ids


async def _filter_owned_message_ids(client: Client, cid: int, message_ids: list[int], pause_event=None, stop_event=None) -> list[int]:
    """Fetch requested messages and keep only IDs still proven to belong to the current user."""
    owned: list[int] = []
    if not message_ids:
        return owned
    try:
        messages = await client.get_messages(cid, message_ids)
        if not isinstance(messages, list):
            messages = [messages]
    except FloodWait as e:
        log.warning("FloodWait ownership recheck: waiting %s sec", e.value)
        if not await _sleep_responsive(e.value, pause_event, stop_event):
            return owned
        try:
            messages = await client.get_messages(cid, message_ids)
            if not isinstance(messages, list):
                messages = [messages]
        except Exception as e2:
            log.warning("ownership recheck failed after FloodWait: %s", e2)
            return owned
    except Exception as e:
        log.warning("ownership recheck failed: %s", e)
        return owned
    for message in messages:
        if _is_stopped(stop_event):
            break
        if message and await check_if_mine(message):
            owned.append(int(message.id))
    skipped = len(message_ids) - len(owned)
    if skipped:
        log.warning("delete_message_ids skipped %s messages that failed ownership recheck", skipped)
    return owned


async def scan_chat(cid: int, pause_event=None, stop_event=None) -> list[tuple[int, str, str]]:
    """
    Сканирует один чат и возвращает список своих сообщений: [(message_id, preview, date_str), ...].
    """
    log.debug("scan_chat: chat_id=%s", cid)
    result = []
    scan_limit = get_scan_limit()
    kwargs = {"limit": scan_limit} if scan_limit else {}
    client = get_app()
    if not client:
        return result
    while True:
        try:
            async for message in client.get_chat_history(cid, **kwargs):
                if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
                    break
                if await check_if_mine(message):
                    preview = make_preview(message)
                    date_str = _message_date_str(message)
                    result.append((message.id, preview, date_str))
            break
        except FloodWait as e:
            log.warning("FloodWait scan_chat %s: ждём %s сек", cid, e.value)
            if not await _sleep_responsive(e.value, pause_event, stop_event):
                break
        except Exception as e:
            log.warning("scan_chat error %s: %s", cid, e)
            break
    log.debug("scan_chat done: chat_id=%s found=%s", cid, len(result))
    return result


async def scan_all_dialogs(
    include_groups: bool = True,
    include_channels: bool = True,
    include_private: bool = True,
    pause_event=None,
    stop_event=None,
    progress_callback=None,
    dialog_progress_callback=None,
    max_my_messages_per_chat: int | None = None,
) -> list[Place]:
    """
    Обходит все диалоги, в каждом ищет свои сообщения.
    progress_callback(place) — при нахождении места с сообщениями.
    dialog_progress_callback(n, title, count=None) — в начале диалога (без count) и после обработки (count=0 или число сообщений).
    max_my_messages_per_chat: если задано, в каждом чате собирать не более N своих и ограничивать объём истории (меньше FloodWait).
    stop_event: если передан и is_set(), скан прерывается, возвращается текущий places.
    """
    log.debug("scan_all_dialogs start (groups=%s channels=%s private=%s max_per_chat=%s)", include_groups, include_channels, include_private, max_my_messages_per_chat)
    places = []
    n = 0
    client = get_app()
    if not client:
        return places
    async for dialog in client.get_dialogs():
        if stop_event is not None and stop_event.is_set():
            log.debug("scan_all_dialogs: останов по stop_event")
            break

        chat = dialog.chat
        if _is_private_chat_type(chat) and not include_private:
            continue
        if _is_group_chat_type(chat) and not include_groups:
            continue
        if _is_channel_chat_type(chat) and not include_channels:
            continue

        if not await _wait_if_paused(pause_event, stop_event):
            log.debug("scan_all_dialogs: останов во время паузы")
            break

        n += 1
        title = _chat_title(chat)
        if dialog_progress_callback:
            try:
                dialog_progress_callback(n, title)
            except Exception:
                pass
        log.debug("scan_all_dialogs: диалог %s — %s", n, title[:50] if title else "?")

        cid = chat.id
        type_str = _chat_type_str(chat)
        # Ограничиваем объём истории на чат, чтобы снизить число GetHistory и FloodWait
        if max_my_messages_per_chat is not None:
            chat_limit = max(100, max_my_messages_per_chat * 15)
            kwargs = {"limit": chat_limit}
        else:
            kwargs = {"limit": get_scan_limit()} if get_scan_limit() else {}
        messages = []
        while True:
            try:
                async for message in client.get_chat_history(cid, **kwargs):
                    if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
                        break
                    try:
                        if await check_if_mine(message):
                            preview = make_preview(message)
                            date_str = _message_date_str(message)
                            messages.append((message.id, preview, date_str))
                            if max_my_messages_per_chat is not None and len(messages) >= max_my_messages_per_chat:
                                break
                    except Exception:
                        pass
                break
            except FloodWait as e:
                log.warning("FloodWait при скане «%s»: ждём %s сек", title[:30], e.value)
                if not await _sleep_responsive(e.value, pause_event, stop_event):
                    break
            except Exception as e:
                log.warning("Пропуск диалога %s: %s", title[:30], e)
                break
        if messages:
            place = Place(chat_id=cid, title=title, type_str=type_str, messages=messages)
            places.append(place)
            log.debug("scan_all_dialogs: найдено место %s — %s постов", title[:30], len(messages))
            if progress_callback:
                try:
                    progress_callback(place)
                except Exception:
                    pass
        if dialog_progress_callback:
            try:
                dialog_progress_callback(n, title, count=len(messages))
            except Exception:
                pass
        if get_scan_delay_between_chats() > 0:
            if not await _sleep_responsive(get_scan_delay_between_chats(), pause_event, stop_event):
                break
    log.debug("scan_all_dialogs done: всего мест %s", len(places))
    return places


async def list_export_dialogs(
    include_groups: bool = True,
    include_channels: bool = True,
    include_private: bool = True,
    pause_event=None,
    stop_event=None,
    progress_callback=None,
    dialog_progress_callback=None,
) -> list[Place]:
    """Быстро получить список диалогов для экспортера без обхода истории сообщений."""
    places = []
    n = 0
    client = get_app()
    if not client:
        return places
    async for dialog in client.get_dialogs():
        if _is_stopped(stop_event):
            break
        if not await _wait_if_paused(pause_event, stop_event):
            break
        chat = dialog.chat
        if _is_private_chat_type(chat) and not include_private:
            continue
        if _is_group_chat_type(chat) and not include_groups:
            continue
        if _is_channel_chat_type(chat) and not include_channels:
            continue
        place = Place(chat_id=chat.id, title=_chat_title(chat), type_str=_chat_type_str(chat), messages=[])
        places.append(place)
        n += 1
        if progress_callback:
            try:
                progress_callback(place)
            except Exception:
                pass
        if dialog_progress_callback:
            try:
                dialog_progress_callback(n, place.title)
            except Exception:
                pass
    return places


async def delete_all_my_in_chat_no_scan(cid: int, progress_callback=None, pause_event=None, stop_event=None) -> int:
    """
    Обходит историю чата cid и удаляет каждое своё сообщение по ходу (без предварительного списка).
    progress_callback(count) — вызывается каждые 10 удалённых сообщений.
    Возвращает количество удалённых.
    """
    log.debug("delete_all_my_in_chat_no_scan: chat_id=%s", cid)
    scan_limit = get_scan_limit()
    kwargs = {"limit": scan_limit} if scan_limit else {}
    count = 0
    client = get_app()
    if not client:
        return count
    while True:
        try:
            async for message in client.get_chat_history(cid, **kwargs):
                if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
                    break
                if not await check_if_mine(message):
                    continue
                while True:
                    if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
                        break
                    try:
                        await client.delete_messages(cid, message.id)
                        log.debug("Удалён пост (no_scan): chat_id=%s message_id=%s", cid, message.id)
                        count += 1
                        if progress_callback and count % 10 == 0:
                            try:
                                progress_callback(count)
                            except Exception:
                                pass
                        if not await _sleep_responsive(get_delay_sec(), pause_event, stop_event):
                            break
                        break
                    except FloodWait as e:
                        log.warning("FloodWait: ждём %s сек", e.value)
                        if not await _sleep_responsive(e.value, pause_event, stop_event):
                            break
                    except Exception as e:
                        log.exception("Ошибка удаления message_id=%s: %s", message.id, e)
                        break
            break
        except FloodWait as e:
            log.warning("FloodWait на чтении истории (no_scan): ждём %s сек", e.value)
            if not await _sleep_responsive(e.value, pause_event, stop_event):
                break
        except Exception as e:
            log.exception("Ошибка обхода истории (no_scan) chat_id=%s: %s", cid, e)
            break
    log.debug("delete_all_my_in_chat_no_scan done: chat_id=%s deleted=%s", cid, count)
    return count


_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

def _safe_filename(value, fallback="chat", max_len=80):
    """Безопасное имя папки/файла для Windows и Linux."""
    text = str(value or "").strip() or fallback
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    text = text[:max_len].rstrip(" .") or fallback
    if text.split(".")[0].upper() in _WINDOWS_RESERVED:
        text = "_" + text
    return text


def _message_sender_name(message):
    from_user = getattr(message, "from_user", None)
    if from_user:
        first = getattr(from_user, "first_name", None) or ""
        last = getattr(from_user, "last_name", None) or ""
        username = getattr(from_user, "username", None)
        name = f"{first} {last}".strip()
        if username:
            return f"{name} (@{username})" if name else f"@{username}"
        return name or str(getattr(from_user, "id", ""))
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat:
        return _chat_title(sender_chat)
    return ""


def _message_text(message):
    text = getattr(message, "text", None) or getattr(message, "caption", None)
    if text:
        return str(text)
    media = getattr(message, "media", None)
    if media:
        return f"[{getattr(media, 'value', media)}]"
    service = getattr(message, "service", None)
    if service:
        return f"[{getattr(service, 'value', service)}]"
    return ""


def _normalize_media_types(media_types):
    result = dict(_EXPORT_MEDIA_TYPE_DEFAULTS)
    if isinstance(media_types, dict):
        for key in result:
            if key in media_types:
                result[key] = bool(media_types[key])
    return result


def _message_media_kind(message):
    if getattr(message, "photo", None):
        return "photos"
    if getattr(message, "video", None) or getattr(message, "video_note", None):
        return "videos"
    if getattr(message, "document", None):
        return "documents"
    if getattr(message, "audio", None) or getattr(message, "voice", None):
        return "audio"
    if getattr(message, "sticker", None) or getattr(message, "animation", None):
        return "stickers"
    if getattr(message, "media", None):
        return "other"
    return None


def _should_export_media(message, media_types):
    media_kind = _message_media_kind(message)
    if not media_kind:
        return False
    return bool(media_types.get(media_kind, True))


async def _get_chat_history_count(client, chat_id, limit=None):
    count = None
    count_fn = getattr(client, "get_chat_history_count", None)
    if count_fn:
        try:
            count = await count_fn(chat_id)
            count = int(count) if count is not None else None
        except Exception as e:
            log.debug("get_chat_history_count skip for %s: %s", chat_id, e)
            count = None
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = None
        if limit is not None:
            return min(limit, count) if count is not None else limit
    return count


def _message_record(chat_id, message, media_rel_path=None, media_kind=None):
    date = getattr(message, "date", None)
    return {
        "id": getattr(message, "id", None),
        "chat_id": chat_id,
        "date": date.isoformat() if date else None,
        "sender": _message_sender_name(message),
        "text": _message_text(message),
        "media": media_rel_path,
        "media_type": media_kind,
        "outgoing": bool(getattr(message, "out", False) or getattr(message, "outgoing", False)),
    }


def _html_header(title):
    safe_title = html.escape(title or "Telegram export")
    return (
        "<!doctype html>\n<html lang=\"ru\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{safe_title}</title>\n"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#0e1621;color:#d7e3ee;margin:0;padding:24px;}"
        "main{max-width:920px;margin:0 auto;}"
        "h1{font-size:22px;margin:0 0 16px;}"
        ".msg{background:#182533;border:1px solid #26394d;border-radius:8px;padding:10px 12px;margin:8px 0;}"
        ".meta{color:#8aa2b7;font-size:12px;margin-bottom:6px;}"
        ".text{white-space:pre-wrap;line-height:1.45;}"
        "a{color:#2aabee;}"
        "</style>\n</head>\n<body><main>\n"
        f"<h1>{safe_title}</h1>\n"
    )


def _html_message(record):
    date = html.escape(record.get("date") or "")
    sender = html.escape(record.get("sender") or "")
    text = html.escape(record.get("text") or "")
    media = record.get("media")
    media_html = ""
    if media:
        media_escaped = html.escape(media)
        media_html = f'<div><a href="{media_escaped}">media</a></div>'
    msg_id = html.escape(str(record.get('id', '')))
    return (
        "<article class=\"msg\">"
        f"<div class=\"meta\">{date} · {sender} · id {msg_id}</div>"
        f"<div class=\"text\">{text}</div>{media_html}</article>\n"
    )


async def _download_message_media(client, message, media_dir, pause_event=None, stop_event=None):
    if _is_stopped(stop_event):
        return None
    if not getattr(message, "media", None):
        return None
    while True:
        if not await _wait_if_paused(pause_event, stop_event):
            return None
        try:
            downloaded = await client.download_media(message, file_name=str(media_dir) + os.sep)
            if downloaded and os.path.isfile(downloaded):
                return downloaded
            return None
        except FloodWait as e:
            log.warning("FloodWait download_media: ждём %s сек", e.value)
            if not await _sleep_responsive(e.value, pause_event, stop_event):
                return None
        except Exception as e:
            log.warning("download_media skip message_id=%s: %s", getattr(message, "id", None), e)
            return None


async def export_chats_streaming(options: ExportOptions, pause_event=None, stop_event=None, progress_callback=None) -> tuple[str, dict]:
    """
    Потоковый параллельный экспорт выбранных чатов.

    Пишет:
      - messages.jsonl — основной машинный формат, одна строка на сообщение;
      - messages.html — читаемый просмотр;
      - media/ — скачанные вложения, если включено;
      - manifest.json — сводка по экспортированным чатам.
    """
    client = get_app()
    if not client:
        raise RuntimeError("Telegram-клиент не подключён.")

    chat_ids = [int(x) for x in options.chat_ids if str(x).strip()]
    if not chat_ids:
        raise ValueError("Не выбраны чаты для экспорта.")

    base_dir = Path(options.output_dir).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)
    session = _safe_filename(get_cache_session_key(), "session", 40)
    export_root = base_dir / f"TG_Deleter_export_{session}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    export_root.mkdir(parents=True, exist_ok=False)

    parallel = max(1, min(6, int(options.parallel_chats or 1)))
    media_types = _normalize_media_types(options.media_types)
    semaphore = asyncio.Semaphore(parallel)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "session": get_cache_session_key(),
        "parallel_chats": parallel,
        "include_media": bool(options.include_media),
        "media_types": media_types,
        "message_limit": options.message_limit,
        "stopped": False,
        "chats": [],
    }

    def emit(kind, **payload):
        if not progress_callback:
            return
        try:
            progress_callback(kind, payload)
        except Exception:
            pass

    emit(
        "overall_start",
        total_chats=len(chat_ids),
        done_chats=0,
        total_messages=None,
        done_messages=0,
        parallel_chats=parallel,
    )

    count_semaphore = asyncio.Semaphore(parallel)

    async def count_one(chat_id):
        async with count_semaphore:
            return chat_id, await _get_chat_history_count(client, chat_id, options.message_limit)

    counts_by_chat = {}
    for result in await asyncio.gather(*(count_one(cid) for cid in chat_ids), return_exceptions=True):
        if isinstance(result, Exception):
            log.debug("export count skipped: %s", result)
            continue
        cid, count = result
        counts_by_chat[cid] = count

    progress_state = {
        "done_chats": 0,
        "chat_done": {cid: 0 for cid in chat_ids},
        "chat_total": dict(counts_by_chat),
    }

    def overall_payload():
        totals = [v for v in progress_state["chat_total"].values() if v is not None]
        total_messages = sum(totals) if totals else None
        return {
            "done_chats": progress_state["done_chats"],
            "total_chats": len(chat_ids),
            "done_messages": sum(progress_state["chat_done"].values()),
            "total_messages": total_messages,
            "total_messages_known": len(totals) == len(chat_ids),
            "parallel_chats": parallel,
        }

    emit("overall_progress", **overall_payload())

    async def export_one(chat_id):
        async with semaphore:
            if _is_stopped(stop_event):
                return {
                    "chat_id": chat_id,
                    "title": str(chat_id),
                    "status": "skipped",
                    "messages": 0,
                    "media": 0,
                }
            title = str(chat_id)
            stats = {
                "chat_id": chat_id,
                "title": title,
                "type": "Чат",
                "folder": "",
                "status": "ok",
                "messages": 0,
                "total_messages": counts_by_chat.get(chat_id),
                "media": 0,
            }
            try:
                chat = await client.get_chat(chat_id)
                title = _chat_title(chat)
                folder = export_root / f"{_safe_filename(title)}_{chat_id}"
                media_dir = folder / "media"
                folder.mkdir(parents=True, exist_ok=True)
                media_dir.mkdir(exist_ok=True)
                jsonl_path = folder / "messages.jsonl"
                html_path = folder / "messages.html"
                stats.update({
                    "title": title,
                    "type": _chat_type_str(chat),
                    "folder": folder.name,
                })
                emit("chat_start", chat_id=chat_id, title=title, chat_total_messages=stats["total_messages"], **overall_payload())
                kwargs = {"limit": options.message_limit} if options.message_limit else {}
                with open(jsonl_path, "w", encoding="utf-8") as jf, open(html_path, "w", encoding="utf-8") as hf:
                    hf.write(_html_header(title))
                    async for message in client.get_chat_history(chat_id, **kwargs):
                        if _is_stopped(stop_event) or not await _wait_if_paused(pause_event, stop_event):
                            stats["status"] = "stopped"
                            break
                        media_rel = None
                        media_kind = _message_media_kind(message)
                        if options.include_media and _should_export_media(message, media_types):
                            media_path = await _download_message_media(client, message, media_dir, pause_event, stop_event)
                            if media_path:
                                stats["media"] += 1
                                media_rel = os.path.relpath(media_path, folder).replace(os.sep, "/")
                        record = _message_record(chat_id, message, media_rel, media_kind)
                        jf.write(json.dumps(record, ensure_ascii=False) + "\n")
                        hf.write(_html_message(record))
                        stats["messages"] += 1
                        progress_state["chat_done"][chat_id] = stats["messages"]
                        if stats["messages"] % 25 == 0:
                            jf.flush()
                            hf.flush()
                            emit(
                                "chat_progress",
                                chat_id=chat_id,
                                title=title,
                                messages=stats["messages"],
                                chat_total_messages=stats["total_messages"],
                                media=stats["media"],
                                **overall_payload(),
                            )
                    hf.write("</main></body></html>\n")
                progress_state["chat_done"][chat_id] = stats["messages"]
                emit(
                    "chat_done",
                    chat_id=chat_id,
                    title=title,
                    messages=stats["messages"],
                    chat_total_messages=stats["total_messages"],
                    media=stats["media"],
                    status=stats["status"],
                    **overall_payload(),
                )
            except FloodWait as e:
                log.warning("FloodWait export chat %s: %s sec, retrying", chat_id, e.value)
                if await _sleep_responsive(e.value, pause_event, stop_event):
                    try:
                        chat = await client.get_chat(chat_id)
                        title = _chat_title(chat)
                    except Exception:
                        pass
                    stats["status"] = "flood_retry"
                else:
                    stats["status"] = "flood_wait"
                    stats["error"] = f"FloodWait {e.value}"
            except Exception as e:
                stats["status"] = "error"
                stats["error"] = str(e)
                log.exception("export chat %s failed: %s", chat_id, e)
                emit("chat_error", chat_id=chat_id, title=title, error=str(e))
            return stats

    tasks = [asyncio.create_task(export_one(cid)) for cid in chat_ids]
    for task in asyncio.as_completed(tasks):
        result = await task
        manifest["chats"].append(result)
        progress_state["done_chats"] += 1
        progress_state["chat_done"][result.get("chat_id")] = result.get("messages", 0)
        emit("overall_progress", **overall_payload())
        if _is_stopped(stop_event):
            manifest["stopped"] = True
            for t in tasks:
                if not t.done():
                    t.cancel()
            break

    pending = [t for t in tasks if not t.done()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["total_messages"] = sum(c.get("messages", 0) for c in manifest["chats"])
    manifest["total_media"] = sum(c.get("media", 0) for c in manifest["chats"])
    with open(export_root / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    emit("done", export_root=str(export_root), manifest=manifest)
    return str(export_root), manifest
