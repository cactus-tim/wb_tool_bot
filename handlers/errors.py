from aiogram import Router, types, Bot
import asyncio
from aiogram.types import ReplyKeyboardRemove, Message
from aiogram.enums import ParseMode
from typing import Any
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramUnauthorizedError, TelegramNetworkError
from functools import wraps

from instance import logger, bot
from aiohttp import ClientConnectorError
from errors.errors import *
from keyboards.keyboards import get_main_kb

router = Router()


@router.errors()
async def global_error_handler(event: Any):
    exception = event.exception
    update = event.update

    # Определяем user_id если возможно
    user_id = (
        update.message.from_user.id
        if update and update.message and update.message.from_user
        else "Unknown"
    )

    # Функция для безопасного получения chat_id из разных типов обновлений
    def get_chat_id(update):
        if update and update.message and update.message.chat:
            return update.message.chat.id
        elif update and getattr(update, 'callback_query', None) and update.callback_query.message:
            return update.callback_query.message.chat.id
        # Можно добавить дополнительные проверки для других типов обновлений, если требуется
        return None

    if isinstance(exception, TelegramBadRequest):
        logger.error(f"Некорректный запрос: {exception}. Пользователь: {user_id}")
        return True
    elif isinstance(exception, TelegramRetryAfter):
        logger.error(f"Request limit exceeded. Retry after {exception.retry_after} seconds.")
        await asyncio.sleep(exception.retry_after)
        return True
    elif isinstance(exception, TelegramUnauthorizedError):
        logger.error(f"Authorization error: {exception}")
        return True
    elif isinstance(exception, TelegramNetworkError):
        logger.error(f"Network error: {exception}")
        await asyncio.sleep(5)

        chat_id = get_chat_id(update)
        if chat_id is not None:
            await safe_send_message(bot, chat_id, text="Повторная попытка...")
        else:
            logger.error("Не удалось определить chat_id для отправки сообщения")
        return True
    else:
        logger.exception(f"Неизвестная ошибка: {exception}")
        return True


def db_error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Error404 as e:
            logger.exception(str(e))
            return None
        except DatabaseConnectionError as e:
            logger.exception(str(e))
            return None
        except Error409 as e:
            logger.exception(str(e))
            return None
        except Exception as e:
            logger.exception(f"Неизвестная ошибка: {str(e)}")
            return None
    return wrapper


async def safe_send_message(bott: Bot, recipient, text: str, reply_markup=get_main_kb(), retry_attempts=3, delay=5) -> Message:
    """Отправка сообщения с обработкой ClientConnectorError, поддержкой reply_markup и выбором метода отправки."""

    for attempt in range(retry_attempts):
        try:
            if isinstance(recipient, types.Message):
                msg = await recipient.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif isinstance(recipient, types.CallbackQuery):
                msg = await recipient.message.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif isinstance(recipient, int):
                msg = await bott.send_message(chat_id=recipient, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else:
                raise TypeError(f"Неподдерживаемый тип recipient: {type(recipient)}")

            return msg

        except ClientConnectorError as e:
            logger.error(f"Ошибка подключения: {e}. Попытка {attempt + 1} из {retry_attempts}.")
            if attempt < retry_attempts - 1:
                await asyncio.sleep(delay)
            else:
                logger.error(f"Не удалось отправить сообщение после {retry_attempts} попыток.")
                return None
        except Exception as e:
            logger.error(str(e))
            return None
