from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import Float, cast, func, select

from app.api.v1.dependencies import Account, Db, Offset, PageSize, owned, require_writable
from app.core.config import settings
from app.models import Incident, Monitor, MonitorCheck, User, now
from app.schemas import CheckView, IncidentView, MonitorInput, MonitorPatch, MonitorRow, MonitorStatus, MonitorView, Window
from app.services.analytics import (
    chart, list_incidents, monitor_stats, start_of, status_priority, totals, uptime, uptime_per_monitor, with_uptime,
)
from app.services.monitoring.target import UnsafeTarget, validate_url

monitors = APIRouter(prefix="/monitors", tags=["monitors"])
dashboard = APIRouter(prefix="/dashboard", tags=["dashboard"])
incidents = APIRouter(prefix="/incidents", tags=["incidents"])
IncidentStatus = Literal["ongoing", "resolved"]


def normalize(data: MonitorInput) -> dict:
    address = data.url if "://" in data.url else f"https://{data.url}"
    try:
        url = validate_url(address)
    except UnsafeTarget as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**data.model_dump(), "url": str(url)}


def cancel_reservation(monitor: Monitor):
    monitor.dispatch_token = None
    monitor.lease_until = None
    monitor.check_started = False


@monitors.get("")
async def index(
    db: Db, user: Account, search: Annotated[str, Query(max_length=100)] = "", status: MonitorStatus | None = None,
    sort: Literal["name", "status", "uptime", "latency", "last_checked", "interval", "newest"] = "newest",
    limit: PageSize = 50, offset: Offset = 0,
) -> list[MonitorRow]:
    ids = list(await db.scalars(select(Monitor.id).where(Monitor.user_id == user.id)))
    summary = uptime_per_monitor(ids).subquery()
    percentage = cast(summary.c.successful, Float) / summary.c.checks
    ordering = {
        "name": func.lower(Monitor.name), "status": status_priority(), "uptime": percentage.desc().nulls_last(),
        "latency": Monitor.last_response_time_ms.asc().nulls_last(),
        "last_checked": Monitor.last_checked_at.desc().nulls_last(), "interval": Monitor.interval_seconds,
        "newest": Monitor.created_at.desc(),
    }
    query = select(Monitor, summary.c.successful, summary.c.checks).outerjoin(
        summary, summary.c.id == Monitor.id,
    ).where(Monitor.user_id == user.id)
    if search:
        query = query.where(Monitor.name.icontains(search, autoescape=True) | Monitor.url.icontains(search, autoescape=True))
    if status:
        query = query.where(Monitor.status == status)
    rows = (await db.execute(query.order_by(ordering[sort], Monitor.id).limit(limit).offset(offset))).all()
    return [
        MonitorRow(**MonitorView.model_validate(item).model_dump(), uptime=uptime(successful or 0, checked or 0))
        for item, successful, checked in rows
    ]


@monitors.post("", status_code=201)
async def create(data: MonitorInput, db: Db, user: Account) -> MonitorView:
    require_writable(user)
    values = normalize(data)
    await db.get(User, user.id, with_for_update=True)
    count = await db.scalar(select(func.count()).select_from(Monitor).where(Monitor.user_id == user.id))
    if count >= settings().max_monitors_per_user:
        raise HTTPException(409, "Достигнут лимит мониторов")
    monitor = Monitor(user_id=user.id, **values)
    db.add(monitor)
    await db.commit()
    return MonitorView.model_validate(monitor)


@monitors.get("/{monitor_id}")
async def detail(monitor_id: UUID, db: Db, user: Account) -> MonitorView:
    return MonitorView.model_validate(await owned(db, Monitor, monitor_id, user))


@monitors.patch("/{monitor_id}")
async def edit(monitor_id: UUID, data: MonitorPatch, db: Db, user: Account) -> MonitorView:
    require_writable(user)
    monitor = await owned(db, Monitor, monitor_id, user, lock=True)
    old = MonitorInput.model_validate(monitor, from_attributes=True).model_dump()
    try:
        values = normalize(MonitorInput.model_validate({**old, **data.model_dump(exclude_unset=True)}))
    except ValidationError as exc:
        raise HTTPException(422, "Проверьте настройки монитора и ключевое слово") from exc
    check_fields = {"url", "type", "interval_seconds", "timeout_seconds", "expected_status_code", "keyword", "response_threshold_ms"}
    if any(values[field] != old[field] for field in check_fields):
        cancel_reservation(monitor)
        monitor.next_check_at = now()
        monitor.consecutive_failures = 0
    if values["url"] != old["url"]:
        monitor.ssl_expires_at = monitor.ssl_valid = monitor.ssl_hostname_valid = None
        monitor.status = "pending" if monitor.is_active else "paused"
        monitor.last_response_time_ms = None
    for field, value in values.items():
        setattr(monitor, field, value)
    await db.commit()
    return MonitorView.model_validate(monitor)


@monitors.delete("/{monitor_id}", status_code=204)
async def remove(monitor_id: UUID, db: Db, user: Account):
    require_writable(user)
    await db.delete(await owned(db, Monitor, monitor_id, user, lock=True))
    await db.commit()


@monitors.post("/{monitor_id}/pause")
async def pause(monitor_id: UUID, db: Db, user: Account) -> MonitorView:
    require_writable(user)
    monitor = await owned(db, Monitor, monitor_id, user, lock=True)
    monitor.is_active = False
    monitor.status = "paused"
    monitor.consecutive_failures = 0
    cancel_reservation(monitor)
    await db.commit()
    return MonitorView.model_validate(monitor)


