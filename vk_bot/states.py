"""In-memory state machine для VK пользователей."""
from typing import Dict

_states: Dict[int, str] = {}
_data: Dict[int, dict] = {}

WELCOME = "welcome"
CHOOSE_OCCASION = "choose_occasion"
CHOOSE_RECIPIENT = "choose_recipient"
CHOOSE_BUDGET = "choose_budget"
AI_CHAT = "ai_chat"
PRESENTATION = "presentation"
GET_NAME = "get_name"
GET_PHONE = "get_phone"
COMPLETED = "completed"
ORDER_DATE = "order_date"
ORDER_PLACE = "order_place"
ORDER_PHRASE = "order_phrase"
ORDER_DESIGN = "order_design"
ORDER_FORMAT = "order_format"
ORDER_DELIVERY = "order_delivery"
ORDER_POSTCARD = "order_postcard"
ORDER_POSTCARD_TEXT = "order_postcard_text"
ORDER_PAY = "order_pay"

WAITING_MANAGER = "waiting_manager"
MANAGER_TAKEOVER = "manager_takeover"
SET_REMINDER_EVENT = "set_reminder_event"
SET_REMINDER_DATE = "set_reminder_date"
SET_REMINDER_DAYS = "set_reminder_days"


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


def set_data(user_id: int, data: dict) -> None:
    _data[user_id] = data
