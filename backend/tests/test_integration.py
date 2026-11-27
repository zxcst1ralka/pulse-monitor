import asyncio
import os
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.api.v1 import extras
from app.core.config import settings
from app.core.security import redis_client
from app.db.session import session_factory
from app.main import create_app
from app.models import Incident, Monitor, MonitorCheck, NotificationChannel, NotificationLog, User, now
from app.services.monitoring import run
from app.services.monitoring.probe import ProbeResult
from app.services.notifications.outbox import TelegramError, record_event
from app.services.notifications.poll import redeem

TEST_DATABASE = os.environ.get("TEST_DATABASE_URL")
TEST_REDIS = os.environ.get("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not (TEST_DATABASE and TEST_REDIS), reason="requires isolated PostgreSQL and Redis")


@pytest.fixture
async def test_env(monkeypatch):
    assert urlsplit(TEST_DATABASE).path.endswith("_test"), "Use a dedicated test database"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("FRONTEND_URL", "http://pulse.test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE)
    monkeypatch.setenv("REDIS_URL", TEST_REDIS)
    monkeypatch.setenv("JWT_SECRET_KEY", uuid4().hex + uuid4().hex)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "")
    monkeypatch.setenv("DEMO_MODE", "false")
    ids = []
    settings.cache_clear()
    try:
        yield ids
    finally:
        async with session_factory(worker=True)() as db, db.begin():
            await db.execute(delete(User).where(User.id.in_(ids)))
        await redis_client().aclose()
        await session_factory().kw["bind"].dispose()
        await session_factory(worker=True).kw["bind"].dispose()
        redis_client.cache_clear()
        session_factory.cache_clear()
        settings.cache_clear()


@pytest.fixture
async def client(test_env):
    address = f"198.18.{uuid4().int % 254}.{uuid4().int % 254}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(), client=(address, 4000)),
        base_url="http://pulse.test/api/v1", headers={"Origin": "http://pulse.test"},
    ) as client:
        yield client


async def register(client, ids):
    email = f"pytest-{uuid4().hex}@example.com"
    password = uuid4().hex
    response = await client.post("/auth/register", json={"email": email, "password": password, "name": "Integration test"})
    assert response.status_code == 201, response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    data = response.json()
    ids.append(UUID(data["user"]["id"]))
    return {"Authorization": "Bearer " + data["access_token"]}, email, password


async def add_monitor(client, auth, **updates):
    response = await client.post("/monitors", headers=auth, json={"name": "Public service", "url": "https://example.com/health", **updates})
    assert response.status_code == 201, response.text
    return response.json()


async def test_auth_profile_and_session_rotation(client, test_env):
    headers, email, password = await register(client, test_env)
    assert (await client.get("/auth/me", headers=headers)).json()["email"] == email
    assert (await client.post("/auth/refresh", headers={"Origin": "https://elsewhere.example"})).status_code == 403
    initial = client.cookies.get("pulse_refresh")
    rotated = await client.post("/auth/refresh")
    assert rotated.status_code == 200
    assert initial != client.cookies.get("pulse_refresh")
    current = {"Authorization": "Bearer " + rotated.json()["access_token"]}
    assert (await client.get("/auth/me", headers=current)).status_code == 200
    assert (await client.post("/auth/refresh", headers={"Cookie": "pulse_refresh=" + initial})).status_code == 401
    assert (await client.get("/auth/me", headers=current)).status_code == 401
    failed = {"email": email, "password": "incorrect"}
    invalid_login = await client.post("/auth/login", json=failed)
    missing_login = await client.post("/auth/login", json={**failed, "email": "missing@example.com"})
    assert invalid_login.json() == missing_login.json() == {"detail": "Неверный email или пароль"}
    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    current = {"Authorization": "Bearer " + login.json()["access_token"]}
    rename = await client.patch("/profile", headers=current, json={"name": "New name"})
    assert rename.json()["name"] == "New name"
    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/auth/me", headers=current)).status_code == 401


async def test_monitor_crud_permissions_and_public_projection(client, test_env):
    owner, _, _ = await register(client, test_env)
    another, _, _ = await register(client, test_env)
    monitor = await add_monitor(client, owner)
    path = "/monitors/" + monitor["id"]
    assert (await client.get(path, headers=another)).status_code == 404
    assert (await client.post(path + "/check", headers=another)).status_code == 404
    assert (await client.get("/admin/stats", headers=owner)).status_code == 403
    rejected = await client.patch(path, headers=owner, json={"url": "http://127.0.0.1"})
    assert rejected.status_code == 422
    changed = await client.patch(path, headers=owner, json={"name": "Renamed"})
    assert changed.json()["name"] == "Renamed"
    assert (await client.get("/monitors?search=renamed", headers=owner)).json()[0]["name"] == "Renamed"
    assert (await client.get(path + "/stats", headers=owner)).json()["uptime"] is None
    assert (await client.post(path + "/pause", headers=owner)).json()["status"] == "paused"
    assert (await client.post(path + "/check", headers=owner)).status_code == 409
    assert (await client.post(path + "/resume", headers=owner)).json()["status"] == "pending"
    assert (await client.post(path + "/check", headers=owner)).status_code == 202
    slug = "pytest-" + uuid4().hex
    payload = {"title": "Public test", "slug": slug, "monitor_ids": [monitor["id"]]}
    assert (await client.post("/status-pages", headers=another, json=payload)).status_code == 422
    page = await client.post("/status-pages", headers=owner, json=payload)
    assert page.status_code == 201, page.text
    assert (await client.get("/public/status/" + slug)).status_code == 404
    assert (await client.patch("/status-pages/" + page.json()["id"], headers=owner, json={"is_public": True})).status_code == 200
    public = await client.get("/public/status/" + slug)
    assert public.status_code == 200, public.text
    assert public.json()["monitors"][0] == {
        "id": monitor["id"], "name": "Renamed", "status": "pending", "uptime": None,
    }
    assert "example.com" not in public.text
    assert (await client.delete(path, headers=owner)).status_code == 204
    assert (await client.get(path, headers=owner)).status_code == 404


