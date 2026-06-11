"""In-memory state machine для VK пользователей."""
from typing import Dict

_states: Dict[int, str] = {}
_data: Dict[int, dict] = {}

WELCOME = "welcome"
CHOOSE_OCCASION = "choose_occasion"
CHOOSE_RECIPIENT = "choose_recipient"
CHOOSE_BUDGET = "choose_budget"
AI_CHAT = "ai_chat"
GET_NAME = "get_name"
GET_PHONE = "get_phone"
COMPLETED = "completed"
MANAGER_TAKEOVER = "manager_takeover"


def get_state(user_id: int) -> str:
    return _states.get(user_id, WELCOME)


def set_state(user_id: int, state: str) -> None:
    _states[user_id] = state


def get_data(user_id: int) -> dict:
    return dict(_data.get(user_id, {}))


def update_data(user_id: int, **kwargs) -> None:
    if user_id not in _data:
        _data[user_id] = {}
    _data[user_id].update(kwargs)


def clear(user_id: int) -> None:
    _states.pop(user_id, None)
    _data.pop(user_id, None)
