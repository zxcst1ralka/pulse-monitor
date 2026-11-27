import logging
from redis.asyncio import Redis

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.security import digest
from app.db.session import session_factory
from app.models import NotificationChannel, TelegramLink, User, now
from app.services.notifications.outbox import EVENTS, TelegramError, telegram

logger = logging.getLogger(__name__)


async def redeem(code: str, chat_id: int) -> bool:
    async with session_factory(worker=True)() as db, db.begin():
        link = await db.scalar(select(TelegramLink).where(
            TelegramLink.code_hash == digest(code), TelegramLink.expires_at > now(),
        ).with_for_update())
        if not link:
            return False
        user = await db.get(User, link.user_id)
        if not user or not user.is_active:
            return False
        values = {"chat_id": chat_id, "events": list(EVENTS)}
        await db.execute(insert(NotificationChannel).values(
            user_id=link.user_id, type="telegram", configuration=values, is_active=True,
        ).on_conflict_do_update(constraint="uq_user_channel", set_={"configuration": values, "is_active": True}))
        await db.delete(link)
        return True


async def poll_telegram():
    config = settings()
    if not config.telegram_enabled:
        return
    key = f"pulse:telegram:{digest(config.telegram_bot_token.get_secret_value())[:16]}"
    async with Redis.from_url(config.redis_url, socket_timeout=3) as redis:
        lock = redis.lock(f"{key}:lock", timeout=180, blocking=False)
        if not await lock.acquire():
            return
        try:
            offset = int(await redis.get(f"{key}:offset") or 0)
            updates = await telegram("getUpdates", {"offset": offset, "limit": 10, "timeout": 0, "allowed_updates": ["message"]})
            for update in updates:
                message = update.get("message", {})
                chat = message.get("chat", {})
                parts = message.get("text", "").split(maxsplit=1)
                if chat.get("type") == "private" and len(parts) == 2 and parts[0] == "/start" and parts[1].startswith("pulse_"):
                    if await redeem(parts[1], chat["id"]):
                        try:
                            await telegram("sendMessage", {"chat_id": chat["id"], "text": "Telegram подключён к PulseMonitor."})
                        except TelegramError:
                            logger.warning("Telegram linkage recorded, confirmation unavailable")
                await redis.set(f"{key}:offset", update["update_id"] + 1)
        except TelegramError as exc:
            logger.warning("%s", exc)
        finally:
            await lock.release()
