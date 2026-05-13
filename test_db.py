import asyncio
import sys
sys.path.insert(0, 'D:/date-wise/06-04-2026(live current autopilot)/impulse_analyst_v2/backend')

from app.core.database import AsyncSessionLocal
from app.models.ai_memory import UserFeedback
from sqlalchemy import select, func

async def test():
    print("Testing database...")
    try:
        async with AsyncSessionLocal() as db:
            # Test simple insert
            fb = UserFeedback(user_id=1, is_helpful=True)
            db.add(fb)
            await db.commit()
            print("Inserted!")
            
            # Test select
            result = await db.execute(select(UserFeedback).where(UserFeedback.user_id == 1))
            records = result.scalars().all()
            print(f"Found {len(records)} records")
            
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())