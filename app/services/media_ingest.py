from __future__ import annotations

import hashlib
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urljoin

import anyio
import httpx
import ipaddress
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import gen_id
from app.models.media_object import MediaObject
from app.services.media_storage.provider import get_media_storage

MAX_MEDIA_BYTES = 25 * 1024 * 1024  # 25MB

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0

DNS_TIMEOUT = 2.0
TOTAL_TIMEOUT = 40.0

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_MAX_REDIRECTS = 5
_ALLOWED_SCHEMES = ("http", "https")


def _ext_from_mime(mime: str) -> str:
    return _MIME_TO_EXT.get(mime, "bin")


def _is_private_host(host: str) -> bool:
    # host may be an IP literal
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
        )
    except ValueError:
        return False


async def _resolve_and_block_private(hostname: str) -> None:
    """
    Resolve hostname and reject any non-global IP results.
    NOTE: This is best-effort SSRF hardening; DNS rebinding is still possible without pinning.
    """

    def _get_ips() -> list[str]:
        infos = socket.getaddrinfo(hostname, None)
        if len(infos) > 32:
            raise ValueError("too many DNS results")
        ips: list[str] = []
        for _fam, _socktype, _proto, _canonname, sockaddr in infos:
            ips.append(sockaddr[0])
        return ips

    try:
        with anyio.fail_after(DNS_TIMEOUT):
            ips = await anyio.to_thread.run_sync(_get_ips)
    except (anyio.exceptions.TimeoutError, TimeoutError) as e:
        raise ValueError("dns lookup timeout") from e
    except socket.gaierror as e:
        raise ValueError("dns lookup failed") from e

    for ip_s in ips:
        try:
            ip = ipaddress.ip_address(ip_s)
        except ValueError:
            continue
        if not ip.is_global:
            raise ValueError("forbidden non-global IP host")


def _validate_public_url(url: str) -> None:
    u = urlparse(url)

    if u.username or u.password:
        raise ValueError("forbidden credentials in URL")

    if u.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("unsupported URL scheme")
    if not u.netloc:
        raise ValueError("missing URL host")

    host = u.hostname or ""
    if not host:
        raise ValueError("missing URL host")
    if host in ("localhost",):
        raise ValueError("forbidden host")
    if _is_private_host(host):
        raise ValueError("forbidden private IP host")

    # Restrict weird ports (SSRF surface)
    if u.port and u.port not in (80, 443):
        raise ValueError("forbidden port")


