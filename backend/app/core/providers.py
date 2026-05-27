"""
Central AI Provider Registry
All provider configuration lives here. Imported by ai.py, autopilot.py,
historical_lab.py, backtest.py — single source of truth.
"""
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


# Each provider entry:
#   name: display name for frontend
#   env_key: settings attribute name for the API key
#   base_url: OpenAI-compatible API endpoint
#   models: default model list (overridden by live fetch)
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "nvidia": {
        "name": "NVIDIA NIM",
        "env_key": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "needs_nvapi_prefix": True,
        "models": [
            "qwen/qwen3.5-122b-a10b",
            "qwen/qwen2.5-coder-32b-instruct",
            "deepseek-ai/deepseek-v3.1",
            "deepseek-ai/deepseek-r1-distill-qwen-32b",
            "nvidia/llama-3.1-405b-instruct",
        ],
    },
    "groq": {
        "name": "Groq",
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_nvapi_prefix": False,
        "models": [
            "llama3-70b-8192",
            "llama3-8b-8192",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "deepseek-r1-distill-llama-70b",
        ],
    },
    "openrouter": {
        "name": "OpenRouter",
        "env_key": "OPEN_ROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_nvapi_prefix": False,
        "models": [
            "anthropic/claude-3.5-sonnet",
            "meta-llama/llama-3.1-70b-instruct",
            "google/gemini-pro-1.5",
            "mistralai/mixtral-8x22b-instruct",
        ],
    },
    "gemini": {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "needs_nvapi_prefix": False,
        "models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
    },
    "github": {
        "name": "GitHub Models",
        "env_key": "GITHUB_API_KEY",
        "base_url": "https://models.inference.ai.azure.com",
        "needs_nvapi_prefix": False,
        "models": ["gpt-4o", "gpt-4o-mini", "meta-llama-3.1-70b-instruct"],
    },
    "cerebras": {
        "name": "Cerebras",
        "env_key": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "needs_nvapi_prefix": False,
        "models": ["gpt-oss-120b", "llama3.1-8b"],
    },
    "mistral": {
        "name": "Mistral AI",
        "env_key": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "needs_nvapi_prefix": False,
        "models": ["mistral-large-latest", "mistral-small-latest", "open-mistral-nemo"],
    },
}


def get_api_key(provider_id: str, settings_obj) -> str:
    """Get the API key for a provider from settings."""
    cfg = PROVIDERS.get(provider_id)
    if not cfg:
        return ""
    val = getattr(settings_obj, cfg["env_key"], "")
    if cfg.get("needs_nvapi_prefix") and val and not val.startswith("nvapi-"):
        return f"nvapi-{val}"
    return val


def get_base_url(provider_id: str) -> str:
    """Get the base URL for a provider."""
    cfg = PROVIDERS.get(provider_id)
    return cfg["base_url"] if cfg else ""


def validate_provider(provider_id: str) -> bool:
    """Check if a provider exists in the registry."""
    return provider_id in PROVIDERS


def get_provider_names() -> list:
    """Return list of provider IDs for API responses."""
    return list(PROVIDERS.keys())


async def resolve_api_key(
    provider: str,
    settings_obj,
    user_id: Optional[int] = None,
    db_session_factory=None,
) -> str:
    """Check user's saved key (encrypted in DB) first, fall back to server .env key."""
    if user_id and db_session_factory:
        from .encryption import decrypt_api_key
        from ..models.user import UserApiKey
        async with db_session_factory() as db:
            result = await db.execute(
                select(UserApiKey).where(
                    UserApiKey.user_id == user_id, UserApiKey.provider == provider
                )
            )
            row = result.scalar_one_or_none()
            if row:
                return decrypt_api_key(
                    row.encrypted_key,
                    settings_obj.SECRET_KEY or settings_obj.effective_secret_key,
                )
    return get_api_key(provider, settings_obj)
