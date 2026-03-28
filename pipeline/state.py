"""Pipeline State：与《docs/LangGraph 状态机设计.md》字段对齐。

与 ``ingestion.models.TweetEvent`` 的对应关系（由 ``TweetEvent.pipeline_initial_state()`` 写入）：

- ``tweet_id`` ← ``TweetEvent.id``
- ``raw_text`` ← ``TweetEvent.text``
- ``permalink`` ← ``TweetEvent.permalink``
- ``author_username`` ← ``TweetEvent.author_username``
- ``created_at`` ← ``TweetEvent.created_at``
- ``raw_json`` ← ``TweetEvent.raw_json``（审计；默认不送入 LLM）
- ``source`` ← ``TweetEvent.source``（如 ``tweet.received``）
- ``tweet_lang`` ← ``TweetEvent.lang``（可选，用于英译中判断）

``raw_text_zh``（``body_translate`` 节点写入）：英文正文的大模型简体中文译文，供飞书卡片展示。

``analysis``（relevance_filter 写入）除 ``is_relevant`` / ``confidence`` 等外，另含
``broad_push_eligible``：宽松口径（实质涉 AI 或中国），供下游与 ``is_relevant`` 组合决策。
"""

from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    tweet_id: str
    raw_text: str
    permalink: str
    author_username: str
    created_at: str | None
    raw_json: str
    source: str
    tweet_lang: str | None
    raw_text_zh: str | None
    analysis: dict[str, Any]
    market_map: dict[str, Any]
    market_impact: dict[str, Any]
    status: str
    retry_count: int
    feishu_payload: dict[str, Any] | str
    error: str | None
    publish_status: str
    """ok | retry | failed — Feishu 节点内部路由用。"""
