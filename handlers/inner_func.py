import asyncio
import json
import logging

from aiogram.types import BufferedInputFile
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message, ping_tg
from keyboards.keyboards import get_main_kb, get_func_kb
from instance import bot, wb_discounts_semaphore, get_next_proxy
from database.req import *

logger = logging.getLogger(__name__)


async def send_df(bot, user, df: pd.DataFrame, base_filename: str = "report.xlsx", chunk_size: int = 10000):
    """
    Асинхронно отправляет DataFrame. Если строк меньше или равно chunk_size — Excel-файл,
    иначе — CSV-файл. Запись в файловый буфер выполняется в фоновом потоке,
    чтобы не блокировать event loop.
    """
    total_rows = len(df)
    if total_rows == 0:
        return  # Нечего отправлять

    chat_id = user.id if hasattr(user, "id") else user

    def _build_excel_bytes(dataframe: pd.DataFrame) -> tuple[bytes, str]:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="Sheet1")
            worksheet = writer.sheets["Sheet1"]
            for idx, col in enumerate(dataframe.columns):
                max_len = max(dataframe[col].astype(str).map(len).max(), len(str(col))) + 2
                worksheet.set_column(idx, idx, max_len)
        buf.seek(0)
        fname = base_filename
        if not fname.lower().endswith('.xlsx'):
            fname += '.xlsx'
        return buf.read(), fname

    def _build_csv_bytes(dataframe: pd.DataFrame) -> tuple[bytes, str]:
        csv_data = dataframe.to_csv(index=False).encode('utf-8')
        fname_root = base_filename.rsplit('.', 1)[0] if '.' in base_filename else base_filename
        return csv_data, f"{fname_root}.csv"

    if total_rows <= chunk_size:
        # Генерируем Excel в отдельном потоке
        content, filename = await asyncio.to_thread(_build_excel_bytes, df)
        temp_file = BufferedInputFile(content, filename=filename)
        await bot.send_document(
            chat_id=chat_id,
            document=temp_file,
            caption="Отчет",
            reply_markup=get_func_kb()
        )
    else:
        # Генерируем CSV в отдельном потоке
        content, filename = await asyncio.to_thread(_build_csv_bytes, df)
        temp_file = BufferedInputFile(content, filename=filename)
        await bot.send_document(
            chat_id=chat_id,
            document=temp_file,
            caption="Отчет (CSV)",
            reply_markup=get_func_kb()
        )


