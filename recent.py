"""Последние реплики диалога — только в памяти, без записи в БД.

Пришло на смену таблице messages: менеджеру нужен контекст последних
нескольких фраз, а не вечный архив переписки. Переживать рестарт тут
нечему — если контейнер перезапустился, разговор всё равно оборвался.
"""
from collections import deque
from typing import Deque, Dict, List, Tuple

MAX_PER_USER = 10

# user_db_id -> [(direction, text), ...]
_buf: Dict[int, Deque[Tuple[str, str]]] = {}


def remember(user_id: int, direction: str, text: str) -> None:
    """direction: incoming | outgoing | outgoing_admin"""
    if not text:
        return
    if user_id not in _buf:
        _buf[user_id] = deque(maxlen=MAX_PER_USER)
    _buf[user_id].append((direction, text[:400]))


def recent(user_id: int, limit: int = 6) -> List[Tuple[str, str]]:
    items = list(_buf.get(user_id, ()))
    return items[-limit:]


def forget(user_id: int) -> None:
    _buf.pop(user_id, None)
