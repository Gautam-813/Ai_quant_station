from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

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


from sqlalchemy import text

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Add is_active column if it doesn't exist
        try:
            # Check if column exists first for SQLite
            await conn.execute(text("ALTER TABLE users ADD COLUMN is_active VARCHAR(20) DEFAULT 'true'"))
            await conn.commit()
            print("Database migration: added is_active column to users table.")
        except Exception as e:
            # Column likely already exists or other non-critical error
            pass