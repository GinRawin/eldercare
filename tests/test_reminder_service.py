"""
Step 5 · 提醒事件物化服务单测

覆盖：
1. _parse_repeat_pattern：daily / weekdays / weekends / weekly / 自定义 / 中文 / 数字
2. _parse_schedule_times：单时间 / 多时间 / 空默认 09:00 / 全角逗号
3. materialize_events：
   - 首次按区间正确生成事件
   - 重复调用幂等（events_created=0 / skipped=N）
   - rule_ids 过滤生效
   - active=False 的规则不会被物化
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.models.elder_profile import ElderProfile
from app.models.reminder import ReminderEvent, ReminderRule
from app.services.reminder_service import (
    _parse_repeat_pattern,
    _parse_schedule_times,
    materialize_events,
)

from .conftest import TEST_ELDER_PREFIX

# ---------- 1. repeat_pattern 解析 ----------


@pytest.mark.parametrize(
    "pattern,anchor,expected",
    [
        (None, date(2026, 5, 25), {0, 1, 2, 3, 4, 5, 6}),
        ("", date(2026, 5, 25), {0, 1, 2, 3, 4, 5, 6}),
        ("daily", date(2026, 5, 25), {0, 1, 2, 3, 4, 5, 6}),
        ("每天", date(2026, 5, 25), {0, 1, 2, 3, 4, 5, 6}),
        ("weekdays", date(2026, 5, 25), {0, 1, 2, 3, 4}),
        ("工作日", date(2026, 5, 25), {0, 1, 2, 3, 4}),
        ("weekends", date(2026, 5, 25), {5, 6}),
        ("周末", date(2026, 5, 25), {5, 6}),
        # anchor 2026-05-25 是周一 → weekly 仅命中周一
        ("weekly", date(2026, 5, 25), {0}),
        ("mon,wed,fri", date(2026, 5, 25), {0, 2, 4}),
        ("周一,周三,周五", date(2026, 5, 25), {0, 2, 4}),
        # ISO 数字 1=Mon..7=Sun
        ("1,3,5", date(2026, 5, 25), {0, 2, 4}),
        # 全角逗号兼容
        ("周一，周三", date(2026, 5, 25), {0, 2}),
    ],
)
def test_parse_repeat_pattern(pattern, anchor, expected) -> None:
    assert _parse_repeat_pattern(pattern, anchor) == expected


# ---------- 2. schedule_time 解析 ----------


def test_parse_schedule_times_default() -> None:
    assert _parse_schedule_times(None) == [time(9, 0)]
    assert _parse_schedule_times("") == [time(9, 0)]


def test_parse_schedule_times_single() -> None:
    assert _parse_schedule_times("08:00") == [time(8, 0)]


def test_parse_schedule_times_multi() -> None:
    assert _parse_schedule_times("08:00,12:30,18:45") == [
        time(8, 0),
        time(12, 30),
        time(18, 45),
    ]


def test_parse_schedule_times_fullwidth_comma() -> None:
    assert _parse_schedule_times("08:00，12:30") == [time(8, 0), time(12, 30)]


def test_parse_schedule_times_skips_bad_tokens() -> None:
    # 坏 token 跳过，仅保留可解析项
    assert _parse_schedule_times("08:00,not_a_time") == [time(8, 0)]


# ---------- 3. materialize_events（用真实 DB） ----------


def _seed_rules(db: Session, elder_id: str) -> tuple[int, int, int]:
    db.add(
        ElderProfile(
            elder_id=elder_id,
            name="提醒测试老人",
            age=70,
            gender="M",
            allergies="[]",
            diseases="[]",
            health_notes=None,
        )
    )
    db.commit()
    r1 = ReminderRule(
        elder_id=elder_id,
        type="medication",
        title="早药",
        schedule_time="08:00",
        repeat_pattern="daily",
        active=True,
    )
    r2 = ReminderRule(
        elder_id=elder_id,
        type="meal",
        title="午餐",
        schedule_time="12:00",
        repeat_pattern="weekdays",
        active=True,
    )
    r3 = ReminderRule(
        elder_id=elder_id,
        type="medication",
        title="历史规则",
        schedule_time="22:00",
        repeat_pattern="daily",
        active=False,  # 非 active
    )
    db.add_all([r1, r2, r3])
    db.commit()
    return r1.rule_id, r2.rule_id, r3.rule_id


def test_materialize_events_daily_and_weekdays(db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}materialize_basic"
    r1_id, r2_id, r3_id = _seed_rules(db, elder_id)

    # 2026-05-25 是周一；7 天 = 周一~周日
    res = materialize_events(db, elder_id, date(2026, 5, 25), date(2026, 5, 31))
    # daily 7 + weekdays 5 = 12（r3 active=False 应被跳过）
    assert res.rules_processed == 2
    assert res.events_created == 12
    assert res.events_skipped_existing == 0

    # 再跑一次：完全幂等
    res2 = materialize_events(db, elder_id, date(2026, 5, 25), date(2026, 5, 31))
    assert res2.events_created == 0
    assert res2.events_skipped_existing == 12

    # 数据库验证：r3 没有任何事件
    count_r3 = db.query(ReminderEvent).filter(ReminderEvent.rule_id == r3_id).count()
    assert count_r3 == 0


def test_materialize_events_rule_ids_filter(db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}materialize_filter"
    r1_id, r2_id, _ = _seed_rules(db, elder_id)

    res = materialize_events(
        db,
        elder_id,
        date(2026, 5, 25),
        date(2026, 5, 31),
        rule_ids=[r1_id],
    )
    assert res.rules_processed == 1
    assert res.events_created == 7  # 仅 daily 规则


def test_materialize_events_invalid_range(db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}invalid_range"
    db.add(
        ElderProfile(
            elder_id=elder_id,
            name="x",
            age=70,
            gender="M",
            allergies="[]",
            diseases="[]",
            health_notes=None,
        )
    )
    db.commit()
    with pytest.raises(ValueError):
        materialize_events(db, elder_id, date(2026, 5, 31), date(2026, 5, 25))


def test_materialize_events_no_rules(db: Session) -> None:
    elder_id = f"{TEST_ELDER_PREFIX}no_rules"
    db.add(
        ElderProfile(
            elder_id=elder_id,
            name="x",
            age=70,
            gender="M",
            allergies="[]",
            diseases="[]",
            health_notes=None,
        )
    )
    db.commit()
    res = materialize_events(db, elder_id, date(2026, 5, 25), date(2026, 5, 25))
    assert res.rules_processed == 0
    assert res.events_created == 0
    assert res.events_skipped_existing == 0
