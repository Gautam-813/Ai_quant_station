
import asyncio
from app.core.database import engine
from sqlalchemy import text

async def run():
    async with engine.begin() as conn:
        try:
            await conn.execute(text('ALTER TABLE trade_records ALTER COLUMN mt5_ticket TYPE BIGINT;'))
            await conn.execute(text('ALTER TABLE autopilot_trades ALTER COLUMN mt5_ticket TYPE BIGINT;'))
            print('Database columns upgraded to BIGINT successfully.')
        except Exception as e:
            print(f"Error upgrading database: {e}")

if __name__ == "__main__":
    asyncio.run(run())
