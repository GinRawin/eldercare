from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.reminder import ReminderEvent, ReminderRule
from app.schemas.reminder import (
    MedicationPlanCreate,
    MedicationPlanResponse,
    ReminderActionResponse,
    ReminderEventOut,
    ReminderRuleCreate,
)
from app.services.reminder_service import create_medication_plan

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("/due", response_model=list[ReminderEventOut], summary="查询待处理提醒")
def get_due_reminders(elder_id: str, db: Session = Depends(get_db)):
    events = (
        db.query(ReminderEvent)
        .filter(ReminderEvent.elder_id == elder_id, ReminderEvent.status == "pending")
        .order_by(ReminderEvent.due_at)
        .all()
    )
    return events


@router.post("/rules", status_code=201, summary="创建提醒规则")
def create_rule(body: ReminderRuleCreate, db: Session = Depends(get_db)):
    rule = ReminderRule(**body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"rule_id": rule.rule_id}


@router.post(
    "/medication-plan",
    response_model=MedicationPlanResponse,
    status_code=201,
    summary="创建用药计划（自动展开为 N 条提醒事件）",
)
def create_medication_plan_endpoint(body: MedicationPlanCreate, db: Session = Depends(get_db)):
    """
    一次请求即建立完整的用药计划：

    - 入参：药物名、每次剂量、持续天数、一天频次、间隔小时、起始时间（可选）
    - 落库：medication_plan + 1 条锚点 reminder_rule + N 条 reminder_event
    - N = duration_days × times_per_day，事件按 interval_hours 严格等间隔从 start_at 排，允许跨天
    """
    return create_medication_plan(db, body)


@router.post(
    "/{reminder_id}/complete", response_model=ReminderActionResponse, summary="标记提醒已完成"
)
def complete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    return _update_status(reminder_id, "completed", db)


@router.post("/{reminder_id}/snooze", response_model=ReminderActionResponse, summary="标记提醒稍后")
def snooze_reminder(reminder_id: int, db: Session = Depends(get_db)):
    return _update_status(reminder_id, "snoozed", db)


@router.post("/{reminder_id}/skip", response_model=ReminderActionResponse, summary="标记提醒跳过")
def skip_reminder(reminder_id: int, db: Session = Depends(get_db)):
    return _update_status(reminder_id, "skipped", db)


def _update_status(event_id: int, status: str, db: Session) -> ReminderActionResponse:
    event = db.get(ReminderEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Reminder not found")
    event.status = status
    if status == "completed":
        event.completed_at = datetime.utcnow()
    db.commit()
    return ReminderActionResponse(event_id=event_id, status=status)
