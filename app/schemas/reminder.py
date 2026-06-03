from datetime import datetime

from pydantic import BaseModel, Field


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


# ---------------------------------------------------------------------------
# 用药计划接口（POST /api/v1/reminders/medication-plan）
# ---------------------------------------------------------------------------


class MedicationPlanCreate(BaseModel):
    """一次请求 = 一份用药计划，后端自动展开为 N 条 ReminderEvent。"""

    elder_id: str = Field(..., description="老人 ID")
    drug_name: str = Field(..., min_length=1, max_length=256, description="药物名称")
    dose_per_time: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="每次服用剂量，例如 '100mg' / '1片' / '5ml'，自由文本",
    )
    duration_days: int = Field(..., ge=1, le=365, description="持续天数")
    times_per_day: int = Field(..., ge=1, le=24, description="一天使用频次")
    interval_hours: float = Field(..., gt=0, le=24, description="两次之间的间隔小时数")
    start_at: datetime | None = Field(
        default=None,
        description="第一次提醒时刻（ISO 8601）。省略时取服务端当前时间",
    )
    notes: str | None = Field(default=None, max_length=2048, description="备注，可选")


class MedicationPlanResponse(BaseModel):
    plan_id: int
    rule_id: int
    drug_name: str
    dose_per_time: str
    events_created: int
    first_due_at: datetime
    last_due_at: datetime
    # 当 times_per_day × interval_hours 偏离 24 较远时给一个温和警告，不阻断请求
    warning: str | None = None
