import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def add_column():
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("ALTER TABLE autopilot_settings ADD COLUMN mt5_connector_url VARCHAR"))
            print("Column added successfully!")
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(add_column())