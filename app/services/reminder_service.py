"""
提醒事件物化服务（Step 4 · 块 4）

把 ReminderRule（schedule_time + repeat_pattern）展开成具体日期上的
ReminderEvent，落库以便 `GET /api/v1/reminders/due` 直接读取。

第一版仅提供「按需手动调用」的物化函数 + CLI 脚本，
不引入定时任务（Celery/APScheduler），演示前手动跑一次即可。

设计要点：
1. 不破坏接口契约：只新增 service 层文件，路由与 schemas 不变
2. 幂等：对已存在的 (rule_id, due_at) 不重复插入
3. repeat_pattern 解析：
     - None / "" / "daily" / "everyday"        → 每天
     - "weekdays"                              → 周一至周五
     - "weekends"                              → 周六周日
     - "weekly"                                → 与 start_date 同 weekday
     - "mon,wed,fri" / "1,3,5"                 → 自定义星期集合
4. schedule_time 解析：
     - "HH:MM"（单时间）
     - "HH:MM,HH:MM"（多时间，逗号分隔）
     - None / "" → 默认 09:00
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models.reminder import ReminderEvent, ReminderRule

# ---------- repeat_pattern 解析 ----------

_WEEKDAY_NAMES: dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "周一": 0,
    "星期一": 0,
    "tue": 1,
    "tuesday": 1,
    "周二": 1,
    "星期二": 1,
    "wed": 2,
    "wednesday": 2,
    "周三": 2,
    "星期三": 2,
    "thu": 3,
    "thursday": 3,
    "周四": 3,
    "星期四": 3,
    "fri": 4,
    "friday": 4,
    "周五": 4,
    "星期五": 4,
    "sat": 5,
    "saturday": 5,
    "周六": 5,
    "星期六": 5,
    "sun": 6,
    "sunday": 6,
    "周日": 6,
    "星期日": 6,
    "星期天": 6,
}


def _parse_repeat_pattern(pattern: str | None, anchor: date) -> set[int]:
    """返回该 pattern 命中的 weekday 集合（0=周一, 6=周日）。

    anchor 仅用于 "weekly" 这种「与起始同 weekday」的语义。
    """
    p = (pattern or "").strip().lower()
    if p in ("", "daily", "everyday", "每天", "日"):
        return set(range(7))
    if p in ("weekdays", "工作日"):
        return {0, 1, 2, 3, 4}
    if p in ("weekends", "周末"):
        return {5, 6}
    if p in ("weekly", "每周"):
        return {anchor.weekday()}

    weekdays: set[int] = set()
    for token in p.replace("，", ",").split(","):
        t = token.strip()
        if not t:
            continue
        if t in _WEEKDAY_NAMES:
            weekdays.add(_WEEKDAY_NAMES[t])
            continue
        # 数字写法：1=Mon ... 7=Sun（ISO），0=Sun（部分系统），都做兼容
        if t.isdigit():
            n = int(t)
            if 1 <= n <= 7:
                weekdays.add((n - 1) % 7)
            elif n == 0:
                weekdays.add(6)
    return weekdays


# ---------- schedule_time 解析 ----------


def _parse_schedule_times(schedule_time: str | None) -> list[time]:
    """支持 "HH:MM" 或 "HH:MM,HH:MM,..."；空则默认 09:00。"""
    raw = (schedule_time or "").strip()
    if not raw:
        return [time(9, 0)]
    out: list[time] = []
    for token in raw.replace("，", ",").split(","):
        t = token.strip()
        if not t:
            continue
        try:
            hh, mm = t.split(":")
            out.append(time(int(hh), int(mm)))
        except ValueError:
            # 忽略无法解析的片段（导入脚本式容错，不抛错阻塞其它规则）
            continue
    return out or [time(9, 0)]


# ---------- 物化结果 ----------


@dataclass
class MaterializeResult:
    rules_processed: int
    events_created: int
    events_skipped_existing: int

    def as_dict(self) -> dict[str, int]:
        return {
            "rules_processed": self.rules_processed,
            "events_created": self.events_created,
            "events_skipped_existing": self.events_skipped_existing,
        }


# ---------- 主入口 ----------


def materialize_events(
    db: Session,
    elder_id: str,
    start_date: date,
    end_date: date,
    *,
    rule_ids: list[int] | None = None,
) -> MaterializeResult:
    """为指定老人在 [start_date, end_date] 区间内批量生成 ReminderEvent。

    幂等：先查已存在的 (rule_id, due_at)，仅插入缺失的。
    返回值统计本次实际新建 / 跳过条数。
    """
    if end_date < start_date:
        raise ValueError("end_date 必须不早于 start_date")

    q = db.query(ReminderRule).filter(
        ReminderRule.elder_id == elder_id,
        ReminderRule.active.is_(True),
    )
    if rule_ids:
        q = q.filter(ReminderRule.rule_id.in_(rule_ids))
    rules = q.all()

    if not rules:
        return MaterializeResult(0, 0, 0)

    # 区间起止 datetime，用于一次性查出所有已存在事件
    range_start = datetime.combine(start_date, time.min)
    range_end = datetime.combine(end_date, time.max)

    existing_pairs: set[tuple[int, datetime]] = {
        (e.rule_id, e.due_at)
        for e in db.query(ReminderEvent.rule_id, ReminderEvent.due_at)
        .filter(
            ReminderEvent.elder_id == elder_id,
            ReminderEvent.rule_id.in_([r.rule_id for r in rules]),
            ReminderEvent.due_at >= range_start,
            ReminderEvent.due_at <= range_end,
        )
        .all()
    }

    created = 0
    skipped = 0
    new_events: list[ReminderEvent] = []

    for rule in rules:
        weekday_set = _parse_repeat_pattern(rule.repeat_pattern, start_date)
        times = _parse_schedule_times(rule.schedule_time)

        d = start_date
        while d <= end_date:
            if d.weekday() in weekday_set:
                for t in times:
                    due_at = datetime.combine(d, t)
                    key = (rule.rule_id, due_at)
                    if key in existing_pairs:
                        skipped += 1
                        continue
                    new_events.append(
                        ReminderEvent(
                            rule_id=rule.rule_id,
                            elder_id=rule.elder_id,
                            title=rule.title,
                            due_at=due_at,
                            status="pending",
                        )
                    )
                    existing_pairs.add(key)
                    created += 1
            d += timedelta(days=1)

    if new_events:
        db.add_all(new_events)
        db.commit()

    return MaterializeResult(
        rules_processed=len(rules),
        events_created=created,
        events_skipped_existing=skipped,
    )
