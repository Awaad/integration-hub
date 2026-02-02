from __future__ import annotations
from functools import lru_cache
from app.core.config import settings
from app.services.media_storage.base import MediaStorage
from app.services.media_storage.local import LocalMediaStorage


@lru_cache(maxsize=1)
def get_media_storage() -> MediaStorage:
    # later: switch by settings.media_backend
    base_dir = getattr(settings, "media_local_dir", "var/media")
    return LocalMediaStorage(base_dir=base_dir)