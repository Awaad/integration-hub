from fastapi import Header, HTTPException

from app.core.config import settings


async def require_internal_admin(x_internal_admin_key: str | None = Header(default=None)) -> None:
    if not x_internal_admin_key or x_internal_admin_key != settings.internal_admin_key:
        raise HTTPException(status_code=403, detail="Internal admin key required")
