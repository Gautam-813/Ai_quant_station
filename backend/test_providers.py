"""
Test all configured AI providers by making a simple API call.
Dynamically fetches available models from each provider.
Run: python test_providers.py
"""
import asyncio
import sys
from openai import AsyncOpenAI

sys.path.insert(0, ".")
from app.core.config import settings
from app.core.providers import PROVIDERS, get_base_url, get_api_key


async def _get_models(client) -> list:
    """Fetch available models from provider, return empty list on failure."""
    try:
        resp = await asyncio.wait_for(client.models.list(), timeout=10)
        return [m.id for m in resp.data]
    except Exception:
        return []


async def test_provider(provider_id: str) -> dict:
    cfg = PROVIDERS[provider_id]
    api_key = get_api_key(provider_id, settings)

    result = {
        "provider": provider_id,
        "name": cfg["name"],
        "env_key": cfg["env_key"],
        "has_key": bool(api_key),
        "key_preview": api_key[:10] + "..." if api_key else "",
        "working": False,
        "error": None,
        "model_used": None,
    }

    if not api_key:
        result["error"] = "No API key found in .env"
        return result

    client = AsyncOpenAI(base_url=get_base_url(provider_id), api_key=api_key, max_retries=0)

    # Dynamically discover available models
    models = await _get_models(client)
    if models:
        result["models_found"] = len(models)

    # Pick the model to test: first discovered model, or fallback to hardcoded list
    test_models = models[:5] if models else cfg.get("models", [])
    if not test_models:
        result["error"] = "No models available (discovery failed + no fallback list)"
        return result

    for model in test_models:
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "OK"}],
                    max_tokens=5,
                    temperature=0.1,
                ),
                timeout=20,
            )
            reply = response.choices[0].message.content or ""
            result["working"] = True
            result["model_used"] = model
            result["reply"] = reply.strip()
            return result
        except Exception as e:
            err = str(e).lower()
            # If model-specific error, try next model
            if "model" in err and ("not found" in err or "does not exist" in err or "not supported" in err or "not available" in err):
                continue
            # If auth/rate-limit/quota error, don't try more models
            if "401" in err or "unauthorized" in err or "403" in err or "429" in err or "quota" in err:
                result["error"] = str(e)[:200]
                return result
            # If timeout or connection error, don't try more
            if "timeout" in err or "connect" in err or "eof" in err:
                result["error"] = str(e)[:200]
                return result
            continue

    # All models failed
    result["error"] = f"Tried {len(test_models)} models, all failed"
    return result


async def main():
    print("=" * 60)
    print("  AI PROVIDER CONNECTION TEST")
    print("=" * 60)

    providers = list(PROVIDERS.keys())
    results = await asyncio.gather(*[test_provider(p) for p in providers])

    print()
    print(f"{'Provider':<16} {'Status':<10}  {'Model Used / Error'}")
    print("-" * 60)

    working = has_key = 0
    for r in results:
        if r["has_key"]:
            has_key += 1
        if r["working"]:
            working += 1

        if r["working"]:
            icon = "OK"
            detail = r["model_used"] or ""
        elif r["has_key"]:
            icon = "ERR"
            detail = r["error"] or ""
            # Truncate for display
            if len(detail) > 70:
                detail = detail[:70] + "..."
        else:
            icon = "---"
            detail = "No API key"

        print(f"{r['name']:<16} {icon:<10}  {detail}")

    print("-" * 60)
    print(f"Providers: {len(providers)}  |  Keys found: {has_key}  |  Working: {working}  |  Failed: {has_key - working}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
