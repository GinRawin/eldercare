from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntakeLog(Base):
    __tablename__ = "intake_log"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    elder_id: Mapped[str] = mapped_column(String(64), ForeignKey("elder_profile.elder_id"), nullable=False)
    drugs: Mapped[str | None] = mapped_column(Text)         # JSON array
    foods: Mapped[str | None] = mapped_column(Text)         # JSON array
    recognized_text: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(16))  # red / yellow / green
    risk_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
