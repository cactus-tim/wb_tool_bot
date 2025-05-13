import asyncio
import json

from aiogram.types import BufferedInputFile
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from keyboards.keyboards import get_main_kb
from instance import bot, logger
from database.req import *


async def fetch_data(task_id, headers, bot, msg, user, max_retries=3):
    """
    Внутренняя функция для получения данных с API Wildberries с обработкой ошибок и повторными попытками.
    Предусматривает сложную обработку длинных запросов

    :param task_id: номер задачи в системе Wildberries
    :param headers: заголовки для запроса
    :param bot: экземпляр бота
    :param msg: сообщение, которое нужно удалить после завершения
    :param user: пользователь, которому отправляется сообщение об ошибке
    :param max_retries: максимальное кол-во попыток
    :return: json с данными
    """
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
                await safe_send_message(bot, user.id, text=f"Ошибка при запросе {response.status_code}: {error_data}")
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
                await safe_send_message(bot, user.id, text=f"Ошибка соединения при получении чанков: {e}")
                await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
                return None
        except Exception as e:
            await safe_send_message(bot, user.id, text=f"Произошла ошибка: {e}")
            await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
            return None


async def get_all_ids(user_id: int, return_dict: bool = False):
    """
    Получение всех артикулов пользователя из базы данных Wildberries

    :param return_dict: формат ответа
    :param user_id: пользователь по которому получаем все артикулы
    :return: список или словарь {артикул:цена} артикулов
    """
    res = []
    all = {}
    user = await get_user(user_id)
    if not user:
        logger.exception(f"Uncorrect user data")
        return res
    key = user.api_key
    headers = {
        'Authorization': f'Bearer {key}'
    }
    offset = 0
    while True:
        url = f"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1000&offset={offset}"
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
        df = pd.DataFrame(response.json()['data']['listGoods'])

        part_res = [int(row['sizes'][0].get('discountedPrice')) for _, row in df.iterrows()]
        part_all = {int(row['nmID']): int(row['sizes'][0].get('discountedPrice')) for _, row in df.iterrows()}
        if not part_res:
            break
        else:
            if return_dict:
                all.update(part_all)
            else:
                res += part_res
            offset += 1000

    if return_dict:
        return all
    else:
        return res


async def get_spp(ids: list, user_id: int) -> dict:
    """
    Получение СПП на товары Wildberries по артикулам

    :param ids: список артикулов
    :param user_id: пользователь для которого получаем СПП
    :return: словарь {артикул: СПП}
    """
    res = {}
    user = await get_user(user_id)
    if not user:
        logger.exception(f"Uncorrect user data")
        return res
    key = user.api_key
    headers = {
        'Authorization': f'Bearer {key}'
    }
    start_time = time.perf_counter()
    good, retry, all = [], [], await get_all_ids(user_id, return_dict=True)
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
                    after = int(response.json()['data']['products'][0]['sizes'][0]['price']['total'] / 100)  # TODO: her problem too (set of sizes)
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
                try:
                    before = int(response.json()['data']['listGoods'][0]['sizes'][0][
                                     'discountedPrice'])
                except Exception as e:
                    res[el] = 'Товар не найден'
                    continue
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
    """
    Отправка СПП пользователю в зависимости от формата

    :param user_id: пользователь которому надо отправить СПП
    :param spp: словарь {артикул: СПП} (get_spp)
    :param output_format: формат отправки (list или xlsx)
    :param to_del: id сообщения, которое нужно удалить
    :param msg_id: id сообщения, которое нужно удалить (если есть)
    :param df: таблица с данными (если есть)
    """
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
