from pydantic_settings import BaseSettings
from typing import List
import os
import secrets

env_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')


class Settings(BaseSettings):
    # JWT Settings
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # MT5 Settings
    MT5_SERVER_PORT: int = 5001
    MT5_API_TOKEN: str = ""
    MT5_TERMINAL_PATH: str | None = None
    
    # MT5 Connector (External Windows Server)
    MT5_CONNECTOR_URL: str = ""
    MT5_USE_EXTERNAL_CONNECTOR: bool = False

    # HuggingFace
    HF_REPO_ID: str = ""
    HUGGINGFACE_API_KEY: str = ""

    # AI Providers
    NVIDIA_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPEN_ROUTER_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GITHUB_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./finance_engine.db"

    # MT5 broker UTC offset (brokers often return timestamps in local time)
    # Examples: UTC+2 = 2, UTC+3 = 3, UTC = 0. Set to 0 if your broker returns UTC.
    MT5_BROKER_UTC_OFFSET: int = 0

    # Yahoo Finance (for market data)
    YAHOO_FINANCE_ENABLED: bool = True
    
    # Extra fields from .env (legacy/compat)
    PASSWORD: str = ""
    Bytez: str = ""
    Completions: str = ""

    # Default admin credentials (MUST be set via .env in production!)
    DEFAULT_ADMIN_PASSWORD: str = ""

    @property
    def effective_secret_key(self) -> str:
        if self.SECRET_KEY:
            return self.SECRET_KEY
        key = secrets.token_hex(32)
        print("WARNING: SECRET_KEY not set in .env. Generated a temporary key. Set SECRET_KEY in .env for persistence.")
        return key

    class Config:
        env_file = env_file_path
        case_sensitive = True
        extra = "ignore"


settings = Settings()