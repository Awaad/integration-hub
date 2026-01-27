from __future__ import annotations
from typing import Any

def destination_mode(config: dict[str, Any] | None) -> str:
    cfg = config or {}
    m = str(cfg.get("mode") or "live").lower().strip()
    return "sandbox" if m == "sandbox" else "live"
