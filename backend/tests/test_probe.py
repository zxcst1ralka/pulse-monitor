import socket

import httpx
import pytest

from app.services.monitoring import probe as client
from app.services.monitoring.target import UnsafeTarget, public_ip, resolve_public, validate_url


@pytest.mark.parametrize("url", [
    "file:///tmp/file", "http://localhost", "http://something.internal", "http://127.0.0.1",
    "http://10.0.0.1", "http://169.254.169.254", "http://224.0.0.1", "http://100.100.100.200",
    "http://[::1]", "http://[fe80::1]", "http://[fc00::1]", "http://[::ffff:127.0.0.1]",
    "http://[64:ff9b::c000:201]", "http://[2002:7f00:1::]", "http://2130706433",
    "http://[fec0::1]", "http://192.88.99.1",
    "http://0x7f.0.0.1", "https://user:pass@example.com", "https://example.com:6379",
    "https://example.com/#fragment",
])
def test_destination_validation(url):
    with pytest.raises(UnsafeTarget):
        validate_url(url)


def test_public_dual_stack():
    assert str(public_ip("8.8.8.8")) == "8.8.8.8"
    assert str(public_ip("2606:4700:4700::1111")) == "2606:4700:4700::1111"
    assert str(validate_url("https://example.com:8443/health")) == "https://example.com:8443/health"


async def test_dns_rejects_mixed_public_private_answers(monkeypatch):
    import asyncio

    async def answers(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 443, 0, 0)),
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
    with pytest.raises(UnsafeTarget):
        await resolve_public(validate_url("https://example.com"))


@pytest.fixture
def pinned(monkeypatch):
    async def resolve(url):
        assert url.host in {"example.com", "status.example.com"}
        return ("8.8.8.8",)

    monkeypatch.setattr(client, "resolve_public", resolve)


async def test_pinned_connection_uses_host_and_sni(pinned):
    async def response(req):
        assert req.url.host == "8.8.8.8"
        assert req.url.path == "/health"
        assert req.headers["host"] == "example.com:8443"
        assert req.extensions["sni_hostname"] == "example.com"
        return httpx.Response(200, text="healthy")

    result = await client.probe("https://example.com:8443/health", 5, 200, 2000, None, transport=httpx.MockTransport(response))
    assert result.status == "up"
    assert result.http_status_code == 200
    assert result.response_time_ms >= 0


async def test_redirect_is_individually_validated(pinned):
    observed = []

    async def response(req):
        observed.append(req.headers["host"])
        if len(observed) == 1:
            return httpx.Response(302, headers={"location": "https://status.example.com/health"})
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    result = await client.probe("https://example.com", 5, 200, 2000, None, transport=httpx.MockTransport(response))
    assert result.status == "down"
    assert "Небезопасный" in result.reason
    assert observed == ["example.com", "status.example.com"]


@pytest.mark.parametrize(("code", "keyword", "text", "expected"), [
    (503, None, "service unavailable", "down"),
    (200, "ready", "server ready", "up"),
    (200, "ready", "starting", "down"),
])
async def test_http_and_keyword_checks(pinned, code, keyword, text, expected):
    async def response(_req):
        return httpx.Response(code, stream=httpx.ByteStream(text.encode()))

    result = await client.probe("https://example.com", 5, 200, 2000, keyword, transport=httpx.MockTransport(response))
    assert result.status == expected
    assert result.http_status_code == code


async def test_timeout(pinned):
    async def response(req):
        raise httpx.ReadTimeout("upstream did not respond", request=req)

    result = await client.probe("https://example.com", 5, 200, 2000, None, transport=httpx.MockTransport(response))
    assert result.status == "down"
    assert result.reason == "Истекло время ожидания"
