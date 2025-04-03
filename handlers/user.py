import asyncio
import tempfile

from aiogram.filters import Command, CommandStart
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from keyboards.keyboards import get_some_kb, get_some_ikb
from instance import bot
from database.req import *


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user.id)
    await safe_send_message(bot, message, text="Привет! Это бот для атвоматизации работы с Wildberries. "
                                               "Мы поможем тебе упростить работу с этой платформой.\n"
                                               "Для начала используй <pre><code>/help</code></pre>")


@router.message(Command('help'))
async def cmd_info(message: Message):
    link = "https://blog-promopult-ru.turbopages.org/turbo/blog.promopult.ru/s/marketplejsy/api-klyuch-wildberries.html"
    await safe_send_message(
        bot, message,
        text=("Для работы с ботом необходимо добавить ключ доступа к API Wildberries\n"
              f"<a href=\"{link}\">Как получить ключ?</a>\n"
              "Чтобы это сделать используй кнопку 'Добавить ключ'\n"
              "Что бы получить отчет о стоимости хранения используй кнопку 'Получить отчет'\n"
        )
    )


class AddKey(StatesGroup):
    key = State()


@router.message(F.text == 'Добавить ключ' or Command('key'))
async def cmd_key(message: Message, state: FSMContext):
    if message.text == 'Добавить ключ':
        await safe_send_message(bot, message, text="Укажите ключ")
        await state.set_state(AddKey.key)
        return
    try:
        key = message.text.split(' ')[1]
    except Exception as e:
        await safe_send_message(bot, message, text="Необходимо указать ключ доступа")
        return
    url = 'https://common-api.wildberries.ru/ping'
    headers = {
        'Authorization': f'Bearer {key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        await update_user(message.from_user.id, {'api_key': key})
        await safe_send_message(bot, message, text="Ключ добавлен!")
    elif response.status_code == 401:
        await safe_send_message(bot, message, text="Недействительный ключ")
    else:
        await safe_send_message(bot, message, text="Ошибка при запросе")


@router.message(AddKey.key)
async def add_key(message: Message, state: FSMContext):
    url = 'https://common-api.wildberries.ru/ping'
    headers = {
        'Authorization': f'Bearer {message.text}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        await update_user(message.from_user.id, {'api_key': message.text})
        await safe_send_message(bot, message, text="Ключ добавлен!")
    elif response.status_code == 401:
        await safe_send_message(bot, message, text="Недействительный ключ")
    else:
        await safe_send_message(bot, message, text="Ошибка при запросе")
    await state.clear()


class Report(StatesGroup):
    waiting_first_date = State()
    waiting_second_date = State()


@router.message(F.text == 'Получить отчет' or Command('report'))
async def cmd_report(message: Message, state: FSMContext):
    if message.text == 'Получить отчет':
        await safe_send_message(bot, message, text="Укажите дату начала отчета в формате YYYY-MM-DD")
        await state.set_state(Report.waiting_first_date)
        return
    try:
        date_from, date_to = message.text.split(' ')[1:]
    except Exception as e:
        await safe_send_message(bot, message, text="Необходимо указать дату начала и дату конца")
        return
    user = await get_user(message.from_user.id)
    if not user.api_key:
        await safe_send_message(bot, message, text="Необходимо добавить ключ доступа")
        return
    msg = await safe_send_message(bot, message, text="Отчет формируется, пожалуйста подождите, это займет пару минут")
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage?dateFrom={date_from}&dateTo={date_to}'
    headers = {
        'Authorization': f'Bearer {user.api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        if response.status_code == 401:
            await safe_send_message(bot, message, text="Недействительный ключ")
        elif response.status_code == 400:
            await safe_send_message(bot, message, text="Неправильный формат данных")
        else:
            await safe_send_message(bot, message, text="Ошибка при запросе")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        return
    task_id = response.json()['data']['taskId']
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download'
    await asyncio.sleep(70)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        await safe_send_message(bot, message, text=f"Ошибка при запросе {response.status_code} {response.json()}")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        return

    data = response.json()
    df = pd.DataFrame(data)

    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
            worksheet = writer.sheets["Sheet1"]
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                worksheet.set_column(idx, idx, max_len)
        buffer.seek(0)
        temp_file = BufferedInputFile(buffer.read(), filename="report.xlsx")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        await bot.send_document(chat_id=message.chat.id, document=temp_file, caption="Отчет готов")


@router.message(Report.waiting_first_date)
async def first_date(message: Message, state: FSMContext):
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD")
        return
    await state.update_data(first_date=message.text)
    await safe_send_message(bot, message, text="Укажите дату конца отчета в формате YYYY-MM-DD")
    await state.set_state(Report.waiting_second_date)


@router.message(Report.waiting_second_date)
async def second_date(message: Message, state: FSMContext):
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD")
        return
    user = await get_user(message.from_user.id)
    if not user.api_key:
        await safe_send_message(bot, message, text="Необходимо добавить ключ доступа")
        return
    date_to = message.text
    date_from = (await state.get_data()).get('first_date')
    msg = await safe_send_message(bot, message, text="Отчет формируется, пожалуйста подождите, это займет пару минут")
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage?dateFrom={date_from}&dateTo={date_to}'
    headers = {
        'Authorization': f'Bearer {user.api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        if response.status_code == 401:
            await safe_send_message(bot, message, text="Недействительный ключ")
        elif response.status_code == 400:
            await safe_send_message(bot, message, text="Неправильный формат данных")
        else:
            await safe_send_message(bot, message, text="Ошибка при запросе")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        return
    task_id = response.json()['data']['taskId']
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download'
    await asyncio.sleep(70)
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        await safe_send_message(bot, message, text=f"Ошибка при запросе {response.status_code} {response.json()}")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        return

    data = response.json()
    df = pd.DataFrame(data)

    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
            worksheet = writer.sheets["Sheet1"]
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                worksheet.set_column(idx, idx, max_len)
        buffer.seek(0)
        temp_file = BufferedInputFile(buffer.read(), filename="report.xlsx")
        await bot.delete_message(chat_id=message.chat.id, message_id=msg.message_id)
        await bot.send_document(chat_id=message.chat.id, document=temp_file, caption="Отчет готов")
    await state.clear()
