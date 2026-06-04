"""
补充迭代 · 药物/食物安全检查接口端到端测试

覆盖 /api/v1/risk/safety-check：
  1. 输入药物 × 老人 active 用药命中 DDInter（阿司匹林 vs 华法林）→ red
  2. 输入命中老人过敏记录（花生 子串）→ allergy_hit=true / red
  3. 查不到任何风险 → green，conclusion 含「不代表绝对安全」+ 免责声明
  4. 老人档案不存在 → 不报错，过敏部分为空仍能跑完
  5. 别名扩展未配置 LLM 时降级为 [name]（含原始输入），llm_used=false

依赖本地 PostgreSQL 已导入的 DDInter 真实数据（见 Step 1 进展记录）。
LLM 默认未配置（.env 留空），故 llm_used 恒为 False。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.elder_profile import ElderProfile
from app.models.medication_plan import MedicationPlan
from app.services import llm_client

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


def _add_medication(db: Session, elder_id: str, drug_name: str, *, active: bool = True) -> None:
    db.add(MedicationPlan(elder_id=elder_id, drug_name=drug_name, active=active))
    db.commit()


def _cleanup_meds(db: Session, elder_id: str) -> None:
    db.query(MedicationPlan).filter(MedicationPlan.elder_id == elder_id).delete(
        synchronize_session=False
    )
    db.commit()


def _post(client: TestClient, payload: dict) -> dict:
    resp = client.post("/api/v1/risk/safety-check", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- 1. 与在用药物的 DDInter 相互作用 ----------


def test_safety_interaction_with_active_medication(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}safety_inter"
    _create_elder(db, elder_id)
    _add_medication(db, elder_id, "华法林")
    try:
        body = _post(client, {"elder_id": elder_id, "name": "阿司匹林"})

        assert body["risk_level"] == "red"
        assert body["interactions"], body
        assert all(i["severity"] in {"high", "medium", "low"} for i in body["interactions"])
        assert "不能替代专业医疗意见" in body["conclusion"]
        # 默认未配置 LLM → 降级
        assert body["llm_used"] is False
        assert body["aliases_used"] == ["阿司匹林"]
    finally:
        _cleanup_meds(db, elder_id)


# ---------- 2. 过敏命中 ----------


def test_safety_allergy_hit(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}safety_allergy"
    _create_elder(db, elder_id, allergies=["花生"])

    body = _post(client, {"elder_id": elder_id, "name": "花生酱"})

    assert body["allergy_hit"] is True
    assert body["risk_level"] == "red"
    assert "花生" in body["conclusion"]


# ---------- 3. 无风险 → green ----------


def test_safety_no_risk_green(client: TestClient, db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}safety_green"
    _create_elder(db, elder_id)  # 无过敏、无在用药

    body = _post(client, {"elder_id": elder_id, "name": "米饭"})

    assert body["risk_level"] == "green"
    assert body["allergy_hit"] is False
    assert body["interactions"] == []
    assert "不代表绝对安全" in body["conclusion"]
    assert "不能替代专业医疗意见" in body["conclusion"]


# ---------- 4. 老人档案不存在 ----------


def test_safety_unknown_elder_no_crash(client: TestClient) -> None:
    body = _post(
        client,
        {"elder_id": f"{TEST_ELDER_PREFIX}safety_nobody", "name": "阿司匹林"},
    )
    assert body["risk_level"] in {"red", "yellow", "green"}
    assert body["allergy_hit"] is False
    # 无档案 + 无在用药 → 无相互作用
    assert body["interactions"] == []


# ---------- 5. 别名扩展降级（直接单测 llm_client） ----------


def test_expand_aliases_degrades_without_config() -> None:
    aliases, used = llm_client.expand_aliases("阿司匹林")
    assert used is False
    assert aliases == ["阿司匹林"]  # 仅原始输入，去重保序


def test_expand_aliases_empty_name() -> None:
    aliases, used = llm_client.expand_aliases("   ")
    assert aliases == []
    assert used is False
