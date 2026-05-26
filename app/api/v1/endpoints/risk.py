from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.risk import RiskCheckRequest, RiskCheckResponse
from app.services.risk_service import check_risk

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/check", response_model=RiskCheckResponse, summary="药物食物风险检查")
def check_risk_endpoint(body: RiskCheckRequest, db: Session = Depends(get_db)):
    """
    风险检查接口（block 2 完成）。

    聚合四类风险：
    - drug_drug      ：DDInter 本地查询（含中英文别名解析）
    - food_allergy   ：与老人档案 allergies 字段比对
    - disease_related：基于老人档案 diseases 与启发式规则
    - drug_food      ：第一版交由 Dify 侧模型辅助，service 保留接口位

    返回 risk_level ∈ {red, yellow, green}，并附医疗免责声明。
    """
    return check_risk(
        db=db,
        elder_id=body.elder_id,
        drugs=body.drugs,
        foods=body.foods,
        context=body.context,
    )
