from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQLite doesn't support pool_size; MySQL/PostgreSQL do
_engine_kwargs = {"echo": False}
if "sqlite" not in settings.DATABASE_URL:
    _engine_kwargs["pool_size"] = 20

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
