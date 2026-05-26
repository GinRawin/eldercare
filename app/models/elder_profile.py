from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ElderProfile(Base):
    __tablename__ = "elder_profile"

    elder_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    age: Mapped[int | None]
    gender: Mapped[str | None] = mapped_column(String(16))
    allergies: Mapped[str | None] = mapped_column(Text)  # JSON array stored as text
    diseases: Mapped[str | None] = mapped_column(Text)  # JSON array stored as text
    health_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
