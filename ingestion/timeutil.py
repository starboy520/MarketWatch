"""Time helpers shared by ingestion/pipeline.

`created_at` from X legacy is typically UTC, e.g. "Mon Jan 01 00:00:00 +0000 2024".
We convert it to Beijing time (Asia/Shanghai) for display and LLM metadata.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from zoneinfo import ZoneInfo

_BJT = ZoneInfo("Asia/Shanghai")
# 财联社等国内源常用「墙钟」字符串，无时区；勿当成 UTC 再加 8 小时（会跨日错位）。
_NAIVE_LOCAL_BJT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[ ]\d{2}:\d{2}:\d{2}$")


def format_created_at_bjt(created_at: Optional[str]) -> Optional[str]:
    """
    Convert a time string to Beijing time display.

    - If parsing fails, returns the original string (stripped).
    - If input is empty/None, returns None.
    """

    raw = (created_at or "").strip()
    if not raw:
        return None

    dt: datetime | None = None
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        dt = None

    if dt is None:
        # Best-effort ISO8601 support
        try:
            iso = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
        except Exception:
            return raw

    if dt.tzinfo is None:
        # X legacy 多为 RFC2822 带 +0000；此处已能解析出 tzinfo。
        # 无时区且为「YYYY-MM-DD HH:MM:SS」视为已是北京时间（财联社 _format_time 等）。
        if _NAIVE_LOCAL_BJT_PATTERN.fullmatch(raw):
            dt = dt.replace(tzinfo=_BJT)
        else:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

    bjt = dt.astimezone(_BJT)
    return bjt.strftime("%Y-%m-%d %H:%M:%S 北京时间")

