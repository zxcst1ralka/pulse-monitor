import asyncio
import socket
import ssl
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import perf_counter

import httpx
from cryptography import x509

from app.services.monitoring.target import UnsafeTarget, resolve_public, validate_url

REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 4
MAX_BODY = 1024 * 1024


@dataclass(frozen=True)
class ProbeResult:
    status: str
    http_status_code: int | None = None
    response_time_ms: int | None = None
    reason: str | None = None
    ssl_expires_at: datetime | None = None
    ssl_valid: bool | None = None
    ssl_hostname_valid: bool | None = None


def tls_info(response: httpx.Response):
    stream = response.extensions.get("network_stream")
    ssl_object = stream.get_extra_info("ssl_object") if stream else None
    if ssl_object is None:
        return None
    return x509.load_der_x509_certificate(ssl_object.getpeercert(binary_form=True)).not_valid_after_utc


async def contains_keyword(response: httpx.Response, keyword: str) -> bool:
    encoding = response.encoding or "utf-8"
    content = bytearray()
    async for chunk in response.aiter_raw(chunk_size=16_384):
        if len(content) + len(chunk) > MAX_BODY:
            return keyword in content.decode(encoding, errors="replace")
        content.extend(chunk)
    return keyword in content.decode(encoding, errors="replace")


def connection_failure(exc: httpx.ConnectError) -> ProbeResult:
    cause: BaseException | None = exc
    while cause:
        if isinstance(cause, ssl.SSLCertVerificationError):
            expired = cause.verify_code == 10
            mismatch = cause.verify_code in {62, 64}
            reason = "Срок TLS-сертификата истёк" if expired else (
                "Имя хоста не совпадает с TLS-сертификатом" if mismatch else "TLS-сертификат не прошёл проверку"
            )
            return ProbeResult("down", reason=reason, ssl_valid=False, ssl_hostname_valid=False if mismatch else None)
        cause = cause.__cause__
    return ProbeResult("down", reason="Не удалось установить соединение")


async def probe(
    target: str, timeout: int, expected: int, threshold_ms: int, keyword: str | None,
    *, transport: httpx.AsyncBaseTransport | None = None,
) -> ProbeResult:
    start = perf_counter()
    certificate = None
    try:
        async with asyncio.timeout(timeout), httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=timeout,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            transport=transport,
            headers={"Accept-Encoding": "identity", "User-Agent": "PulseMonitor/1.0"},
        ) as client:
            url = validate_url(target)
            for hop in range(MAX_REDIRECTS + 1):
                addresses = await resolve_public(url)
                hostname = url.raw_host.decode("ascii").rstrip(".")
                host = f"[{hostname}]" if ":" in hostname else hostname
                if url.port:
                    host = f"{host}:{url.port}"
                for index, ip in enumerate(addresses):
                    try:
                        request = client.build_request(
                            "GET", url.copy_with(host=ip), headers={"Host": host},
                            extensions={"sni_hostname": hostname},
                        )
                        response = await client.send(request, stream=True)
                        break
                    except httpx.ConnectError as exc:
                        failure = connection_failure(exc)
                        if index == len(addresses) - 1 or failure.ssl_valid is False:
                            return failure
                try:
                    if certificate is None and url.scheme == "https":
                        certificate = tls_info(response)
                    code = response.status_code
                    location = response.headers.get("location")
                    if code in REDIRECT_CODES and code != expected and location:
                        if hop == MAX_REDIRECTS:
                            result = ProbeResult("down", code, reason="Слишком много перенаправлений")
                            break
                        if "\\" in location or any(ord(char) < 33 or ord(char) == 127 for char in location):
                            raise UnsafeTarget("Некорректное перенаправление")
                        url = validate_url(str(url.join(location)))
                        continue
                    latency = round((perf_counter() - start) * 1000)
                    if code != expected:
                        result = ProbeResult("down", code, latency, f"HTTP {code}, ожидался {expected}")
                    elif keyword and response.headers.get("content-encoding", "identity").lower() != "identity":
                        result = ProbeResult("down", code, latency, "Сервер вернул неподдерживаемое сжатие для проверки текста")
                    elif keyword and not await contains_keyword(response, keyword):
                        result = ProbeResult("down", code, latency, "Текст не найден в первом 1 МиБ ответа")
                    else:
                        result = ProbeResult("degraded" if latency > threshold_ms else "up", code, latency)
                    break
                finally:
                    await response.aclose()
    except UnsafeTarget:
        result = ProbeResult("down", reason="Небезопасный адрес назначения или перенаправление")
    except (TimeoutError, httpx.TimeoutException):
        result = ProbeResult("down", reason="Истекло время ожидания")
    except socket.gaierror:
        result = ProbeResult("down", reason="Не удалось разрешить доменное имя")
    except (httpx.NetworkError, httpx.RemoteProtocolError, httpx.InvalidURL):
        result = ProbeResult("down", reason="Сервер вернул некорректный ответ")
    if certificate:
        return replace(result, ssl_expires_at=certificate.astimezone(timezone.utc), ssl_valid=True, ssl_hostname_valid=True)
    return result
