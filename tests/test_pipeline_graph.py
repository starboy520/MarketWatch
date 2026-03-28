"""pipeline StateGraph：需 pip install -e '.[pipeline]'。"""

from __future__ import annotations

import pytest

from ingestion.models import TweetEvent

pytest.importorskip("langgraph")

from pipeline.graph import (  # noqa: E402
    PipelineCompileConfig,
    build_pipeline_graph,
    invoke_for_tweet,
)


def test_build_and_invoke_dry_run() -> None:
    g = build_pipeline_graph(PipelineCompileConfig(feishu_dry_run=True, enable_prefilter=False))
    ev = TweetEvent(
        id="999",
        text="hello world test",
        author_username="business",
        permalink="https://x.com/i/web/status/999",
        created_at=None,
        raw_json="{}",
    )
    out = invoke_for_tweet(ev, graph=g)
    assert out.get("status") == "published"
    assert out.get("publish_status") == "ok"
    assert "feishu_payload" in out


def test_prefilter_short_text_filtered() -> None:
    g = build_pipeline_graph(
        PipelineCompileConfig(feishu_dry_run=True, enable_prefilter=True),
    )
    ev = TweetEvent(
        id="1",
        text="short",
        author_username="u",
        permalink="https://x.com/i/web/status/1",
        created_at=None,
        raw_json="{}",
    )
    out = invoke_for_tweet(ev, graph=g)
    assert out.get("status") == "filtered"
