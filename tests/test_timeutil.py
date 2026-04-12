from __future__ import annotations

from ingestion.timeutil import format_created_at_bjt


def test_naive_space_datetime_treated_as_bjt_not_utc() -> None:
    """无时区「YYYY-MM-DD HH:MM:SS」视为已是北京时间，不得再 +8h 跨日。"""
    out = format_created_at_bjt("2026-04-11 20:06:56")
    assert out == "2026-04-11 20:06:56 北京时间"


def test_x_style_utc_rfc2822_converts_to_bjt() -> None:
    out = format_created_at_bjt("Sat, 11 Apr 2026 12:06:56 +0000")
    assert out == "2026-04-11 20:06:56 北京时间"
