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
from handlers.inner_func import fetch_data, get_spp, send_spp, get_all_ids
from keyboards.keyboards import get_cancel_ikb, get_input_format_ikb, get_output_format_ikb, get_main_kb
from instance import bot, logger
from database.req import *

router = Router()


# @router.message(F.text == 'Сменить API ключ')
# @router.message(F.text == 'Статус оплаты')
# @router.message(F.text == 'Оплатить')
# @router.message(F.text == 'Добавить сотрудника')
