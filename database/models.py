from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, ARRAY, BigInteger, ForeignKey, Numeric, JSON, Date, Enum
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from enum import Enum as PyEnum

from instance import SQL_URL_RC

engine = create_async_engine(url=SQL_URL_RC, echo=True)
async_session = async_sessionmaker(engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id = Column(BigInteger, primary_key=True, index=True, nullable=False)
    cur_uric = Column(String, default='')
    is_superuser = Column(Boolean, default=False)


class SubsribeStatus(PyEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class Uric(Base):
    __tablename__ = "uric"

    name = Column(String, primary_key=True, index=True)
    owner_id = Column(BigInteger, ForeignKey("user.id"), nullable=False)
    api_key = Column(String, default=None)
    subsribe = Column(Enum(SubsribeStatus, name='subsribe_status'), default=SubsribeStatus.ACTIVE)
    exp_date = Column(Date, nullable=True, default=None)
    hash = Column(String, nullable=False)
    trade_mark = Column(String, default=None)


class UserXUric(Base):
    __tablename__ = "user_x_uric"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("user.id"), nullable=False)
    uric_id = Column(String, ForeignKey("uric.name"), nullable=False)


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
