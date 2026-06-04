from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReminderRule(Base):
    __tablename__ = "reminder_rule"

    rule_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    elder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("elder_profile.elder_id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32))  # medication / meal / water
    title: Mapped[str] = mapped_column(String(256))
    schedule_time: Mapped[str | None] = mapped_column(String(8))  # HH:MM
    repeat_pattern: Mapped[str | None] = mapped_column(String(64))  # daily / weekdays / etc.
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReminderEvent(Base):
    __tablename__ = "reminder_event"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("reminder_rule.rule_id"), nullable=False)
    elder_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("elder_profile.elder_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256))
    # Step 3 调整：String → DateTime，便于范围查询 / due 排序 / 与 created_at 类型一致
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending/completed/snoozed/skipped
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # 提醒中心高频查询：(elder_id, status, due_at) — 找“某老人当前 pending 的最近提醒”
        Index("ix_reminder_event_elder_status_due", "elder_id", "status", "due_at"),
    )
