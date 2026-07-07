from aiogram.fsm.state import State, StatesGroup


class Funnel(StatesGroup):
    welcome = State()
    choose_occasion = State()
    choose_recipient = State()
    choose_budget = State()
    presentation = State()
    ai_chat = State()
    get_name = State()
    get_phone = State()
    completed = State()
    subscribe_email = State()


class Reminder(StatesGroup):
    set_event = State()
    set_date = State()
    set_days = State()


class Admin(StatesGroup):
    waiting_password = State()
    panel = State()
    takeover = State()
    broadcast = State()
    add_note = State()
