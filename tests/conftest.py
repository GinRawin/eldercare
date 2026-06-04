"""
Step 5 共用测试 fixture。

设计原则：
- 复用仓库本地已经运行的 PostgreSQL（与 alembic upgrade head 共用同一库），
  这样 DDInter 22 万条数据可直接被 test_risk 使用，不再二次导入。
- 每个测试自带 elder_id / rule_id 前缀，结束后按前缀清理，避免污染。
- 通过 dependency_overrides 把 FastAPI 的 get_db 切到测试 SessionLocal，
  方便后续如果想换库（如临时 sqlite）只改一处。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.deps import get_db
from app.main import app
from app.models.elder_profile import ElderProfile
from app.models.reminder import ReminderEvent, ReminderRule


def _override_get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def _override_dependency() -> Generator[None, None, None]:
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------- 测试数据清理 ----------

# 所有测试创建的 elder_id 一律以这个前缀开头，便于精确清理
TEST_ELDER_PREFIX = "TEST_STEP5_"


@pytest.fixture(autouse=True)
def _cleanup_test_rows() -> Generator[None, None, None]:
    """测试前后清理以 TEST_ELDER_PREFIX 开头的所有数据。"""
    yield
    s = SessionLocal()
    try:
        s.query(ReminderEvent).filter(ReminderEvent.elder_id.like(f"{TEST_ELDER_PREFIX}%")).delete(
            synchronize_session=False
        )
        s.query(ReminderRule).filter(ReminderRule.elder_id.like(f"{TEST_ELDER_PREFIX}%")).delete(
            synchronize_session=False
        )
        s.query(ElderProfile).filter(ElderProfile.elder_id.like(f"{TEST_ELDER_PREFIX}%")).delete(
            synchronize_session=False
        )
        s.commit()
    finally:
        s.close()
