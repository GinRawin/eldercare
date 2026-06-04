"""
DDInter 数据导入脚本

DDInter 2.0 下载地址：https://ddinter.scbdd.com/
下载后将原始 CSV 文件放在 scripts/ddinter_raw/ 目录（该目录在 .gitignore 中，不提交）。
详细说明见 scripts/ddinter_raw/README.md

运行方式：
    uv run python scripts/import_ddinter.py
    uv run python scripts/import_ddinter.py --reset   # 清空旧数据后重新导入
    uv run python scripts/import_ddinter.py --dry-run # 只解析、不写库

设计要点：
1. 按列名读取（DDInterID_A/Drug_A/DDInterID_B/Drug_B/Level），列序无关，缺列报错
2. 列名别名映射：兼容历史/变体命名（见 COLUMN_ALIASES）
3. 严重度归一化：Major→major, Moderate→moderate, Minor→minor
4. 药名归一化：去空格、去全角符号、转小写
5. 中英文别名表：aliases.yaml，把"阿司匹林"映射到 aspirin 的同一 drug_id
6. 幂等：以 DDInter 原始 ID 为唯一键，重复导入不会产生重复记录
7. UTF-8 容错：遇到非法字节用 utf-8-sig 解码并跳过损坏行（打印行号）

合规：DDInter 2.0 仅授权非商业研究和演示。
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

# 让脚本能直接 import app.*（无需安装为包）
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.ddinter import DDInterDrug, DDInterInteraction  # noqa: E402

RAW_DIR = Path(__file__).parent / "ddinter_raw"
ALIASES_PATH = RAW_DIR / "aliases.yaml"

# DDInter 2.0 标准列名（脚本以这些名字为基准）
REQUIRED_COLS = {"DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"}

# 兼容历史/不一致的列名变体 → 标准列名
COLUMN_ALIASES: dict[str, str] = {
    "ddinter_id_a": "DDInterID_A",
    "ddinter_id_b": "DDInterID_B",
    "drug_a_id": "DDInterID_A",
    "drug_b_id": "DDInterID_B",
    "drug_a": "Drug_A",
    "drug_b": "Drug_B",
    "druganame": "Drug_A",
    "drugbname": "Drug_B",
    "severity": "Level",
    "interaction_level": "Level",
}

# 严重度归一化（DDInter 2.0 的 Level 列实际包含 Major/Moderate/Minor/Unknown）
SEVERITY_MAP = {
    "major": "major",
    "moderate": "moderate",
    "minor": "minor",
    "unknown": "unknown",
    "high": "major",
    "medium": "moderate",
    "low": "minor",
    "严重": "major",
    "中等": "moderate",
    "轻微": "minor",
}


# ---------- 归一化工具 ----------

def normalize_drug_name(name: str) -> str:
    """
    药物名归一化：
    - NFKC 归一（全角→半角、合并字符等）
    - 去除两侧/中间空白
    - 转小写
    - 去除尾部的剂量括注，例如 "Aspirin (300 mg)" → "aspirin"
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).strip()
    # 去掉括号及其内容
    if "(" in s:
        s = s.split("(", 1)[0].strip()
    if "（" in s:
        s = s.split("（", 1)[0].strip()
    # 多余空格压成单空格
    s = " ".join(s.split())
    return s.lower()


def normalize_severity(raw: str | None) -> str | None:
    if not raw:
        return None
    return SEVERITY_MAP.get(raw.strip().lower())


def normalize_column_name(name: str) -> str:
    """将各种变体列名映射到标准列名；无映射时原样返回。"""
    if name in REQUIRED_COLS:
        return name
    return COLUMN_ALIASES.get(name.strip().lower(), name)


# ---------- 别名表 ----------

def load_aliases() -> dict[str, list[str]]:
    """读取 scripts/ddinter_raw/aliases.yaml；不存在则返回空 dict。"""
    if not ALIASES_PATH.exists():
        return {}
    with ALIASES_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # 统一 key 走归一化
    return {normalize_drug_name(k): [normalize_drug_name(x) for x in v] for k, v in data.items()}


# ---------- CSV 解析 ----------

def iter_interactions(csv_path: Path):
    """
    逐行 yield 标准化后的相互作用记录 dict：
        {"a_ext_id": str, "a_name": str, "b_ext_id": str, "b_name": str, "severity": str|None}
    跳过缺失关键字段的行（打印行号警告）。
    """
    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print(f"  [WARN] {csv_path.name}: 没有 header，跳过")
            return
        # 列名归一化
        normalized_fields = [normalize_column_name(c) for c in reader.fieldnames]
        missing = REQUIRED_COLS - set(normalized_fields)
        if missing:
            print(f"  [WARN] {csv_path.name}: 缺少列 {missing}，跳过整个文件")
            print(f"         实际列：{reader.fieldnames}")
            return

        # 把 reader 的每一行 key 也归一化
        for row_no, raw in enumerate(reader, start=2):  # 2 = 第一条数据行（含 header）
            row = {normalize_column_name(k): v for k, v in raw.items()}
            a_ext = (row.get("DDInterID_A") or "").strip()
            b_ext = (row.get("DDInterID_B") or "").strip()
            a_name = (row.get("Drug_A") or "").strip()
            b_name = (row.get("Drug_B") or "").strip()
            if not (a_ext and b_ext and a_name and b_name):
                print(f"  [WARN] {csv_path.name}:{row_no} 关键字段缺失，跳过")
                continue
            yield {
                "a_ext_id": a_ext,
                "a_name": a_name,
                "b_ext_id": b_ext,
                "b_name": b_name,
                "severity": normalize_severity(row.get("Level")),
            }


# ---------- 导入主流程 ----------

