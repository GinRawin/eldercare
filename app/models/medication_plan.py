from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MedicationPlan(Base):
    __tablename__ = "medication_plan"

    plan_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    elder_id: Mapped[str] = mapped_column(String(64), ForeignKey("elder_profile.elder_id"), nullable=False)
    drug_name: Mapped[str] = mapped_column(String(256))
    dosage: Mapped[str | None] = mapped_column(String(128))
    frequency: Mapped[str | None] = mapped_column(String(128))
    time_of_day: Mapped[str | None] = mapped_column(String(128))  # e.g. "morning,evening"
    with_meal: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
