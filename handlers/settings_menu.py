from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests

from handlers.errors import safe_send_message
from keyboards.keyboards import get_cancel_ikb, get_settings_kb
from instance import bot, bot_link
from database.req import *

router = Router()


class ChangeApiKey(StatesGroup):
    change_api_key = State()


@router.message(F.text == 'Обновить API ключ')
async def change_api_key_start(message: Message, state: FSMContext):
    """
    Функция для смены API ключа.
    """
    msg = await safe_send_message(bot, message, 'Загрузка...', reply_markup=ReplyKeyboardRemove())
    await msg.delete()
    link = "https://blog-promopult-ru.turbopages.org/turbo/blog.promopult.ru/s/marketplejsy/api-klyuch-wildberries.html"
    await message.answer(f"Введите новый API ключ:\n<a href=\"{link}\">Как получить ключ?</a>\n",
                         reply_markup=get_cancel_ikb('settings'))
    await state.set_state(ChangeApiKey.change_api_key)


@router.message(ChangeApiKey.change_api_key)
async def change_api_key(message: Message, state: FSMContext):
    """
    Функция для смены API ключа.
    """
    new_api_key = message.text.strip().replace('\n', '').replace('\r', '')
    tg_id = message.from_user.id

    user = await get_user(tg_id)
    uric = await get_uric(user.cur_uric)

    if uric.api_key == new_api_key:
        await message.answer("Этот API ключ уже установлен", reply_markup=get_settings_kb(uric.owner_id == tg_id))
        return

    url = 'https://common-api.wildberries.ru/api/v1/seller-info'
    headers = {
        'Authorization': f'Bearer {new_api_key}'
    }
    try:
        response = requests.get(url, headers=headers)
    except Exception:
        await safe_send_message(bot, message, 'Некорректный API ключ.\nПопробуйте еше раз',
                                reply_markup=get_cancel_ikb('settings'))
        return
    if response.status_code == 200:
        trade_mark = (await get_uric(user.cur_uric)).trade_mark
        if trade_mark != 'admin' and trade_mark != response.json()['tradeMark']:
            await safe_send_message(bot, message, "Вы пытаетесь использовать API ключ другого юр лица.\n"
                                                  "Используйте только от своего!",
                                    get_settings_kb(uric.owner_id == tg_id))
            await state.clear()
            return
        await update_uric_api_key(user.cur_uric, new_api_key)

        await message.answer("API ключ успешно изменен", reply_markup=get_settings_kb(uric.owner_id == tg_id))
        await state.clear()
    elif response.status_code == 401:
        await safe_send_message(bot, message, text="Недействительный ключ, попробуйте еще раз",
                                reply_markup=get_cancel_ikb('settings'))
    else:
        await safe_send_message(bot, message, text="Ошибка при запросе", reply_markup=get_cancel_ikb('settings'))


@router.message(F.text == 'Статус оплаты')
async def status_payment(message: Message):
    """
    Функция для получения статуса оплаты.
    """
    user = await get_user(message.from_user.id)
    uric = await get_uric(user.cur_uric)
    text = (f"Статус подписки по юр. лицу {uric.name}:\n"
            f"Подпсика - {uric.subsribe.value}\n"
            f"Дата окончания подписки - {uric.exp_date}\n")
    await safe_send_message(bot, message, text=text, reply_markup=get_settings_kb(uric.owner_id == user.id))


@router.message(F.text == 'Оплатить')
async def cmd_pay(message: Message):
    """
    Функция для получения ссылки на оплату.
    """
    await safe_send_message(bot, message, "Напишите сюда @If9090",
                            reply_markup=get_settings_kb((await get_uric(
                                (await get_user(message.from_user.id)).cur_uric)).owner_id == message.from_user.id))


@router.message(F.text == 'Добавить сотрудника')
async def add_employee(message: Message):
    """
    Функция для добавления сотрудника.
    """
    cur_uric = (await get_user(message.from_user.id)).cur_uric
    hash = (await get_uric(cur_uric)).hash
    url = f'https://t.me/@{bot_link}?start={hash}'
    await safe_send_message(bot, message, f"Отправьте эту сслыку сотруднику {url}",
                            reply_markup=get_settings_kb((await get_uric(cur_uric)).owner_id == message.from_user.id))
