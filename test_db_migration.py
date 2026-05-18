"""Test database initialization, migrations, and cascading deletes."""
import sys, os, asyncio

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-1234567890"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_migration.db"
os.environ["DEFAULT_ADMIN_PASSWORD"] = "testadmin123"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
from app import models
from app.core.config import settings
assert "test_migration" in settings.DATABASE_URL, f"Wrong DB URL: {settings.DATABASE_URL}"
print(f"Using DB: {settings.DATABASE_URL}")

from app.core.database import init_db, AsyncSessionLocal, engine, Base
from app.core.security import get_password_hash
from sqlalchemy import text, select


async def test():
    # === STEP 1: Fresh DB creation ===
    print("\n=== Step 1: Fresh DB creation ===")
    await init_db()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = sorted([r[0] for r in result.fetchall()])
        print(f"  Tables: {len(tables)}")
        expected = ["autopilot_settings", "autopilot_trades", "calculation_history",
            "chat_memories", "default_prompt_strategies", "global_insights",
            "historical_backtests", "indicator_requests", "market_data",
            "model_usage", "trade_records", "user_feedback", "user_preferences",
            "user_prompts", "users"]
        for t in expected:
            assert t in tables, f"Missing: {t}"
        print("  PASS: All 15 tables created")

    # === STEP 2: Verify users table schema ===
    print("\n=== Step 2: Verify users table schema ===")
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        cols = {row[1]: row for row in result.fetchall()}
        print(f"  Columns: {list(cols.keys())}")
        assert "is_active" in cols, "is_active missing"
        is_type = cols["is_active"][2].upper()
        assert "BOOL" in is_type, f"is_active should be Boolean, got {is_type}"
        print("  PASS: is_active is Boolean type")

    # === STEP 3: Insert & read user ===
    print("\n=== Step 3: Insert & read user ===")
    async with AsyncSessionLocal() as db:
        from app.models.user import User
        user = User(username="testuser", name="Test User",
            hashed_password=get_password_hash("testpass123"),
            role="trader", is_active=True)
        db.add(user)
        await db.commit()
        u = (await db.execute(select(User).where(User.username == "testuser"))).scalar_one()
        assert u.is_active == True
        assert isinstance(u.is_active, bool)
        print(f"  PASS: is_active={u.is_active} ({type(u.is_active).__name__})")

    # === STEP 4: Test FK cascade delete ===
    print("\n=== Step 4: Test FK cascade delete ===")
    async with AsyncSessionLocal() as db:
        from app.models.ai_memory import ChatMemory, TradeRecord
        db.add(ChatMemory(user_id=user.id, role="user", content="test"))
        db.add(TradeRecord(user_id=user.id, symbol="XAUUSD", direction="BUY", entry_price=100.0, volume=0.1))
        await db.commit()
        uid = user.id
    async with AsyncSessionLocal() as db:
        assert len((await db.execute(select(ChatMemory).where(ChatMemory.user_id == uid))).scalars().all()) == 1
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        await db.commit()
        chats = len((await db.execute(select(ChatMemory).where(ChatMemory.user_id == uid))).scalars().all())
        trades = len((await db.execute(select(TradeRecord).where(TradeRecord.user_id == uid))).scalars().all())
        assert chats == 0, f"ChatMemory not cascaded: {chats}"
        assert trades == 0, f"TradeRecord not cascaded: {trades}"
        print("  PASS: Cascade delete works")

    # === STEP 5: VARCHAR to Boolean migration ===
    print("\n=== Step 5: VARCHAR->Boolean migration ===")
    # Drop all tables and recreate with old VARCHAR schema
    async with engine.begin() as conn:
        # Drop all tables
        for tbl in reversed(expected):
            await conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        # Create old-style users table
        await conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT DEFAULT 'trader',
                is_active VARCHAR(20) DEFAULT 'true',
                created_at TIMESTAMP,
                last_login TIMESTAMP
            )
        """))
        await conn.execute(text("INSERT INTO users (username, name, hashed_password) VALUES ('u1', 'Uno', 'hash1')"))
        await conn.execute(text("INSERT INTO users (username, name, hashed_password, is_active) VALUES ('u2', 'Dos', 'hash2', 'false')"))
        result = await conn.execute(text("SELECT username, is_active FROM users ORDER BY username"))
        before = [(r[0], r[1]) for r in result.fetchall()]
        print(f"  Before: {before}")

    # Run init_db to trigger migration
    print("  Running init_db (migration)...")
    await init_db()
    print("  init_db done")

    # Verify migration result
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables_after = [r[0] for r in result.fetchall()]
        temp_tables = [t for t in tables_after if "temp" in t or "old" in t or "migrate" in t]
        print(f"  Tables after: {tables_after}")
        if temp_tables:
            print(f"  WARNING: Temp tables not cleaned up: {temp_tables}")

        result = await conn.execute(text("PRAGMA table_info(users)"))
        cols = {row[1]: row for row in result.fetchall()}
        print(f"  is_active type: {cols['is_active'][2]}")
        for name, info in cols.items():
            print(f"    {name}: {info[2]}")

        if "BOOL" not in cols["is_active"][2].upper():
            # Debug: check if migration code ran at all
            print("  Migration did not convert to BOOLEAN. Checking temp table...")
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%temp%'"))
            temps = [r[0] for r in result.fetchall()]
            print(f"  Temp tables: {temps}")
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%migrate%'"))
            migrates = [r[0] for r in result.fetchall()]
            print(f"  Migrate tables: {migrates}")

        assert "BOOL" in cols["is_active"][2].upper(), f"Should be Boolean, got {cols['is_active'][2]}"
        result = await conn.execute(text("SELECT username, is_active FROM users ORDER BY username"))
        after = [(r[0], bool(r[1])) for r in result.fetchall()]
        print(f"  After: {after}")
        assert after[0][1] == True, f"u1 should be active"
        assert after[1][1] == False, f"u2 should be inactive"
        print("  PASS: VARCHAR->Boolean migration works")

    # Cleanup
    await engine.dispose()
    os.remove("test_migration.db")
    print("\n=== ALL TESTS PASSED ===")


asyncio.run(test())