def _parse_mime(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _content_length(resp: httpx.Response) -> int | None:
    v = resp.headers.get("content-length")
    if not v:
        return None
    try:
        n = int(v)
        return n if n >= 0 else None
    except Exception:
        return None


def _is_redirect(status_code: int) -> bool:
    return status_code in (301, 302, 303, 307, 308)


def _sniff_image_mime(prefix: bytes) -> str | None:
    """
    Very small magic-byte sniff. Returns canonical MIME if detected, else None.
    """
    if len(prefix) >= 3 and prefix[:3] == b"\xFF\xD8\xFF":
        return "image/jpeg"
    if len(prefix) >= 8 and prefix[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # WEBP: "RIFF" .... "WEBP"
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp"
    return None

def _cleanup_tmp(tmp_path: str | None) -> None:
    if not tmp_path:
        return
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass


async def _stream_to_temp_and_hash(
    client: httpx.AsyncClient, url: str
) -> tuple[str, int, str, str]:
    """
    Returns (tmp_path, byte_size, content_hash_hex, mime).
    """
    url = (url or "").strip()
    _validate_public_url(url)

    # DNS hardening for initial URL (best-effort)
    host = urlparse(url).hostname
    if host:
        try:
            ipaddress.ip_address(host)  # IP literal -> skip DNS
        except ValueError:
            await _resolve_and_block_private(host)

    h = hashlib.sha256()
    byte_size = 0

    fd, tmp_path = tempfile.mkstemp(prefix="media_ingest_", suffix=".tmp")
    os.close(fd)

    cur_url = url
    redirects = 0

    try:
        with anyio.fail_after(TOTAL_TIMEOUT):
            while True:
                cur_url = (cur_url or "").strip()
                _validate_public_url(cur_url)

                # DNS hardening each hop (best-effort)
                host = urlparse(cur_url).hostname
                if host:
                    try:
                        ipaddress.ip_address(host)
                    except ValueError:
                        await _resolve_and_block_private(host)

                async with client.stream("GET", cur_url) as resp:
                    if _is_redirect(resp.status_code):
                        if redirects >= _MAX_REDIRECTS:
                            raise ValueError("too many redirects")

                        loc = resp.headers.get("location")
                        if not loc:
                            raise ValueError("redirect missing location")

                        # Build absolute URL and validate it (SSRF guard)
                        cur_url = urljoin(cur_url, loc)
                        redirects += 1
                        continue

                    resp.raise_for_status()

                    header_mime = _parse_mime(resp.headers.get("content-type"))
                    if header_mime not in ALLOWED_MIME:
                        raise ValueError(f"unsupported mime_type: {header_mime}")

                    cl = _content_length(resp)
                    if cl is not None and cl > MAX_MEDIA_BYTES:
                        raise ValueError(
                            f"media_too_large: content-length {cl} > {MAX_MEDIA_BYTES}"
                        )

                    sniff_buf = bytearray()
                    sniff_mime: str | None = None

                    async with await anyio.open_file(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue

                            # size limit
                            byte_size += len(chunk)
                            if byte_size > MAX_MEDIA_BYTES:
                                raise ValueError(f"media_too_large: > {MAX_MEDIA_BYTES} bytes")

                            # sniff first bytes before trusting header
                            if sniff_mime is None and len(sniff_buf) < 32:
                                take = min(32 - len(sniff_buf), len(chunk))
                                sniff_buf.extend(chunk[:take])
                                if len(sniff_buf) >= 12:  # enough for webp check
                                    sniff_mime = _sniff_image_mime(bytes(sniff_buf))
                                    if sniff_mime and sniff_mime != header_mime:
                                        raise ValueError(
                                            f"mime_mismatch: header={header_mime} sniff={sniff_mime}"
                                        )

                            h.update(chunk)
                            await f.write(chunk)

                    # If we never got enough bytes to sniff, accept header MIME (tiny files may still sniff)
                    final_mime = header_mime
                    if sniff_mime is not None:
                        final_mime = sniff_mime

                    return tmp_path, byte_size, h.hexdigest(), final_mime

    except (anyio.exceptions.TimeoutError, TimeoutError) as e:
        await _cleanup_tmp(tmp_path)
        raise ValueError("download timeout") from e
    except Exception:
        await _cleanup_tmp(tmp_path)
        raise


async def ingest_media_from_url(
    db: AsyncSession,
    *,
    tenant_id: str,
    partner_id: str,
    agent_id: str,
    url: str,
    created_by: str,
) -> MediaObject:
    """
    Download -> hash -> dedupe by (tenant_id, partner_id, agent_id, content_hash)
    -> store -> insert MediaObject.

    Notes:
    - No cross-agent work: caller must provide the target agent_id; dedupe is scoped to agent_id.
    - Partner admin can publish for agents: handled at authorization layer; this function just enforces
      the scoping by using agent_id as part of the dedupe/storage key.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("missing url")

    if not agent_id:
        raise ValueError("missing agent_id")

    _validate_public_url(url)

    timeout = httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    headers = {
        "User-Agent": "hub-media-normalizer/1.0",
        "Accept": "image/*",
        "Accept-Encoding": "identity",
    }

    tmp_path: str | None = None

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,  # we handle redirects manually
        limits=limits,
        headers=headers,
    ) as client:
        tmp_path, byte_size, content_hash, mime = await _stream_to_temp_and_hash(client, url)

    ext = _ext_from_mime(mime)

    # Dedup read (agent_id is NOT NULL)
    where = [
        MediaObject.tenant_id == tenant_id,
        MediaObject.partner_id == partner_id,
        MediaObject.agent_id == agent_id,
        MediaObject.content_hash == content_hash,
    ]

    existing = (await db.execute(select(MediaObject).where(*where))).scalar_one_or_none()
    if existing:
        await _cleanup_tmp(tmp_path)
        return existing

    storage = get_media_storage()

    # IMPORTANT: storage key is deterministic in LocalMediaStorage:
    #   tenant/partner/agent/hash.ext
    # This makes uploads idempotent and prevents orphaned duplicates on race.
    stored = await storage.put_file(
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        content_hash=content_hash,
        file_path=Path(tmp_path),
        ext=ext,
        byte_size=byte_size,
    )

    # tmp already unlinked by LocalMediaStorage.put_file when it moves/copies
    tmp_path = None

    m = MediaObject(
        id=gen_id("med"),
        tenant_id=tenant_id,
        partner_id=partner_id,
        agent_id=agent_id,
        content_hash=content_hash,
        byte_size=stored.byte_size,
        mime_type=mime,
        storage_backend=stored.backend,
        storage_key=stored.key,
        source_url=url,
        width=None,
        height=None,
        created_by=created_by,
        updated_by=created_by,
    )

    try:
        async with db.begin_nested():
            db.add(m)
            await db.flush()
        return m
    except IntegrityError:
        # Someone else inserted same (tenant, partner, agent, hash). Storage is deterministic so no orphan.
        winner = (await db.execute(select(MediaObject).where(*where).limit(1))).scalar_one()
        return winner
    finally:
        _cleanup_tmp(tmp_path)