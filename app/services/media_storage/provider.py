from __future__ import annotations
from functools import lru_cache
from app.core.config import settings
from app.services.media_storage.base import MediaStorage
from app.services.media_storage.local import LocalMediaStorage


@lru_cache(maxsize=1)
def get_media_storage() -> MediaStorage:
    # switch by settings.media_backend
    if settings.media_backend == "local":
        return LocalMediaStorage(base_dir=settings.media_local_dir)
    raise RuntimeError(f"unsupported media_backend: {settings.media_backend}")