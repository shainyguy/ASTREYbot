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


class Order(StatesGroup):
    """Сбор заказа: дата → место → фраза → дизайн → формат → оплата."""
    event_date = State()
    event_place = State()
    phrase = State()
    design = State()
    choose_format = State()
    choose_delivery = State()
    awaiting_payment = State()


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
