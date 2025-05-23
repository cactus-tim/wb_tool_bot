import asyncio
import datetime
import json
import re
import tempfile

from aiogram.filters import Command, CommandStart, StateFilter, CommandObject
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import requests
import io
import pandas as pd
import time

from handlers.errors import safe_send_message
from handlers.inner_func import fetch_data, get_spp, send_spp, get_all_ids
from handlers.texts import text_info
from keyboards.keyboards import get_cancel_ikb, get_input_format_ikb, get_output_format_ikb, get_main_kb, get_func_kb, \
    get_settings_kb
from instance import bot, logger
from database.req import *

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    """
    Обработчик команды /start. Проверяет наличие пользователя в базе данных и отправляет приветственное сообщение.
    """
    hash_value = command.args
    user = await get_user(message.from_user.id)
    if hash_value:
        if not user:
            await create_user(message.from_user.id)
        uric = await get_uric_by_hash(hash_value)
        if not uric:
            await safe_send_message(bot, message, text='Привет, ссылка недействительна, обратитесь к отправителю')
            return
        await update_user(message.from_user.id, uric.name)
        user_uric = await get_user_uric(message.from_user.id, uric.name)
        if user_uric:
            await safe_send_message(bot, message, text='Привет, вы уже добавлены в компанию')
            return
        await add_user_uric(message.from_user.id, uric.name)
        await safe_send_message(bot, message, text=f"Привет, вы добавлены как сотрудник компании {uric.name}.\n",
                                reply_markup=get_main_kb(uric.name))
    else:
        if not user:
            await create_user(message.from_user.id)
        await safe_send_message(bot, message, text="Привет! Это бот для автоматизации работы с Wildberries. "
                                                   "Мы поможем тебе упростить работу с этой платформой.\n"
                                                   "Что бы получше познакомится с нами используй "
                                                   "<pre><code>/info</code></pre>\n"
                                                   "А что бы начать использование <pre><code>/help</code></pre>")


@router.message(Command('info'))
async def cmd_info(message: Message):
    """
    Обработчик команды /info. Отправляет пользователю информацию о боте и его функционале.
    """
    await safe_send_message(bot, message, text=text_info)


@router.message(Command('help'))
async def cmd_help(message: Message):
    """
    Обработчик команды /help. Отправляет пользователю информацию о боте и его функционале.
    """
    cur_uric = (await get_user(message.from_user.id)).cur_uric
    await safe_send_message(
        bot, message,
        text="Ты попал в главное меню, тут ты можешь выбрать от какого юр лица будешь работать, "
             "а если у тебя ещё их нет, то можешь создать!\nВ одной из кнопок меню ты найдешь полную инструкцию.",
        reply_markup=get_main_kb(cur_uric)
    )


@router.message(F.text.startswith('Продолжить с'))
async def cmd_func_menu(message: Message):
    """
    Обработчик нажатия кнопки "Продолжить с [название юрлица]". Отправляет пользователю меню действий с юр лицом.
    """
    cur_uric = message.text.split(' ')[2:][0]
    await safe_send_message(
        bot, message,
        text=(
            f"Вы выбрали юр. лицо: {cur_uric}\n"
            "Чтобы начать работу, выберите нужный пункт меню.\n"
        ),
        reply_markup=get_func_kb()
    )


@router.message(F.text == 'Назад в главное меню')
async def back_to_main_menu(message: Message):
    """
    Обработчик нажатия кнопки "Назад в главное меню". Отправляет пользователю главное меню.
    """
    cur_uric = (await get_user(message.from_user.id)).cur_uric
    await safe_send_message(
        bot, message,
        text=(
            f"Вы вернулись в главное меню.\n"
            "Чтобы начать работу, выберите нужный пункт меню.\n"
        ),
        reply_markup=get_main_kb(cur_uric)
    )


@router.message(F.text == 'Настройки Юр лица')
async def uric_settings(message: Message):
    """
    Обработчик нажатия кнопки "Настройки Юр лица". Отправляет пользователю меню настроек юр лица.
    """
    cur_uric = (await get_user(message.from_user.id)).cur_uric
    is_owner = (await get_uric(cur_uric)).owner_id == message.from_user.id
    await safe_send_message(
        bot, message,
        text=(
            f"Выберите действие с юр. лицом: {cur_uric}\n"
            "Чтобы начать работу, выберите нужный пункт меню.\n"
        ),
        reply_markup=get_settings_kb(is_owner)
    )


@router.message(F.text == 'Назад')
async def back_to_func_menu(message: Message):
    """
    Обработчик нажатия кнопки "Назад". Отправляет пользователя обратно в меню действий с юр лицом.
    """
    cur_uric = (await get_user(message.from_user.id)).cur_uric
    await safe_send_message(
        bot, message,
        text=(
            f"Вы вернулись в меню действий с юр. лицом: {cur_uric}\n"
            "Чтобы начать работу, выберите нужный пункт меню.\n"
        ),
        reply_markup=get_func_kb()
    )


@router.callback_query(lambda c: c.data and c.data.startswith("cancel"))
async def cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    reply_kb = callback.data.split(':')[1]
    if reply_kb == 'func':
        await safe_send_message(bot, callback, 'Отменено', reply_markup=get_func_kb())
    elif reply_kb == 'main':
        await safe_send_message(bot, callback, 'Отменено',
                                reply_markup=get_main_kb((await get_user(callback.from_user.id)).cur_uric))
    elif reply_kb == 'settings':
        await safe_send_message(bot, callback, 'Отменено',
                                reply_markup=get_settings_kb(
                                    (await get_uric((await get_user(callback.from_user.id)).cur_uric)).owner_id ==
                                    callback.from_user.id))
    await state.clear()
