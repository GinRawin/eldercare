from pydantic import BaseModel


class ReminderRuleCreate(BaseModel):
    elder_id: str
    type: str
    title: str
    schedule_time: str | None = None
    repeat_pattern: str | None = None


class ReminderEventOut(BaseModel):
    event_id: int
    rule_id: int
    elder_id: str
    title: str
    due_at: str
    status: str
    completed_at: str | None = None

    model_config = {"from_attributes": True}


class ReminderActionResponse(BaseModel):
    event_id: int
    status: str
