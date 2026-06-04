from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.risk import RiskCheckRequest, RiskCheckResponse
from app.schemas.safety import SafetyCheckRequest, SafetyCheckResponse
from app.services.risk_service import check_risk
from app.services.safety_service import check_safety

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


@router.post(
    "/safety-check",
    response_model=SafetyCheckResponse,
    summary="药物/食物安全检查（供大模型调用）",
)
def safety_check_endpoint(body: SafetyCheckRequest, db: Session = Depends(get_db)):
    """
    供 Dify 大模型调用的单项安全检查接口。

    传入单个中文药物/食物名 + 老人 ID，后端完成完整流程：
    1. 别名扩展（调大模型客户端；未配置时降级为仅原始名）
    2. 过敏史命中（老人档案 allergies × 别名列表）
    3. DDInter 相互作用查询（输入名 × 老人在用药物）
    4. 综合成一段自然语言结论（conclusion），供大模型直接使用

    返回含 conclusion 文字结论 + 结构化字段（risk_level / interactions 等）。
    """
    return check_safety(
        db=db,
        elder_id=body.elder_id,
        name=body.name,
        context=body.context,
    )
