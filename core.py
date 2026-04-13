"""
Ядро TG Deleter: api_config.json (API и скан), config.json (аккаунты/сессия), Pyrogram-клиент.
"""
import os
import sys
import json
import logging
import asyncio
import re
from dataclasses import dataclass, field

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
}
# Дефолты для config.json (только приложение: сессии и аккаунты)
_APP_DEFAULTS = {
    "session_name": "session",
    "accounts": [],
    "current_session": None,
}
_api_config_cache = None
_app_config_cache = None


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
    except (TypeError, ValueError):
        return default

def _float(val, default=0.2):
    if val is None or val == "":
        return default
    try:
        return float(val)
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

def load_api_config():
    global _api_config_cache
    _migrate_to_api_config()
    path = _api_config_path()
    data = dict(_API_DEFAULTS)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception as e:
            log.warning("load_api_config failed: %s", e)
    _api_config_cache = data
    return data


def save_api_config(data):
    global _api_config_cache
    path = _api_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        _api_config_cache = dict(data)
    except Exception as e:
        log.warning("save_api_config failed: %s", e)


def get_api_config():
    global _api_config_cache
    if _api_config_cache is None:
        load_api_config()
    return dict(_api_config_cache)


def reset_api_config():
    save_api_config(dict(_API_DEFAULTS))


def get_api_id():
    return _int(get_api_config().get("api_id"))


def get_api_hash():
    return (get_api_config().get("api_hash") or "").strip()


def get_scan_limit():
    return _int(get_api_config().get("scan_limit"))


def get_delay_sec():
    return _float(get_api_config().get("delay_sec"), 0.2)


def get_scan_delay_between_chats():
    return _float(get_api_config().get("scan_delay_between_chats"), 2.0)


def get_chat_id_cli():
    return _int(get_api_config().get("chat_id_cli"))


def get_scan_include_groups():
    v = get_api_config().get("scan_include_groups")
    return v if isinstance(v, bool) else True


def get_scan_include_channels():
    v = get_api_config().get("scan_include_channels")
    return v if isinstance(v, bool) else True


def get_scan_include_private():
    v = get_api_config().get("scan_include_private")
    return v if isinstance(v, bool) else True


# ---------- App config (config.json): session_name, accounts, current_session ----------

def load_config():
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
    _app_config_cache = data
    return data


def save_config(data):
    global _app_config_cache
    path = _app_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        _app_config_cache = dict(data)
    except Exception as e:
        log.warning("save_config failed: %s", e)


def get_config():
    global _app_config_cache
    if _app_config_cache is None:
        load_config()
    return dict(_app_config_cache)


def get_config_value(key):
    return get_config().get(key, _APP_DEFAULTS.get(key))


def set_config_value(key, value):
    c = get_config()
    c[key] = value
    save_config(c)


def reset_config():
    save_config(dict(_APP_DEFAULTS))

_current_app = None
my_user_id = None
my_username = None
my_first_name = None
my_last_name = None
my_channel_ids: set = set()


def set_my_channels(channel_ids: set):
    """Сохранить ID каналов, где пользователь является admin/creator."""
    global my_channel_ids
    my_channel_ids = set(channel_ids)
    log.debug("set_my_channels: %d каналов", len(my_channel_ids))


async def fetch_and_set_my_channels(client):
    """Обходит диалоги один раз и собирает ID каналов где пользователь — admin или creator."""
    ids = set()
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


def get_account_profile(session_name):
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


def save_account_profile(session_name, profile):
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


def get_accounts_list():
    """Список имён сессий из config.json. Может быть пустым."""
    acc = get_config_value("accounts")
    if isinstance(acc, list):
        return [str(x).strip() for x in acc if str(x).strip()]
    return []


def save_accounts_list(accounts):
    """Сохранить список аккаунтов в config."""
    set_config_value("accounts", list(accounts))


def add_account(session_name):
    """Добавить аккаунт (сессию) в список. Не дублирует."""
    name = (session_name or "").strip()
    if not name:
        return False
    accounts = get_accounts_list()
    if name in accounts:
        return True
    accounts.append(name)
    save_accounts_list(accounts)
    return True


