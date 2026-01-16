from __future__ import annotations

from typing import Dict

from app.adapters.base import PartnerAdapter
from app.adapters.partners.passthrough import PassthroughAdapter


_ADAPTERS: Dict[str, PartnerAdapter] = {
    PassthroughAdapter.partner_key: PassthroughAdapter(),
}


def get_adapter(partner_key: str) -> PartnerAdapter:
    key = partner_key.lower().strip()
    if key not in _ADAPTERS:
        raise KeyError(f"Unknown partner adapter: {partner_key}")
    return _ADAPTERS[key]


def supported_adapters() -> list[str]:
    return sorted(_ADAPTERS.keys())
