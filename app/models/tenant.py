import uuid
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"tnt_{uuid.uuid4().hex}")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