def remove_account(session_name):
    """Удалить аккаунт из списка. Файл сессии не удаляется."""
    name = (session_name or "").strip()
    if not name:
        return False
    accounts = get_accounts_list()
    if name not in accounts:
        return False
    accounts = [a for a in accounts if a != name]
    save_accounts_list(accounts)
    return True


def get_current_session():
    """Текущая выбранная сессия или первая из списка. None если аккаунтов нет."""
    name = get_config_value("current_session")
    accounts = get_accounts_list()
    if name and (name or "").strip() and (name or "").strip() in accounts:
        return (name or "").strip()
    return accounts[0] if accounts else None


def get_cache_session_key():
    """Ключ сессии для имени файла кэша: текущая сессия или имя по умолчанию, если аккаунтов нет."""
    return get_current_session() or (get_config_value("session_name") or "session").strip()


def set_current_session(session_name):
    """Сохранить выбранную сессию в config."""
    set_config_value("current_session", session_name)


def create_client(session_name):
    """Создать Pyrogram Client для указанной сессии."""
    api_id = get_api_id()
    api_hash = get_api_hash()
    if not api_id or not api_hash:
        raise ValueError("Введите API ID и API Hash в настройках приложения.")
    return Client(session_name, api_id=api_id, api_hash=api_hash, workdir=get_project_root())


def set_app(client):
    """Установить текущий клиент (вызывает воркер после подключения)."""
    global _current_app
    _current_app = client


def get_app():
    """Текущий активный клиент (None до подключения воркера)."""
    return _current_app


def set_me_from_dict(me_dict):
    """Обновить my_user_id / my_username / имя из результата get_me (для check_if_mine)."""
    global my_user_id, my_username, my_first_name, my_last_name
    if me_dict:
        my_user_id = me_dict.get("id") or my_user_id
        my_username = (me_dict.get("username") or "").strip() or my_username
        my_first_name = (me_dict.get("first_name") or "").strip() or my_first_name
        my_last_name = (me_dict.get("last_name") or "").strip() or my_last_name
    log.debug("set_me_from_dict: my_user_id=%s my_username=%s", my_user_id, my_username)


@dataclass
class Place:
    """Место (чат/группа/канал) с списком своих сообщений."""
    chat_id: int
    title: str
    type_str: str
    messages: list = field(default_factory=list)  # [(message_id, preview, date_str), ...]


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


async def check_if_mine(message):
    try:
        # Исходящее (я отправил) — в каналах from_user часто пустой, полагаемся на out/outgoing
        if getattr(message, "out", None) is True or getattr(message, "outgoing", None) is True:
            return True
        # Сообщение отправлено от имени канала, которым владеет/управляет пользователь
        sender_chat = getattr(message, "sender_chat", None)
        if sender_chat and my_channel_ids and getattr(sender_chat, "id", None) in my_channel_ids:
            return True
        if message.from_user:
            uid = message.from_user.id
            uname = (getattr(message.from_user, "username") or "").strip()
            if my_user_id is not None and uid == my_user_id:
                return True
            if my_username and uname and uname.lower() == my_username.lower():
                return True
        # Подписи админов/авторов в канале (когда from_user может быть пустым)
        sig = getattr(message, "author_signature", None)
        if sig:
            sig_l = str(sig).lower()
            sig_words = re.findall(r"\w+", sig_l)
            if my_username and my_username.lower() in sig_words:
                return True
            if my_first_name and my_first_name.lower() in sig_words:
                return True
            if my_last_name and my_last_name.lower() in sig_words:
                return True
        return False
    except (UnicodeDecodeError, UnicodeEncodeError, TypeError, ValueError, AttributeError):
        return False


def make_preview(message, max_len=50):
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
    return d.strftime("%Y-%m-%d %H:%M")


