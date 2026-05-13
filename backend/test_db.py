import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(user='postgres', password='postgres', database='impulse_analyst')
    users = await conn.fetch('SELECT username, role FROM users')
    for u in users:
        print(f"  {u['username']} - {u['role']}")
    await conn.close()

asyncio.run(test())