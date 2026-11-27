from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Incident, Monitor, MonitorCheck, now
from app.schemas import IncidentView, Window

WINDOWS = {"24h": (timedelta(days=1), 3600), "7d": (timedelta(days=7), 21600), "30d": (timedelta(days=30), 86400)}
HEALTHY = ("up", "degraded")


def start_of(window: Window, current: datetime | None = None) -> datetime:
    return (current or now()) - WINDOWS[window][0]


def totals():
    elapsed = MonitorCheck.response_time_ms
    success = MonitorCheck.status.in_(HEALTHY)
    return (
        func.count().label("checks"), func.count().filter(success).label("successful"),
        func.avg(elapsed).filter(success).label("average_ms"),
        func.min(elapsed).filter(success).label("min_ms"),
        func.max(elapsed).filter(success).label("max_ms"),
        func.percentile_cont(0.95).within_group(elapsed).filter(success).label("p95_ms"),
    )


def uptime(successful: int, total: int) -> float | None:
    return round(successful * 100 / total, 2) if total else None


def with_uptime(row):
    return {**row, "uptime": uptime(row["successful"], row["checks"])}


async def chart(
    db: AsyncSession, ids: list[UUID], window: Window, current: datetime,
    *, metric: Literal["latency", "availability"] = "latency",
):
    duration, step = WINDOWS[window]
    start = current - duration
    index = func.floor(func.extract("epoch", MonitorCheck.checked_at - start) / step)
    successful = MonitorCheck.status.in_(HEALTHY)
    if metric == "availability":
        value = 100.0 * func.count().filter(successful) / func.count()
        precision = 2
    else:
        value = func.avg(MonitorCheck.response_time_ms).filter(successful)
        precision = None
    results = dict((await db.execute(select(index, value).where(
        MonitorCheck.monitor_id.in_(ids), MonitorCheck.checked_at >= start, MonitorCheck.checked_at < current,
    ).group_by(index))).all())
    return [
        {
            "time": start + timedelta(seconds=i * step),
            "value": round(float(results[i]), precision) if results.get(i) is not None else None,
        }
        for i in range(int(duration.total_seconds()) // step)
    ]


async def monitor_stats(db: AsyncSession, monitor_id: UUID, window: Window):
    current = now()
    start = start_of(window, current)
    filters = [MonitorCheck.monitor_id == monitor_id, MonitorCheck.checked_at <= current]
    aggregate = (await db.execute(select(*totals()).where(*filters, MonitorCheck.checked_at >= start))).mappings().one()
    aggregate_windows = []
    for name in WINDOWS:
        interval = MonitorCheck.checked_at >= start_of(name, current)
        aggregate_windows.extend([
            func.count().filter(and_(interval, MonitorCheck.status.in_(HEALTHY))).label(f"successful_{name}"),
            func.count().filter(interval).label(f"total_{name}"),
        ])
    windows = (await db.execute(select(*aggregate_windows).where(
        *filters, MonitorCheck.checked_at >= start_of("30d", current),
    ))).mappings().one()
    duration = func.extract("epoch", func.least(func.coalesce(Incident.resolved_at, current), current) -
                            func.greatest(Incident.started_at, start))
    count, seconds = (await db.execute(select(func.count(), func.coalesce(func.sum(duration), 0)).where(
        Incident.monitor_id == monitor_id, Incident.started_at <= current,
        (Incident.resolved_at.is_(None) | (Incident.resolved_at >= start)),
    ))).one()
    history = await chart(db, [monitor_id], window, current)
    return {
        **with_uptime(aggregate), "window": window, "incident_count": count, "incident_seconds": int(seconds),
        "uptime_windows": {name: uptime(windows[f"successful_{name}"], windows[f"total_{name}"]) for name in WINDOWS},
        "series": history,
    }


async def list_incidents(
    db: AsyncSession, user_id: UUID, *, monitor_id: UUID | None = None, incident_id: UUID | None = None,
    status: str | None = None, limit: int = 50, offset: int = 0,
) -> list[IncidentView]:
    query = select(Incident, Monitor.name).join(Monitor).where(Monitor.user_id == user_id)
    if monitor_id:
        query = query.where(Incident.monitor_id == monitor_id)
    if incident_id:
        query = query.where(Incident.id == incident_id)
    if status:
        query = query.where(Incident.status == status)
    rows = (await db.execute(query.order_by(Incident.started_at.desc(), Incident.id).limit(limit).offset(offset))).all()
    return [
        IncidentView(
            id=item.id, monitor_id=item.monitor_id, monitor_name=name, status=item.status, reason=item.reason,
            http_status_code=item.http_status_code, started_at=item.started_at, resolved_at=item.resolved_at,
            duration_seconds=item.duration_seconds if item.resolved_at else max(0, int((now() - item.started_at).total_seconds())),
        )
        for item, name in rows
    ]


def uptime_per_monitor(ids: list[UUID]):
    return select(
        MonitorCheck.monitor_id.label("id"), func.count().label("checks"),
        func.count().filter(MonitorCheck.status.in_(HEALTHY)).label("successful"),
    ).where(MonitorCheck.monitor_id.in_(ids), MonitorCheck.checked_at >= start_of("30d")).group_by(MonitorCheck.monitor_id)


def status_priority():
    return case(
        (Monitor.status == "down", 0), (Monitor.status == "degraded", 1), (Monitor.status == "pending", 2),
        (Monitor.status == "up", 3), else_=4,
    )
