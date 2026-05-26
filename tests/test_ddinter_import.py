"""
Step 5 · DDInter 导入脚本单测

策略：
- 不依赖真实的 222k 条 DDInter CSV，构造小段 fixture CSV 验证导入逻辑
- 用 in-memory SQLite + 重新绑定 Base.metadata 创建表，避免污染本地 Postgres
- 直接调用 scripts/import_ddinter.py 中的内部函数（iter_interactions /
  upsert_drugs / upsert_interactions / normalize_drug_name / normalize_severity）

验证点：
1. 列名变体（小写 / 别名）能正确归一化
2. 严重度字符串能映射（Major→major / Unknown→unknown / 中文「严重」→major）
3. 药名归一化：去括号剂量、NFKC、压空白、小写
4. 别名机制：alias_of:<canonical_drug_id> 编码 + 中文别名能解析到学名
5. 幂等：同一 fixture 跑两次，第二次新增数 = 0
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.ddinter import DDInterDrug, DDInterInteraction

# 通过 importlib 拉起 scripts/import_ddinter.py 当作模块（脚本不在包里）
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "import_ddinter.py"


@pytest.fixture(scope="module")
def importer():
    spec = importlib.util.spec_from_file_location("import_ddinter", _SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["import_ddinter"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------- 隔离 DB（SQLite in-memory） ----------


@pytest.fixture()
def isolated_db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    # 仅建 DDInter 两张表，避免拉起所有依赖
    DDInterDrug.__table__.create(engine)
    DDInterInteraction.__table__.create(engine)
    SessionLocalTest = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = SessionLocalTest()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


# ---------- 1. 归一化纯函数 ----------


def test_normalize_drug_name_variants(importer) -> None:
    n = importer.normalize_drug_name
    # 大小写 + 空白
    assert n("Aspirin") == "aspirin"
    assert n("  ASPIRIN  ") == "aspirin"
    # 括号剂量
    assert n("Aspirin (300 mg)") == "aspirin"
    assert n("阿司匹林（300毫克）") == "阿司匹林"
    # NFKC（全角字母→半角）
    assert n("Ａｓｐｉｒｉｎ") == "aspirin"
    # 空 / None 兼容
    assert n("") == ""
    assert n(None) == ""  # type: ignore[arg-type]


def test_normalize_severity_mapping(importer) -> None:
    s = importer.normalize_severity
    assert s("Major") == "major"
    assert s("Moderate") == "moderate"
    assert s("Minor") == "minor"
    assert s("Unknown") == "unknown"
    # 中文 / 通俗
    assert s("严重") == "major"
    assert s("中等") == "moderate"
    assert s("轻微") == "minor"
    assert s("HIGH") == "major"
    # 不识别的取值 → None
    assert s("random_text") is None
    assert s("") is None
    assert s(None) is None


def test_normalize_column_name(importer) -> None:
    nc = importer.normalize_column_name
    # 标准列名原样
    assert nc("DDInterID_A") == "DDInterID_A"
    # 小写别名
    assert nc("ddinter_id_a") == "DDInterID_A"
    assert nc("drug_a") == "Drug_A"
    assert nc("severity") == "Level"
    # 未知列名原样
    assert nc("Foo") == "Foo"


# ---------- 2. iter_interactions ----------


def _write_csv(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_iter_interactions_standard_columns(importer, tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path,
        "std.csv",
        [
            "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level",
            "D001,Aspirin,D002,Warfarin,Major",
            "D003,Metformin,D004,Insulin,Moderate",
        ],
    )
    rows = list(importer.iter_interactions(csv))
    assert len(rows) == 2
    assert rows[0]["a_name"] == "Aspirin"
    assert rows[0]["severity"] == "major"
    assert rows[1]["severity"] == "moderate"


def test_iter_interactions_alias_columns(importer, tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path,
        "alias.csv",
        [
            # 全部用小写别名
            "ddinter_id_a,drug_a,ddinter_id_b,drug_b,severity",
            "D001,Aspirin,D002,Warfarin,Major",
        ],
    )
    rows = list(importer.iter_interactions(csv))
    assert len(rows) == 1
    assert rows[0]["a_ext_id"] == "D001"


def test_iter_interactions_skips_missing_required(importer, tmp_path: Path, capsys) -> None:
    csv = _write_csv(
        tmp_path,
        "bad.csv",
        [
            "DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level",
            ",Aspirin,D002,Warfarin,Major",  # 关键字段缺失
            "D001,,D002,Warfarin,Major",  # 关键字段缺失
            "D003,Metformin,D004,Insulin,Moderate",
        ],
    )
    rows = list(importer.iter_interactions(csv))
    assert len(rows) == 1
    assert rows[0]["a_ext_id"] == "D003"


def test_iter_interactions_missing_column_skips_file(importer, tmp_path: Path) -> None:
    csv = _write_csv(
        tmp_path,
        "miss.csv",
        [
            "DDInterID_A,Drug_A,DDInterID_B,Drug_B",  # 缺 Level
            "D001,Aspirin,D002,Warfarin",
        ],
    )
    rows = list(importer.iter_interactions(csv))
    assert rows == []


# ---------- 3. upsert_drugs + 别名 ----------


def test_upsert_drugs_with_alias(importer, isolated_db: Session) -> None:
    records = [
        {
            "a_ext_id": "D001",
            "a_name": "Acetylsalicylic acid",
            "b_ext_id": "D002",
            "b_name": "Warfarin",
            "severity": "major",
        },
    ]
    aliases = {"acetylsalicylic acid": ["阿司匹林", "aspirin"]}
    ext_to_db = importer.upsert_drugs(isolated_db, records, aliases)

    assert "D001" in ext_to_db and "D002" in ext_to_db
    # 两条学名 + 两条别名
    all_drugs = isolated_db.query(DDInterDrug).all()
    names = {d.drug_name_normalized for d in all_drugs}
    assert {"acetylsalicylic acid", "warfarin", "阿司匹林", "aspirin"} <= names

    # 别名记录指向学名 drug_id
    canonical_id = ext_to_db["D001"]
    aliases_rows = (
        isolated_db.query(DDInterDrug)
        .filter(DDInterDrug.drug_name_normalized.in_(["阿司匹林", "aspirin"]))
        .all()
    )
    for r in aliases_rows:
        assert r.atc_code == f"alias_of:{canonical_id}"


# ---------- 4. 端到端：upsert_drugs + upsert_interactions + 幂等 ----------


def test_full_import_is_idempotent(importer, isolated_db: Session) -> None:
    records = [
        {
            "a_ext_id": "D001",
            "a_name": "Acetylsalicylic acid",
            "b_ext_id": "D002",
            "b_name": "Warfarin",
            "severity": "major",
        },
        {
            "a_ext_id": "D003",
            "a_name": "Metformin",
            "b_ext_id": "D004",
            "b_name": "Insulin",
            "severity": "moderate",
        },
        # 自相互作用（a==b 同 ext）应被跳过
        {"a_ext_id": "D005", "a_name": "X", "b_ext_id": "D005", "b_name": "X", "severity": "minor"},
    ]
    aliases: dict[str, list[str]] = {}
    ext_to_db = importer.upsert_drugs(isolated_db, records, aliases)
    importer.upsert_interactions(isolated_db, records, ext_to_db)

    inter_cnt_1 = isolated_db.query(DDInterInteraction).count()
    drug_cnt_1 = isolated_db.query(DDInterDrug).count()
    assert inter_cnt_1 == 2  # 自相互作用被剔除
    assert drug_cnt_1 == 5  # D001..D005 各一条

    # 再跑一遍：数量保持
    ext_to_db_2 = importer.upsert_drugs(isolated_db, records, aliases)
    importer.upsert_interactions(isolated_db, records, ext_to_db_2)
    assert isolated_db.query(DDInterInteraction).count() == inter_cnt_1
    assert isolated_db.query(DDInterDrug).count() == drug_cnt_1


def test_severity_update_path(importer, isolated_db: Session) -> None:
    """同一对药物，第二次导入 severity 不同时应更新而非重复插入。"""
    rec1 = [
        {
            "a_ext_id": "D001",
            "a_name": "Aspirin",
            "b_ext_id": "D002",
            "b_name": "Warfarin",
            "severity": "moderate",
        },
    ]
    ext = importer.upsert_drugs(isolated_db, rec1, {})
    importer.upsert_interactions(isolated_db, rec1, ext)
    assert isolated_db.query(DDInterInteraction).count() == 1

    rec2 = [
        {
            "a_ext_id": "D001",
            "a_name": "Aspirin",
            "b_ext_id": "D002",
            "b_name": "Warfarin",
            "severity": "major",
        },
    ]
    importer.upsert_interactions(isolated_db, rec2, ext)
    assert isolated_db.query(DDInterInteraction).count() == 1
    only = isolated_db.query(DDInterInteraction).one()
    assert only.severity == "major"
