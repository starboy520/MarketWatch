"""
LLM 统一输出 Schema（对齐 bloomberg_twitter_agent_design.md §5）。
分析侧使用；采集层仅产出 TweetEvent。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


class RelevanceBlock(TypedDict, total=False):
    china_related: bool
    themes: List[str]
    confidence: float


class SentimentBlock(TypedDict, total=False):
    label: Literal["positive", "negative", "neutral", "mixed"]
    confidence: float
    rationale_short: str


class SectorRef(TypedDict, total=False):
    name: str
    code: str


class StockRef(TypedDict, total=False):
    code: str
    name: str
    role: Literal["leader", "follower", "other"]


class MarketImpactBlock(TypedDict, total=False):
    direction: Literal["bullish", "bearish", "neutral"]
    sectors: List[SectorRef]
    stocks: List[StockRef]
    mapping_confidence: Literal["low", "medium", "high"]


class TweetAnalysisPayload(TypedDict, total=False):
    tweet_id: str
    relevance: RelevanceBlock
    sentiment: SentimentBlock
    market_impact: MarketImpactBlock


EXAMPLE_JSON: Dict[str, Any] = {
    "tweet_id": "string",
    "relevance": {
        "china_related": True,
        "themes": ["semiconductor", "ai"],
        "confidence": 0.86,
    },
    "sentiment": {
        "label": "negative",
        "confidence": 0.72,
        "rationale_short": "提及对华出口限制，偏供应链利空",
    },
    "market_impact": {
        "direction": "bearish",
        "sectors": [{"name": "半导体", "code": "SW801081"}],
        "stocks": [{"code": "603XXX.SH", "name": "示例", "role": "leader"}],
        "mapping_confidence": "medium",
    },
}
