"""
Shared model cache — fetches live available models from each provider's API once per day.

All modules (autopilot, ai, backtest) import get_live_models() from here.
Cache TTL: 24 hours. Falls back to hardcoded list if API call fails.
"""

import logging
import time
import httpx

logger = logging.getLogger(__name__)

# Module-level cache: {provider_id: {"models": [...], "fetched_at": timestamp}}
_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


async def get_live_models(provider_id: str, api_key: str, base_url: str, needs_nvapi_prefix: bool = False) -> list[str]:
    """Get available models for a provider. Uses cache if fresh, otherwise fetches live.

    Returns list of model IDs. Falls back to empty list on failure.
    """
    now = time.time()

    # Check cache
    if provider_id in _cache:
        age = now - _cache[provider_id]["fetched_at"]
        if age < CACHE_TTL_SECONDS:
            return _cache[provider_id]["models"]

    # Fetch live models
    models = await _fetch_models_from_api(provider_id, api_key, base_url, needs_nvapi_prefix)

    if models:
        _cache[provider_id] = {"models": models, "fetched_at": now}
        logger.info(f"[models_cache] {provider_id}: cached {len(models)} live models")
    elif provider_id in _cache:
        # API failed but we have stale cache — use it
        models = _cache[provider_id]["models"]
        logger.warning(f"[models_cache] {provider_id}: API failed, using stale cache ({len(models)} models)")
    else:
        logger.warning(f"[models_cache] {provider_id}: API failed and no cache available")

    return models


async def _fetch_models_from_api(provider_id: str, api_key: str, base_url: str, needs_nvapi_prefix: bool) -> list[str]:
    """Call GET {base_url}/models to get available models."""
    if not api_key:
        return []

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        if needs_nvapi_prefix and not api_key.startswith("nvapi-"):
            headers["Authorization"] = f"Bearer nvapi-{api_key}"

        url = f"{base_url.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    item["id"] for item in data.get("data", [])
                    if item.get("id") and not item.get("deprecated", False)
                ]
                if models:
                    return sorted(models)
            else:
                logger.warning(f"[models_cache] {provider_id}: GET /models returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"[models_cache] {provider_id}: fetch failed: {e}")

    return []


def get_stale_models(provider_id: str) -> list[str]:
    """Synchronous fallback — returns cached models without fetching.
    Useful in sync contexts or when event loop is already running.
    """
    if provider_id in _cache:
        return _cache[provider_id]["models"]
    return []


def force_refresh_all(providers_config: dict, api_keys: dict) -> None:
    """Sync refresh for startup — call once at boot.
    providers_config: dict of {provider_id: {"base_url": ..., "needs_nvapi_prefix": ..., "models": [...]}}
    api_keys: dict of {provider_id: api_key_string}
    """
    import asyncio

    async def _refresh():
        for pid, cfg in providers_config.items():
            key = api_keys.get(pid, "")
            models = await get_live_models(pid, key, cfg["base_url"], cfg.get("needs_nvapi_prefix", False))
            if not models and cfg.get("models"):
                # API failed, seed cache with hardcoded fallback
                _cache[pid] = {"models": cfg["models"], "fetched_at": time.time()}

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in event loop — schedule as task
            asyncio.create_task(_refresh())
        else:
            loop.run_until_complete(_refresh())
    except RuntimeError:
        asyncio.run(_refresh())
