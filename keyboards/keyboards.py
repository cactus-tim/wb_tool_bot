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


def get_input_format_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Список артикулов", callback_data="type_input_spp:list")],
        [InlineKeyboardButton(text="Excel таблица с артикулями", callback_data="type_input_spp:xlsx")],
        [InlineKeyboardButton(text="Выгрузка по юр лицу", callback_data="type_input_spp:table")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_output_format_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Список", callback_data="type_output_spp:list")],
        [InlineKeyboardButton(text="Excel таблица", callback_data="type_output_spp:xlsx")],
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
