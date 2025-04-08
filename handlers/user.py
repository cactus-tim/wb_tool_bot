import asyncio
import json
import re
import tempfile

from aiogram.filters import Command, CommandStart
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from pyrogram import Client, errors
from telethon import TelegramClient, errors
from telethon.tl.custom import Conversation
import math
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from instance import name, api_id, api_hash
from keyboards.keyboards import get_some_kb, get_cancel_ikb, get_app_ikb
from instance import bot, logger
from database.req import *


router = Router()


async def fetch_data(task_id, headers, bot, callback, msg, user, max_retries=3):
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download'
    await asyncio.sleep(70)

    for attempt in range(max_retries):
        try:
            # Запрос с включённым потоковым режимом и заданием таймаута
            response = requests.get(url, headers=headers, stream=True, timeout=(5, 30))

            if response.status_code != 200:
                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text
                await safe_send_message(bot, callback, text=f"Ошибка при запросе {response.status_code}: {error_data}")
                await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
                return None

            # Определяем, используется ли chunked transfer encoding
            if 'chunked' in response.headers.get('Transfer-Encoding', '').lower():
                content_bytes = b""
                # Читаем данные по частям с обработкой чанков
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        content_bytes += chunk
                data = json.loads(content_bytes.decode('utf-8'))
            else:
                # Если данные передаются целиком
                data = response.json()

            return data

        except requests.exceptions.ChunkedEncodingError as e:
            # Если произошла ошибка чтения чанков, повторяем попытку
            if attempt < max_retries - 1:
                time.sleep(2)  # небольшая задержка перед повторной попыткой
                continue
            else:
                await safe_send_message(bot, callback, text=f"Ошибка соединения при получении чанков: {e}")
                await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
                return None
        except Exception as e:
            await safe_send_message(bot, callback, text=f"Произошла ошибка: {e}")
            await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
            return None


async def get_spp_old(ids: list, user_id: int, message_id: int) -> dict:
    client = TelegramClient(name, api_id=api_id, api_hash=api_hash)
    error_list = []
    spp = {}
    total_ids = len(ids)
    total_parts = min(25, total_ids) if total_ids > 0 else 1
    visual_parts = 25
    chunk_size = math.ceil(total_ids / total_parts)

    async with client:
        for part in range(total_parts):
            chunk = ids[part * chunk_size: (part + 1) * chunk_size]
            if not chunk:
                break
            async with client.conversation("EvirmaBot") as conv:
                for idx in chunk:
                    try:
                        start_time = time.perf_counter()
                        await conv.send_message(str(idx))
                        await asyncio.wait_for(conv.get_response(), timeout=10)
                        response = await asyncio.wait_for(conv.get_response(), timeout=30)
                        price = re.search(r"—\s*СПП:\s*(\d+%)", response.message)
                        if not price:
                            raise Exception("Не удалось получить данные")
                        spp[idx] = price.group(1)
                        response_time = time.perf_counter() - start_time
                        print('==' * 25, response_time, '==' * 25)
                    except asyncio.TimeoutError:
                        logger.exception("Нет ответа от бота (таймаут)")
                        error_list.append(idx)
                    except errors.FloodWaitError as e:
                        await asyncio.sleep(e.seconds)
                        logger.exception(f"FloodWait: ожидаем {e.seconds} секунд.")
                        error_list.append(idx)
                    except Exception as e:
                        logger.exception(f"Ошибка: {str(e)}")
                        error_list.append(idx)

            completed = part + 1
            visual_completed = round((completed / total_parts) * visual_parts)
            progress_bar = '#' * visual_completed + '.' * (visual_parts - visual_completed)
            progress_percent = int((completed / total_parts) * 100)
            text = f"{progress_bar} {progress_percent}%"
            await bot.delete_message(user_id, message_id)
            message_id = (await safe_send_message(bot, user_id, text=text)).message_id

        if error_list:
            to_del = await safe_send_message(bot, user_id, text='Извините, небольшая задержка...')
            async with client.conversation("EvirmaBot") as conv:
                for idx in error_list:
                    try:
                        await conv.send_message(str(idx))
                        response = await asyncio.wait_for(conv.get_response(), timeout=10)
                        spp[idx] = response
                    except asyncio.TimeoutError:
                        logger.exception("Нет ответа от бота (таймаут)")
                        spp[idx] = None
                    except errors.FloodWaitError as e:
                        await asyncio.sleep(e.seconds)
                        logger.exception(f"FloodWait: ожидаем {e.seconds} секунд.")
                        spp[idx] = None
                    except Exception as e:
                        logger.exception(f"Ошибка: {str(e)}")
                        spp[idx] = None
            if to_del:
                await bot.delete_message(user_id, to_del.message_id)
            await bot.delete_message(user_id, message_id)

    return spp


