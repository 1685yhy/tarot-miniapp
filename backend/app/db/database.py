from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from app.config import settings

# SQLite doesn't support pool_size; MySQL/PostgreSQL do
_engine_kwargs = {"echo": False}
if "sqlite" not in settings.DATABASE_URL:
    _engine_kwargs["pool_size"] = 20
else:
    # SQLite WAL mode: allows concurrent reads + one write, no more "database is locked"
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# Enable WAL mode on every new SQLite connection
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass

# Import all models so they are registered with SQLAlchemy Base metadata
import app.models  # noqa: F401 — ensures create_all creates all tables


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
