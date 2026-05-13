import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def check_tables():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [row[0] for row in result.fetchall()]
        print('Tables:', tables)

asyncio.run(check_tables())