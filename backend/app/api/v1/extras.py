from datetime import timedelta
from secrets import token_urlsafe
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.api.v1.dependencies import Account, Db, Offset, PageSize, owned, require_writable
from app.core.config import settings
from app.core.security import admin_user, digest, limit
from app.models import (
    Incident, Monitor, NotificationChannel, NotificationLog, RefreshSession, StatusPage, StatusPageMonitor,
    TelegramLink, User, now,
)
from app.schemas import AdminUpdate, ChannelUpdate, StatusPageInput, StatusPagePatch, StatusPageView, UserView
from app.services.analytics import start_of, uptime, uptime_per_monitor
from app.services.notifications.outbox import EVENTS, TelegramError, telegram

pages = APIRouter(prefix="/status-pages", tags=["status pages"])
public = APIRouter(prefix="/public/status", tags=["status pages"])
notifications = APIRouter(prefix="/notifications", tags=["notifications"])
admin = APIRouter(prefix="/admin", tags=["admin"])
Administrator = Annotated[User, Depends(admin_user)]


async def selected(db: Db, page: StatusPage) -> list[UUID]:
    return list(await db.scalars(select(StatusPageMonitor.monitor_id).where(
        StatusPageMonitor.status_page_id == page.id,
    ).order_by(StatusPageMonitor.display_order)))


def page_view(page: StatusPage, ids: list[UUID]) -> StatusPageView:
    return StatusPageView(
        id=page.id, title=page.title, slug=page.slug, description=page.description, is_public=page.is_public,
        updated_at=page.updated_at, monitor_ids=ids,
    )


async def save_page(db: Db, user: User, page: StatusPage, values: dict) -> StatusPageView:
    ids = values.pop("monitor_ids", None)
    try:
        if ids is not None:
            ids = list(dict.fromkeys(ids))
            valid = set(await db.scalars(select(Monitor.id).where(
                Monitor.user_id == user.id, Monitor.id.in_(ids),
            ).order_by(Monitor.id).with_for_update(read=True)))
            if valid != set(ids):
                raise HTTPException(422, "Выберите собственные мониторы")
        for field, value in values.items():
            setattr(page, field, value)
        page.updated_at = now()
        await db.flush()
        if ids is not None:
            await db.execute(delete(StatusPageMonitor).where(StatusPageMonitor.status_page_id == page.id))
            db.add_all([
                StatusPageMonitor(status_page_id=page.id, monitor_id=monitor_id, display_order=index)
                for index, monitor_id in enumerate(ids)
            ])
        else:
            ids = await selected(db, page)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Такой адрес страницы уже занят") from exc
    return page_view(page, ids)


@pages.get("")
async def page_list(db: Db, user: Account, limit: PageSize = 50, offset: Offset = 0) -> list[StatusPageView]:
    items = list(await db.scalars(select(StatusPage).where(StatusPage.user_id == user.id).order_by(
        StatusPage.created_at.desc(), StatusPage.id,
    ).limit(limit).offset(offset)))
    return [page_view(page, await selected(db, page)) for page in items]


@pages.post("", status_code=201)
async def page_create(data: StatusPageInput, db: Db, user: Account) -> StatusPageView:
    require_writable(user)
    await db.get(User, user.id, with_for_update=True)
    count = await db.scalar(select(func.count()).select_from(StatusPage).where(StatusPage.user_id == user.id))
    if count >= 20:
        raise HTTPException(409, "Достигнут лимит статус-страниц")
    page = StatusPage(user_id=user.id, id=uuid4())
    db.add(page)
    # Prevent the monitor ownership lookup from flushing the incomplete page.
    with db.no_autoflush:
        return await save_page(db, user, page, data.model_dump())


@pages.get("/{page_id}")
async def page_detail(page_id: UUID, db: Db, user: Account) -> StatusPageView:
    page = await owned(db, StatusPage, page_id, user)
    return page_view(page, await selected(db, page))


@pages.patch("/{page_id}")
async def page_edit(page_id: UUID, data: StatusPagePatch, db: Db, user: Account) -> StatusPageView:
    require_writable(user)
    page = await owned(db, StatusPage, page_id, user, lock=True)
    return await save_page(db, user, page, data.model_dump(exclude_unset=True))


@pages.delete("/{page_id}", status_code=204)
async def page_delete(page_id: UUID, db: Db, user: Account):
    require_writable(user)
    await db.delete(await owned(db, StatusPage, page_id, user, lock=True))
    await db.commit()


@public.get("/{slug}")
async def public_page(slug: str, request: Request, db: Db):
    await limit(request, "public-status", 90)
    page = await db.scalar(select(StatusPage).join(User).where(StatusPage.slug == slug, StatusPage.is_public, User.is_active))
    if not page:
        raise HTTPException(404, "Статус-страница не найдена")
    rows = list(await db.scalars(select(Monitor).join(StatusPageMonitor).where(
        StatusPageMonitor.status_page_id == page.id, Monitor.user_id == page.user_id,
    ).order_by(StatusPageMonitor.display_order)))
    ids = [row.id for row in rows]
    stats = {row.id: uptime(row.successful, row.checks) for row in (await db.execute(uptime_per_monitor(ids))).all()}
    history = (await db.execute(select(Incident, Monitor.name).join(Monitor).where(
        Incident.monitor_id.in_(ids), (Incident.started_at >= start_of("30d")) | (Incident.status == "ongoing"),
    ).order_by(Incident.started_at.desc()).limit(30))).all()
    states = {row.status for row in rows if row.is_active}
    overall = next((state for state in ("down", "degraded", "pending", "up") if state in states), "paused" if rows else "pending")
    updated_at = max([
        page.updated_at,
        *(row.updated_at if row.status in {"paused", "pending"} else row.last_checked_at or row.updated_at for row in rows),
    ])
    return {
        "title": page.title, "description": page.description, "overall": overall,
        "updated_at": updated_at,
        "synthetic": any(row.is_synthetic for row in rows),
        "monitors": [{"id": row.id, "name": row.name, "status": row.status, "uptime": stats.get(row.id)} for row in rows],
        "incidents": [{
            "id": incident.id, "monitor_name": name, "status": incident.status,
            "started_at": incident.started_at, "resolved_at": incident.resolved_at,
        } for incident, name in history],
    }