async def get_spp(ids: list, user_id: int) -> dict:
    res = {}
    key = (await get_user(user_id)).api_key
    headers = {
        'Authorization': f'Bearer {key}'
    }
    url = f"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1000"
    try:
        response = requests.get(url, headers=headers)
    except requests.exceptions.RequestException as e:
        logger.exception(f"Ошибка при запросе к {url}:\n{e}")
        await safe_send_message(bot, user_id, 'Ошибка при получении СПП')
        return res
    if response.status_code != 200:
        if response.status_code == 401:
            logger.exception("Пользователь не авторизован (401).")
            await safe_send_message(bot, user_id, 'Ошибка при получении СПП, ващ ключ устарел, укажите новый')
        elif response.status_code == 429:
            logger.exception("Слишком много запросов (429).")
            await safe_send_message(bot, user_id, 'Ошибка при получении СПП, попробуйте позже')
        else:
            logger.exception(f"Неожиданный статус код: {response.status_code}")
            await safe_send_message(bot, user_id, 'Ошибка при получении СПП')
        return res
    start_time = time.perf_counter()
    df = pd.DataFrame(response.json()['data']['listGoods'])
    good, retry, all = [], [], {int(row['nmID']): int(row['sizes'][0].get('discountedPrice'))
    for _, row in df.iterrows()}
    for el in ids:
        if el in all.keys():
            url = f'https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-3339985&hide_dtype=13&spp=30&ab_testing=false&lang=ru&nm={el}'
            try:
                response = requests.get(url)
            except requests.exceptions.RequestException as e:
                logger.exception(f"Ошибка при запросе к {url}:\n{e}")
                res[el] = 'Не удалось получить СПП'
                continue
            before = all[el]
            if before == 0:
                res[el] = 'Не удалось получить СПП'
                continue
            if response.status_code == 200:
                try:
                    after = int(response.json()['data']['products'][0]['sizes'][0]['price']['total'] / 100)
                except Exception as e:
                    res[el] = 'Товара нет в наличии'
                    continue
                res[el] = 100 - int((after / before)*100)
            else:
                res[el] = 'Не удалось получить СПП'
        else:
            retry.append(el)
    cur_timer = time.perf_counter() - start_time
    if cur_timer <= 10:
        await asyncio.sleep(10-cur_timer)
    chunks = [retry[i:i + 6] for i in range(0, len(retry), 6)]
    for chunk in chunks:
        start_time = time.perf_counter()
        for el in chunk:
            url = f"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1&filterNmID={el}"
            try:
                response = requests.get(url, headers=headers)
            except requests.exceptions.RequestException as e:
                logger.exception(f"Ошибка при запросе к {url}:\n{e}")
                res[el] = 'Не удалось получить СПП'
                continue
            if response.status_code != 200:
                if response.status_code == 401:
                    logger.exception(f"Пользователь не авторизован (401) для {el}.")
                elif response.status_code == 429:
                    logger.exception(f"Слишком много запросов (429) для {el}.")
                else:
                    logger.exception(f"Неожиданный статус код: {response.status_code} для {el}")
                res[el] = 'Не удалось получить СПП'
                continue
            url1 = f'https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-3339985&hide_dtype=13&spp=30&ab_testing=false&lang=ru&nm={el}'
            try:
                response1 = requests.get(url1, headers={})
            except requests.exceptions.RequestException as e:
                logger.exception(f"Ошибка при запросе к {url1}:\n{e}")
                res[el] = 'Не удалось получить СПП'
                continue
            if response1.status_code == 200:
                before = int(response.json()['data']['listGoods'][0]['sizes'][0]['discountedPrice'])
                if before == 0:
                    res[el] = 'Не удалось получить СПП'
                    continue
                try:
                    after = int(response1.json()['data']['products'][0]['sizes'][0]['price']['total'] / 100)
                except Exception as e:
                    res[el] = 'Товара нет в наличии'
                    continue
                res[el] = 100 - int((after / before)*100) if after != 0 else 0
            else:
                res[el] = 'Не удалось получить СПП'
        cur_timer = time.perf_counter() - start_time
        if cur_timer <= 11:
            await asyncio.sleep(11 - cur_timer)

    return res


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
    waiting_spp = State()


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
async def add_spp(message: Message, state: FSMContext):
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD")
        return
    await state.update_data(second_date=message.text)
    await safe_send_message(bot, message, text="Добавить СПП к отсчету?\nЭто займет дополнительное время",
                            reply_markup=get_app_ikb())
    await state.set_state(Report.waiting_spp)


