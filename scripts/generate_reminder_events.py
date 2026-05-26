"""
批量生成提醒事件 CLI（Step 4 · 块 4）

用法：
    uv run python scripts/generate_reminder_events.py --elder-id E001 --days 7
    uv run python scripts/generate_reminder_events.py --elder-id E001 \
        --start 2026-05-26 --end 2026-06-01
    uv run python scripts/generate_reminder_events.py --elder-id E001 --days 3 --rules 1,2

幂等：重复执行不会产生重复事件（已存在的 (rule_id, due_at) 自动跳过）。
第一版仅手动跑一次即可，不引入定时任务。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# 允许直接 `python scripts/generate_reminder_events.py` 运行（与 import_ddinter.py 一致）
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.reminder_service import materialize_events  # noqa: E402


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="批量生成 ReminderEvent")
    parser.add_argument("--elder-id", required=True, help="老人 ID")
    parser.add_argument("--start", type=_parse_date, help="起始日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--end", type=_parse_date, help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="若未提供 --end，则从 --start 起向后 N 天（默认 7）",
    )
    parser.add_argument(
        "--rules",
        type=str,
        help="只为指定 rule_id 生成（逗号分隔，可选）",
    )
    args = parser.parse_args()

    start = args.start or date.today()
    end = args.end or (start + timedelta(days=args.days - 1))

    rule_ids: list[int] | None = None
    if args.rules:
        rule_ids = [int(x.strip()) for x in args.rules.split(",") if x.strip()]

    db = SessionLocal()
    try:
        result = materialize_events(
            db,
            elder_id=args.elder_id,
            start_date=start,
            end_date=end,
            rule_ids=rule_ids,
        )
    finally:
        db.close()

    print(
        f"[materialize_events] elder_id={args.elder_id} "
        f"range=[{start}, {end}] "
        f"rules_processed={result.rules_processed} "
        f"events_created={result.events_created} "
        f"events_skipped_existing={result.events_skipped_existing}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
