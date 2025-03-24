from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_some_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Кнопка 1", callback_data="f_btn")],
        [InlineKeyboardButton(text="Кнопка 2", callback_data="s_btn"), InlineKeyboardButton(text="Кнопка 3", callback_data="t_btn")],

    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_some_kb() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='пу')], [KeyboardButton(text='пупу'), KeyboardButton(text='пупупу')]],
        resize_keyboard=True
    )
    return keyboard
