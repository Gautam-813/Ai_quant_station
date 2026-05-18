from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text, event
from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

# Enable foreign keys for SQLite (required for CASCADE deletes)
@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_fks(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "execute"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            result = await conn.execute(text("PRAGMA table_info(users)"))
            cols = {row[1]: row for row in result.fetchall()}
            is_active_col = cols.get("is_active")
            if is_active_col and is_active_col[2].upper().startswith(("VARCHAR", "TEXT")):
                temp = "users_migrate_temp"
                await conn.execute(text(f"ALTER TABLE users RENAME TO {temp}"))
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(text(f"""
                    INSERT INTO users (id, username, name, hashed_password, role, is_active, created_at, last_login)
                    SELECT id, username, name, hashed_password, role,
                        CASE WHEN is_active IN ('true','1') THEN 1 ELSE 0 END,
                        created_at, last_login
                    FROM {temp}
                """))
                await conn.execute(text(f"DROP TABLE {temp}"))
                await conn.execute(text("DELETE FROM sqlite_sequence WHERE name='users'"))
        except Exception:
            pass