async def test_worker_reserves_only_once_and_restores_incident(client, test_env, monkeypatch):
    headers, _, _ = await register(client, test_env)
    monitor = await add_monitor(client, headers)
    monitor_id = UUID(monitor["id"])
    results = iter([ProbeResult("down", 503, 190, "HTTP 503")] * 3 + [ProbeResult("up", 200, 112)])
    observed = 0

    async def probe(*_args):
        nonlocal observed
        observed += 1
        await asyncio.sleep(.02)
        return next(results)

    monkeypatch.setattr(run, "probe", probe)
    for step in range(4):
        if step:
            async with session_factory(worker=True)() as db, db.begin():
                item = await db.get(Monitor, monitor_id)
                item.next_check_at = now() - timedelta(seconds=1)
        queues = await asyncio.gather(run.reserve_due(), run.reserve_due())
        tokens = [UUID(token) for queue in queues for item_id, token in queue if item_id == str(monitor_id)]
        assert len(tokens) == 1
        await asyncio.gather(run.run_one(monitor_id, tokens[0]), run.run_one(monitor_id, tokens[0]))
        matching = (await client.get("/incidents", headers=headers)).json()
        assert len(matching) == (0 if step == 0 else 1)
        if matching:
            assert matching[0]["status"] == ("resolved" if step == 3 else "ongoing")
    assert observed == 4
    response = await client.get("/dashboard/summary", headers=headers)
    assert response.status_code == 200, response.text
    stats = response.json()
    assert stats["uptime"] == 25
    assert stats["average_ms"] == 112
    assert stats["open_incidents"] == 0
    series = (await client.get("/dashboard/response-times?window=24h", headers=headers)).json()
    assert len(series) == 24
    assert series[-1]["value"] == 112
    async with session_factory(worker=True)() as db:
        assert await db.scalar(select(func.count()).select_from(MonitorCheck).where(MonitorCheck.monitor_id == monitor_id)) == 4
        assert await db.scalar(select(func.count()).select_from(Incident).where(Incident.monitor_id == monitor_id)) == 1


async def test_notification_event_deduplication(client, test_env, monkeypatch):
    headers, _, _ = await register(client, test_env)
    monitor = await add_monitor(client, headers)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", uuid4().hex)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "integration_test_bot")
    settings.cache_clear()
    async with session_factory(worker=True)() as db, db.begin():
        channel = NotificationChannel(user_id=test_env[-1], type="telegram", configuration={"chat_id": 1, "events": ["down"]})
        db.add(channel)
        await db.flush()
        item = await db.get(Monitor, UUID(monitor["id"]))
        await record_event(db, item, "down", "same-event", "First")
        await record_event(db, item, "down", "same-event", "Second")
        assert await db.scalar(select(func.count()).select_from(NotificationLog).where(NotificationLog.channel_id == channel.id)) == 1


async def test_telegram_link_is_single_use_and_delivery_is_reported(client, test_env, monkeypatch):
    headers, _, _ = await register(client, test_env)
    assert (await client.post("/notifications/telegram/connect", headers=headers)).status_code == 503
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", uuid4().hex)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "integration_test_bot")
    settings.cache_clear()
    connection = await client.post("/notifications/telegram/connect", headers=headers)
    assert connection.status_code == 200, connection.text
    code = parse_qs(urlsplit(connection.json()["url"]).query)["start"][0]
    assert await redeem(code, 9123)
    assert not await redeem(code, 9124)
    status = (await client.get("/notifications/telegram/status", headers=headers)).json()
    assert status["connected"] and "chat_id" not in status["channel"]
    channel = "/notifications/channels/" + status["channel"]["id"]
    assert (await client.patch(channel, headers=headers, json={"is_active": True, "events": ["down"]})).status_code == 200
    calls = 0

    async def send(method, payload):
        nonlocal calls
        assert method == "sendMessage" and payload["chat_id"] == 9123
        calls += 1
        if calls == 1:
            raise TelegramError("Telegram mock unavailable")
        return {"message_id": 7}

    monkeypatch.setattr(extras, "telegram", send)
    assert (await client.post(channel + "/test", headers=headers)).status_code == 502
    assert (await client.post(channel + "/test", headers=headers)).json() == {"status": "sent"}
    logs = (await client.get("/notifications/logs", headers=headers)).json()
    assert [row["status"] for row in logs] == ["sent", "failed"]