@router.callback_query(lambda c: c.data and c.data.startswith("spp"))
async def second_date(callback: CallbackQuery, state: FSMContext):
    flag = callback.data.split(':')[1]
    user = await get_user(callback.from_user.id)
    if not user.api_key:
        await safe_send_message(bot, callback, text="Необходимо добавить ключ доступа")
        return
    date_to = (await state.get_data()).get('second_date')
    date_from = (await state.get_data()).get('first_date')
    msg = await safe_send_message(bot, callback, text="Отчет формируется, пожалуйста подождите, это займет пару минут")
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage?dateFrom={date_from}&dateTo={date_to}'
    headers = {
        'Authorization': f'Bearer {user.api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        if response.status_code == 401:
            await safe_send_message(bot, callback, text="Недействительный ключ")
        elif response.status_code == 400:
            await safe_send_message(bot, callback, text="Неправильный формат данных")
        else:
            await safe_send_message(bot, callback, text="Ошибка при запросе")
        await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
        return
    task_id = response.json()['data']['taskId']
    data = await fetch_data(task_id, headers, bot, callback, msg, user)
    if data is not None:
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
        await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
        if flag == 'yes':
            await bot.send_document(chat_id=user.id, document=temp_file, caption="Отчет без СПП, готовлю с ним")
        else:
            await bot.send_document(chat_id=user.id, document=temp_file, caption="Отчет готов")

    if flag == 'yes':
        ids = list(int(el) for el in df['nmId'].unique())
        to_del = (await safe_send_message(bot, callback,
                                          text=f'Ожидаемое время получения - {int(len(ids) * 0.6)} секунд')).message_id
        spp = await get_spp(ids, user.id)

        df['spp'] = df['nmId'].map(spp)

        with io.BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                worksheet = writer.sheets["Sheet1"]
                for idx, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                    worksheet.set_column(idx, idx, max_len)
            buffer.seek(0)
            temp_file = BufferedInputFile(buffer.read(), filename="report.xlsx")
            await bot.delete_message(chat_id=user.id, message_id=to_del)
            await bot.send_document(chat_id=user.id, document=temp_file, caption="Отчет готов")

    await state.clear()


@router.callback_query(F.data == 'cancel')
async def cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_send_message(bot, callback, 'Отменено')
    await state.clear()


class SPP(StatesGroup):
    waiting_list = State()


@router.message(F.text == 'Получить SPP' or Command('spp'))
async def cmd_spp(message: Message, state: FSMContext):
    await safe_send_message(bot, message, text="Отправьте список артикулов через перевод строки",
                            reply_markup=get_cancel_ikb())
    await state.set_state(SPP.waiting_list)


@router.message(SPP.waiting_list)
async def spp_list(message: Message, state: FSMContext):
    try:
        ids = message.text.split('\n')
        ids = [int(i) for i in ids]
    except Exception as e:
        await safe_send_message(bot, message, text="Необходимо указать список артикулов через перевод строки")
        return
    to_del = (await safe_send_message(bot, message, text=f'Ожидаемое время получения - {int(len(ids)*0.6)} секунд')).message_id
    spp = await get_spp(ids, message.from_user.id)
    text = ''.join(f"{key} - {val}\n" for key, val in spp.items())
    await bot.delete_message(chat_id=message.chat.id, message_id=to_del)
    await safe_send_message(bot, message, text=text)
    await state.clear()
