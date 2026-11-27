from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@lru_cache
def session_factory(worker: bool = False):
    options = {"poolclass": NullPool} if worker else {"pool_pre_ping": True}
    engine = create_async_engine(settings().database_url, hide_parameters=True, **options)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with session_factory()() as session:
        yield session