async def fetch_data(task_id, headers, bot, msg, user, max_retries=3):
    """
    Внутренняя функция для получения данных с API Wildberries с обработкой ошибок и повторными попытками,
    в том числе при кодах ответа != 200.

    :param task_id: номер задачи в системе Wildberries
    :param headers: заголовки для запроса
    :param bot: экземпляр бота
    :param msg: сообщение, которое нужно удалить после завершения
    :param user: пользователь, которому отправляется сообщение об ошибке
    :param max_retries: максимальное кол-во попыток
    :return: json с данными или None
    """
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage/tasks/{task_id}/download'

    for attempt in range(max_retries):
        # задержка перед запросом: 10 с. перед первой, 70 с. перед последующими
        await asyncio.sleep(10 if attempt == 0 else 70)

        try:
            response = requests.get(url, headers=headers, stream=True, timeout=(5, 30))

            if response.status_code != 200:
                # если не последний заход — повторяем
                if attempt < max_retries - 1:
                    continue
                # если последняя попытка — сообщаем об ошибке и выходим
                try:
                    error_data = response.json()
                except Exception:
                    error_data = response.text
                await safe_send_message(bot, user.id, text=f"Ошибка при запросе {response.status_code}: {error_data}",
                                        reply_markup=get_func_kb())
                await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
                return None

            # успешный ответ — разбираем тело
            if 'chunked' in response.headers.get('Transfer-Encoding', '').lower():
                content_bytes = b""
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        content_bytes += chunk
                data = json.loads(content_bytes.decode('utf-8'))
            else:
                data = response.json()

            return data

        except requests.exceptions.ChunkedEncodingError as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            await safe_send_message(bot, user.id, text=f"Ошибка соединения при получении чанков: {e}",
                                    reply_markup=get_func_kb())
            await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
            return None

        except Exception as e:
            # любая другая непредвиденная ошибка — не пытаемся повторить
            await safe_send_message(bot, user.id, text=f"Произошла ошибка: {e}", reply_markup=get_func_kb())
            await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
            return None

    # все попытки исчерпаны без успешного ответа
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
    key = (await get_uric(user.cur_uric)).api_key
    headers = {
        'Authorization': f'Bearer {key}'
    }
    offset = 0
    # бежим в цикле и забираем все товары которые есть у продавца, оставляем либо артикулы, либо артикулы и цены
    while True:
        url = f"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1000&offset={offset}"
        response = None
        for attempt in range(5):
            logger.info(f"[get_all_ids] user={user_id} offset={offset} attempt={attempt+1} (no proxy — official API)")
            try:
                async with wb_discounts_semaphore:
                    await asyncio.sleep(11)
                    t0 = time.perf_counter()
                    response = requests.get(url, headers=headers, timeout=15)
                    elapsed = time.perf_counter() - t0
                logger.info(f"[get_all_ids] status={response.status_code} elapsed={elapsed:.2f}s")
            except requests.exceptions.RequestException as e:
                logger.error(f"[get_all_ids] RequestException: {e}")
                await safe_send_message(bot, user_id, 'Ошибка при получении СПП', reply_markup=get_func_kb())
                return all if return_dict else res
            if response.status_code == 429:
                wait = 2 ** attempt * 5
                logger.warning(f"[get_all_ids] 429 → ждём {wait}с (попытка {attempt+1}/5)")
                await asyncio.sleep(wait)
                continue
            break
        if response is None or response.status_code != 200:
            if response is not None and response.status_code == 401:
                logger.error(f"[get_all_ids] 401 — ключ устарел, user={user_id}")
                await safe_send_message(bot, user_id, 'Ошибка при получении СПП, ващ ключ устарел, укажите новый',
                                        reply_markup=get_func_kb())
            elif response is not None and response.status_code == 429:
                logger.error(f"[get_all_ids] 429 — все {5} попытки исчерпаны, user={user_id}")
                await safe_send_message(bot, user_id, 'Ошибка при получении СПП, попробуйте позже',
                                        reply_markup=get_func_kb())
            else:
                code = response.status_code if response else 'None'
                logger.error(f"[get_all_ids] неожиданный статус {code}, user={user_id}")
                await safe_send_message(bot, user_id, 'Ошибка при получении СПП', reply_markup=get_func_kb())
            return all if return_dict else res
        df = pd.DataFrame(response.json()['data']['listGoods'])

        part_res = [int(row['nmID']) for _, row in df.iterrows()]
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
    key = (await get_uric(user.cur_uric)).api_key
    headers = {
        'Authorization': f'Bearer {key}'
    }
    wb_card_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    }
    # Получаем все товары юр лица с ценами из официального API
    all = await get_all_ids(user_id, return_dict=True)
    # Делим ids на найденные в юр лице и те, которых нет
    ids_in_uric = [el for el in ids if el in all]
    retry = [el for el in ids if el not in all]

    # Батчами по 20 артикулов за запрос к card.wb.ru
    CARD_BATCH = 20
    for i in range(0, len(ids_in_uric), CARD_BATCH):
        batch = ids_in_uric[i:i + CARD_BATCH]
        nm_param = ';'.join(str(x) for x in batch)
        url = f'https://card.wb.ru/cards/v4/detail?nm={nm_param}&dest=-337422&locale=ru'
        await asyncio.sleep(1)
        proxy = get_next_proxy()
        proxy_label = list(proxy.values())[0] if proxy else 'NO PROXY'
        logger.info(f"[get_spp card] batch={len(batch)} ids={batch[:2]}... proxy={proxy_label}")
        try:
            t0 = time.perf_counter()
            response = requests.get(url, headers=wb_card_headers, timeout=10, proxies=proxy)
            elapsed = time.perf_counter() - t0
            logger.info(f"[get_spp card] status={response.status_code} elapsed={elapsed:.2f}s")
        except requests.exceptions.RequestException as e:
            logger.error(f"[get_spp card] RequestException: {e}")
            for el in batch:
                res[el] = 'Не удалось получить СПП'
            continue
        if response.status_code != 200:
            logger.warning(f"[get_spp card] статус {response.status_code} batch={batch[:2]}...")
            for el in batch:
                res[el] = 'Не удалось получить СПП'
            continue
        # Разбираем ответ: products — список товаров в том же порядке
        products_map = {}
        try:
            for product in response.json().get('products', []):
                nm_id = int(product['id'])
                after = 0
                for ell in product.get('sizes', []):
                    if ell.get('price', 0):
                        after = int(ell['price']['product'] / 100)
                products_map[nm_id] = after
        except Exception as e:
            logger.exception(f"Ошибка при разборе ответа card.wb.ru: {e}")
        for el in batch:
            before = all.get(el, 0)
            if before == 0:
                res[el] = 'Не удалось получить СПП'
                continue
            after = products_map.get(el, 0)
            if after == 0:
                res[el] = 'Товара нет в наличии'
                continue
            spp_val = int(100 - (after / before) * 100)
            res[el] = spp_val if spp_val > 0 else 0
    # если остались товары, которые не нашли в базе, то делаем запросы к ним (вб апи + цена на сайте),
    # бьем на чанки что бы не было 429
    chunks = [retry[i:i + 6] for i in range(0, len(retry), 6)]
    for chunk in chunks:
        start_time = time.perf_counter()
        for el in chunk:
            url = f"https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter?limit=1&filterNmID={el}"
            response = None
            for attempt in range(5):
                logger.info(f"[get_spp retry] nm={el} attempt={attempt+1} (no proxy — official API)")
                try:
                    async with wb_discounts_semaphore:
                        await asyncio.sleep(11)
                        t0 = time.perf_counter()
                        response = requests.get(url, headers=headers, timeout=15)
                        elapsed = time.perf_counter() - t0
                    logger.info(f"[get_spp retry] nm={el} status={response.status_code} elapsed={elapsed:.2f}s")
                except requests.exceptions.RequestException as e:
                    logger.error(f"[get_spp retry] nm={el} RequestException: {e}")
                    break
                if response.status_code == 429:
                    wait = 2 ** attempt * 5
                    logger.warning(f"[get_spp retry] nm={el} 429 → ждём {wait}с (попытка {attempt+1}/5)")
                    await asyncio.sleep(wait)
                    continue
                break
            if response is None or response.status_code != 200:
                code = response.status_code if response else 'None'
                logger.error(f"[get_spp retry] nm={el} финальный статус {code}, пропускаем")
                res[el] = 'Не удалось получить СПП'
                continue
            proxy2 = get_next_proxy()
            url1 = f'https://card.wb.ru/cards/v4/detail?nm={el}&dest=-337422&locale=ru'
            proxy2_label = list(proxy2.values())[0] if proxy2 else 'NO PROXY'
            logger.info(f"[get_spp retry] card.wb.ru nm={el} proxy={proxy2_label}")
            try:
                response1 = requests.get(url1, headers=wb_card_headers, timeout=10, proxies=proxy2)
            except requests.exceptions.RequestException as e:
                logger.error(f"[get_spp retry] card.wb.ru nm={el} RequestException: {e}")
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
                    after = 0
                    for ell in response1.json()['products'][0]['sizes']:
                        if ell.get('price', 0):
                            if after != 0 and after != int(ell['price']['product'] / 100):  # TODO: after test del it
                                await ping_tg(f"find diff sizes price for {el}")
                            after = int(ell['price']['product'] / 100)
                            # break TODO: after test return it
                except Exception as e:
                    res[el] = 'Товара нет в наличии'
                    continue
                res[el] = int(100 - (after / before) * 100) if (100 - int((after / before) * 100)) > 0 and after != 0 \
                    else 0
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
            await safe_send_message(bot, user_id, text=text, reply_markup=get_func_kb())
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
                                        reply_markup=get_main_kb((await get_user(user_id)).cur_uric))
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
                                        reply_markup=get_func_kb())
