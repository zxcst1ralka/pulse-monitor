import asyncio
import ipaddress
import re
import socket

import httpx

ALLOWED_PORTS = {"http": {80, 8080}, "https": {443, 8443}}
UNSAFE_V4 = tuple(map(ipaddress.ip_network, ("192.0.0.0/24", "192.88.99.0/24")))
UNSAFE_V6 = tuple(map(ipaddress.ip_network, (
    "::/96", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001::/32", "2002::/16", "fec0::/10",
)))
UNSAFE_NAMES = ("localhost", "local", "internal", "localhost.localdomain", "home.arpa")
DNS_LABEL = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)$", re.I)


class UnsafeTarget(ValueError):
    pass


def public_ip(raw: str):
    if "%" in raw:
        raise UnsafeTarget("Адрес назначения запрещён")
    ip = ipaddress.ip_address(raw)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    special_ranges = UNSAFE_V6 if isinstance(ip, ipaddress.IPv6Address) else UNSAFE_V4
    if not ip.is_global or ip.is_multicast or ip.is_reserved or any(ip in network for network in special_ranges):
        raise UnsafeTarget("Адрес назначения должен быть публичным")
    return ip


def validate_url(value: str) -> httpx.URL:
    if len(value) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value:
        raise UnsafeTarget("Некорректный URL")
    try:
        url = httpx.URL(value)
        host = url.raw_host.decode("ascii").lower().rstrip(".")
    except (httpx.InvalidURL, UnicodeError) as exc:
        raise UnsafeTarget("Некорректный URL") from exc
    if url.scheme not in ALLOWED_PORTS or not host or url.userinfo or "#" in value or "@" in value.split("/")[2]:
        raise UnsafeTarget("Укажите HTTP(S)-адрес без учётных данных и фрагмента")
    if url.port is not None and url.port not in ALLOWED_PORTS[url.scheme]:
        raise UnsafeTarget("Порт этого протокола запрещён")
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in UNSAFE_NAMES) or "%" in host:
        raise UnsafeTarget("Адрес назначения запрещён")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or "." not in host or not all(DNS_LABEL.fullmatch(label) for label in host.split(".")):
            raise UnsafeTarget("Укажите публичное доменное имя или IP-адрес")
        if host.rsplit(".", 1)[-1].isdigit():
            raise UnsafeTarget("Некорректный IP-адрес")
    else:
        public_ip(host)
    return url


async def resolve_public(url: httpx.URL) -> tuple[str, ...]:
    host = url.raw_host.decode("ascii").rstrip(".")
    port = url.port or (443 if url.scheme == "https" else 80)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        loop = asyncio.get_running_loop()
        addresses = await loop.getaddrinfo(f"{host}.", port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        if not addresses:
            raise socket.gaierror("empty DNS answer")
        return tuple(dict.fromkeys(str(public_ip(record[4][0])) for record in addresses))
    return (str(public_ip(host)),)
