from pydantic import BaseModel, Field, HttpUrl
from typing import Literal


class MediaV1(BaseModel):
    """
    Canonical Media object. Destinations may support a subset of these fields.
    """
    id: str = Field(min_length=1, max_length=80, description="Canonical media id (stable within Hub).")
    type: Literal["image", "video", "floorplan", "document"] = "image"
    url: HttpUrl
    order: int = 0

    # Optional metadata
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=500)
    mime_type: str | None = Field(default=None, max_length=100)
