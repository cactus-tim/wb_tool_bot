from aiogram import Bot
from aiogram.enums import ParseMode
import os
from dotenv import load_dotenv
import sys
from aiogram.client.bot import DefaultBotProperties
import logging
import asyncio
import itertools
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore


load_dotenv('.env')
token = os.getenv('TOKEN_API_TG')
SQL_URL_RC = (f'postgresql+asyncpg://{os.getenv("DB_USER")}:{os.getenv("DB_PASS")}'
              f'@{os.getenv("DB_HOST")}:{os.getenv("DB_PORT")}/{os.getenv("DB_NAME")}')


jobstores = {
    'default': SQLAlchemyJobStore(url=SQL_URL_RC)
}
scheduler = AsyncIOScheduler()

bot = Bot(
    token=token,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

bot_link = os.getenv('BOT_LINK')

logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


logger = logging.getLogger(__name__)

# Глобальный семафор для запросов к discounts-prices-api.wildberries.ru
# Не более 1 параллельного запроса от всех пользователей одновременно
wb_discounts_semaphore = asyncio.Semaphore(1)

# Прокси для запросов к card.wb.ru
# Формат в .env: http://user:pass@host:port,http://user:pass@host2:port2
_raw_proxies = os.getenv('WB_PROXIES', '')
_proxy_list = [p.strip() for p in _raw_proxies.split(',') if p.strip()]
_proxy_cycle = itertools.cycle(_proxy_list) if _proxy_list else None


def get_next_proxy() -> dict | None:
    """Возвращает следующий прокси из ротации или None если прокси не настроены."""
    if _proxy_cycle is None:
        return None
    proxy_url = next(_proxy_cycle)
    return {'http': proxy_url, 'https': proxy_url}
