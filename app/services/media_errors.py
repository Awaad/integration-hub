from __future__ import annotations
from enum import Enum


class MediaErrorCode(str, Enum):
    # validation
    MISSING_URL = "missing_url"
    INVALID_URL = "invalid_url"
    FORBIDDEN_HOST = "forbidden_host"
    FORBIDDEN_PORT = "forbidden_port"
    FORBIDDEN_SCHEME = "forbidden_scheme"
    DNS_FAILED = "dns_failed"
    DNS_TIMEOUT = "dns_timeout"

    # policy
    EXTERNAL_DISABLED = "external_disabled"
    DOMAIN_NOT_ALLOWED = "domain_not_allowed"

    # content
    UNSUPPORTED_MIME = "unsupported_mime"
    MIME_MISMATCH = "mime_mismatch"
    MEDIA_TOO_LARGE = "media_too_large"

    # network
    DOWNLOAD_TIMEOUT = "download_timeout"
    NETWORK_ERROR = "network_error"

    # system
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"


class MediaError(Exception):
    def __init__(self, code: MediaErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")


class MediaForbiddenError(MediaError):
    pass


class MediaRetryableError(MediaError):
    pass