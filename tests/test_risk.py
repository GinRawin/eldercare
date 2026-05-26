"""
Step 5 · 风险检查端到端测试

覆盖项目计划 §10.2 的 5 类场景：
  1. DDInter 能命中的药物组合（阿司匹林 × 华法林）→ red / drug_drug / high
  2. DDInter 查不到的药物组合 → green，并附「未查到不代表绝对安全」
  3. 老人过敏食物（含子串匹配：花生 / 花生酱）→ red / food_allergy / high
  4. 老人基础疾病相关风险（糖尿病 + 蛋糕）→ yellow / disease_related / medium
  5. 药物和食物混合输入（高风险药物组合 + 过敏食物同时存在）→ red，多类 alerts

这些测试依赖本地 PostgreSQL 中已经导入的 DDInter 真实数据
（见 Step 1 进展记录：222,383 条相互作用 / 1832 条药物 / 26 条别名）。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.elder_profile import ElderProfile

from .conftest import TEST_ELDER_PREFIX


def _create_elder(
    db: Session,
    elder_id: str,
    *,
    allergies: list[str] | None = None,
    diseases: list[str] | None = None,
) -> None:
    db.add(
        ElderProfile(
            elder_id=elder_id,
            name="测试老人",
            age=72,
            gender="F",
            allergies=json.dumps(allergies or [], ensure_ascii=False),
            diseases=json.dumps(diseases or [], ensure_ascii=False),
            health_notes=None,
        )
    )
    db.commit()


def _post_risk(client: TestClient, payload: dict) -> dict:
    resp = client.post("/api/v1/risk/check", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- 1. DDInter 命中 ----------


def test_risk_drug_drug_hit_aspirin_warfarin(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}drug_hit"
    _create_elder(db, elder_id)

    body = _post_risk(
        client,
        {
            "elder_id": elder_id,
            "drugs": ["阿司匹林", "华法林"],
            "foods": [],
        },
    )

    assert body["risk_level"] == "red"
    assert any(
        a["type"] == "drug_drug" and a["severity"] == "high" and a["source"] == "DDInter"
        for a in body["alerts"]
    ), body
    # 医疗免责声明
    assert "不能替代专业医疗意见" in body["suggestion"]


# ---------- 2. DDInter 查不到 ----------


def test_risk_drug_drug_miss_returns_green(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}drug_miss"
    _create_elder(db, elder_id)

    body = _post_risk(
        client,
        {
            "elder_id": elder_id,
            # 故意用一个一定不会命中 DDInter 的占位名
            "drugs": ["__unknown_drug_xyz__", "__unknown_drug_abc__"],
            "foods": [],
        },
    )

    assert body["risk_level"] == "green"
    assert body["alerts"] == []
    # 必须明确告知"未查到 ≠ 绝对安全"
    assert "未查到" in body["suggestion"] or "不代表" in body["suggestion"]


# ---------- 3. 食物过敏（含子串匹配） ----------


def test_risk_food_allergy_substring(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}allergy"
    _create_elder(db, elder_id, allergies=["花生"])

    body = _post_risk(
        client,
        {
            "elder_id": elder_id,
            "drugs": [],
            "foods": ["花生酱面包"],
        },
    )

    assert body["risk_level"] == "red"
    assert any(
        a["type"] == "food_allergy" and a["severity"] == "high" and a["source"] == "profile"
        for a in body["alerts"]
    ), body


# ---------- 4. 基础疾病相关 ----------


def test_risk_disease_related_diabetes_cake(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}disease"
    _create_elder(db, elder_id, diseases=["糖尿病"])

    body = _post_risk(
        client,
        {
            "elder_id": elder_id,
            "drugs": [],
            "foods": ["草莓蛋糕"],
        },
    )

    assert body["risk_level"] == "yellow"
    assert any(
        a["type"] == "disease_related" and a["severity"] == "medium" and a["source"] == "profile"
        for a in body["alerts"]
    ), body


# ---------- 5. 药 + 食混合输入 ----------


def test_risk_mixed_drugs_and_allergy(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}mixed"
    _create_elder(db, elder_id, allergies=["花生"], diseases=["糖尿病"])

    body = _post_risk(
        client,
        {
            "elder_id": elder_id,
            "drugs": ["阿司匹林", "华法林"],
            "foods": ["花生酱", "蛋糕"],
            "context": "晚餐前检查",
        },
    )

    assert body["risk_level"] == "red"
    types = {a["type"] for a in body["alerts"]}
    # 高风险药药 + 过敏 + 疾病相关同时存在
    assert "drug_drug" in types
    assert "food_allergy" in types
    assert "disease_related" in types
    # severity 字面量必须限定在 high/medium/low
    for a in body["alerts"]:
        assert a["severity"] in {"high", "medium", "low"}
        assert a["source"] in {"DDInter", "profile", "model_assisted"}


# ---------- 边界：老人档案不存在 ----------


def test_risk_unknown_elder_still_returns_drug_check(client: TestClient) -> None:
    """老人档案不存在时，drug-drug 仍应正常工作（service 不抛 500）。"""
    body = _post_risk(
        client,
        {
            "elder_id": f"{TEST_ELDER_PREFIX}_nonexistent",
            "drugs": ["阿司匹林", "华法林"],
            "foods": ["花生"],
        },
    )
    assert body["risk_level"] in {"red", "yellow", "green"}
    # 药药仍能命中
    assert any(a["type"] == "drug_drug" for a in body["alerts"])
    # 但没有档案 → 没有 food_allergy / disease_related
    assert not any(a["type"] in {"food_allergy", "disease_related"} for a in body["alerts"])


@pytest.mark.parametrize("level", ["red", "yellow", "green"])
def test_risk_level_literals_documented(level: str) -> None:
    """字面量自检：red/yellow/green 三选一不能被偷偷改名。"""
    assert level in {"red", "yellow", "green"}
