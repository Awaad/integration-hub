from __future__ import annotations

from typing import Dict, Tuple

from app.adapters.base import PartnerAdapter
from app.adapters.partners.passthrough import PassthroughAdapterV1


_ADAPTERS: Dict[Tuple[str, str], PartnerAdapter] = {
    (PassthroughAdapterV1.partner_key, PassthroughAdapterV1.version): PassthroughAdapterV1(),
}


# Default version per partner_key
_DEFAULT_VERSIONS: Dict[str, str] = {
    PassthroughAdapterV1.partner_key: PassthroughAdapterV1.version,
}


def get_adapter(partner_key: str, version: str | None = None) -> PartnerAdapter:
    key = partner_key.lower().strip()
    ver = (version or _DEFAULT_VERSIONS.get(key))

    if not ver:
        raise KeyError(f"No default adapter version configured for partner_key={partner_key}")
    k = (key, ver)
    if k not in _ADAPTERS:
        raise KeyError(f"Unknown adapter: {partner_key}@{ver}")
    return _ADAPTERS[k]


def supported_adapters() -> list[dict]:
    out = []
    for (k, v) in sorted(_ADAPTERS.keys()):
        out.append({"partner_key": k, "version": v, "is_default": _DEFAULT_VERSIONS.get(k) == v})
    return out

def default_adapter_version(partner_key: str) -> str:
    key = partner_key.lower().strip()
    if key not in _DEFAULT_VERSIONS:
        raise KeyError(f"No default adapter version configured for partner_key={partner_key}")
    return _DEFAULT_VERSIONS[key]