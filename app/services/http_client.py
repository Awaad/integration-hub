from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Literal

import httpx


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


@dataclass(frozen=True)
class HttpResult:
    ok: bool
    status_code: int | None
    detail: dict[str, Any]

    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False

    elapsed_ms: int | None = None
    response_headers: dict[str, str] | None = None


def _is_json_response(resp: httpx.Response) -> bool:
    ct = (resp.headers.get("content-type") or "").lower()
    return "application/json" in ct or ct.endswith("+json")


def _cap_text(s: str, *, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"...(truncated, {len(s)} chars)"


class HubHttpClient:
    """
    Shared HTTP client wrapper for destination connectors.

    - Uses one AsyncClient instance (connection pooling).
    - Does NOT implement exponential backoff retries (Delivery layer handles it).
    - Returns structured result with retryable classification.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_response_body_chars: int = 20_000,
        default_headers: Mapping[str, str] | None = None,
    ):
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_body = max_response_body_chars
        self._default_headers = dict(default_headers or {})
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request_json(
        self,
        *,
        method: HttpMethod,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> HttpResult:
        # Merge headers (caller wins)
        h = dict(self._default_headers)
        if headers:
            h.update(dict(headers))
        if request_id and "X-Request-Id" not in h:
            h["X-Request-Id"] = request_id

        try:
            resp = await self._client.request(
                method=method,
                url=url,
                headers=h,
                params=dict(params or {}),
                json=json_body,
            )
        except httpx.TimeoutException as e:
            return HttpResult(
                ok=False,
                status_code=None,
                detail={"error": "timeout"},
                error_code="TIMEOUT",
                error_message=str(e),
                retryable=True,
            )
        except httpx.RequestError as e:
            # DNS errors, connection refused, TLS, etc.
            return HttpResult(
                ok=False,
                status_code=None,
                detail={"error": "request_error"},
                error_code="REQUEST_ERROR",
                error_message=str(e),
                retryable=True,
            )

        # Parse response
        detail: dict[str, Any]
        if _is_json_response(resp):
            try:
                parsed = resp.json()
                # Ensure dict payload (if API returns list/string, still keep it)
                detail = parsed if isinstance(parsed, dict) else {"data": parsed}
            except Exception:
                detail = {"raw": _cap_text(resp.text, max_chars=self._max_body)}
        else:
            # Non-JSON response (HTML, text, etc.)
            detail = {
                "raw": _cap_text(resp.text, max_chars=self._max_body),
                "content_type": resp.headers.get("content-type"),
            }

        elapsed_ms = int(resp.elapsed.total_seconds() * 1000) if resp.elapsed else None
        response_headers = {
            # small subset that is commonly useful
            "content-type": resp.headers.get("content-type", ""),
            "date": resp.headers.get("date", ""),
            "retry-after": resp.headers.get("retry-after", ""),
            "x-request-id": resp.headers.get("x-request-id", ""),
            "x-ratelimit-remaining": resp.headers.get("x-ratelimit-remaining", ""),
            "x-ratelimit-reset": resp.headers.get("x-ratelimit-reset", ""),
        }

        if 200 <= resp.status_code < 300:
            return HttpResult(
                ok=True,
                status_code=resp.status_code,
                detail=detail,
                retryable=False,
                elapsed_ms=elapsed_ms,
                response_headers=response_headers,
            )

        # Retryability
        retryable = resp.status_code in (408, 429, 500, 502, 503, 504)

        # 401/403 are non-retryable explicitly for now
        if resp.status_code in (401, 403, 404):
            retryable = False

        return HttpResult(
            ok=False,
            status_code=resp.status_code,
            detail=detail,
            error_code=f"HTTP_{resp.status_code}",
            error_message=f"HTTP {resp.status_code}",
            retryable=retryable,
            elapsed_ms=elapsed_ms,
            response_headers=response_headers,
        )

    # helpers
    async def post_json(self, *, url: str, headers: Mapping[str, str] | None = None, params: Mapping[str, str] | None = None, json_body: dict[str, Any] | None = None, request_id: str | None = None) -> HttpResult:
        return await self.request_json(method="POST", url=url, headers=headers, params=params, json_body=json_body, request_id=request_id)

    async def put_json(self, *, url: str, headers: Mapping[str, str] | None = None, params: Mapping[str, str] | None = None, json_body: dict[str, Any] | None = None, request_id: str | None = None) -> HttpResult:
        return await self.request_json(method="PUT", url=url, headers=headers, params=params, json_body=json_body, request_id=request_id)

    async def patch_json(self, *, url: str, headers: Mapping[str, str] | None = None, params: Mapping[str, str] | None = None, json_body: dict[str, Any] | None = None, request_id: str | None = None) -> HttpResult:
        return await self.request_json(method="PATCH", url=url, headers=headers, params=params, json_body=json_body, request_id=request_id)
