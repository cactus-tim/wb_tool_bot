import asyncio

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from confige import BotConfig
from handlers import errors, user, admin, main_menu, func_menu, settings_menu
from instance import bot, scheduler
from database.models import async_main


def register_routers(dp: Dispatcher) -> None:
    dp.include_routers(
        errors.router,
        user.router,
        admin.router,
        main_menu.router,
        func_menu.router,
        settings_menu.router
    )


async def main() -> None:
    await async_main()

    config = BotConfig(
        admin_ids=[],
        welcome_message=""
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp["config"] = config

    register_routers(dp)

    scheduler.start()

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as _ex:
        print(f'Exception: {_ex}')


if __name__ == '__main__':
    asyncio.run(main())
