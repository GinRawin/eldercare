from datetime import datetime

from pydantic import BaseModel


class ElderProfileBase(BaseModel):
    name: str
    age: int | None = None
    gender: str | None = None
    allergies: list[str] = []
    diseases: list[str] = []
    health_notes: str | None = None


class ElderProfileCreate(ElderProfileBase):
    elder_id: str


class ElderProfileUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    allergies: list[str] | None = None
    diseases: list[str] | None = None
    health_notes: str | None = None


class ElderProfileOut(ElderProfileBase):
    elder_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
