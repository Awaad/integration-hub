from __future__ import annotations

import socket
import ipaddress
from urllib.parse import urlparse

from app.services.media_errors import (
    MediaErrorCode,
    MediaForbiddenError,
    MediaRetryableError,
)

_ALLOWED_SCHEMES = ("http", "https")
_ALLOWED_PORTS = (80, 443)


def _resolve_ips(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, None)
    if len(infos) > 32:
        raise MediaForbiddenError(
            MediaErrorCode.DNS_FAILED,
            "too many DNS results",
        )
    return [sockaddr[0] for *_rest, sockaddr in infos]


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _assert_ip_is_public(ip_str: str) -> None:
    ip = ipaddress.ip_address(ip_str)
    if not ip.is_global:
        raise MediaForbiddenError(
            MediaErrorCode.FORBIDDEN_HOST,
            f"non-global ip {ip_str}",
        )


def validate_media_url(
    url: str,
    *,
    allow_external: bool,
    allowed_domains: list[str],
) -> None:
    """
    Full SSRF + policy enforcement.
    SINGLE SOURCE OF TRUTH.
    """

    if not url:
        raise MediaForbiddenError(MediaErrorCode.MISSING_URL, "missing url")

    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise MediaForbiddenError(
            MediaErrorCode.FORBIDDEN_SCHEME,
            parsed.scheme or "",
        )

    if parsed.username or parsed.password:
        raise MediaForbiddenError(
            MediaErrorCode.INVALID_URL,
            "credentials not allowed",
        )

    if not parsed.hostname:
        raise MediaForbiddenError(
            MediaErrorCode.MISSING_URL,
            "missing hostname",
        )

    if parsed.port and parsed.port not in _ALLOWED_PORTS:
        raise MediaForbiddenError(
            MediaErrorCode.FORBIDDEN_PORT,
            str(parsed.port),
        )

    if not allow_external:
        raise MediaForbiddenError(
            MediaErrorCode.EXTERNAL_DISABLED,
            "external ingest disabled",
        )

    host = parsed.hostname.lower()

    # Domain allowlist
    if allowed_domains:
        if not any(
            host == d or host.endswith("." + d)
            for d in allowed_domains
        ):
            raise MediaForbiddenError(
                MediaErrorCode.DOMAIN_NOT_ALLOWED,
                host,
            )

    # SSRF protection
    if _is_ip_literal(host):
        _assert_ip_is_public(host)
    else:
        try:
            ips = _resolve_ips(host)
        except socket.gaierror as e:
            raise MediaRetryableError(
                MediaErrorCode.DNS_FAILED,
                str(e),
            )
        for ip in ips:
            _assert_ip_is_public(ip)