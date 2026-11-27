from datetime import timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import (
    COOKIE, COOKIE_PATH, current_user, digest, dummy_hash, hasher, limit,
    password_matches, require_origin, sign_access,
)
from app.db.session import get_db
from app.models import RefreshSession, User, now
from app.schemas import Access, Login, PasswordUpdate, ProfileUpdate, Register, UserView

auth = APIRouter(prefix="/auth", tags=["auth"])
profile = APIRouter(prefix="/profile", tags=["profile"])


def add_session(db: AsyncSession, response: Response, user: User, family: UUID | None = None) -> Access:
    value = token_urlsafe(48)
    age = timedelta(days=settings().jwt_refresh_token_expire_days)
    session = RefreshSession(
        user_id=user.id, token_hash=digest(value), expires_at=now() + age, family_id=family or uuid4(),
    )
    db.add(session)
    response.set_cookie(
        COOKIE, value, max_age=int(age.total_seconds()), path=COOKIE_PATH,
        secure=settings().secure_cookies, httponly=True, samesite="strict",
    )
    return Access(access_token=sign_access(user, session), user=UserView.model_validate(user))


async def clear_family(db: AsyncSession, session: RefreshSession):
    await db.execute(update(RefreshSession).where(
        RefreshSession.family_id == session.family_id, RefreshSession.revoked_at.is_(None),
    ).values(revoked_at=now()))


@auth.post("/register", status_code=201)
async def register(data: Register, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Access:
    require_origin(request)
    await limit(request, "register", 8, 600)
    user = User(email=data.email.lower(), name=data.name, password_hash=await run_in_threadpool(hasher.hash, data.password))
    db.add(user)
    try:
        await db.flush()
        result = add_session(db, response, user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Не удалось создать аккаунт с этим адресом") from exc
    return result


@auth.post("/login")
async def login(data: Login, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Access:
    require_origin(request)
    email = data.email.lower()
    await limit(request, "login", 15, 300)
    await limit(request, "login-account", 10, 300, email)
    user = await db.scalar(select(User).where(User.email == email))
    stored = user.password_hash if user else await run_in_threadpool(dummy_hash)
    valid = await run_in_threadpool(password_matches, stored, data.password)
    if not valid or not user or not user.is_active or (user.is_demo and not settings().demo_mode):
        raise HTTPException(401, "Неверный email или пароль")
    if hasher.check_needs_rehash(stored):
        user.password_hash = await run_in_threadpool(hasher.hash, data.password)
    result = add_session(db, response, user)
    await db.commit()
    return result


async def locked_session(db: AsyncSession, value: str | None):
    if not value or len(value) > 128:
        return None
    # Lock the user first. Logout, refresh, password changes and blocking share this ordering.
    candidate = (await db.execute(select(RefreshSession.id, RefreshSession.user_id).where(
        RefreshSession.token_hash == digest(value),
    ))).one_or_none()
    if candidate is None:
        return None
    user = await db.get(User, candidate.user_id, with_for_update=True)
    session = await db.get(RefreshSession, candidate.id, with_for_update=True)
    return (user, session) if user and session else None


@auth.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> Access:
    require_origin(request)
    await limit(request, "refresh", 40)
    found = await locked_session(db, request.cookies.get(COOKIE))
    if found:
        user, session = found
        if session.revoked_at:
            await clear_family(db, session)
            await db.commit()
        elif session.expires_at > now() and user.is_active and (not user.is_demo or settings().demo_mode):
            session.revoked_at = now()
            result = add_session(db, response, user, session.family_id)
            await db.commit()
            return result
    raise HTTPException(401, "Сессия завершена")


@auth.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    require_origin(request)
    found = await locked_session(db, request.cookies.get(COOKIE))
    if found:
        await clear_family(db, found[1])
        await db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH, secure=settings().secure_cookies, httponly=True, samesite="strict")


@auth.get("/me")
@profile.get("")
async def me(user: User = Depends(current_user)) -> UserView:
    return UserView.model_validate(user)


@profile.patch("")
async def update_profile(data: ProfileUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> UserView:
    if user.is_demo:
        raise HTTPException(403, "Профиль демонстрационного аккаунта доступен только для чтения")
    user.name = data.name
    await db.commit()
    return UserView.model_validate(user)


@profile.post("/change-password", status_code=204)
async def change_password(
    data: PasswordUpdate, request: Request, response: Response,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
):
    if user.is_demo:
        raise HTTPException(403, "Демонстрационный аккаунт")
    await limit(request, "password", 6, 600, str(user.id))
    await db.refresh(user, with_for_update=True)
    if not user.is_active:
        raise HTTPException(401, "Сессия завершена")
    if not await run_in_threadpool(password_matches, user.password_hash, data.current_password):
        raise HTTPException(400, "Текущий пароль не совпадает")
    user.password_hash = await run_in_threadpool(hasher.hash, data.new_password)
    await db.execute(update(RefreshSession).where(
        RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None),
    ).values(revoked_at=now()))
    await db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH, secure=settings().secure_cookies, httponly=True, samesite="strict")
