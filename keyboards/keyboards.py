from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_cancel_ikb(reply_kb: str) -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Отмена", callback_data=f"cancel:{reply_kb}")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_input_format_ikb() -> InlineKeyboardMarkup:
    reply_kb = 'func'
    ikb = [
        [InlineKeyboardButton(text="Список артикулов", callback_data="type_input_spp:list")],
        [InlineKeyboardButton(text="Excel таблица с артикулями", callback_data="type_input_spp:xlsx")],
        [InlineKeyboardButton(text="Выгрузка по юр лицу", callback_data="type_input_spp:table")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"cancel:{reply_kb}")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_output_format_ikb() -> InlineKeyboardMarkup:
    reply_kb = 'func'
    ikb = [
        [InlineKeyboardButton(text="Список", callback_data="type_output_spp:list")],
        [InlineKeyboardButton(text="Excel таблица", callback_data="type_output_spp:xlsx")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"cancel:{reply_kb}")],
    ]
    ikeyboard = InlineKeyboardMarkup(inline_keyboard=ikb)
    return ikeyboard


def get_urics_ikb(urics: list) -> InlineKeyboardMarkup:
    """
    Формирует InlineKeyboardMarkup из списка строк urics,
    группируя кнопки по 3 в строке (aiogram 3.x).
    """
    builder = InlineKeyboardBuilder()
    for uri in urics:
        builder.button(text=uri.uric_id, callback_data=f"uric:{uri.uric_id}")
    builder.adjust(3)
    return builder.as_markup()


def get_main_kb(cur_uric: str) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Создать Юр лицо')],
                  [KeyboardButton(text='Выбрать Юр лицо')],
                  ],
        resize_keyboard=True
    )
    if cur_uric:
        keyboard.keyboard.append([KeyboardButton(text=f'Продолжить с {cur_uric}')])
    keyboard.keyboard.append([KeyboardButton(text='Полная инструкция')])
    return keyboard


def get_func_kb() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Получить отчет')],
                  [KeyboardButton(text='Получить СПП')],
                  [KeyboardButton(text='Настройки Юр лица')],
                  [KeyboardButton(text='Назад в главное меню')]],
        resize_keyboard=True
    )
    return keyboard


def get_settings_kb(is_owner: bool) -> ReplyKeyboardMarkup:
    if is_owner:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text='Обновить API ключ')]],
            resize_keyboard=True
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[]],
            resize_keyboard=True
        )
    keyboard.keyboard.append([KeyboardButton(text='Статус оплаты')])
    keyboard.keyboard.append([KeyboardButton(text='Оплатить')])
    if is_owner:
        keyboard.keyboard.append([KeyboardButton(text='Добавить сотрудника')])
    keyboard.keyboard.append([KeyboardButton(text='Назад')])
    return keyboard
