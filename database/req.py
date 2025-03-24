from sqlalchemy import select, desc, distinct, and_

from database.models import User, async_session
from errors.errors import *
from handlers.errors import db_error_handler


@db_error_handler
async def get_user(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        if user:
            return user
        else:
            return None


@db_error_handler
async def create_user(tg_id: int):
    async with async_session() as session:
        user = await get_user(tg_id)
        data = {}
        if not user:
            data['id'] = tg_id
            user_data = User(**data)
            session.add(user_data)
            await session.commit()
        else:
            raise Error409


@db_error_handler
async def update_user(tg_id: int, data: dict):
    async with async_session() as session:
        user = await get_user(tg_id)
        if not user:
            raise Error404
        else:
            for key, value in data.items():
                setattr(user, key, value)
            session.add(user)
            await session.commit()
