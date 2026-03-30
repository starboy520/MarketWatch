"""飞书通知：仅暴露 FeishuClient，配置见 ingestion.config.FeishuConfig（[feishu]）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import requests

from ingestion.config import FeishuConfig
from ingestion.models import TweetEvent
from ingestion.timeutil import format_created_at_bjt

_TENANT_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
_IM_MESSAGES_PATH = "/open-apis/im/v1/messages"

_TEXT_LEN_LIMIT = 8000
_TOKEN_REFRESH_MARGIN_SEC = 60


def _truncate(text: str, limit: int = _TEXT_LEN_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit]


def _response_to_dict(resp: requests.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as e:
        raise RuntimeError(f"Feishu 非 JSON 响应: {resp.text[:500]!r}") from e
    if resp.status_code >= 400:
        raise RuntimeError(f"Feishu HTTP {resp.status_code}: {data!r}")
    if not isinstance(data, dict):
        raise RuntimeError(f"Feishu 期望 JSON 对象: {data!r}")
    return data


def _require_openapi_ok(data: dict[str, Any], what: str) -> None:
    code = int(data.get("code", -1))
    if code != 0:
        raise RuntimeError(f"{what} 失败 (code={code}): {data}")


@dataclass
class FeishuClient:
    """
    应用 tenant_access_token + IM 发送文本（需 app_id、app_secret、receive_id）。

    使用：``FeishuClient.from_config(cfg.feishu)``（仅当 ``cfg.feishu.enabled``）。
    """

    _cfg: FeishuConfig = field(repr=False)
    _token: Optional[str] = field(default=None, repr=False)
    _token_deadline: float = field(default=0.0, repr=False)
    _http: requests.Session = field(default_factory=requests.Session, repr=False, compare=False)

    @classmethod
    def from_config(cls, cfg: FeishuConfig) -> FeishuClient:
        if not cfg.enabled:
            raise ValueError("Feishu 未启用：请配置 app_id、app_secret、receive_id")
        return cls(_cfg=cfg)

    @staticmethod
    def format_tweet_event(ev: TweetEvent) -> str:
        """单条帖子的飞书文本（含独立链接行，便于客户端识别为可点击 URL）。"""
        body = ev.text.replace("\r", "").strip()
        body_one = " ".join(body.split()) if body else "(无正文)"
        body_one = _truncate(body_one, 3500)
        ts = format_created_at_bjt(ev.created_at) or ((ev.created_at or "").strip() or "—")
        link = (ev.permalink or "").strip()
        lines = [
            f"🐦 新帖 @{ev.author_username}",
            f"推文 ID：{ev.id}",
            f"时间：{ts}",
            "",
            body_one,
            "",
            "链接：",
            link if link else "(无链接)",
        ]
        return "\n".join(lines)

    def _timeout(self) -> float:
        return float(self._cfg.timeout_sec)

    def _openapi_url(self, path: str) -> str:
        return f"{self._cfg.openapi_base}{path}"

    def _post_openapi(
        self,
        path: str,
        body: dict[str, Any],
        *,
        params: Optional[Mapping[str, str]] = None,
        bearer: Optional[str] = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        resp = self._http.post(
            self._openapi_url(path),
            json=body,
            headers=headers,
            params=dict(params) if params else None,
            timeout=self._timeout(),
        )
        return _response_to_dict(resp)

    def get_tenant_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        if (
            not force_refresh
            and self._token
            and now < self._token_deadline - _TOKEN_REFRESH_MARGIN_SEC
        ):
            return self._token

        data = self._post_openapi(
            _TENANT_TOKEN_PATH,
            {"app_id": self._cfg.app_id, "app_secret": self._cfg.app_secret},
        )
        _require_openapi_ok(data, "tenant_access_token")
        tok = str(data.get("tenant_access_token") or "").strip()
        if not tok:
            raise RuntimeError(f"tenant_access_token 为空: {data}")
        expire = int(data.get("expire") or 7200)
        self._token = tok
        self._token_deadline = now + max(60, expire)
        return tok

    def send_text(self, text: str) -> None:
        token = self.get_tenant_access_token()
        inner = json.dumps({"text": _truncate(text)}, ensure_ascii=False)
        data = self._post_openapi(
            _IM_MESSAGES_PATH,
            {
                "receive_id": self._cfg.receive_id,
                "msg_type": "text",
                "content": inner,
            },
            params={"receive_id_type": self._cfg.receive_id_type},
            bearer=token,
        )
        _require_openapi_ok(data, "发送 IM")

    def push_incremental_tweet_events(self, events: list[TweetEvent]) -> None:
        for ev in events:
            self.send_text(self.format_tweet_event(ev))
