"""
Script to create initial admin user in the database.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import init_db, AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User


async def create_admin():
    await init_db()
    
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        
        # Check if admin exists
        result = await session.execute(select(User).where(User.username == "admin"))
        existing_admin = result.scalar_one_or_none()
        
        if existing_admin:
            print("Admin user already exists!")
            return
        
        # Create admin user
        admin = User(
            username="admin",
            name="System Administrator",
            hashed_password=get_password_hash("admin@2026"),
            role="admin"
        )
        session.add(admin)
        
        # Create test users
        users = [
            User(username="keval_viradiya", name="Keval Viradiya", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
            User(username="sagar_barot", name="Sagar Barot", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
            User(username="meet_rao", name="Meet Rao", hashed_password=get_password_hash("Usdt@2026"), role="trader"),
            User(username="guest", name="Guest Viewer", hashed_password=get_password_hash("Usdt@2026"), role="viewer"),
        ]
        
        for user in users:
            session.add(user)
        
        await session.commit()
        print("Users created successfully!")
        print("Admin login: admin / admin@2026")


if __name__ == "__main__":
    asyncio.run(create_admin())