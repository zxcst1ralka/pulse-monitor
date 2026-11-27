from datetime import timedelta
from functools import lru_cache
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import RefreshSession, User, now

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
COOKIE = "pulse_refresh"
COOKIE_PATH = "/api/v1/auth"
_RATE = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return value
"""


@lru_cache
def redis_client():
    return Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


async def limit(request: Request, bucket: str, count: int, seconds: int = 60, identity: str | None = None):
    address = identity or (request.client.host if request.client else "unknown")
    key = f"pulse:rate:{bucket}:{digest(address)}"
    try:
        used = await redis_client().eval(_RATE, 1, key, seconds)
    except RedisError as exc:
        raise HTTPException(503, "Сервис временно недоступен") from exc
    if used > count:
        raise HTTPException(429, "Слишком много запросов. Попробуйте позже.", headers={"Retry-After": str(seconds)})


def require_origin(request: Request):
    if request.headers.get("origin") not in settings().origins:
        raise HTTPException(403, "Запрос с этого источника запрещён")


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


@lru_cache
def dummy_hash() -> str:
    return hasher.hash(token_urlsafe(32))


def password_matches(stored: str, supplied: str) -> bool:
    try:
        return hasher.verify(stored, supplied)
    except (VerificationError, InvalidHashError):
        return False


def sign_access(user: User, session: RefreshSession) -> str:
    current = now()
    return jwt.encode(
        {
            "sub": str(user.id), "sid": str(session.family_id), "iat": current,
            "exp": current + timedelta(minutes=settings().jwt_access_token_expire_minutes),
            "iss": "pulse-monitor", "aud": "pulse-web",
        },
        settings().jwt_secret_key.get_secret_value(), algorithm="HS256",
    )


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(401, "Войдите в аккаунт", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(
            credentials.credentials, settings().jwt_secret_key.get_secret_value(),
            algorithms=["HS256"], audience="pulse-web", issuer="pulse-monitor",
            options={"require": ["sub", "sid", "iat", "exp"]},
        )
        user_id, family_id = UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise unauthorized from exc
    active_session = select(RefreshSession.id).where(
        RefreshSession.user_id == User.id, RefreshSession.family_id == family_id,
        RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > now(),
    ).exists()
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active, active_session))
    if not user:
        raise unauthorized
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Требуются права администратора")
    return user
