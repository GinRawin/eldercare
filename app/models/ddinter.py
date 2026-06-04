from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DDInterDrug(Base):
    __tablename__ = "ddinter_drug"

    drug_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    drug_name: Mapped[str] = mapped_column(String(256), index=True)
    drug_name_normalized: Mapped[str | None] = mapped_column(String(256), index=True)
    atc_code: Mapped[str | None] = mapped_column(String(32))


class DDInterInteraction(Base):
    __tablename__ = "ddinter_interaction"

    interaction_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    drug_a_id: Mapped[int] = mapped_column(Integer)
    drug_b_id: Mapped[int] = mapped_column(Integer)
    drug_a_name: Mapped[str] = mapped_column(String(256))
    drug_b_name: Mapped[str] = mapped_column(String(256))
    severity: Mapped[str | None] = mapped_column(String(32))  # major / moderate / minor
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="DDInter")
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        # 联合索引：加速 ddinter_service.lookup_interaction 的双向 OR 查询
        Index("ix_ddinter_interaction_drug_a_b", "drug_a_id", "drug_b_id"),
        Index("ix_ddinter_interaction_drug_b_a", "drug_b_id", "drug_a_id"),
    )
