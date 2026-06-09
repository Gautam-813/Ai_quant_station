import httpx
import sqlite3

# Send chat
c = httpx.Client(base_url="http://localhost:8002", timeout=60)
r = c.post("/api/auth/login", json={"username": "admin", "password": "admin@2026"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Count chat_memories before
conn = sqlite3.connect("backend/finance_engine.db")
before = conn.execute("SELECT COUNT(*) FROM chat_memories").fetchone()[0]
conn.close()

r2 = c.post("/api/ai/chat", json={
    "messages": [{"role": "user", "content": "Say hello and tell me today's date"}],
    "provider": "mistral",
    "model": "codestral-2508",
    "persona": "technical_analyst",
}, headers=headers, timeout=60)

resp = r2.json()
print(f"Status: {r2.status_code}")
print(f"chat_memory_id: {resp.get('chat_memory_id')}")
print(f"Message length: {len(resp.get('message',''))}")

# Count chat_memories after
conn = sqlite3.connect("backend/finance_engine.db")
after = conn.execute("SELECT COUNT(*) FROM chat_memories").fetchone()[0]
print(f"Rows in chat_memories: {before} -> {after}")
if after > before:
    last = conn.execute("SELECT id, user_id, role, substr(content,1,60) FROM chat_memories ORDER BY id DESC LIMIT 2").fetchall()
    print(f"New rows: {last}")
conn.close()

# Check if there's an error in any recent logs by looking at the DB
try:
    errs = conn.execute("SELECT * FROM alembic_version").fetchall()
except:
    errs = "N/A"
print(f"alembic_version: {errs}")
