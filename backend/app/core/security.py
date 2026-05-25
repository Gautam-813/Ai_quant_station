from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def blacklist_token(token: str):
    """Revoke a JWT token immediately.  ENQUEUES an async DB write (non-blocking)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            _persist_blacklisted_token(token)
        )
    except RuntimeError:
        # No running loop (e.g. called from sync context) — write synchronously
        _persist_blacklisted_token_sync(token)


def _persist_blacklisted_token(token: str) -> None:
    """Async fire-and-forget: persist revoked token."""
    from .blacklist import blacklist_token as _db_blacklist
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(_db_blacklist(token))
    except RuntimeError:
        _persist_blacklisted_token_sync(token)


def _persist_blacklisted_token_sync(token: str) -> None:
    """Sync fallback for environments without an event loop."""
    from sqlalchemy import create_engine, text
    from .config import settings
    from datetime import timedelta, timezone
    url = str(settings.DATABASE_URL).replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS or 7)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO revoked_tokens (token_jti, expires_at, created_at)"
                " VALUES (:jti, :exp, :created)"
                " ON CONFLICT (token_jti) DO NOTHING"
            ),
            {"jti": token, "exp": expires_at, "created": datetime.now(timezone.utc)},
        )


def is_token_blacklisted(token: str) -> bool:
    """Check the DB-backed revocation list. Gracefully falls back to False on DB error."""
    try:
        return _db_is_revoked(token)
    except Exception:
        return False


def _db_is_revoked(token: str) -> bool | None:
    """Sync lookup — called from is_token_blacklisted."""
    from sqlalchemy import create_engine, text
    from .config import settings
    from datetime import datetime as _dt
    url = str(settings.DATABASE_URL).replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT expires_at FROM revoked_tokens WHERE token_jti = :jti"),
            {"jti": token},
        ).fetchone()
        if row is None:
            return False
        expires_at = row[0]
        if expires_at.tzinfo is None:
            from datetime import timezone
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > _dt.now(timezone.utc)


import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        password_bytes = plain_password.encode('utf-8')
        # Warn if password exceeds bcrypt's 72-byte limit
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False


def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.effective_secret_key, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.effective_secret_key, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict | None:
    if is_token_blacklisted(token):
        return None
    try:
        payload = jwt.decode(token, settings.effective_secret_key, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return {"username": username, "id": payload.get("user_id"), "role": payload.get("role")}


async def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))):
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None