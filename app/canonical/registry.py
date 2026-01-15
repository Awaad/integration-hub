from typing import Type
from pydantic import BaseModel

from app.canonical.v1.listing import ListingCanonicalV1

# Schema IDs are stable; versions are semantic-ish but we keep it simple for now.
# - Backward compatible additions: bump minor (1.1, 1.2...)
# - Breaking changes: bump major (2.0)
_CANONICAL_REGISTRY: dict[tuple[str, str], Type[BaseModel]] = {
    ("canonical.listing", "1.0"): ListingCanonicalV1,
}

def resolve_schema(schema: str, version: str) -> Type[BaseModel]:
    """
    Resolve (schema, version) to a Pydantic model.
    """
    key = (schema, version)
    if key not in _CANONICAL_REGISTRY:
        raise KeyError(f"Unknown schema/version: {schema}@{version}")
    return _CANONICAL_REGISTRY[key]

def supported_schemas() -> list[dict]:
    """
    Useful for docs/ops.
    """
    return [{"schema": s, "version": v} for (s, v) in sorted(_CANONICAL_REGISTRY.keys())]
