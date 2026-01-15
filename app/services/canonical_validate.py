from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from app.canonical.registry import resolve_schema


@dataclass(frozen=True)
class CanonicalValidationResult:
    ok: bool
    model: BaseModel | None
    normalized: dict[str, Any] | None
    content_hash: str | None
    errors: list[dict[str, Any]]


def _stable_json(data: Any) -> str:
    # Deterministic JSON string for hashing
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_hex(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return h.hexdigest()


def validate_and_normalize_canonical(
    *,
    schema: str,
    schema_version: str,
    payload: dict[str, Any],
) -> CanonicalValidationResult:
    """
    Validate and normalize canonical payload.
    Returns (normalized_dict, content_hash) suitable for storage and idempotency.
    """
    try:
        Model: Type[BaseModel] = resolve_schema(schema, schema_version)
    except KeyError as e:
        return CanonicalValidationResult(
            ok=False,
            model=None,
            normalized=None,
            content_hash=None,
            errors=[{"type": "schema_not_supported", "message": str(e)}],
        )

    try:
        obj = Model.model_validate(payload)
    except ValidationError as e:
        # Pydantic v2 error format is already structured
        return CanonicalValidationResult(
            ok=False,
            model=None,
            normalized=None,
            content_hash=None,
            errors=e.errors(),
        )

    normalized = obj.model_dump(mode="json", exclude_none=True)
    content_hash = _sha256_hex(_stable_json(normalized))

    return CanonicalValidationResult(
        ok=True,
        model=obj,
        normalized=normalized,
        content_hash=content_hash,
        errors=[],
    )
