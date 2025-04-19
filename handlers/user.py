import asyncio
import datetime
import json
import re
import tempfile

from aiogram.filters import Command, CommandStart, StateFilter
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from keyboards.keyboards import get_cancel_ikb, get_app_ikb, get_input_format_ikb, get_output_format_ikb, get_main_kb
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


async def get_spp(ids: list, user_id: int) -> dict:
    res = {}
    user = await get_user(user_id)
    if not user:
        logger.exception(f"Uncorrect user data")
        return res
    key = user.api_key
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
                res[el] = 100 - int((after / before) * 100)
            else:
                res[el] = 'Не удалось получить СПП'
        else:
            retry.append(el)
    cur_timer = time.perf_counter() - start_time
    if cur_timer <= 10:
        await asyncio.sleep(10 - cur_timer)
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
                before = int(response.json()['data']['listGoods'][0]['sizes'][0][
                                 'discountedPrice'])  # TODO: list index out of range
                if before == 0:
                    res[el] = 'Не удалось получить СПП'
                    continue
                try:
                    after = int(response1.json()['data']['products'][0]['sizes'][0]['price']['total'] / 100)
                except Exception as e:
                    res[el] = 'Товара нет в наличии'
                    continue
                res[el] = 100 - int((after / before) * 100) if after != 0 else 0
            else:
                res[el] = 'Не удалось получить СПП'
        cur_timer = time.perf_counter() - start_time
        if cur_timer <= 11:
            await asyncio.sleep(11 - cur_timer)

    return res


async def send_spp(user_id: int, spp: dict, output_format: str, to_del: int, msg_id: int = None, df: pd.DataFrame = None):
    if output_format == 'list':
        texts = []
        text, cnt = '', 0
        for key, val in spp.items():
            if cnt >= 120:
                texts.append(text)
                text, cnt = '', 0
            text += f"{key} - {val}\n"
            cnt += 1
        texts.append(text)

        await bot.delete_message(chat_id=user_id, message_id=to_del)
        if msg_id:
            await bot.delete_message(chat_id=user_id, message_id=msg_id)
        for text in texts:
            await safe_send_message(bot, user_id, text=text)
    elif output_format == 'xlsx':
        if df is not None:
            df['Value'] = df['nmId'].map(spp)
            with io.BytesIO() as buffer:
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Sheet1")
                    worksheet = writer.sheets["Sheet1"]
                    for idx, col in enumerate(df.columns):
                        max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                        worksheet.set_column(idx, idx, max_len)
                buffer.seek(0)
                temp_file = BufferedInputFile(buffer.read(), filename="report.xlsx")
                await bot.delete_message(chat_id=user_id, message_id=to_del)
                if msg_id:
                    await bot.delete_message(chat_id=user_id, message_id=msg_id)
                await bot.send_document(chat_id=user_id, document=temp_file, caption="Отчет готов",
                                        reply_markup=get_main_kb())
        else:
            df = pd.DataFrame(list(spp.items()), columns=['nmId', 'Value'])
            with io.BytesIO() as buffer:
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Sheet1")
                    worksheet = writer.sheets["Sheet1"]
                    for idx, col in enumerate(df.columns):
                        max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                        worksheet.set_column(idx, idx, max_len)
                buffer.seek(0)
                temp_file = BufferedInputFile(buffer.read(), filename="report.xlsx")
                await bot.delete_message(chat_id=user_id, message_id=to_del)
                if msg_id:
                    await bot.delete_message(chat_id=user_id, message_id=msg_id)
                await bot.send_document(chat_id=user_id, document=temp_file, caption="Отчет готов",
                                        reply_markup=get_main_kb())


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
        await safe_send_message(bot, message, text="Укажите дату начала отчета в формате YYYY-MM-DD\n"
                                                   "Помните, что период не может превышать неделю")
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
        await bot.send_document(chat_id=message.chat.id, document=temp_file, caption="Отчет готов",
                                reply_markup=get_main_kb())


@router.message(Report.waiting_first_date)
async def first_date(message: Message, state: FSMContext):
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD")
        await state.clear()
        return
    await state.update_data(first_date=message.text)
    await safe_send_message(bot, message, text="Укажите дату конца отчета в формате YYYY-MM-DD\n"
                                               "Помните, что период не может превышать неделю")
    await state.set_state(Report.waiting_second_date)


@router.message(Report.waiting_second_date)
async def add_spp(message: Message, state: FSMContext):
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD")
        await state.clear()
        return

    user = await get_user(message.from_user.id)
    if not user.api_key:
        await safe_send_message(bot, message, text="Необходимо добавить ключ доступа")
        await state.clear()
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
        await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
        await state.clear()
        return
    task_id = response.json()['data']['taskId']
    data = await fetch_data(task_id, headers, bot, message, msg, user)
    if data is not None:
        df = pd.DataFrame(data)
    else:
        await safe_send_message(bot, message, 'Какая-то ошибка, попробуйте позже')
        await state.clear()
        return

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
        await bot.send_document(chat_id=user.id, document=temp_file, caption="Отчет готов",
                                reply_markup=get_main_kb())
    await state.clear()


@router.callback_query(F.data == 'cancel')
async def cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_send_message(bot, callback, 'Отменено')
    await state.clear()


class SPP(StatesGroup):
    waiting_input = State()
    waiting_output = State()
    waiting_list = State()


@router.message(F.text == 'Получить SPP' or Command('spp'))
async def cmd_spp_input(message: Message, state: FSMContext):
    await safe_send_message(bot, message,
                            text="Выберете формат предоставляемых данных",
                            reply_markup=get_input_format_ikb())
    # await state.set_state(SPP.waiting_list)
    await state.set_state(SPP.waiting_input)


