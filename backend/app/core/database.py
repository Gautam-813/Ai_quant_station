from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# PostgreSQL enforces foreign keys natively. For SQLite, we handle it below.
_is_sqlite = str(settings.DATABASE_URL).startswith("sqlite")
if _is_sqlite:
    from sqlalchemy import event

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
        # SQLite-specific migration: convert is_active from VARCHAR to BOOLEAN
        if _is_sqlite:
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

        # PostgreSQL-specific migration: convert TIMESTAMP to TIMESTAMPTZ
        if not _is_sqlite:
            try:
                # Find all timestamp without time zone columns and convert them
                result = await conn.execute(text("""
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND data_type = 'timestamp without time zone'
                """))
                rows = result.fetchall()
                for table_name, column_name in rows:
                    try:
                        await conn.execute(text(
                            f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE TIMESTAMP WITH TIME ZONE'
                        ))
                    except Exception:
                        pass  # column might have been altered already
            except Exception:
                pass