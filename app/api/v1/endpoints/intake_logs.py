from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.intake_log import IntakeLog
from app.schemas.intake_log import IntakeLogCreate, IntakeLogOut

router = APIRouter(prefix="/intake-logs", tags=["intake-logs"])


@router.post("", response_model=IntakeLogOut, status_code=201, summary="保存饮食用药日志")
def create_log(body: IntakeLogCreate, db: Session = Depends(get_db)):
    # Step 3 调整：drugs/foods 改为 JSONB，无需再 json.dumps；SQLAlchemy 直接接收 list
    log = IntakeLog(
        elder_id=body.elder_id,
        drugs=body.drugs,
        foods=body.foods,
        recognized_text=body.recognized_text,
        risk_level=body.risk_level,
        risk_summary=body.risk_summary,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return _serialize(log)


@router.get("", response_model=list[IntakeLogOut], summary="查询饮食用药日志")
def list_logs(elder_id: str, days: int = 7, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta
    from sqlalchemy import and_

    cutoff = datetime.utcnow() - timedelta(days=days)
    logs = (
        db.query(IntakeLog)
        .filter(and_(IntakeLog.elder_id == elder_id, IntakeLog.created_at >= cutoff))
        .order_by(IntakeLog.created_at.desc())
        .all()
    )
    return [_serialize(log) for log in logs]


def _serialize(log: IntakeLog) -> IntakeLogOut:
    # JSONB 返回原生 list；NULL 回退为空数组，保持原响应契约
    return IntakeLogOut(
        log_id=log.log_id,
        elder_id=log.elder_id,
        drugs=log.drugs or [],
        foods=log.foods or [],
        recognized_text=log.recognized_text,
        risk_level=log.risk_level,
        risk_summary=log.risk_summary,
        created_at=log.created_at,
    )
