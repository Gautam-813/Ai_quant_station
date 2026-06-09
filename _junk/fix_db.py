import sqlite3
conn = sqlite3.connect("backend/finance_engine.db")

# Fix chat_memories table
cols = {r[1]: r for r in conn.execute("PRAGMA table_info(chat_memories)").fetchall()}
print("chat_memories columns:", list(cols.keys()))

chat_missing = []
for c in ["reasoning", "provider", "model", "tokens_used", "latency_ms"]:
    if c not in cols:
        col_type = "INTEGER" if c in ["tokens_used", "latency_ms"] else "TEXT"
        conn.execute(f"ALTER TABLE chat_memories ADD COLUMN {c} {col_type}")
        chat_missing.append(c)

if chat_missing:
    conn.commit()
    print(f"Added to chat_memories: {chat_missing}")
else:
    print("chat_memories: all columns present")

# Fix historical_backtests table
hb_cols = {r[1]: r for r in conn.execute("PRAGMA table_info(historical_backtests)").fetchall()}
print("historical_backtests columns:", list(hb_cols.keys()))

hb_missing = []
for c, t in [("trade_log", "TEXT"), ("lot_size", "FLOAT DEFAULT 0.01")]:
    if c not in hb_cols:
        conn.execute(f"ALTER TABLE historical_backtests ADD COLUMN {c} {t}")
        hb_missing.append(c)

if hb_missing:
    conn.commit()
    print(f"Added to historical_backtests: {hb_missing}")
else:
    print("historical_backtests: all columns present")

conn.close()
print("Done")
