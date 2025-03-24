from aiogram.filters import Command, CommandStart
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
    await safe_send_message(bot, message, text="")


@router.message(Command('info'))
async def cmd_info(message: Message):
    await safe_send_message(bot, message, text="Какая-то информация")


@router.message(F.text.contains("ss"))
async def ss_contains(message: Message):
    await safe_send_message(bot, message, text="Это обработчик сообщения, которое содержит 'ss'")


@router.message(Command('kb_ex'))
async def cmd_kb_ex(message: Message):
    await safe_send_message(bot, message, text='Это пример reply keyboard\nВсе кнопки отпраляются боту как сообщения',
                            reply_markup=get_some_kb())


@router.message(Command('ikb_ex'))
async def cmd_ikb_ex(message: Message):
    await safe_send_message(bot, message, text='Это пример inline keyboard\nВсе кнопки отпралвяются боту как '
                                               'callback_data', reply_markup=get_some_ikb())


@router.callback_query(F.data == "f_btn")
async def callback_data_ex1(callback: CallbackQuery):
    await safe_send_message(bot, callback, text='Это сообщение после нажатие на первую кнопку')
    await callback.answer()


@router.callback_query(F.data == "s_btn")
async def callback_data_ex1(callback: CallbackQuery):
    await safe_send_message(bot, callback, text='Это сообщение после нажатие на вторую кнопку')
    await callback.answer()


@router.callback_query(F.data == "t_btn")
async def callback_data_ex1(callback: CallbackQuery):
    await safe_send_message(bot, callback, text='Это сообщение после нажатие на третью кнопку')
    await callback.answer()


class ExState(StatesGroup):
    first_mes = State()
    second_mes = State()


@router.message(Command('state_ex'))
async def state_ex_begin(message: Message, state: FSMContext):
    await safe_send_message(bot, message, text='Это пример использования состояний\nЗагадай число')
    await state.set_state(ExState.first_mes)


@router.message(ExState.first_mes)
async def state_ex_mid(message: Message, state: FSMContext):
    await safe_send_message(bot, message, text='Теперь я тасую числа и пытаюсь тебя запутать\nЗагадай букву')
    await state.set_data({'numb': message.text})
    await state.set_state(ExState.second_mes)


@router.message(ExState.second_mes)
async def state_ex_end(message: Message, state: FSMContext):
    data = await state.get_data()
    numb = data.get('numb')
    await safe_send_message(bot, message, text=f'Твое число - {numb}')
    await state.clear()

