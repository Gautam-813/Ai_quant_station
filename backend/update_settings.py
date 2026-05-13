
import asyncio
from app.core.database import AsyncSessionLocal
from app.models.ai_memory import AutopilotSettings
from sqlalchemy import update

async def run():
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(AutopilotSettings)
            .where(AutopilotSettings.user_id == 1)
            .values(provider='cerebras', model='llama3.1-8b')
        )
        await db.commit()
        print('Settings updated to Cerebras (llama3.1-8b)')

if __name__ == "__main__":
    asyncio.run(run())
