import asyncio
import time
from random import randint

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from confige import BotConfig
from database.req import *
from handlers import errors, user
from instance import bot
from database.models import async_main


def register_routers(dp: Dispatcher) -> None:
    dp.include_routers(errors.router, user.router)


async def main() -> None:
    await async_main()

    config = BotConfig(
        admin_ids=[],
        welcome_message=""
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["config"] = config

    register_routers(dp)

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as _ex:
        print(f'Exception: {_ex}')


if __name__ == '__main__':
    asyncio.run(main())
