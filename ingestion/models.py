"""采集层标准化事件（对齐 docs/bloomberg_twitter_agent_design.md §4.1）。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

EVENT_NAME = "tweet.received"


@dataclass(frozen=True)
class TweetEvent:
    """
    采集层标准事件（对齐 docs/bloomberg_twitter_agent_design.md §4.1）。

    字段约定
    --------
    - ``id``：推文 ID；编排层 State 中对应 ``tweet_id``。
    - ``text``：正文；编排层 State 中对应 ``raw_text``（避免与 LLM 输出的 ``analysis`` 混淆）。
    - ``author_username``：不带 @ 的 screen name。
    - ``permalink``：稳定可分享的原文链接。
    - ``created_at``：上游时间串（如 Twitter ``legacy.created_at``），可为空。
    - ``raw_json``：原始 JSON 字符串，供审计；pipeline 默认不喂给 LLM，仅在 State 携带。
    - ``source``：事件来源标识，默认 ``tweet.received``。
    - ``lang``：上游语言码（如 X ``legacy.lang``），可选；用于 pipeline 判断是否英译中。
    """

    id: str
    text: str
    author_username: str
    permalink: str
    created_at: Optional[str]
    raw_json: str
    source: str = EVENT_NAME
    lang: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def pipeline_initial_state(self) -> Dict[str, Any]:
        """LangGraph 初始 State：与 ``pipeline.state.PipelineState`` 键名一致。"""
        return {
            "tweet_id": self.id,
            "raw_text": self.text,
            "permalink": self.permalink,
            "author_username": self.author_username,
            "created_at": self.created_at,
            "raw_json": self.raw_json,
            "source": self.source,
            "tweet_lang": self.lang,
            "retry_count": 0,
            "status": "pending",
        }


def tweet_permalink(tweet_id: str) -> str:
    return f"https://x.com/i/web/status/{tweet_id}"


def normalize_post_to_event(tweet: Dict[str, Any], author_username: str) -> TweetEvent:
    tid = str(tweet.get("id", "")).strip()
    link = str(tweet.get("permalink") or "").strip() or tweet_permalink(tid)
    lang_raw = tweet.get("lang")
    lang = str(lang_raw).strip().lower() if isinstance(lang_raw, str) and lang_raw.strip() else None
    return TweetEvent(
        id=tid,
        text=str(tweet.get("text") or ""),
        author_username=author_username.lstrip("@"),
        permalink=link,
        created_at=tweet.get("created_at") if tweet.get("created_at") is not None else None,
        raw_json=json.dumps(tweet, ensure_ascii=False),
        source=EVENT_NAME,
        lang=lang,
    )
