"""
Test all configured AI providers by making a simple API call.
Run: python test_providers.py

Reports which providers have valid API keys and which are working.
"""
import asyncio
import sys
from openai import AsyncOpenAI

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.providers import PROVIDERS, get_base_url, get_api_key


async def test_provider(provider_id: str) -> dict:
    cfg = PROVIDERS[provider_id]
    api_key = get_api_key(provider_id, settings)

    result = {
        "provider": provider_id,
        "name": cfg["name"],
        "env_key": cfg["env_key"],
        "has_key": bool(api_key),
        "key_preview": api_key[:8] + "..." if api_key else "",
        "working": False,
        "error": None,
    }

    if not api_key:
        result["error"] = "No API key found in .env"
        return result

    try:
        client = AsyncOpenAI(base_url=get_base_url(provider_id), api_key=api_key)
        response = await client.chat.completions.create(
            model=cfg["models"][0],
            messages=[{"role": "user", "content": "Reply with just the word OK"}],
            max_tokens=10,
            timeout=15,
        )
        reply = response.choices[0].message.content or ""
        result["working"] = True
        result["reply"] = reply.strip()
    except Exception as e:
        err = str(e)
        # Truncate long errors
        result["error"] = err[:200] + "..." if len(err) > 200 else err

    return result


async def main():
    print("=" * 60)
    print("  AI PROVIDER CONNECTION TEST")
    print("=" * 60)

    providers = list(PROVIDERS.keys())
    results = await asyncio.gather(*[test_provider(p) for p in providers])

    print()
    print(f"{'Provider':<15} {'Key':<12} {'Status':<10}  Notes")
    print("-" * 60)

    working_count = 0
    has_key_count = 0

    for r in results:
        status = "✅ WORKING" if r["working"] else ("❌ FAILED" if r["has_key"] else "⏭️  NO KEY")
        key_status = "✓" if r["has_key"] else "✗"
        notes = r["reply"] if r.get("reply") else (r["error"] or "")

        if r["working"]:
            working_count += 1
        if r["has_key"]:
            has_key_count += 1

        print(f"{r['name']:<15} {key_status:<12} {status:<10}  {notes[:50]}")

    print("-" * 60)
    print(f"Total providers: {len(providers)}")
    print(f"API keys found:  {has_key_count}")
    print(f"Working:         {working_count}")
    print(f"Failed:          {has_key_count - working_count}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
