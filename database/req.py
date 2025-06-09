import base64
import datetime
import hashlib
from typing import Optional

from sqlalchemy import select, desc, distinct, and_

from database.models import User, async_session, Uric, UserXUric, SubsribeStatus
from errors.errors import *
from handlers.errors import db_error_handler


async def make_url_safe_hash(data: str, length: int = 12) -> str:
    sha = hashlib.sha256(data.encode()).digest()
    b64 = base64.urlsafe_b64encode(sha).decode()
    return b64[:length]


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
async def update_user_cur_uric(tg_id: int, uric: str):
    async with async_session() as session:
        user = await get_user(tg_id)
        if user:
            user.cur_uric = uric
            session.add(user)
            await session.commit()
        else:
            raise Error404


@db_error_handler
async def get_uric(name: str):
    async with async_session() as session:
        uric = await session.scalar(select(Uric).where(Uric.name == name))
        if uric:
            return uric
        else:
            return None


@db_error_handler
async def get_uric_by_hash(hash: str):
    async with async_session() as session:
        uric = await session.scalar(select(Uric).where(Uric.hash == hash))
        if uric:
            return uric
        else:
            return None


@db_error_handler
async def create_uric(name: str, owner_id: int, api_key: str, trade_mark: str) -> bool:
    async with async_session() as session:
        uric = await get_uric(name)
        data = {}
        if not uric:
            data['name'] = name
            data['owner_id'] = owner_id
            data['api_key'] = api_key
            data['hash'] = await make_url_safe_hash(name)
            data['trade_mark'] = trade_mark
            uric_data = Uric(**data)
            session.add(uric_data)
            await session.commit()
            return True
        else:
            return False


@db_error_handler
async def update_uric(name: str, data: dict):
    async with async_session() as session:
        uric = await get_uric(name)
        if uric:
            for key, value in data.items():
                setattr(uric, key, value)
            session.add(uric)
            await session.commit()
        else:
            raise Error404


@db_error_handler
async def update_uric_api_key(name: str, api_key: str):
    async with async_session() as session:
        uric = await get_uric(name)
        if uric:
            uric.api_key = api_key
            session.add(uric)
            await session.commit()
        else:
            raise Error404


@db_error_handler
async def pay_sub(name: str, subsribe: SubsribeStatus, exp_date: datetime.date | None):
    async with async_session() as session:
        uric = await get_uric(name)
        if uric:
            uric.subsribe = subsribe
            uric.exp_date = exp_date
            session.add(uric)
            await session.commit()
        else:
            raise Error404


@db_error_handler
async def get_uric_by_owner(owner_id: int):
    async with async_session() as session:
        uric = await session.scalars(select(Uric).where(Uric.owner_id == owner_id))
        if uric:
            return uric.all()
        else:
            return None


@db_error_handler
async def get_user_uric(user_id: int, uric_id: str):
    async with async_session() as session:
        user_uric = await session.scalar(select(UserXUric).where(and_(UserXUric.user_id == user_id,
                                                                      UserXUric.uric_id == uric_id)))
        if user_uric:
            return user_uric
        else:
            return None


@db_error_handler
async def add_user_uric(user_id: int, uric_id: str):
    async with async_session() as session:
        user_uric = await session.scalar(select(UserXUric).where(and_(UserXUric.user_id == user_id, UserXUric.uric_id == uric_id)))
        if not user_uric:
            data = {}
            data['user_id'] = user_id
            data['uric_id'] = uric_id
            user_uric_data = UserXUric(**data)
            session.add(user_uric_data)
            await session.commit()
        else:
            raise Error409


@db_error_handler
async def get_users_by_uric(uric_id: str):
    async with async_session() as session:
        user_uric = await session.scalars(select(UserXUric).where(UserXUric.uric_id == uric_id))
        if user_uric:
            return user_uric.all()
        else:
            return None


@db_error_handler
async def get_urics_by_user(user_id: int):
    async with async_session() as session:
        uric = await session.scalars(select(UserXUric).where(UserXUric.user_id == user_id))
        if uric:
            return uric.all()
        else:
            return None
