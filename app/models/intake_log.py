from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntakeLog(Base):
    __tablename__ = "intake_log"

    log_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    elder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("elder_profile.elder_id"), nullable=False
    )
    # Step 3 调整：Text(JSON 字符串) → JSONB，原生数组结构，未来可走 GIN 索引检索单个药/食物
    drugs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    foods: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recognized_text: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(16))  # red / yellow / green
    risk_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        # 日常建议常用查询：某老人最近 N 天日志
        Index("ix_intake_log_elder_created", "elder_id", "created_at"),
    )
