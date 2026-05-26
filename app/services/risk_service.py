"""
风险检查聚合服务

把四类风险源汇总成一个 RiskCheckResponse：
  - drug_drug         ：调用 ddinter_service，源标记 DDInter
  - food_allergy      ：查老人档案 allergies 字段，源标记 profile
  - disease_related   ：基于老人档案 diseases + 启发式规则，源标记 profile
  - drug_food         ：本版仅留位（无模型接入），保留一个保守提示位即可

不直接定义 RiskAlert/RiskCheckResponse 的字面量取值，全部走 schemas/risk.py
里的字符串约定（red/yellow/green、high/medium/low、drug_drug/...）。
"""

from __future__ import annotations

import json
from itertools import combinations

from sqlalchemy.orm import Session

from app.models.elder_profile import ElderProfile
from app.schemas.risk import RiskAlert, RiskCheckResponse
from app.services.ddinter_service import lookup_interaction

# DDInter severity → RiskAlert.severity
DDINTER_SEVERITY_MAP: dict[str, str] = {
    "major": "high",
    "moderate": "medium",
    "minor": "low",
    # "unknown" 不映射，使用单独的占位规则
}

# 简单的疾病-食物高风险启发式（演示用，第一版仅覆盖最直观的几条）
# 真实规则库后续可移到 yaml/数据库表
DISEASE_FOOD_RULES: dict[str, list[tuple[str, str, str]]] = {
    # 疾病名（小写）: [(食物关键词小写, severity, message)]
    "糖尿病": [
        ("糖", "medium", "糖尿病患者应控制高糖食品摄入。"),
        ("蛋糕", "medium", "糖尿病患者应避免高糖糕点。"),
        ("含糖饮料", "medium", "糖尿病患者应避免含糖饮料。"),
    ],
    "高血压": [
        ("咸", "medium", "高血压患者应避免高盐食物。"),
        ("腌", "medium", "高血压患者应避免腌制食品。"),
    ],
    "痛风": [
        ("海鲜", "medium", "痛风患者应避免高嘌呤海鲜。"),
        ("动物内脏", "high", "痛风患者应严格避免动物内脏。"),
        ("啤酒", "high", "痛风患者应避免饮用啤酒。"),
    ],
}

DISCLAIMER = "本系统不能替代专业医疗意见，如有疑问请咨询医生或药师。"


def _safe_json_list(raw: str | None) -> list[str]:
    """安全解析存在 TEXT 字段里的 JSON 数组；失败或为空时返回 []。"""
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(v, list):
        return []
    return [str(x) for x in v]


def _check_drug_drug(db: Session, drugs: list[str]) -> list[RiskAlert]:
    """两两组合调用 DDInter；命中即生成一个 RiskAlert。"""
    alerts: list[RiskAlert] = []
    seen: set[tuple[str, str]] = set()
    for a, b in combinations(drugs, 2):
        key = tuple(sorted([a.strip().lower(), b.strip().lower()]))
        if key in seen:
            continue
        seen.add(key)

        res = lookup_interaction(db, a, b)
        if res is None:
            continue
        inter, la, lb = res
        sev_raw = (inter.severity or "").lower()
        severity = DDINTER_SEVERITY_MAP.get(sev_raw)
        if severity is None:
            # severity 缺失 / unknown：保守起见标 medium
            severity = "medium"
            sev_text = "未明确"
        else:
            sev_text = sev_raw

        message = (
            f"{a} 与 {b} 在 DDInter 中存在相互作用"
            f"（{la.canonical_name} × {lb.canonical_name}，严重度：{sev_text}）。"
        )
        if inter.description:
            message += f" {inter.description}"
        alerts.append(
            RiskAlert(
                type="drug_drug",
                severity=severity,
                message=message,
                source="DDInter",
            )
        )
    return alerts


def _check_food_allergy(profile: ElderProfile | None, foods: list[str]) -> list[RiskAlert]:
    if profile is None:
        return []
    allergies = _safe_json_list(profile.allergies)
    if not allergies:
        return []
    # 大小写不敏感的子串匹配（覆盖"花生" / "花生酱"等场景）
    alerts: list[RiskAlert] = []
    allergies_norm = [a.strip().lower() for a in allergies if a and a.strip()]
    for food in foods:
        fn = food.strip().lower()
        if not fn:
            continue
        for allergen in allergies_norm:
            if allergen and (allergen in fn or fn in allergen):
                alerts.append(
                    RiskAlert(
                        type="food_allergy",
                        severity="high",
                        message=f"{food} 命中老人过敏记录（{allergen}），请避免摄入。",
                        source="profile",
                    )
                )
                break
    return alerts


def _check_disease_related(profile: ElderProfile | None, foods: list[str]) -> list[RiskAlert]:
    if profile is None:
        return []
    diseases = _safe_json_list(profile.diseases)
    if not diseases:
        return []
    alerts: list[RiskAlert] = []
    foods_norm = [(f, f.strip().lower()) for f in foods if f and f.strip()]
    for disease in diseases:
        rules = DISEASE_FOOD_RULES.get(disease.strip().lower())
        if not rules:
            continue
        for keyword, severity, msg in rules:
            kw = keyword.lower()
            for original, fn in foods_norm:
                if kw in fn:
                    alerts.append(
                        RiskAlert(
                            type="disease_related",
                            severity=severity,
                            message=f"{original}：{msg}",
                            source="profile",
                        )
                    )
    return alerts


def _aggregate_level(alerts: list[RiskAlert]) -> tuple[str, str]:
    """根据 alerts 汇总 risk_level 与 suggestion。"""
    if any(a.severity == "high" for a in alerts):
        return (
            "red",
            f"存在高风险提示，请立即咨询医生或药师，切勿自行决定。{DISCLAIMER}",
        )
    if any(a.severity == "medium" for a in alerts):
        return (
            "yellow",
            f"存在潜在风险，请谨慎使用并关注身体反应。{DISCLAIMER}",
        )
    if alerts:
        return (
            "green",
            f"已发现一些低风险提示，建议留意。{DISCLAIMER}",
        )
    return (
        "green",
        f"未发现明确风险，但 DDInter 未查到不代表绝对安全。{DISCLAIMER}",
    )


def check_risk(
    db: Session,
    elder_id: str,
    drugs: list[str],
    foods: list[str],
    context: str | None = None,
) -> RiskCheckResponse:
    """
    聚合 drug_drug / food_allergy / disease_related 三类风险。
    drug_food 暂留为 model_assisted 接口位，第一版不在 service 内调用模型。
    """
    profile = db.get(ElderProfile, elder_id)
    alerts: list[RiskAlert] = []
    alerts.extend(_check_drug_drug(db, drugs))
    alerts.extend(_check_food_allergy(profile, foods))
    alerts.extend(_check_disease_related(profile, foods))

    risk_level, suggestion = _aggregate_level(alerts)
    return RiskCheckResponse(risk_level=risk_level, alerts=alerts, suggestion=suggestion)
