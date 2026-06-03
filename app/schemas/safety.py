from pydantic import BaseModel


class SafetyCheckRequest(BaseModel):
    elder_id: str
    name: str  # 大模型传入的中文药物或食物名称
    context: str | None = None


class InteractionItem(BaseModel):
    with_drug: str  # 与老人在用药中的哪一种发生相互作用（DDInter 学名）
    severity: str  # high / medium / low
    description: str | None = None


class SafetyCheckResponse(BaseModel):
    name: str
    conclusion: str  # 供大模型直接使用的自然语言结论（含医疗免责声明）
    risk_level: str  # red / yellow / green
    allergy_hit: bool
    interactions: list[InteractionItem] = []
    aliases_used: list[str] = []
    llm_used: bool = False
