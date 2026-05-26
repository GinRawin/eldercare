from datetime import datetime

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
    # Step 3 调整：底层改为 DateTime；Pydantic 序列化为 ISO 8601 字符串，
    # JSON 表层格式与字段名保持不变，Dify 侧无需重新导入
    due_at: datetime
    status: str
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReminderActionResponse(BaseModel):
    event_id: int
    status: str
