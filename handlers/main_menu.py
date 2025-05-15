from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests

from handlers.errors import safe_send_message
from keyboards.keyboards import get_cancel_ikb, get_main_kb, get_urics_ikb
from instance import bot
from database.req import *

router = Router()


class CreateUric(StatesGroup):
    name = State()
    api_key = State()


@router.message(F.text == 'Создать Юр лицо')
async def create_uric_cmd(message: Message, state: FSMContext):
    """
    Обработчик команды создания юр лица.
    """
    await safe_send_message(bot, message, "Введите название Юр лица\n"
                                          "Учтите, что все названия должны быть уникальными",
                            reply_markup=get_cancel_ikb('main'))
    await state.set_state(CreateUric.name)


@router.message(CreateUric.name)
async def get_uric_name(message: Message, state: FSMContext):
    """
    Обработчик ввода названия юр лица.
    """
    uric = await get_uric(message.text)
    if uric:
        await safe_send_message(bot, message, "Такое название уже существует", reply_markup=get_cancel_ikb('main'))
        return

    await state.update_data(uric_name=message.text)
    link = "https://blog-promopult-ru.turbopages.org/turbo/blog.promopult.ru/s/marketplejsy/api-klyuch-wildberries.html"
    await safe_send_message(bot, message, "Введите API ключ\n<a href=\"{link}\">Как получить ключ?</a>\n",
                            reply_markup=get_cancel_ikb('main'))
    await state.set_state(CreateUric.api_key)


@router.message(CreateUric.api_key)
async def get_uric_api_key(message: Message, state: FSMContext):
    """
    Обработчик ввода API ключа юр лица.
    """
    data = await state.get_data()
    uric_name = data.get('uric_name')
    api_key = message.text

    url = 'https://common-api.wildberries.ru/ping'
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        await create_uric(uric_name, message.from_user.id, api_key)
        await update_user(message.from_user.id, uric_name)
        await add_user_uric(message.from_user.id, uric_name)
        await safe_send_message(bot, message, "Юр лицо успешно создано", reply_markup=get_main_kb(uric_name))
        await state.clear()
    elif response.status_code == 401:
        await safe_send_message(bot, message, text="Недействительный ключ, попробуйте еще раз",
                                reply_markup=get_cancel_ikb('main'))
    else:
        await safe_send_message(bot, message, text="Ошибка при запросе", reply_markup=get_cancel_ikb('main'))


@router.message(F.text == 'Выбрать Юр лицо')
async def cmd_choose_uric(message: Message):
    """
    Обработчик команды выбора юр лица.
    """
    user_id = message.from_user.id
    urics = await get_urics_by_user(user_id)
    if not urics:
        await safe_send_message(bot, message, "У вас нет созданных юр лиц", reply_markup=get_main_kb(''))
        return

    await safe_send_message(bot, message, "Выберите юр лицо", reply_markup=get_urics_ikb(urics))


@router.callback_query(F.data.startswith('uric'))
async def choose_uric(callback: CallbackQuery):
    """
    Обработчик выбора юр лица.
    """
    uric_name = callback.data.split(':')[1]
    await update_user(callback.from_user.id, uric_name)
    await safe_send_message(bot, callback.message, "Юр лицо выбрано", reply_markup=get_main_kb(uric_name))
    await callback.answer()