def view_channel(channel: NotificationChannel) -> dict:
    return {"id": channel.id, "type": channel.type, "is_active": channel.is_active, "events": channel.configuration.get("events", [])}


@notifications.get("/channels")
async def channels(db: Db, user: Account):
    return [view_channel(row) for row in await db.scalars(select(NotificationChannel).where(NotificationChannel.user_id == user.id))]


@notifications.get("/telegram/status")
async def connection_status(db: Db, user: Account):
    channel = await db.scalar(select(NotificationChannel).where(
        NotificationChannel.user_id == user.id, NotificationChannel.type == "telegram",
    ))
    return {"configured": settings().telegram_enabled, "connected": bool(channel), "channel": view_channel(channel) if channel else None}


@notifications.post("/telegram/connect")
async def connect(request: Request, db: Db, user: Account):
    require_writable(user)
    await limit(request, "telegram-link", 5, 300, str(user.id))
    if not settings().telegram_enabled:
        raise HTTPException(503, "Интеграция Telegram пока не настроена")
    code = f"pulse_{token_urlsafe(24)}"
    expires = now() + timedelta(minutes=10)
    values = {"code_hash": digest(code), "expires_at": expires}
    await db.execute(insert(TelegramLink).values(user_id=user.id, **values).on_conflict_do_update(
        index_elements=["user_id"], set_=values,
    ))
    await db.commit()
    return {"url": f"https://t.me/{settings().telegram_bot_username}?start={code}", "expires_at": expires}


@notifications.patch("/channels/{channel_id}")
async def channel_edit(channel_id: UUID, data: ChannelUpdate, db: Db, user: Account):
    require_writable(user)
    channel = await owned(db, NotificationChannel, channel_id, user, lock=True)
    channel.is_active = data.is_active
    channel.configuration = {**channel.configuration, "events": sorted(data.events)}
    await db.commit()
    return view_channel(channel)


@notifications.delete("/channels/{channel_id}", status_code=204)
async def channel_delete(channel_id: UUID, db: Db, user: Account):
    require_writable(user)
    await db.delete(await owned(db, NotificationChannel, channel_id, user, lock=True))
    await db.commit()


@notifications.post("/channels/{channel_id}/test")
async def test_channel(channel_id: UUID, request: Request, db: Db, user: Account):
    require_writable(user)
    await limit(request, "telegram-test", 3, 60, str(user.id))
    channel = await owned(db, NotificationChannel, channel_id, user)
    if not channel.is_active:
        raise HTTPException(409, "Включите канал, чтобы отправить тест")
    error = None
    try:
        await telegram("sendMessage", {"chat_id": channel.configuration["chat_id"], "text": "PulseMonitor · тестовое уведомление"})
    except TelegramError as exc:
        error = str(exc)
    db.add(NotificationLog(
        channel_id=channel.id, event_type="test", deduplication_key=str(uuid4()), message="Тестовое уведомление",
        status="failed" if error else "sent", error_message=error, sent_at=None if error else now(),
    ))
    await db.commit()
    if error:
        raise HTTPException(502, error)
    return {"status": "sent"}


@notifications.get("/logs")
async def notification_logs(db: Db, user: Account, limit: PageSize = 50, offset: Offset = 0):
    rows = await db.scalars(select(NotificationLog).join(NotificationChannel).where(
        NotificationChannel.user_id == user.id,
    ).order_by(NotificationLog.created_at.desc(), NotificationLog.id).limit(limit).offset(offset))
    return [{
        "id": row.id, "event_type": row.event_type, "status": row.status,
        "error_message": row.error_message, "created_at": row.created_at,
    } for row in rows]


@admin.get("/users")
async def admin_users(db: Db, user: Administrator, limit: PageSize = 50, offset: Offset = 0) -> list[UserView]:
    return [UserView.model_validate(row) for row in await db.scalars(
        select(User).order_by(User.created_at.desc(), User.id).limit(limit).offset(offset),
    )]


@admin.patch("/users/{user_id}")
async def admin_block(user_id: UUID, data: AdminUpdate, db: Db, user: Administrator) -> UserView:
    target = await db.get(User, user_id, with_for_update=True)
    if not target:
        raise HTTPException(404, "Пользователь не найден")
    if target.role == "admin":
        raise HTTPException(409, "Этот аккаунт администрируется через командную строку")
    target.is_active = data.is_active
    if not data.is_active:
        await db.execute(update(RefreshSession).where(
            RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None),
        ).values(revoked_at=now()))
    await db.commit()
    return UserView.model_validate(target)


@admin.get("/stats")
async def admin_stats(db: Db, user: Administrator):
    current = now()
    return {
        "users": await db.scalar(select(func.count()).select_from(User)),
        "monitors": await db.scalar(select(func.count()).select_from(Monitor)),
        "reserved": await db.scalar(select(func.count()).select_from(Monitor).where(Monitor.lease_until > current)),
        "running": await db.scalar(select(func.count()).select_from(Monitor).where(Monitor.lease_until > current, Monitor.check_started)),
        "telegram_events": list(EVENTS),
    }
