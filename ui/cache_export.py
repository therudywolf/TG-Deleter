"""
Кэш скана и экспорт списков чатов/сообщений в CSV/JSON.
"""
import csv
import json
import os
import logging
from datetime import datetime
from typing import List, Optional

from core import Place, get_current_session, get_cache_session_key, get_project_root, normalize_session_name

log = logging.getLogger("tg_deleter")

_PROJECT_ROOT = get_project_root()


def cache_path(session: Optional[str] = None) -> str:
    if session is None:
        session = get_cache_session_key()
    session = normalize_session_name(session) or "session"
    return os.path.join(_PROJECT_ROOT, f"scan_cache_{session}.json")


def load_places_from_cache(session: Optional[str] = None) -> Optional[List[Place]]:
    """Загружает список чатов из кэша. При ошибке возвращает None."""
    path = cache_path(session)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return None
        places = []
        for d in data:
            places.append(Place(
                chat_id=d["chat_id"],
                title=d.get("title", ""),
                type_str=d.get("type_str", ""),
                messages=[tuple(m) for m in d.get("messages", [])],
            ))
        return places
    except Exception:
        return None


def save_places_to_cache(places: List[Place], session: Optional[str] = None) -> None:
    """Сохраняет список чатов в кэш."""
    path = cache_path(session)
    data = [
        {
            "chat_id": p.chat_id,
            "title": p.title,
            "type_str": p.type_str,
            "messages": list(p.messages),
        }
        for p in places
    ]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def get_cache_mtime_str(session: Optional[str] = None) -> Optional[str]:
    """Возвращает строку «Кэш от DD.MM.YYYY HH:MM» по mtime файла кэша."""
    path = cache_path(session)
    if not os.path.isfile(path):
        return None
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return None


def clear_cache(session: Optional[str] = None) -> bool:
    """Удалить файл кэша скана для сессии. session=None — текущая. Возвращает True если файл удалён или не существовал."""
    path = cache_path(session)
    if not os.path.isfile(path):
        return True
    try:
        os.remove(path)
        log.debug("clear_cache: removed %s", path)
        return True
    except Exception as e:
        log.warning("clear_cache failed: %s", e)
        return False


def export_places_to_csv(places: List[Place], path: str) -> None:
    """Экспорт списка чатов в CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "type_str", "chat_id", "messages_count"])
        for p in places:
            w.writerow([p.title or "", p.type_str, p.chat_id, len(p.messages)])
    log.debug("export_places_to_csv: %s", path)


def export_places_to_json(places: List[Place], path: str) -> None:
    """Экспорт списка чатов в JSON (как в кэше)."""
    data = [
        {"chat_id": p.chat_id, "title": p.title or "", "type_str": p.type_str, "messages": list(p.messages)}
        for p in places
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.debug("export_places_to_json: %s", path)


def export_messages_to_csv(place: Place, path: str) -> None:
    """Экспорт сообщений одного чата в CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["chat_id", "message_id", "date", "preview"])
        for mid, preview, date_str in place.messages:
            w.writerow([place.chat_id, mid, date_str, preview or ""])
    log.debug("export_messages_to_csv: %s", path)


def export_messages_to_json(place: Place, path: str) -> None:
    """Экспорт сообщений одного чата в JSON."""
    data = {
        "chat_id": place.chat_id,
        "title": place.title or "",
        "type_str": place.type_str,
        "messages": [{"id": m[0], "date": m[2], "preview": m[1]} for m in place.messages],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.debug("export_messages_to_json: %s", path)
