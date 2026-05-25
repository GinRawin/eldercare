"""
DDInter 数据导入脚本（由后端成员 2 完善）

DDInter 2.0 下载地址：https://ddinter.scbdd.com/
下载后将原始 CSV 文件放在 scripts/ddinter_raw/ 目录（该目录在 .gitignore 中，不提交）

运行方式：
    uv run python scripts/import_ddinter.py

预期导入流程：
1. 读取 ddinter_raw/ddinter_drugs.csv → 写入 ddinter_drug 表
2. 读取 ddinter_raw/ddinter_interactions.csv → 写入 ddinter_interaction 表
3. 对药物名做归一化（去除空格、统一大小写、中英文别名映射）

注意：DDInter 2.0 仅授权非商业研究和演示，正式商用前请重新确认授权。
"""

import sys
from pathlib import Path

# TODO(backend-member-2): 实现以下函数

def import_drugs(csv_path: Path) -> None:
    raise NotImplementedError("请实现药物导入逻辑")


def import_interactions(csv_path: Path) -> None:
    raise NotImplementedError("请实现药物相互作用导入逻辑")


if __name__ == "__main__":
    raw_dir = Path(__file__).parent / "ddinter_raw"
    if not raw_dir.exists():
        print("请先将 DDInter 原始 CSV 文件放入 scripts/ddinter_raw/")
        sys.exit(1)
    import_drugs(raw_dir / "ddinter_drugs.csv")
    import_interactions(raw_dir / "ddinter_interactions.csv")
    print("导入完成")