def reset_tables(db: Session) -> None:
    db.query(DDInterInteraction).delete()
    db.query(DDInterDrug).delete()
    db.commit()
    print("已清空 ddinter_drug / ddinter_interaction")


def upsert_drugs(db: Session, records: list[dict], aliases: dict[str, list[str]]) -> dict[str, int]:
    """
    根据所有相互作用记录中出现的药物，先把 ddinter_drug 表填好。
    返回：DDInter 原始 ID(字符串) → 数据库 drug_id 的映射。

    备注：ddinter_drug.atc_code 字段在 DDInter 的相互作用 CSV 里没有，先留空，
          后续如果有 ATC 表再单独补一个脚本。
    """
    # 收集所有出现过的 (外部ID, 原名)
    pairs: dict[str, str] = {}
    for r in records:
        pairs[r["a_ext_id"]] = r["a_name"]
        pairs[r["b_ext_id"]] = r["b_name"]

    # 读现有库以做幂等：外部ID 编码进 atc_code 字段太脏，这里改用 drug_name + drug_name_normalized 唯一性
    existing = {
        d.drug_name_normalized: d.drug_id
        for d in db.scalars(select(DDInterDrug)).all()
        if d.drug_name_normalized
    }

    ext_to_db: dict[str, int] = {}
    new_count = 0
    for ext_id, raw_name in pairs.items():
        norm = normalize_drug_name(raw_name)
        if norm in existing:
            ext_to_db[ext_id] = existing[norm]
            continue
        drug = DDInterDrug(
            drug_name=raw_name,
            drug_name_normalized=norm,
            atc_code=None,
        )
        db.add(drug)
        db.flush()  # 拿到自增 drug_id
        existing[norm] = drug.drug_id
        ext_to_db[ext_id] = drug.drug_id
        new_count += 1

    # 别名：把同义词也插入 ddinter_drug，指向同一个归一化药名的 drug_id
    alias_count = 0
    for canonical, alias_list in aliases.items():
        if canonical not in existing:
            # 别名表里的主名暂未在 DDInter 出现，跳过（别名只对已知药物生效）
            continue
        canonical_drug_id = existing[canonical]
        for alias in alias_list:
            if alias in existing:
                continue
            db.add(
                DDInterDrug(
                    drug_name=alias,
                    drug_name_normalized=alias,
                    atc_code=f"alias_of:{canonical_drug_id}",
                )
            )
            existing[alias] = canonical_drug_id  # 查表时按归一化名命中
            alias_count += 1
    db.commit()
    print(f"  - 药物新增 {new_count} 条，别名映射 {alias_count} 条")
    return ext_to_db


def upsert_interactions(
    db: Session, records: list[dict], ext_to_db: dict[str, int]
) -> int:
    """
    导入相互作用记录。幂等策略：
      (drug_a_id, drug_b_id) 排序后作为唯一键，重复则覆盖 severity。
    """
    # 现有记录
    existing: dict[tuple[int, int], DDInterInteraction] = {}
    for inter in db.scalars(select(DDInterInteraction)).all():
        key = tuple(sorted([inter.drug_a_id, inter.drug_b_id]))
        existing[key] = inter

    new_count = 0
    upd_count = 0
    for r in records:
        a = ext_to_db.get(r["a_ext_id"])
        b = ext_to_db.get(r["b_ext_id"])
        if a is None or b is None or a == b:
            continue
        key = tuple(sorted([a, b]))
        if key in existing:
            inter = existing[key]
            if inter.severity != r["severity"]:
                inter.severity = r["severity"]
                upd_count += 1
            continue
        db.add(
            DDInterInteraction(
                drug_a_id=key[0],
                drug_b_id=key[1],
                drug_a_name=r["a_name"],
                drug_b_name=r["b_name"],
                severity=r["severity"],
                description=None,
                source="DDInter",
                confidence=None,
            )
        )
        new_count += 1
    db.commit()
    print(f"  - 相互作用新增 {new_count} 条，更新 {upd_count} 条")
    return new_count + upd_count


def run(reset: bool = False, dry_run: bool = False) -> int:
    if not RAW_DIR.exists():
        print(f"[ERROR] 原始数据目录不存在：{RAW_DIR}")
        print("        请先按 scripts/ddinter_raw/README.md 下载 DDInter 2.0 CSV")
        return 1

    csv_files = sorted(p for p in RAW_DIR.glob("*.csv"))
    if not csv_files:
        print(f"[ERROR] {RAW_DIR} 下没有 .csv 文件")
        return 1

    print(f"[1/3] 扫描 CSV: {len(csv_files)} 个文件")
    for p in csv_files:
        print(f"      - {p.name}")

    print("[2/3] 解析记录 ...")
    records: list[dict] = []
    for p in csv_files:
        before = len(records)
        records.extend(iter_interactions(p))
        print(f"      - {p.name}: +{len(records) - before} 条")
    if not records:
        print("[ERROR] 没有解析到任何有效记录")
        return 1
    print(f"      合计 {len(records)} 条")

    aliases = load_aliases()
    print(f"      别名表条目：{len(aliases)}")

    if dry_run:
        print("[3/3] dry-run 模式，不写库。完成。")
        return 0

    db: Session = SessionLocal()
    try:
        if reset:
            reset_tables(db)
        print("[3/3] 写入数据库 ...")
        ext_to_db = upsert_drugs(db, records, aliases)
        upsert_interactions(db, records, ext_to_db)
        print("完成。")
        return 0
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="DDInter 2.0 导入脚本")
    ap.add_argument("--reset", action="store_true", help="清空旧数据后重新导入")
    ap.add_argument("--dry-run", action="store_true", help="只解析、不写库")
    args = ap.parse_args()
    sys.exit(run(reset=args.reset, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
