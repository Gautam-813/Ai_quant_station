import sqlite3
conn = sqlite3.connect("backend/finance_engine.db")
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
if "chat_memories" in tables:
    count = conn.execute("SELECT COUNT(*) FROM chat_memories").fetchone()[0]
    print(f"chat_memories rows: {count}")
    print("Sample:", conn.execute("SELECT id, user_id, role, substr(content,1,80) FROM chat_memories LIMIT 3").fetchall())
conn.close()
