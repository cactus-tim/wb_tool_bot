from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_cancel_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Отмена", callback_data="cancel")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_app_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Добавить СПП", callback_data="spp:yes"),
         InlineKeyboardButton(text="Без СПП", callback_data="spp:no")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_some_kb() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='пу')], [KeyboardButton(text='пупу'), KeyboardButton(text='пупупу')]],
        resize_keyboard=True
    )
    return keyboard


def get_main_kb() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Добавить ключ')], [KeyboardButton(text='Получить отчет')], [KeyboardButton(text='Получить SPP')]],
        resize_keyboard=True
    )
    return keyboard
