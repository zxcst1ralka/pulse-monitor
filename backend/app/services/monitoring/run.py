from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select

from app.db.session import session_factory
from app.models import Incident, Monitor, MonitorCheck, User, now
from app.services.monitoring.probe import ProbeResult, probe
from app.services.notifications.outbox import record_event


async def reserve_due():
    current = now()
    async with session_factory(worker=True)() as db, db.begin():
        due = list(await db.scalars(select(Monitor).join(User, Monitor.user_id == User.id).where(
            Monitor.is_active, ~Monitor.is_synthetic, User.is_active, Monitor.next_check_at <= current,
            or_(Monitor.lease_until.is_(None), Monitor.lease_until < current),
        ).order_by(Monitor.next_check_at).limit(24).with_for_update(of=Monitor, skip_locked=True)))
        for monitor in due:
            monitor.dispatch_token = uuid4()
            monitor.lease_until = current + timedelta(minutes=4)
            monitor.check_started = False
        return [(str(monitor.id), str(monitor.dispatch_token)) for monitor in due]


async def release_reservation(monitor_id: UUID, token: UUID):
    async with session_factory(worker=True)() as db, db.begin():
        monitor = await db.get(Monitor, monitor_id, with_for_update=True)
        if monitor and monitor.dispatch_token == token and not monitor.check_started:
            monitor.lease_until = None
            monitor.dispatch_token = None


async def run_one(monitor_id: UUID, token: UUID):
    factory = session_factory(worker=True)
    async with factory() as db, db.begin():
        monitor = await db.get(Monitor, monitor_id, with_for_update=True)
        if not monitor or not monitor.is_active or monitor.dispatch_token != token or monitor.check_started:
            return
        user = await db.get(User, monitor.user_id)
        if not user or not user.is_active or not monitor.lease_until or monitor.lease_until <= now():
            return
        monitor.check_started = True
        monitor.lease_until = now() + timedelta(seconds=75)
        values = (monitor.url, monitor.timeout_seconds, monitor.expected_status_code, monitor.response_threshold_ms, monitor.keyword)
    # Unexpected exceptions leave a lease that the scheduler can recover. They do not count as outages.
    result = await probe(*values)
    async with factory() as db, db.begin():
        monitor = await db.get(Monitor, monitor_id, with_for_update=True)
        if not monitor or not monitor.is_active or monitor.dispatch_token != token:
            return
        user = await db.get(User, monitor.user_id)
        if not user or not user.is_active:
            return
        await apply_result(db, monitor, result)


async def apply_result(db, monitor: Monitor, result: ProbeResult):
    current = now()
    incident = await db.scalar(select(Incident).where(
        Incident.monitor_id == monitor.id, Incident.status == "ongoing",
    ))
    if result.status == "down":
        monitor.consecutive_failures += 1
        if monitor.consecutive_failures >= 2 or incident:
            monitor.status = "down"
        if monitor.consecutive_failures >= 2 and not incident:
            incident = Incident(
                monitor_id=monitor.id, reason=result.reason or "Проверка не пройдена",
                http_status_code=result.http_status_code, started_at=current,
            )
            db.add(incident)
            await db.flush()
            await record_event(db, monitor, "down", str(incident.id), f"🔴 {monitor.name} недоступен\n{incident.reason}")
    else:
        monitor.status = result.status
        monitor.consecutive_failures = 0
        if incident:
            incident.status = "resolved"
            incident.resolved_at = current
            incident.duration_seconds = int((current - incident.started_at).total_seconds())
            await record_event(
                db, monitor, "recovered", str(incident.id),
                f"🟢 {monitor.name} восстановлен\nПростой: {incident.duration_seconds} с\nОтвет: {result.response_time_ms} мс",
            )
    db.add(MonitorCheck(
        monitor_id=monitor.id, status=result.status, http_status_code=result.http_status_code,
        response_time_ms=result.response_time_ms, error_message=result.reason,
        scheduled_at=monitor.next_check_at, checked_at=current,
    ))
    if result.ssl_valid is not None:
        monitor.ssl_valid = result.ssl_valid
        monitor.ssl_hostname_valid = result.ssl_hostname_valid
        if result.ssl_expires_at:
            monitor.ssl_expires_at = result.ssl_expires_at
            remaining = (result.ssl_expires_at - current).total_seconds() / 86400
            for days in (1, 7, 14, 30):
                if 0 <= remaining <= days:
                    await record_event(
                        db, monitor, "ssl", f"{result.ssl_expires_at.isoformat()}:{days}",
                        f"🟠 {monitor.name}\nTLS-сертификат истекает в течение {days} дн.",
                    )
                    break
    monitor.last_checked_at = current
    monitor.last_response_time_ms = result.response_time_ms
    monitor.next_check_at = current + timedelta(seconds=monitor.interval_seconds)
    monitor.dispatch_token = None
    monitor.lease_until = None
    monitor.check_started = False
