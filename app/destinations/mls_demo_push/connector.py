from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from app.destinations.capabilities import DestinationCapabilities
from app.services.http_client import HubHttpClient
from app.destinations.base import PublishResult, DestinationConnector


DEST = "mls_demo_push"

_http = HubHttpClient(timeout_seconds=20.0)

@dataclass
class DemoPushConnector:
    destination: str = DEST

    def capabilities(self) -> DestinationCapabilities:
        return DestinationCapabilities(
            destination=self.destination,
            transport="push_api",
            supports_delete=False,
            supports_media=True,
            listing_inclusion_policy="exclude_inactive",
        )

    async def publish_listing(self, *, payload: dict[str, Any], credentials: dict[str, Any], mode: str = "live", request_id: str | None = None,) -> PublishResult:
        """
        payload: projected payload (destination-specific schema)
        credentials: decrypted secrets for this destination
        mode: "live" | "sandbox"
        """
        if mode == "sandbox":
        
            return PublishResult(
                ok=True,
                retryable=False,
                external_id=str(payload.get("external_listing_id") or "sandbox_demo"),
                detail={"sandbox": True, "message": "simulated publish ok", "request_id": request_id},
            )

        base_url = str(credentials.get("base_url") or "").strip()
        api_key = str(credentials.get("api_key") or "").strip()
        if not base_url or not api_key:
            return PublishResult(
                ok=False,
                retryable=False,
                external_id=None,
                detail={"error": "BAD_CREDENTIALS", "message": "Missing base_url/api_key"},
                error_code="BAD_CREDENTIALS",
                error_message="Missing base_url/api_key",)

        url = f"{base_url.rstrip('/')}/listings/upsert"
        headers = {"Authorization": f"Bearer {api_key}"}

        res = await _http.post_json(url=url, headers=headers, json_body=payload, request_id=request_id)

        safe_headers = {}
        for k in ("date", "x-request-id", "content-type"):
            if k in res.response_headers:
                safe_headers[k] = res.response_headers[k]

        if res.ok:
            # external id extraction depends on real API; placeholder | defensive: id can be int/string
            ext_id = res.detail.get("id") or res.detail.get("external_id")
            ext_id = str(ext_id) if ext_id is not None else None

            return PublishResult(
                ok=True, 
                retryable=False, 
                external_id=ext_id, 
                detail={
                    "response": res.detail,
                    "status_code": res.status_code,
                    "elapsed_ms": res.elapsed_ms,
                    "headers": safe_headers,
                },
                )

        return PublishResult(
            ok=False,
            retryable=res.retryable,
            error_code=res.error_code or "PUBLISH_FAILED",
            error_message=res.error_message or "publish failed",
            detail={
                "response": res.detail,
                "status_code": res.status_code,
                "elapsed_ms": res.elapsed_ms,
                "headers": res.response_headers,
            },
        )
