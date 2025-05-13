from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_cancel_ikb() -> InlineKeyboardMarkup:
    ikb = [
        [InlineKeyboardButton(text="Отмена", callback_data="cancel")],
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


def get_main_kb(cur_uric: str) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Создать Юр лицо')], [KeyboardButton(text='Выбрать Юр лицо')]],
        resize_keyboard=True
    )
    if cur_uric:
        keyboard.keyboard.append([KeyboardButton(text=f'Продолжить с {cur_uric}')])
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
            keyboard=[[KeyboardButton(text='Сменить API ключ')]],
            resize_keyboard=True
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[]],
            resize_keyboard=True
        )
    keyboard.keyboard.append([KeyboardButton(text='Статус оплаты')])
    keyboard.keyboard.append([KeyboardButton(text='Оплатить')])
    keyboard.keyboard.append([KeyboardButton(text='Добавить сотрудника')])
    keyboard.keyboard.append([KeyboardButton(text='Назад')])
    return keyboard