async def delete_message_ids(cid, message_ids):
    """
    Удаляет сообщения в чате cid по списку ID с паузами и повторной попыткой при FloodWait.
    Возвращает список успешно удалённых message_id.
    """
    if not message_ids:
        return []
    log.debug("delete_message_ids: chat_id=%s count=%s", cid, len(message_ids))
    deleted_ids = []
    client = get_app()
    if not client:
        return []
    for mid in message_ids:
        while True:
            try:
                mid_int = int(mid)
                await client.delete_messages(cid, mid_int)
                log.debug("Удалён пост: chat_id=%s message_id=%s", cid, mid_int)
                deleted_ids.append(mid_int)
                await asyncio.sleep(get_delay_sec())
                break
            except FloodWait as e:
                log.warning("FloodWait: ждём %s сек", e.value)
                await asyncio.sleep(e.value)
            except Exception as e:
                log.exception("Ошибка удаления message_id=%s: %s", mid, e)
                break
    log.debug("delete_message_ids done: chat_id=%s deleted=%s", cid, len(deleted_ids))
    return deleted_ids


async def scan_chat(cid):
    """
    Сканирует один чат и возвращает список своих сообщений: [(message_id, preview, date_str), ...].
    """
    log.debug("scan_chat: chat_id=%s", cid)
    result = []
    kwargs = {"limit": get_scan_limit()} if get_scan_limit() else {}
    client = get_app()
    if not client:
        return result
    while True:
        try:
            async for message in client.get_chat_history(cid, **kwargs):
                if await check_if_mine(message):
                    preview = make_preview(message)
                    date_str = _message_date_str(message)
                    result.append((message.id, preview, date_str))
            break
        except FloodWait as e:
            log.warning("FloodWait scan_chat %s: ждём %s сек", cid, e.value)
            await asyncio.sleep(e.value)
        except Exception as e:
            log.warning("scan_chat error %s: %s", cid, e)
            break
    log.debug("scan_chat done: chat_id=%s found=%s", cid, len(result))
    return result


async def scan_all_dialogs(
    include_groups=True,
    include_channels=True,
    include_private=True,
    pause_event=None,
    stop_event=None,
    progress_callback=None,
    dialog_progress_callback=None,
    max_my_messages_per_chat=None,
):
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
        ct = getattr(chat, "type", None)
        if ct in (ChatType.PRIVATE, ChatType.BOT) and not include_private:
            continue
        if ct in (ChatType.GROUP, ChatType.SUPERGROUP) and not include_groups:
            continue
        if ct == ChatType.CHANNEL and not include_channels:
            continue

        if pause_event is not None and pause_event.is_set():
            log.debug("scan_all_dialogs: пауза")
            while pause_event.is_set():
                await asyncio.sleep(0.5)

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
                await asyncio.sleep(e.value)
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
            await asyncio.sleep(get_scan_delay_between_chats())
    log.debug("scan_all_dialogs done: всего мест %s", len(places))
    return places


async def delete_all_my_in_chat_no_scan(cid, progress_callback=None):
    """
    Обходит историю чата cid и удаляет каждое своё сообщение по ходу (без предварительного списка).
    progress_callback(count) — вызывается каждые 10 удалённых сообщений.
    Возвращает количество удалённых.
    """
    log.debug("delete_all_my_in_chat_no_scan: chat_id=%s", cid)
    kwargs = {"limit": get_scan_limit()} if get_scan_limit() else {}
    count = 0
    client = get_app()
    if not client:
        return count
    while True:
        try:
            async for message in client.get_chat_history(cid, **kwargs):
                if not await check_if_mine(message):
                    continue
                while True:
                    try:
                        await client.delete_messages(cid, message.id)
                        log.debug("Удалён пост (no_scan): chat_id=%s message_id=%s", cid, message.id)
                        count += 1
                        if progress_callback and count % 10 == 0:
                            try:
                                progress_callback(count)
                            except Exception:
                                pass
                        await asyncio.sleep(get_delay_sec())
                        break
                    except FloodWait as e:
                        log.warning("FloodWait: ждём %s сек", e.value)
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        log.exception("Ошибка удаления message_id=%s: %s", message.id, e)
                        break
            break
        except FloodWait as e:
            log.warning("FloodWait на чтении истории (no_scan): ждём %s сек", e.value)
            await asyncio.sleep(e.value)
        except Exception as e:
            log.exception("Ошибка обхода истории (no_scan) chat_id=%s: %s", cid, e)
            break
    log.debug("delete_all_my_in_chat_no_scan done: chat_id=%s deleted=%s", cid, count)
    return count
