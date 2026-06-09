import httpx
c = httpx.Client(base_url="http://localhost:8002", timeout=30)
r = c.post("/api/auth/login", json={"username": "admin", "password": "admin@2026"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

r2 = c.post("/api/ai/chat", json={
    "messages": [{"role": "user", "content": "Say hello"}],
    "provider": "mistral",
    "model": "codestral-2508",
    "persona": "technical_analyst",
}, headers=headers, timeout=60)

resp = r2.json()
print("Status:", r2.status_code)
print("chat_memory_id:", resp.get("chat_memory_id"))
print("Keys:", list(resp.keys()))
