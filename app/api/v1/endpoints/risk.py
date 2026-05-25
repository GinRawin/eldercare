import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.elder_profile import ElderProfile
from app.schemas.risk import RiskAlert, RiskCheckRequest, RiskCheckResponse

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/check", response_model=RiskCheckResponse, summary="药物食物风险检查")
def check_risk(body: RiskCheckRequest, db: Session = Depends(get_db)):
    """
    第一版 stub:
    - 查询老人档案的过敏和基础疾病
    - 后端成员 2 在此填充 DDInter 查询和风险判断逻辑
    """
    alerts: list[RiskAlert] = []

    profile = db.get(ElderProfile, body.elder_id)
    if profile:
        allergies: list[str] = json.loads(profile.allergies) if profile.allergies else []
        for food in body.foods:
            if food in allergies:
                alerts.append(RiskAlert(
                    type="food_allergy",
                    severity="high",
                    message=f"{food} 在老人的过敏记录中。",
                    source="profile",
                ))

    # TODO(backend-member-2): 在此插入 DDInter 药药相互作用查询
    # TODO(backend-member-2): 在此插入药食相互作用判断

    if any(a.severity == "high" for a in alerts):
        risk_level = "red"
        suggestion = "存在高风险提示，请咨询医生或药师，切勿自行判断。"
    elif alerts:
        risk_level = "yellow"
        suggestion = "存在潜在风险，请谨慎使用并关注身体反应。"
    else:
        risk_level = "green"
        suggestion = "未发现明确风险。本系统不能替代专业医疗意见，如有疑问请咨询医生。"

    return RiskCheckResponse(risk_level=risk_level, alerts=alerts, suggestion=suggestion)
