"""
DDInter 查询服务

职责：
- 把任意写法的药名（中文别名、英文俗名、含剂量括注等）归一化后
  解析到 ddinter_drug.drug_id（必要时跟随 alias_of:* 跳转到学名）。
- 给定两个药名，查询 ddinter_interaction 是否存在相互作用。

与导入脚本（scripts/import_ddinter.py）共享同一套归一化规则；为避免运行期
依赖 scripts/ 包，这里把 normalize_drug_name 复制了一份并保持同步。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.ddinter import DDInterDrug, DDInterInteraction

ALIAS_PREFIX = "alias_of:"


def normalize_drug_name(name: str) -> str:
    """与 scripts/import_ddinter.py 中同名函数保持一致。"""
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip()
    if "(" in s:
        s = s.split("(", 1)[0].strip()
    if "（" in s:
        s = s.split("（", 1)[0].strip()
    s = " ".join(s.split())
    return s.lower()


@dataclass
class DrugLookup:
    """药名查询结果。"""

    drug_id: int
    canonical_name: str  # 入库时的原始写法（首选英文学名）
    matched_via: str  # "direct" | "alias"


def resolve_drug(db: Session, raw_name: str) -> DrugLookup | None:
    """
    根据输入药名解析到 ddinter_drug 记录：
      1. 用归一化名直接匹配 drug_name_normalized
      2. 若命中记录的 atc_code 为 alias_of:<canonical_id>，跳转到对应学名记录
      3. 找不到返回 None
    """
    norm = normalize_drug_name(raw_name)
    if not norm:
        return None

    drug = db.scalar(select(DDInterDrug).where(DDInterDrug.drug_name_normalized == norm))
    if drug is None:
        return None

    # 别名跳转
    if drug.atc_code and drug.atc_code.startswith(ALIAS_PREFIX):
        try:
            canonical_id = int(drug.atc_code[len(ALIAS_PREFIX) :])
        except ValueError:
            return DrugLookup(drug.drug_id, drug.drug_name, "direct")
        canonical = db.get(DDInterDrug, canonical_id)
        if canonical is not None:
            return DrugLookup(canonical.drug_id, canonical.drug_name, "alias")

    return DrugLookup(drug.drug_id, drug.drug_name, "direct")


def lookup_interaction(
    db: Session, drug_a: str, drug_b: str
) -> tuple[DDInterInteraction, DrugLookup, DrugLookup] | None:
    """
    查询两个药物是否存在相互作用。
    返回 (Interaction, DrugLookup_a, DrugLookup_b)；任何一方解析失败或无记录则返回 None。
    """
    a = resolve_drug(db, drug_a)
    b = resolve_drug(db, drug_b)
    if a is None or b is None:
        return None
    if a.drug_id == b.drug_id:
        return None

    stmt = select(DDInterInteraction).where(
        or_(
            (DDInterInteraction.drug_a_id == a.drug_id)
            & (DDInterInteraction.drug_b_id == b.drug_id),
            (DDInterInteraction.drug_a_id == b.drug_id)
            & (DDInterInteraction.drug_b_id == a.drug_id),
        )
    )
    inter = db.scalar(stmt)
    if inter is None:
        return None
    return inter, a, b
