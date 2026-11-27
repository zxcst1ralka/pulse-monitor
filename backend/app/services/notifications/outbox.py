from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.session import session_factory
from app.models import Monitor, NotificationChannel, NotificationLog, User, now

EVENTS = ("down", "recovered", "ssl")


class TelegramError(RuntimeError):
    pass


async def telegram(method: str, body: dict):
    config = settings()
    if not config.telegram_enabled:
        raise TelegramError("Telegram не настроен")
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=8) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{config.telegram_bot_token.get_secret_value()}/{method}", json=body,
            )
            data = response.json()
            if not response.is_success or not data.get("ok"):
                raise TelegramError(f"Telegram API отклонил запрос ({response.status_code})")
            return data["result"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise TelegramError("Ответ Telegram API не получен") from exc


async def record_event(db, monitor: Monitor, event: str, unique_value: str, message: str):
    if not monitor.notifications_enabled or not settings().telegram_enabled:
        return
    channel = await db.scalar(select(NotificationChannel).where(
        NotificationChannel.user_id == monitor.user_id, NotificationChannel.type == "telegram", NotificationChannel.is_active,
    ))
    if not channel or event not in channel.configuration.get("events", []) or not channel.configuration.get("chat_id"):
        return
    key = f"{channel.id}:{monitor.id}:{event}:{unique_value}"
    await db.execute(insert(NotificationLog).values(
        id=uuid4(), channel_id=channel.id, monitor_id=monitor.id, event_type=event,
        deduplication_key=key, message=f"PulseMonitor\n\n{message}", status="pending",
    ).on_conflict_do_nothing(index_elements=["deduplication_key"]))


async def send_outbox():
    if not settings().telegram_enabled:
        return
    factory = session_factory(worker=True)
    async with factory() as db, db.begin():
        await db.execute(update(NotificationLog).where(
            NotificationLog.status == "sending", NotificationLog.sent_at < now() - timedelta(minutes=5),
        ).values(status="failed", error_message="Подтверждение доставки потеряно", sent_at=None))
    for _ in range(8):
        async with factory() as db, db.begin():
            row = await db.scalar(select(NotificationLog).where(
                NotificationLog.status == "pending",
            ).order_by(NotificationLog.created_at).limit(1).with_for_update(skip_locked=True))
            if not row:
                return
            channel = await db.get(NotificationChannel, row.channel_id)
            user = await db.get(User, channel.user_id) if channel else None
            chat_id = channel.configuration.get("chat_id") if channel and channel.is_active and user and user.is_active else None
            if not chat_id:
                row.status = "failed"
                row.error_message = "Канал отключён"
                continue
            row.status = "sending"
            row.sent_at = now()
            log_id, message = row.id, row.message
        error = None
        try:
            await telegram("sendMessage", {"chat_id": chat_id, "text": message})
        except TelegramError as exc:
            error = str(exc)
        async with factory() as db, db.begin():
            await db.execute(update(NotificationLog).where(
                NotificationLog.id == log_id, NotificationLog.status == "sending",
            ).values(status="failed" if error else "sent", error_message=error, sent_at=None if error else now()))
