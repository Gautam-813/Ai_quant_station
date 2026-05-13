
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

from app.api.autopilot import run_autopilot_cycle, sync_trade_results, autopilot_state
from app.core.database import AsyncSessionLocal

async def test():
    user_id = 1
    print(f"Starting Autopilot Test for User ID: {user_id}...")
    
    # Reset MT5 connection status in DB to force re-initialization
    async with AsyncSessionLocal() as db:
        from sqlalchemy import update
        from app.models.ai_memory import AutopilotSettings
        await db.execute(
            update(AutopilotSettings)
            .where(AutopilotSettings.user_id == user_id)
            .values(mt5_connected=False)
        )
        await db.commit()
        
    # Run sync and then a new cycle
    try:
        print("Syncing existing trade results...")
        await sync_trade_results(user_id)
        
        print("Running new autopilot cycle...")
        await run_autopilot_cycle(user_id)
        
        print("\n" + "="*50)
        print("TEST RESULTS")
        print("="*50)
        
        # Show logs
        for log in reversed(autopilot_state["logs"]):
            try:
                print(f"[{log['timestamp']}] {log['level']}: {log['message']}")
            except UnicodeEncodeError:
                # Fallback for terminals that don't support emojis
                clean_msg = log['message'].encode('ascii', 'ignore').decode('ascii')
                print(f"[{log['timestamp']}] {log['level']}: {clean_msg}")
            
        print("\n" + "="*50)
        print("STATS")
        print(autopilot_state["stats"])
        print("="*50)
        
    except Exception as e:
        print(f"An error occurred during the test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
