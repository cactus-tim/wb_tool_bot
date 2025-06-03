from aiogram.filters import StateFilter
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from handlers.inner_func import fetch_data, get_spp, send_spp, get_all_ids
from keyboards.keyboards import get_cancel_ikb, get_input_format_ikb, get_output_format_ikb, get_func_kb
from instance import bot
from database.req import *


router = Router()


class Report(StatesGroup):
    waiting_first_date = State()
    waiting_second_date = State()
    waiting_spp = State()


@router.message(F.text == 'Получить отчет')
async def cmd_report(message: Message, state: FSMContext):
    """
    Функция для обработки команды "Получить отчет"
    """
    uric_name = (await get_user(message.from_user.id)).cur_uric
    subsribe = (await get_uric(uric_name)).subsribe
    if subsribe == SubsribeStatus.INACTIVE:
        await safe_send_message(bot, message, 'У вас не оплачена подписка для этой услуги(', get_func_kb())
        return
    msg = await safe_send_message(bot, message, 'Загрузка...', reply_markup=ReplyKeyboardRemove())
    await msg.delete()
    await safe_send_message(bot, message, text="Укажите дату начала отчета в формате YYYY-MM-DD\n"
                                               "Помните, что период не может превышать неделю",
                            reply_markup=get_cancel_ikb('func'))
    await state.set_state(Report.waiting_first_date)


@router.message(Report.waiting_first_date)
async def first_date(message: Message, state: FSMContext):
    """
    Функция для обработки первой даты отчета
    """
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD",
                                reply_markup=get_cancel_ikb('func'))
        return
    await state.update_data(first_date=message.text)
    await safe_send_message(bot, message, text="Укажите дату конца отчета в формате YYYY-MM-DD\n"
                                               "Помните, что период не может превышать неделю",
                            reply_markup=get_cancel_ikb('func'))
    await state.set_state(Report.waiting_second_date)


@router.message(Report.waiting_second_date)
async def second_date(message: Message, state: FSMContext):
    """
    Функция для обработки второй даты отчета
    """
    try:
        time.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await safe_send_message(bot, message, text="Неверный формат даты, необходимо указать дату в формате YYYY-MM-DD",
                                reply_markup=get_cancel_ikb('func'))
        return

    user = await get_user(message.from_user.id)
    uric = await get_uric(user.cur_uric)
    if not uric.api_key:
        await safe_send_message(bot, message, text="Необходимо добавить ключ доступа", reply_markup=get_func_kb())
        await state.clear()
        return
    date_to = message.text
    date_from = (await state.get_data()).get('first_date')
    msg = await safe_send_message(bot, message, text="Отчет формируется, пожалуйста подождите, это займет пару минут")
    url = f'https://seller-analytics-api.wildberries.ru/api/v1/paid_storage?dateFrom={date_from}&dateTo={date_to}'
    headers = {
        'Authorization': f'Bearer {uric.api_key}'
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        if response.status_code == 401:
            await safe_send_message(bot, message, text="Недействительный ключ", reply_markup=get_func_kb())
        elif response.status_code == 400:
            await safe_send_message(bot, message, text="Неправильный формат данных", reply_markup=get_func_kb())
        else:
            await safe_send_message(bot, message, text="Ошибка при запросе", reply_markup=get_func_kb())
        await bot.delete_message(chat_id=user.id, message_id=msg.message_id)
        await state.clear()
        return
    task_id = response.json()['data']['taskId']
    data = await fetch_data(task_id, headers, bot, msg, user)
    if data is not None:
        df = pd.DataFrame(data)
    else:
        await safe_send_message(bot, message, 'Какая-то ошибка, попробуйте позже', reply_markup=get_func_kb())
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
                                reply_markup=get_func_kb())
    await state.clear()


class SPP(StatesGroup):
    waiting_input = State()
    waiting_output = State()
    waiting_list = State()


@router.message(F.text == 'Получить СПП')
async def cmd_spp_input(message: Message, state: FSMContext):
    """
    Функция для обработки команды "Получить СПП"
    """
    uric_name = (await get_user(message.from_user.id)).cur_uric
    subsribe = (await get_uric(uric_name)).subsribe
    if subsribe == SubsribeStatus.INACTIVE:
        await safe_send_message(bot, message, 'У вас не оплачена подписка для этой услуги(', get_func_kb())
        return
    msg = await safe_send_message(bot, message, 'Загрузка...', reply_markup=ReplyKeyboardRemove())
    await msg.delete()
    await safe_send_message(bot, message,
                            text="Выберете формат предоставляемых данных",
                            reply_markup=get_input_format_ikb())
    await state.set_state(SPP.waiting_input)


