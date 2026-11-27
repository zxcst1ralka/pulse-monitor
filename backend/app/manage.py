import argparse
import asyncio
import getpass
import math
from datetime import timedelta
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, insert, select

from app.core.config import settings
from app.core.security import hasher
from app.db.session import session_factory
from app.models import Incident, Monitor, MonitorCheck, StatusPage, StatusPageMonitor, User, now

SAMPLES = (
    ("Основной сайт", "www.example.com", 119),
    ("Production API", "api.example.com", 146),
    ("Каталог", "catalog.example.com", 173),
    ("Вебхуки", "hooks.example.com", 112),
    ("Сервис авторизации", "auth.example.com", 183),
    ("Платёжный шлюз", "payments.example.com", 151),
)


async def seed_demo(email: str, password: str):
    current = now().replace(second=0, microsecond=0)
    async with session_factory(worker=True)() as db, db.begin():
        existing = await db.scalar(select(User).where(User.email == email).with_for_update())
        if existing:
            if not existing.is_demo:
                raise SystemExit("Email already belongs to a regular account")
            existing.password_hash = hasher.hash(password)
            print("Demo account already seeded. Password updated.")
            return
        if await db.scalar(select(func.count()).select_from(User).where(User.is_demo)):
            raise SystemExit("A demo account already exists. Use its email.")
        user = User(email=email, name="Демо PulseMonitor", password_hash=hasher.hash(password), is_demo=True)
        db.add(user)
        await db.flush()
        monitors = [
            Monitor(
                name=name, url=f"https://{host}/", user_id=user.id, type="http", interval_seconds=1800,
                timeout_seconds=10, expected_status_code=200, response_threshold_ms=2000,
                status="down" if i == 5 else "up", notifications_enabled=False, is_synthetic=True,
                consecutive_failures=2 if i == 5 else 0, last_checked_at=current,
                next_check_at=current + timedelta(minutes=30), last_response_time_ms=None if i == 5 else latency,
                ssl_expires_at=current + timedelta(days=12 if i == 1 else 45 + i),
                ssl_valid=True, ssl_hostname_valid=True,
            )
            for i, (name, host, latency) in enumerate(SAMPLES)
        ]
        db.add_all(monitors)
        await db.flush()
        for index, monitor in enumerate(monitors):
            checks = []
            base = SAMPLES[index][2]
            resolved = {(index + 2) * 47, (index + 2) * 47 + 1} if index in (1, 3, 4) else set()
            for step in range(30 * 48):
                moment = current - timedelta(minutes=30 * step)
                failed = step in resolved or (index == 5 and step in (0, 1))
                checks.append({
                    "id": uuid4(), "monitor_id": monitor.id, "scheduled_at": moment, "checked_at": moment,
                    "status": "down" if failed else "up", "http_status_code": 503 if failed else 200,
                    "response_time_ms": 85 if failed else max(45, round(base + 30 * math.sin(step * 0.51 + index) + 17 * math.cos(step * 1.11))),
                    "error_message": "HTTP 503, ожидался 200" if failed else None,
                })
            await db.execute(insert(MonitorCheck), checks)
            if resolved:
                started_at = current - timedelta(minutes=30 * min(resolved))
                db.add(Incident(
                    monitor_id=monitor.id, status="resolved", reason="HTTP 503, ожидался 200",
                    http_status_code=503, started_at=started_at,
                    resolved_at=started_at + timedelta(minutes=30), duration_seconds=1800,
                ))
        db.add(Incident(
            monitor_id=monitors[-1].id, status="ongoing", reason="HTTP 503, ожидался 200",
            http_status_code=503, started_at=current,
        ))
        page = StatusPage(
            user_id=user.id, title="PulseMonitor Demo", slug="pulse-demo-" + user.id.hex[:8],
            description="Состояние сервисов демонстрационного рабочего пространства.", is_public=True,
        )
        db.add(page)
        await db.flush()
        db.add_all([StatusPageMonitor(status_page_id=page.id, monitor_id=item.id, display_order=i)
                    for i, item in enumerate(monitors)])
    print(f"Demo account seeded. Public page: /status/{page.slug}")


async def promote(email: str):
    async with session_factory(worker=True)() as db, db.begin():
        user = await db.scalar(select(User).where(User.email == email).with_for_update())
        if not user or user.is_demo:
            raise SystemExit("Register a regular account before promoting it")
        user.role = "admin"
    print("Administrator role granted")


def main():
    parser = argparse.ArgumentParser(description="PulseMonitor management")
    parser.add_argument("command", choices=["seed-demo", "promote-admin"])
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    try:
        email = validate_email(args.email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise SystemExit(str(exc)) from exc
    if args.command == "promote-admin":
        asyncio.run(promote(email))
        return
    if not settings().demo_mode or settings().app_env == "production":
        raise SystemExit("Demo data requires DEMO_MODE=true outside production")
    password = getpass.getpass("Choose a demo password: ").removesuffix("\r")
    if not 8 <= len(password) <= 256:
        raise SystemExit("Password length must be 8–256 characters")
    asyncio.run(seed_demo(email, password))


if __name__ == "__main__":
    main()
