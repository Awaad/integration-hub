from __future__ import annotations

import socket
import ipaddress
from urllib.parse import urlparse


class MediaForbiddenError(Exception):
    pass


def _is_private_ip(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
        for family, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return True
        return False
    except Exception:
        return True


def validate_media_url(
    url: str,
    *,
    allow_external: bool,
    allowed_domains: list[str],
) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise MediaForbiddenError("unsupported URL scheme")

    if not parsed.hostname:
        raise MediaForbiddenError("missing hostname")

    if _is_private_ip(parsed.hostname):
        raise MediaForbiddenError("private or internal IP not allowed")

    if not allow_external:
        raise MediaForbiddenError("external media disabled")

    if allowed_domains:
        host = parsed.hostname.lower()
        if not any(host == d or host.endswith("." + d) for d in allowed_domains):
            raise MediaForbiddenError("domain not allowlisted")