import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def test():
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT username, hashed_password FROM users WHERE username='admin'"))
        user = result.fetchone()
        if user:
            print(f"Testing password 'admin@2026'...")
            is_valid = pwd_context.verify("admin@2026", user[1])
            print(f"Password valid: {is_valid}")
        else:
            print("User not found")

asyncio.run(test())