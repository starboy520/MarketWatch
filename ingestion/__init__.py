"""
采集层：X Web GraphQL → ``TweetEvent``；配置、时间线轮询、飞书客户端、checkpoint。

分析侧 JSON 形状说明见项目根目录 ``llm_schema.py``（非采集职责）。
"""

from ingestion.checkpoints import PollCheckpointStore
from ingestion.config import FeishuConfig, load_config
from ingestion.feishu import FeishuClient
from ingestion.models import (
    EVENT_NAME,
    TweetEvent,
    normalize_post_to_event,
    tweet_permalink,
)
from ingestion.timeline import format_events_message, poll_timeline_events
from ingestion.x_api import (
    XClient,
    create_x_client,
)

__all__ = [
    "PollCheckpointStore",
    "EVENT_NAME",
    "TweetEvent",
    "FeishuClient",
    "FeishuConfig",
    "XClient",
    "create_x_client",
    "load_config",
    "format_events_message",
    "normalize_post_to_event",
    "poll_timeline_events",
    "tweet_permalink",
]