@monitors.post("/{monitor_id}/resume")
async def resume(monitor_id: UUID, db: Db, user: Account) -> MonitorView:
    require_writable(user)
    monitor = await owned(db, Monitor, monitor_id, user, lock=True)
    if not monitor.is_active:
        monitor.is_active = True
        monitor.status = "pending"
        monitor.next_check_at = now()
        await db.commit()
    return MonitorView.model_validate(monitor)


@monitors.post("/{monitor_id}/check", status_code=202)
async def enqueue(monitor_id: UUID, db: Db, user: Account):
    require_writable(user)
    monitor = await owned(db, Monitor, monitor_id, user, lock=True)
    current = now()
    if not monitor.is_active:
        raise HTTPException(409, "Возобновите монитор перед проверкой")
    if monitor.lease_until and monitor.lease_until > current:
        return {"scheduled_at": monitor.next_check_at}
    if monitor.last_checked_at and current - monitor.last_checked_at < timedelta(seconds=30):
        raise HTTPException(429, "Между ручными проверками должно пройти 30 секунд")
    cancel_reservation(monitor)
    monitor.next_check_at = min(monitor.next_check_at, current)
    await db.commit()
    return {"scheduled_at": monitor.next_check_at}


@monitors.get("/{monitor_id}/checks")
async def checks(monitor_id: UUID, db: Db, user: Account, limit: PageSize = 50, offset: Offset = 0) -> list[CheckView]:
    await owned(db, Monitor, monitor_id, user)
    rows = await db.scalars(select(MonitorCheck).where(MonitorCheck.monitor_id == monitor_id).order_by(
        MonitorCheck.checked_at.desc(), MonitorCheck.id,
    ).offset(offset).limit(limit))
    return [CheckView.model_validate(row) for row in rows]


@monitors.get("/{monitor_id}/stats")
async def stats(monitor_id: UUID, db: Db, user: Account, window: Window = "24h"):
    await owned(db, Monitor, monitor_id, user)
    return await monitor_stats(db, monitor_id, window)


@monitors.get("/{monitor_id}/incidents")
async def monitor_incidents(
    monitor_id: UUID, db: Db, user: Account, limit: PageSize = 50, offset: Offset = 0,
) -> list[IncidentView]:
    await owned(db, Monitor, monitor_id, user)
    return await list_incidents(db, user.id, monitor_id=monitor_id, limit=limit, offset=offset)


@incidents.get("")
async def incident_index(
    db: Db, user: Account, status: IncidentStatus | None = None, limit: PageSize = 50, offset: Offset = 0,
) -> list[IncidentView]:
    return await list_incidents(db, user.id, status=status, limit=limit, offset=offset)


@incidents.get("/{incident_id}")
async def incident_detail(incident_id: UUID, db: Db, user: Account) -> IncidentView:
    matches = await list_incidents(db, user.id, incident_id=incident_id, limit=1)
    if not matches:
        raise HTTPException(404, "Инцидент не найден")
    return matches[0]


@dashboard.get("/summary")
async def summary(db: Db, user: Account, window: Window = "24h"):
    statuses = dict((await db.execute(select(Monitor.status, func.count()).where(
        Monitor.user_id == user.id,
    ).group_by(Monitor.status))).all())
    ids = select(Monitor.id).where(Monitor.user_id == user.id)
    metrics = (await db.execute(select(*totals()).where(
        MonitorCheck.monitor_id.in_(ids), MonitorCheck.checked_at >= start_of(window),
    ))).mappings().one()
    incidents_open = await db.scalar(select(func.count()).select_from(Incident).where(
        Incident.monitor_id.in_(ids), Incident.status == "ongoing",
    ))
    return {"total": sum(statuses.values()), "statuses": statuses, "open_incidents": incidents_open, **with_uptime(metrics)}


@dashboard.get("/response-times")
async def response_times(db: Db, user: Account, window: Window = "24h"):
    ids = list(await db.scalars(select(Monitor.id).where(Monitor.user_id == user.id)))
    return await chart(db, ids, window, now())


@dashboard.get("/availability")
async def availability(db: Db, user: Account, window: Window = "24h"):
    ids = list(await db.scalars(select(Monitor.id).where(Monitor.user_id == user.id)))
    return await chart(db, ids, window, now(), metric="availability")


@dashboard.get("/ssl-warnings")
async def ssl_warnings(db: Db, user: Account, limit: PageSize = 5, offset: Offset = 0):
    expiry_limit = now() + timedelta(days=30)
    rows = await db.execute(select(
        Monitor.id, Monitor.name, Monitor.ssl_valid, Monitor.ssl_expires_at,
    ).where(
        Monitor.user_id == user.id, Monitor.is_active,
        Monitor.ssl_valid.is_(False) | (Monitor.ssl_expires_at <= expiry_limit),
    ).order_by(
        Monitor.ssl_valid.asc().nulls_last(), Monitor.ssl_expires_at.nulls_last(), Monitor.id,
    ).limit(limit).offset(offset))
    return [dict(row) for row in rows.mappings()]


@dashboard.get("/recent-incidents")
async def recent(db: Db, user: Account, limit: PageSize = 5) -> list[IncidentView]:
    return await list_incidents(db, user.id, limit=limit)
