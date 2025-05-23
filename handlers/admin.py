import asyncio
from datetime import date, datetime as dt
from aiogram.filters import Command
from aiogram import Router
from aiogram.types import Message

from handlers.errors import safe_send_message
from instance import bot, scheduler
from database.req import *


router = Router()


async def deactivate_sub(uric_name):
    await pay_sub(uric_name, SubsribeStatus.INACTIVE, None)
    owner_id = (await get_uric(uric_name)).owner_id
    await safe_send_message(bot, owner_id, f'Ваша подписка для {uric_name} закончилась!')


def schedule_deactivation(uric_name: str, exp_date: date):
    run_date = dt.combine(exp_date, dt.min.time())
    job_id = f"deactivate_{uric_name}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        lambda: asyncio.create_task(deactivate_sub(uric_name)),
        'date',
        run_date=run_date,
        id=job_id,
        replace_existing=True
    )


@router.message(Command('pay'))  # /pay uric_name subscribe exp_date(yyyy.mm.dd)
async def pay(message: Message):
    """
    Обработчик команды /pay.
    """
    user = await get_user(message.from_user.id)
    if not user.is_superuser:
        await safe_send_message(bot, message.from_user.id, 'У вас нет прав для выполнения этой команды.')
        return
    uric_name, subscribe, exp_date = message.text.split()[1:]
    if subscribe == 'active':
        subscribe = SubsribeStatus.ACTIVE
    else:
        await safe_send_message(bot, message.from_user.id, 'Некорректный статус подписки.')
        return
    owner_id = (await get_uric(uric_name)).owner_id
    year, month, day = exp_date.split('.')
    exp_date_obj = date(int(year), int(month), int(day))
    await pay_sub(uric_name, subscribe, exp_date_obj)
    schedule_deactivation(uric_name, exp_date_obj)
    await safe_send_message(bot, message.from_user.id, 'Готово')
    await safe_send_message(bot, owner_id, f'Подписка для {uric_name} активирована до {exp_date}!')
