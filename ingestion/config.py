from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class XConfig:
    public_bearer_token: str
    fetch_proxy: Optional[str]
    fetch_timeout_sec: float
    fetch_user_agent: str
    user_tweets_query_id: str
    user_by_screen_name_query_id: str


@dataclass(frozen=True)
class PollConfig:
    targets: List[str]
    interval_sec: float
    max_results: int
    checkpoint_file: str


@dataclass(frozen=True)
class FeishuConfig:
    """飞书应用发 IM：app_id、app_secret、receive_id（见开放平台文档）。"""

    app_id: str
    app_secret: str
    receive_id: str
    receive_id_type: str
    openapi_base: str
    timeout_sec: float

    @property
    def enabled(self) -> bool:
        return bool(self.app_id and self.app_secret and self.receive_id)


@dataclass(frozen=True)
class LlmConfig:
    """DeepSeek（OpenAI 兼容 API）。密钥优先环境变量 DEEPSEEK_API_KEY。"""

    api_key: str
    base_url: str
    model: str
    timeout_sec: float

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip())


@dataclass(frozen=True)
class AppConfig:
    x: XConfig
    poll: PollConfig
    feishu: FeishuConfig
    llm: LlmConfig


def load_config(path: Optional[str] = None) -> AppConfig:
    """
    从 TOML 配置文件加载配置。

    默认路径：
    - 显式传入 path
    - 或环境变量 NEWS_AGENT_CONFIG
    - 或项目根目录 ./config.toml
    """
    cfg_path = Path(path or os.environ.get("NEWS_AGENT_CONFIG", "config.toml")).expanduser()
    if not cfg_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {str(cfg_path)!r}")

    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    x = data.get("x") or {}
    poll = data.get("poll") or {}
    fs = data.get("feishu") or {}
    llm = data.get("llm") or {}

    xcfg = XConfig(
        public_bearer_token=str(x.get("public_bearer_token") or "").strip(),
        fetch_proxy=(str(x.get("fetch_proxy") or "").strip() or None),
        fetch_timeout_sec=float(x.get("fetch_timeout_sec") or 20),
        fetch_user_agent=str(
            x.get("fetch_user_agent")
            or "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ).strip(),
        user_tweets_query_id=str(x.get("user_tweets_query_id") or "FOlovQsiHGDls3c0Q_HaSQ").strip(),
        user_by_screen_name_query_id=str(
            x.get("user_by_screen_name_query_id") or "s9p9_q_27z5NnUnU0x7V_Q"
        ).strip(),
    )

    pcfg = PollConfig(
        targets=[
            str(x).lstrip("@").strip()
            for x in (poll.get("targets") or [poll.get("target_username") or "business"])
            if str(x).strip()
        ],
        interval_sec=float(poll.get("interval_sec") or 5),
        max_results=int(poll.get("max_results") or 20),
        checkpoint_file=str(poll.get("checkpoint_file") or "checkpoints.json").strip(),
    )

    fcfg = FeishuConfig(
        app_id=str(os.environ.get("FEISHU_APP_ID") or fs.get("app_id") or "").strip(),
        app_secret=str(os.environ.get("FEISHU_APP_SECRET") or fs.get("app_secret") or "").strip(),
        receive_id=str(os.environ.get("FEISHU_RECEIVE_ID") or fs.get("receive_id") or "").strip(),
        receive_id_type=str(
            os.environ.get("FEISHU_RECEIVE_ID_TYPE") or fs.get("receive_id_type") or "chat_id"
        )
        .strip()
        .lower()
        or "chat_id",
        openapi_base=(
            (str(fs.get("openapi_base") or "https://open.feishu.cn").strip().rstrip("/"))
            or "https://open.feishu.cn"
        ),
        timeout_sec=float(fs.get("timeout_sec") or 15),
    )

    lcfg = LlmConfig(
        api_key=str(os.environ.get("DEEPSEEK_API_KEY") or llm.get("api_key") or "").strip(),
        base_url=str(llm.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
        or "https://api.deepseek.com",
        model=str(llm.get("model") or "deepseek-chat").strip() or "deepseek-chat",
        timeout_sec=float(llm.get("timeout_sec") or 120),
    )

    return AppConfig(x=xcfg, poll=pcfg, feishu=fcfg, llm=lcfg)

