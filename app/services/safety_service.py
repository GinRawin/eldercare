"""
药物/食物安全检查服务（供大模型 / Dify 调用）

完整流程（check_safety）：
  1. 接收：elder_id + 单个中文药物/食物名 name (+ 可选 context)
  2. 别名扩展：调 llm_client.expand_aliases（未配置/失败则降级为仅原始名）
  3. 过敏史命中：取老人档案 allergies，用别名列表做大小写不敏感子串匹配
  4. DDInter 查询：对老人 active 用药逐一与输入名查相互作用
  5. 综合文字结论：汇总成一段中文自然语言，回填 risk_level

复用现有逻辑，不重写：
  - risk_service._safe_json_list / DDINTER_SEVERITY_MAP / DISCLAIMER / _aggregate_level
  - ddinter_service.lookup_interaction（内部已含中英文别名跳转）
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.elder_profile import ElderProfile
from app.models.medication_plan import MedicationPlan
from app.schemas.risk import RiskAlert
from app.schemas.safety import InteractionItem, SafetyCheckResponse
from app.services import llm_client
from app.services.ddinter_service import lookup_interaction
from app.services.risk_service import (
    DDINTER_SEVERITY_MAP,
    DISCLAIMER,
    _aggregate_level,
    _safe_json_list,
)


def _match_allergy(aliases: list[str], allergies: list[str]) -> str | None:
    """别名列表 × 过敏列表的大小写不敏感子串匹配，命中返回过敏词。"""
    allergies_norm = [(a, a.strip().lower()) for a in allergies if a and a.strip()]
    for alias in aliases:
        an = alias.strip().lower()
        if not an:
            continue
        for original, norm in allergies_norm:
            if norm and (norm in an or an in norm):
                return original
    return None


def _active_medications(db: Session, elder_id: str) -> list[str]:
    stmt = select(MedicationPlan.drug_name).where(
        MedicationPlan.elder_id == elder_id,
        MedicationPlan.active.is_(True),
    )
    return [d for d in db.scalars(stmt).all() if d and d.strip()]


def check_safety(
    db: Session,
    elder_id: str,
    name: str,
    context: str | None = None,
) -> SafetyCheckResponse:
    # 2. 别名扩展（含原始输入；未配置/失败则降级）
    aliases, llm_used = llm_client.expand_aliases(name)
    if not aliases:
        aliases = [name]

    alerts: list[RiskAlert] = []

    # 3. 过敏史命中
    profile = db.get(ElderProfile, elder_id)
    allergy_word: str | None = None
    if profile is not None:
        allergy_word = _match_allergy(aliases, _safe_json_list(profile.allergies))
        if allergy_word is not None:
            alerts.append(
                RiskAlert(
                    type="food_allergy",
                    severity="high",
                    message=f"{name} 命中老人过敏记录（{allergy_word}），请避免摄入。",
                    source="profile",
                )
            )

    # 4. DDInter 相互作用：输入名 × 老人每种 active 用药
    interactions: list[InteractionItem] = []
    seen_meds: set[str] = set()
    for med in _active_medications(db, elder_id):
        key = med.strip().lower()
        if key in seen_meds:
            continue
        seen_meds.add(key)

        res = lookup_interaction(db, name, med)
        if res is None:
            continue
        inter, _la, lb = res
        sev_raw = (inter.severity or "").lower()
        severity = DDINTER_SEVERITY_MAP.get(sev_raw, "medium")
        interactions.append(
            InteractionItem(
                with_drug=lb.canonical_name,
                severity=severity,
                description=inter.description,
            )
        )
        msg = (
            f"{name} 与在用药物「{med}」可能存在相互作用"
            f"（{lb.canonical_name}，严重度：{sev_raw or '未明确'}）。"
        )
        if inter.description:
            msg += f" {inter.description}"
        alerts.append(RiskAlert(type="drug_drug", severity=severity, message=msg, source="DDInter"))

    # 5. 综合文字结论（复用等级聚合，保证口径一致）
    risk_level, base_suggestion = _aggregate_level(alerts)
    if alerts:
        detail = " ".join(a.message for a in alerts)
        conclusion = f"针对「{name}」的安全检查：{detail} {base_suggestion}"
    else:
        conclusion = (
            f"针对「{name}」的安全检查：未在老人过敏记录与 DDInter 相互作用库中"
            f"发现明确风险，但未查到不代表绝对安全，请留意身体反应。{DISCLAIMER}"
        )

    return SafetyCheckResponse(
        name=name,
        conclusion=conclusion,
        risk_level=risk_level,
        allergy_hit=allergy_word is not None,
        interactions=interactions,
        aliases_used=aliases,
        llm_used=llm_used,
    )
