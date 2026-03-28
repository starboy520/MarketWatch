"""ingestion/feishu.FeishuClient 单元测试（mock HTTP，不打真实 OpenAPI）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ingestion.config import FeishuConfig
from ingestion.feishu import FeishuClient
from ingestion.models import TweetEvent


def _cfg_openapi() -> FeishuConfig:
    return FeishuConfig(
        app_id="cli_test",
        app_secret="secret",
        receive_id="oc_chat_1",
        receive_id_type="chat_id",
        openapi_base="https://open.feishu.cn",
        timeout_sec=10.0,
    )


def test_from_config_disabled_raises() -> None:
    cfg = FeishuConfig(
        app_id="",
        app_secret="",
        receive_id="",
        receive_id_type="chat_id",
        openapi_base="https://open.feishu.cn",
        timeout_sec=15.0,
    )
    assert not cfg.enabled
    with pytest.raises(ValueError, match="未启用"):
        FeishuClient.from_config(cfg)


def test_format_tweet_event() -> None:
    ev = TweetEvent(
        id="123",
        text="hello\nworld",
        author_username="business",
        permalink="https://x.com/i/web/status/123",
        created_at="Mon Jan 01 00:00:00 +0000 2024",
        raw_json="{}",
    )
    s = FeishuClient.format_tweet_event(ev)
    assert "123" in s
    assert "@business" in s
    assert "hello world" in s
    assert "链接：" in s
    assert "https://x.com/i/web/status/123" in s


def test_openapi_send_text_token_then_im() -> None:
    client = FeishuClient.from_config(_cfg_openapi())

    def fake_post(url: str, **kwargs):
        r = MagicMock()
        r.status_code = 200
        if url.endswith("/tenant_access_token/internal"):
            r.json.return_value = {
                "code": 0,
                "tenant_access_token": "t-mock",
                "expire": 7200,
            }
            return r
        if "/messages" in url:
            assert kwargs.get("params") == {"receive_id_type": "chat_id"}
            assert kwargs["headers"]["Authorization"] == "Bearer t-mock"
            inner = kwargs["json"]
            assert inner["receive_id"] == "oc_chat_1"
            r.json.return_value = {"code": 0}
            return r
        raise AssertionError(f"unexpected url: {url!r}")

    with patch.object(client._http, "post", side_effect=fake_post) as m_post:
        client.send_text("hello im")
    assert m_post.call_count == 2


def test_get_tenant_access_token_caches_until_margin() -> None:
    client = FeishuClient.from_config(_cfg_openapi())

    def fake_post(url: str, **kwargs):
        r = MagicMock()
        r.status_code = 200
        if url.endswith("/tenant_access_token/internal"):
            r.json.return_value = {"code": 0, "tenant_access_token": "tok-1", "expire": 7200}
            return r
        raise AssertionError(f"unexpected url: {url!r}")

    with patch.object(client._http, "post", side_effect=fake_post) as m_post:
        assert client.get_tenant_access_token() == "tok-1"
        assert client.get_tenant_access_token() == "tok-1"
    assert m_post.call_count == 1
