import asyncio
from datetime import timedelta
from uuid import UUID

from celery import Celery
from kombu.exceptions import OperationalError
from sqlalchemy import delete

from app.core.config import settings
from app.db.session import session_factory
from app.models import MonitorCheck, RefreshSession, TelegramLink, now
from app.services.monitoring.run import release_reservation, reserve_due, run_one
from app.services.notifications.outbox import send_outbox
from app.services.notifications.poll import poll_telegram

config = settings()
celery = Celery("pulse", broker=config.redis_url)
celery.conf.update(
    accept_content=["json"], task_serializer="json", task_ignore_result=True,
    worker_prefetch_multiplier=1, task_acks_late=True, task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True, broker_transport_options={"visibility_timeout": 600},
    broker_connection_max_retries=12, task_publish_retry=False, task_time_limit=180,
    timezone="UTC",
    beat_schedule={
        "schedule-monitors": {"task": "pulse.schedule", "schedule": 10, "options": {"expires": 10}},
        "deliver-notifications": {"task": "pulse.delivery", "schedule": 15, "options": {"expires": 15}},
        "poll-telegram": {"task": "pulse.telegram", "schedule": 10, "options": {"expires": 10}},
        "prune-checks": {"task": "pulse.clean", "schedule": 3600, "options": {"expires": 3600}},
    },
)


@celery.task(name="pulse.schedule", ignore_result=True)
def schedule_due():
    async def dispatch():
        for monitor_id, token in await reserve_due():
            try:
                execute_check.delay(monitor_id, token)
            except OperationalError:
                await release_reservation(UUID(monitor_id), UUID(token))
    asyncio.run(dispatch())


@celery.task(name="pulse.probe", time_limit=65)
def execute_check(monitor_id: str, token: str):
    asyncio.run(run_one(UUID(monitor_id), UUID(token)))


@celery.task(name="pulse.delivery", time_limit=100)
def deliver_notifications():
    asyncio.run(send_outbox())


@celery.task(name="pulse.telegram")
def telegram_updates():
    asyncio.run(poll_telegram())


@celery.task(name="pulse.clean")
def clean_history():
    async def prune():
        current = now()
        async with session_factory(worker=True)() as db, db.begin():
            await db.execute(delete(MonitorCheck).where(MonitorCheck.checked_at < current - timedelta(days=config.check_retention_days)))
            await db.execute(delete(RefreshSession).where(RefreshSession.expires_at < current))
            await db.execute(delete(TelegramLink).where(TelegramLink.expires_at < current))
    asyncio.run(prune())