@router.callback_query(StateFilter(SPP.waiting_input), lambda c: c.data and c.data.startswith("type_input_spp"))
async def cmd_spp_output(callback: CallbackQuery, state: FSMContext):
    format = callback.data.split(':')[1]
    await state.set_data({'input_format': format})
    await safe_send_message(bot, callback, text="Выберете формат предоставления СПП",
                            reply_markup=get_output_format_ikb())
    await state.set_state(SPP.waiting_output)


@router.callback_query(StateFilter(SPP.waiting_output), lambda c: c.data and c.data.startswith("type_output_spp"))
async def cmd_spp(callback: CallbackQuery, state: FSMContext):
    output_format = callback.data.split(':')[1]
    input_format = (await state.get_data()).get('input_format', '')
    user = await get_user(callback.from_user.id)
    if not user.api_key:
        await safe_send_message(bot, callback, text="Необходимо добавить ключ доступа")
        await state.clear()
        return
    if input_format == '':
        await safe_send_message(bot, callback, 'Какая то ошибка, попробуйте еще раз')
        await state.clear()
        return
    elif input_format == 'list':
        await safe_send_message(bot, callback, text="Отправьте список артикулов через перевод строки",
                                reply_markup=get_cancel_ikb())
        await state.set_data({'output_format': output_format, 'input_format': input_format})
        await state.set_state(SPP.waiting_list)
    elif input_format == 'xlsx':
        await safe_send_message(bot, callback,
                                text="Отправьте excel таблицу, содержащую столбец 'nmId' с артикулами нужных товаров",
                                reply_markup=get_cancel_ikb())
        await state.set_data({'output_format': output_format, 'input_format': input_format})
        await state.set_state(SPP.waiting_list)
    elif input_format == 'table':
        if datetime.datetime.utcnow().hour <= 14:
            date_to = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
        else:
            date_to = datetime.datetime.utcnow().date().strftime('%Y-%m-%d')
        msg = await safe_send_message(bot, callback,
                                      text="Список формируется, пожалуйста подождите, это займет пару минут")
        url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage?dateFrom={date_to}&dateTo={date_to}'
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
            await state.clear()
            return
        task_id = response.json()['data']['taskId']
        data = await fetch_data(task_id, headers, bot, callback, msg, user)
        if data is not None:
            df = pd.DataFrame(data)
        else:
            await safe_send_message(bot, callback, 'Какая-то ошибка, попробуйте позже')
            await state.clear()
            return
        if "nmId" not in df.columns:
            await safe_send_message(bot, callback,
                                    "Wildberries пока не предоставили выгрузку за сегодня, пожалуйста попробуйте позже")
            await state.clear()
            return
        ids = list(int(el) for el in df['nmId'].unique())

        to_del = (await safe_send_message(bot, user.id,
                                          text=f'Ожидаемое время получения - {int(len(ids) * 1.2)} секунд')).message_id
        spp = await get_spp(ids, user.id)
        if spp.get(0, 1) == 0:
            await safe_send_message(bot, user.id, "Неизвестная ошибка, попробуйте позже")
            await state.clear()
            return
        await send_spp(user.id, spp, output_format, to_del, msg_id=msg.message_id)
        await state.clear()


@router.message(SPP.waiting_list)
async def spp_list(message: Message, state: FSMContext):
    output_format = (await state.get_data()).get('output_format', '')
    input_format = (await state.get_data()).get('input_format', '')
    if input_format == '':
        await safe_send_message(bot, message, 'Какая то ошибка, попробуйте еще раз')
        await state.clear()
        return
    elif input_format == 'list':
        try:
            ids = message.text.split('\n')
            ids = [int(i) for i in ids]
        except Exception as e:
            await safe_send_message(bot, message, text="Необходимо указать список артикулов через перевод строки")
            await state.clear()
            return
    elif input_format == 'xlsx':
        if not message.document:
            await safe_send_message(bot, message, "Пожалуйста, отправьте Excel файл.")
            await state.clear()
            return
        file_info = message.document
        file_id = file_info.file_id
        try:
            telegram_file = await message.bot.get_file(file_id)
            file_buffer = io.BytesIO()
            await message.bot.download_file(telegram_file.file_path, destination=file_buffer)
            file_buffer.seek(0)
        except Exception as e:
            print('=='*50, '\n', e)
            await safe_send_message(bot, message, "Ошибка при загрузке файла. Попробуйте позже.")
            await state.clear()
            return
        try:
            df = pd.read_excel(file_buffer)
        except Exception as e:
            await safe_send_message(bot, message, "Ошибка при чтении Excel файла. Убедитесь, что файл корректный.")
            await state.clear()
            return
        if "nmId" not in df.columns:
            await safe_send_message(bot, message, "Столбец 'nmId' отсутствует в файле.")
            await state.clear()
            return
        ids = list(int(el) for el in df['nmId'].unique())

    to_del = (await safe_send_message(bot, message,
                                      text=f'Ожидаемое время получения - {int(len(ids) * 1.2)} секунд')).message_id
    spp = await get_spp(ids, message.from_user.id)
    if spp.get(0, 1) == 0:
        await safe_send_message(bot, message, "Неизвестная ошибка, попробуйте позже")
        await state.clear()
        return
    if input_format == 'xlsx':
        await send_spp(message.from_user.id, spp, output_format, to_del, df=df)
    else:
        await send_spp(message.from_user.id, spp, output_format, to_del)
    await state.clear()
