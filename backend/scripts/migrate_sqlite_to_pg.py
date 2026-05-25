#!/usr/bin/env python3
"""
Migrate data from SQLite (finance_engine.db) to PostgreSQL.

Uses SQLAlchemy Table objects for type-safe INSERTs (handles bool/int,
datetime, etc. conversion automatically).

Usage:
    1. Copy your local finance_engine.db to the server:
       scp backend/finance_engine.db root@YOUR_DO_IP:/opt/impulse_analyst/backend/

    2. Run this script on the server:
       cd /opt/impulse_analyst/backend
       source venv/bin/activate
       python scripts/migrate_sqlite_to_pg.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 — register all models with Base.metadata
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "finance_engine.db")
PG_URL = str(settings.DATABASE_URL).replace("+asyncpg", "")

# Insert order (FK dependencies first)
TABLES_IN_ORDER = [
    "users", "market_data", "global_insights", "default_prompt_strategies",
    "revoked_tokens", "chat_memories", "model_usage", "trade_records",
    "calculation_history", "indicator_requests", "user_preferences",
    "autopilot_trades", "user_prompts", "autopilot_settings",
    "historical_backtests", "position_audits", "user_feedback",
]

# Tables with unique constraints — use ON CONFLICT DO NOTHING
TABLES_WITH_UNIQUES = {
    "users", "market_data", "global_insights", "default_prompt_strategies",
    "revoked_tokens", "model_usage", "trade_records", "indicator_requests",
    "user_preferences", "autopilot_settings",
}

SEQUENCE_TABLES = set(TABLES_IN_ORDER)


def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)

    print("Connecting to SQLite...")
    sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False})

    print(f"Connecting to PostgreSQL: {PG_URL}")
    pg_engine = create_engine(PG_URL)

    # Create schema in PostgreSQL
    print("Creating database schema in PostgreSQL...")
    Base.metadata.create_all(pg_engine)
    print("Schema created.\n")

    total_rows = 0

    with sqlite_engine.connect() as src:
        for table_name in TABLES_IN_ORDER:
            # Get SQLAlchemy Table object — handles type coercion automatically
            pg_table = Base.metadata.tables.get(table_name)
            if pg_table is None:
                print(f"  SKIP {table_name}: not in metadata")
                continue

            # Read all data from SQLite
            result = src.execute(pg_table.select())
            rows = [dict(row._mapping) for row in result.fetchall()]

            if not rows:
                print(f"  {table_name}: 0 rows (empty)")
                continue

            # Build INSERT statement
            if table_name in TABLES_WITH_UNIQUES:
                insert = pg_insert(pg_table).on_conflict_do_nothing()
            else:
                insert = pg_insert(pg_table)

            # Insert into PostgreSQL
            with pg_engine.begin() as pg:
                pg.execute(insert, rows)

            # Update sequence
            if table_name in SEQUENCE_TABLES and "id" in rows[0]:
                max_id = max(r["id"] for r in rows if r["id"] is not None)
                if max_id:
                    try:
                        with pg_engine.begin() as pg:
                            pg.execute(text(f"SELECT setval('{table_name}_id_seq', {max_id})"))
                    except Exception:
                        pass

            total_rows += len(rows)
            print(f"  {table_name}: {len(rows)} rows ✓")

    print(f"\n✅ Migration complete! {total_rows} total rows copied to PostgreSQL.")

    # Verify
    print("\nVerifying row counts...")
    mismatches = 0
    with sqlite_engine.connect() as src, pg_engine.connect() as pg:
        for table_name in TABLES_IN_ORDER:
            pg_table = Base.metadata.tables.get(table_name)
            if pg_table is None:
                continue
            src_count = src.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
            pg_count = pg.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
            if src_count == pg_count:
                print(f"  {table_name}: SQLite={src_count} PostgreSQL={pg_count} ✓")
            else:
                print(f"  {table_name}: SQLite={src_count} PostgreSQL={pg_count} ✗ MISMATCH")
                mismatches += 1

    if mismatches == 0:
        print("\n✅ All tables match!")
    else:
        print(f"\n⚠️  {mismatches} table(s) have mismatches")

    print("\nDone!")


if __name__ == "__main__":
    migrate()
