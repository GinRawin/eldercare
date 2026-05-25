from datetime import datetime

from pydantic import BaseModel


class IntakeLogCreate(BaseModel):
    elder_id: str
    drugs: list[str] = []
    foods: list[str] = []
    recognized_text: str | None = None
    risk_level: str | None = None
    risk_summary: str | None = None


class IntakeLogOut(IntakeLogCreate):
    log_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
