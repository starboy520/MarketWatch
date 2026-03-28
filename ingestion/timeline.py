"""轮询时间线：checkpoint、内存去重、人类可读摘要。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from ingestion.models import EVENT_NAME, TweetEvent, normalize_post_to_event
from ingestion.x_api import (
    XClient,
)


def _id_sort_key(value: str) -> tuple[int, str]:
    try:
        return (0, str(int(value)))
    except ValueError:
        return (1, value)


def format_events_message(
    username: str,
    events: List[TweetEvent],
    *,
    since_id: Optional[str],
    next_since_id: Optional[str],
    errors: Any = None,
) -> str:
    lines: List[str] = []
    if errors:
        lines.append(f"[API 提示] {errors}")
    lines.append(
        f"[{EVENT_NAME}] @{username} since_id={since_id!r} -> next_since_id={next_since_id!r}"
    )
    if not events:
        lines.append("无新帖子（或均被去重）。")
        return "\n".join(lines)

    lines.append(f"共 {len(events)} 条事件：")
    for ev in sorted(events, key=lambda x: _id_sort_key(x.id)):
        text = ev.text.replace("\n", " ")
        lines.append(f"- id={ev.id} | {ev.created_at or ''}")
        lines.append(f"  {text}")
        lines.append(f"  {ev.permalink}")
    return "\n".join(lines)


def poll_timeline_events(
    client: XClient,
    username: str,
    *,
    user_id: Optional[str],
    since_id: Optional[str],
    max_results: int,
    seen_ids: Set[str],
) -> Tuple[List[TweetEvent], str, str, Optional[str]]:
    """
    返回 (新事件列表, message, user_id, next_since_id)。
    seen_ids 原地更新。
    """
    uname = username.lstrip("@")

    if not user_id:
        uid = client.get_user_id(uname)
        payload = client.fetch_user_posts_with_retry(uid, since_id=None, max_results=5)
        raw = payload.get("data") or []
        tweets = [t for t in raw if isinstance(t, dict)]
        newest_id = str(tweets[0]["id"]) if tweets else None
        msg = format_events_message(
            uname, [], since_id=None, next_since_id=newest_id, errors=payload.get("errors")
        )
        msg = f"[首次] user_id={uid}，仅建立 since_id 断点，不灌历史正文。\n" + msg
        return [], msg, uid, newest_id

    payload = client.fetch_user_posts_with_retry(user_id, since_id=since_id, max_results=max_results)
    raw = payload.get("data") or []
    tweets = [t for t in raw if isinstance(t, dict)]

    next_since = since_id
    new_events: List[TweetEvent] = []
    for tw in tweets:
        tid = str(tw["id"])
        if next_since is None or str(tid) > str(next_since):
            next_since = tid
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        new_events.append(normalize_post_to_event(tw, uname))

    msg = format_events_message(
        uname,
        new_events,
        since_id=since_id,
        next_since_id=next_since,
        errors=payload.get("errors"),
    )
    return new_events, msg, user_id, next_since