@router.callback_query(StateFilter(SPP.waiting_input), lambda c: c.data and c.data.startswith("type_input_spp"))
async def cmd_spp_output(callback: CallbackQuery, state: FSMContext):
    """
    Функция для обработки выбора формата предоставления данных
    """
    format = callback.data.split(':')[1]
    await state.set_data({'input_format': format})
    await safe_send_message(bot, callback, text="Выберете формат предоставления СПП",
                            reply_markup=get_output_format_ikb())
    await state.set_state(SPP.waiting_output)


@router.callback_query(StateFilter(SPP.waiting_output), lambda c: c.data and c.data.startswith("type_output_spp"))
async def cmd_spp(callback: CallbackQuery, state: FSMContext):
    """
    Функция для обработки выбора формата предоставления СПП
    + обработка формата входных данных -  выгрузка по юр лицу
    """
    output_format = callback.data.split(':')[1]
    input_format = (await state.get_data()).get('input_format', '')
    user = await get_user(callback.from_user.id)
    uric = await get_uric(user.cur_uric)
    if not uric.api_key:
        await safe_send_message(bot, callback, text="Необходимо добавить ключ доступа", reply_markup=get_func_kb())
        await state.clear()
        return
    if input_format == '':
        await safe_send_message(bot, callback, 'Какая то ошибка, попробуйте еще раз', reply_markup=get_func_kb())
        await state.clear()
        return
    elif input_format == 'list':
        await safe_send_message(bot, callback, text="Отправьте список артикулов через перевод строки",
                                reply_markup=get_cancel_ikb('func'))
        await state.set_data({'output_format': output_format, 'input_format': input_format})
        await state.set_state(SPP.waiting_list)
    elif input_format == 'xlsx':
        await safe_send_message(bot, callback,
                                text="Отправьте excel таблицу, содержащую столбец 'nmId' с артикулами нужных товаров",
                                reply_markup=get_cancel_ikb('func'))
        await state.set_data({'output_format': output_format, 'input_format': input_format})
        await state.set_state(SPP.waiting_list)
    elif input_format == 'table':
        ids = await get_all_ids(user.id)
        if not ids:
            await safe_send_message(bot, callback, 'Какая-то ошибка, попробуйте позже', reply_markup=get_func_kb())
            await state.clear()
            return

        to_del = (await safe_send_message(bot, user.id,
                                          text=f'Ожидаемое время получения - {20 + int(len(ids) * 0.25)} секунд'
                                          )).message_id
        spp = await get_spp(ids, user.id)
        if spp.get(0, 1) == 0:
            await safe_send_message(bot, user.id, "Неизвестная ошибка, попробуйте позже", reply_markup=get_func_kb())
            await state.clear()
            return
        await send_spp(user.id, spp, output_format, to_del)
        await state.clear()


@router.message(SPP.waiting_list)
async def spp_list(message: Message, state: FSMContext):
    """
    Функция для обработки списка и таблицы артикулов
    """
    output_format = (await state.get_data()).get('output_format', '')
    input_format = (await state.get_data()).get('input_format', '')
    if input_format == '':
        await safe_send_message(bot, message, 'Какая то ошибка, попробуйте еще раз', reply_markup=get_func_kb())
        await state.clear()
        return
    elif input_format == 'list':
        try:
            ids = message.text.split('\n')
            ids = [int(i) for i in ids]
        except Exception as e:
            await safe_send_message(bot, message, text="Необходимо указать список артикулов через перевод строки",
                                    reply_markup=get_cancel_ikb('func'))
            await state.clear()
            return
    elif input_format == 'xlsx':
        if not message.document:
            await safe_send_message(bot, message, "Пожалуйста, отправьте Excel файл.",
                                    reply_markup=get_cancel_ikb('func'))
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
            await safe_send_message(bot, message, "Ошибка при загрузке файла. Попробуйте позже.",
                                    reply_markup=get_func_kb())
            await state.clear()
            return
        try:
            df = pd.read_excel(file_buffer)
        except Exception as e:
            await safe_send_message(bot, message, "Ошибка при чтении Excel файла. Убедитесь, что файл корректный.",
                                    reply_markup=get_func_kb())
            await state.clear()
            return
        if "nmId" not in df.columns:
            await safe_send_message(bot, message, "Столбец 'nmId' отсутствует в файле.",
                                    reply_markup=get_func_kb())
            await state.clear()
            return
        ids = list(int(el) for el in df['nmId'].unique())

    to_del = (await safe_send_message(bot, message,
                                      text=f'Ожидаемое время получения - {20 + int(len(ids) * 0.25)} секунд'
                                      )).message_id
    spp = await get_spp(ids, message.from_user.id)
    if spp.get(0, 1) == 0:
        await safe_send_message(bot, message, "Неизвестная ошибка, попробуйте позже", reply_markup=get_func_kb())
        await state.clear()
        return
    if input_format == 'xlsx':
        await send_spp(message.from_user.id, spp, output_format, to_del, df=df)
    else:
        await send_spp(message.from_user.id, spp, output_format, to_del)
    await state.clear()
