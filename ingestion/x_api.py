"""X 采集适配层：基于 Web GraphQL（guest token + public bearer）。

注意：
- 该方式本质是「网页端内部 API」，稳定性与合规风险需要自担。
- 本模块只负责采集与最小字段标准化；下游去重与 LLM 处理在别处。
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TypeVar

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError
from urllib3.exceptions import SSLError as Urllib3SSLError

from ingestion.config import AppConfig, load_config

_RETRYABLE_HTTP_STATUS = frozenset({429, 502, 503, 504})


def _is_transient_request_failure(exc: BaseException) -> bool:
    """TLS 半途断开、连接 reset、urllib3 耗尽重试等，适合退避后重试。"""
    if isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ContentDecodingError,
        ),
    ):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in _RETRYABLE_HTTP_STATUS
    cur: Optional[BaseException] = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, (MaxRetryError, Urllib3SSLError, ProtocolError, NewConnectionError)):
            return True
        msg = str(cur).lower()
        if any(
            s in msg
            for s in (
                "ssl",
                "eof occurred",
                "unexpected_eof",
                "connection reset",
                "broken pipe",
                "remote end closed",
            )
        ):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


T = TypeVar("T")


def _retry_transient_call(fn: Callable[[], T], *, max_retries: int = 8) -> T:
    delay = 1.0
    last_err: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            rate_hint = (
                "429" in msg
                or "too many requests" in msg
                or "rate limit" in msg
                or "timed out" in msg
                or "timeout" in msg
            )
            if rate_hint or _is_transient_request_failure(e):
                if attempt + 1 >= max_retries:
                    break
                time.sleep(delay + random.uniform(0, 0.5))
                delay = min(delay * 2, 60.0)
                continue
            raise
    assert last_err is not None
    raise last_err


@dataclass
class XClient:
    user_tweets_query_id: str
    timeout_sec: float
    user_agent: str
    proxy: Optional[str]
    bearer_token: str
    user_by_screen_name_query_id: str

    def _proxies(self) -> Optional[Dict[str, str]]:
        if not self.proxy:
            return None
        return {"http": self.proxy, "https": self.proxy}

    def get_guest_token(self) -> str:
        url = "https://api.x.com/1.1/guest/activate.json"
        headers = {"authorization": f"Bearer {self.bearer_token}", "user-agent": self.user_agent}
        resp = requests.post(url, headers=headers, proxies=self._proxies(), timeout=self.timeout_sec)
        resp.raise_for_status()
        gt = resp.json().get("guest_token")
        if not gt:
            raise RuntimeError(f"guest_token missing, body={resp.text[:200]}")
        return str(gt)

    def get_user_id(self, username: str) -> str:
        uname = username.lstrip("@").strip()
        if not uname:
            raise ValueError("username 不能为空")
        if uname.isdigit():
            return uname

        guest = self.get_guest_token()
        query_id = self.user_by_screen_name_query_id.strip()
        url = f"https://x.com/i/api/graphql/{query_id}/UserByScreenName"
        params = {
            "variables": json.dumps(
                {"screen_name": uname, "withSafetyModeUserFields": True}, ensure_ascii=False
            ),
            "features": json.dumps(
                {
                    "hidden_profile_likes_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "subscriptions_verification_info_is_identity_verified_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                },
                ensure_ascii=False,
            ),
        }
        headers = {
            "authorization": f"Bearer {self.bearer_token}",
            "x-guest-token": guest,
            "user-agent": self.user_agent,
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
        }
        resp = requests.get(url, headers=headers, params=params, proxies=self._proxies(), timeout=self.timeout_sec)
        resp.raise_for_status()
        data = resp.json()
        rest_id = ((data.get("data") or {}).get("user", {}).get("result", {}) or {}).get("rest_id")
        if not rest_id:
            raise RuntimeError(f"UserByScreenName rest_id missing, body_snippet={resp.text[:200]!r}")
        rid = str(rest_id).strip()
        if not rid.isdigit():
            raise RuntimeError(f"UserByScreenName rest_id not numeric: {rid!r}")
        return rid

    def get_user_id_with_retry(self, username: str, *, max_retries: int = 8) -> str:
        return _retry_transient_call(lambda: self.get_user_id(username), max_retries=max_retries)

    def fetch_user_posts(
        self,
        user_id: str,
        *,
        since_id: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        if max_results < 1 or max_results > 100:
            raise ValueError("max_results 须在 1～100 之间")

        errs: List[str] = []
        uid = str(user_id).strip()
        if not uid.isdigit():
            raise ValueError(f"user_id 必须是数字 userId（GraphQL 方案）。当前: {user_id!r}")

        guest = self.get_guest_token()
        headers = {
            "authorization": f"Bearer {self.bearer_token}",
            "x-guest-token": guest,
            "user-agent": self.user_agent,
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
        }
        user_tweets_url = f"https://x.com/i/api/graphql/{self.user_tweets_query_id}/UserTweets"
        variables = {
            "userId": uid,
            "count": max_results,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        features = {
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
        }
        params = {"variables": json.dumps(variables), "features": json.dumps(features)}
        try:
            resp = requests.get(
                user_tweets_url,
                headers=headers,
                params=params,
                proxies=self._proxies(),
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            errs.append(f"graphql: {type(e).__name__}: {str(e)[:200]}")
            raise

        rows = _extract_tweets(data, limit=max_results)
        if since_id is not None:
            rows = [r for r in rows if str(r.get("id", "")) > str(since_id)]

        meta: Dict[str, Any] = {"source": "x_graphql_guest", "user_id": uid}
        if not rows:
            meta["diagnostics"] = {
                "user_id": uid,
                "checks": {
                    "strategy": "x_graphql_guest",
                    "user_tweets_query_id": self.user_tweets_query_id,
                    "proxy_set": bool(self.proxy),
                    "errors": errs[-3:],
                },
            }
        return {"data": rows, "meta": meta, "errors": errs or None}

    def fetch_user_posts_with_retry(
        self,
        user_id: str,
        *,
        since_id: Optional[str] = None,
        max_results: int = 10,
        max_retries: int = 8,
    ) -> Dict[str, Any]:
        return _retry_transient_call(
            lambda: self.fetch_user_posts(user_id, since_id=since_id, max_results=max_results),
            max_retries=max_retries,
        )


def _resolve_x_bearer_token(*, explicit: Optional[str], from_config: str) -> str:
    """
    Web GraphQL 使用的 public Bearer，须由配置或环境变量提供；**不在代码库中硬编码**。
    优先：参数 ``explicit`` → ``config.toml`` ``[x] public_bearer_token`` → ``NEWS_AGENT_X_BEARER``。
    """
    bt = (explicit or from_config or os.environ.get("NEWS_AGENT_X_BEARER", "")).strip()
    if not bt:
        raise ValueError(
            "X GraphQL 需要 Bearer：请在 config.toml 的 [x] public_bearer_token 填写，"
            "或设置环境变量 NEWS_AGENT_X_BEARER（勿提交到 Git）。说明见 docs/配置与安全.md"
        )
    return bt


def create_x_client(
    bearer_token: Optional[str] = None,
) -> XClient:
    """创建采集客户端。"""
    cfg: AppConfig = load_config()
    x = cfg.x
    bt = _resolve_x_bearer_token(explicit=bearer_token, from_config=x.public_bearer_token)
    return XClient(
        user_tweets_query_id=x.user_tweets_query_id,
        timeout_sec=float(x.fetch_timeout_sec),
        user_agent=x.fetch_user_agent,
        proxy=x.fetch_proxy,
        bearer_token=bt,
        user_by_screen_name_query_id=x.user_by_screen_name_query_id,
    )


def _extract_tweets(payload: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    # 使用“递归找 entries”的策略，避免绑定具体 JSON 路径。
    def iter_entries(obj: Any):
        if isinstance(obj, dict):
            if "entries" in obj and isinstance(obj["entries"], list):
                for e in obj["entries"]:
                    if isinstance(e, dict):
                        yield e
            for v in obj.values():
                yield from iter_entries(v)
        elif isinstance(obj, list):
            for x in obj:
                yield from iter_entries(x)

    tweets: List[Dict[str, Any]] = []
    for entry in iter_entries(payload):
        content = entry.get("content") or {}
        item = content.get("itemContent") or {}
        tweet_r = (item.get("tweet_results") or {}).get("result") or {}
        legacy = tweet_r.get("legacy") or {}
        if not legacy:
            continue
        tid = str(tweet_r.get("rest_id") or legacy.get("id_str") or "").strip()
        if not tid:
            continue
        text = legacy.get("full_text") or legacy.get("text") or ""
        created_at = legacy.get("created_at")
        # 与 ``normalize_post_to_event`` / ``TweetEvent`` 对齐的扁平字段（完整 legacy 在 Graph 响应中，此处仅保留常用键）
        tweets.append(
            {
                "id": tid,
                "text": str(text).replace("\n", " ").strip(),
                "created_at": created_at,
                "lang": legacy.get("lang"),
                "permalink": f"https://x.com/i/web/status/{tid}",
                "raw_source": "x_graphql_guest",
            }
        )
        if len(tweets) >= limit:
            break
    return tweets
