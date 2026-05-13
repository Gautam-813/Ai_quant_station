import asyncio
import httpx

async def test_login():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/auth/login",
            json={"username": "admin", "password": "admin@2026"}
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Login successful! Token: {data['access_token'][:50]}...")
        else:
            print(f"Error: {response.text}")

asyncio.run(test_login())