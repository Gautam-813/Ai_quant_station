
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.ai_memory import AutopilotSettings, AutopilotTrade
from app.models.user import User

async def check():
    async with AsyncSessionLocal() as db:
        # Check users
        result = await db.execute(select(User))
        users = result.scalars().all()
        print(f"Total Users: {len(users)}")
        for u in users:
            print(f"User ID: {u.id}, Username: {u.username}")
            
        # Check settings
        result = await db.execute(select(AutopilotSettings))
        settings = result.scalars().all()
        print(f"Total Settings: {len(settings)}")
        for s in settings:
            print(f"Settings for User ID: {s.user_id}, Symbol: {s.symbol}, Enabled: {s.enabled}, MT5 Connected: {s.mt5_connected}, Connector URL: {s.mt5_connector_url}")

        # Check trades
        result = await db.execute(select(AutopilotTrade))
        trades = result.scalars().all()
        print(f"Total Autopilot Trades: {len(trades)}")
        for t in trades:
            print(f"Trade ID: {t.id}, Ticket: {t.mt5_ticket}, Status: {t.execution_status}, Result: {t.result}")

if __name__ == "__main__":
    asyncio.run(check())
