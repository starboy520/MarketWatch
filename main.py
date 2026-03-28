"""
5 秒轮询多个账号时间线（采集层 -> 标准化事件 -> 去重 -> LangGraph pipeline -> 飞书）。

用法：
  cp config.example.toml config.toml
  pip install -e ".[pipeline]"
  # 按 docs/配置与安全.md 填写 [x] public_bearer_token（或 NEWS_AGENT_X_BEARER）、飞书、[llm]
  python main.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict

from ingestion.checkpoints import PollCheckpointStore
from ingestion.config import AppConfig, load_config
from ingestion.feishu import FeishuClient
from ingestion.models import TweetEvent
from ingestion.timeline import poll_timeline_events
from ingestion.x_api import XClient, create_x_client
from pipeline.graph import build_pipeline_graph_from_app, invoke_for_tweet


@dataclass
class AccountPollRuntime:
    """单账号轮询运行时状态（内存去重 + 断点）。"""

    user_id: str
    since_id: str
    seen_ids: set[str] = field(default_factory=set)


def _bootstrap_accounts(
    client: XClient,
    targets: list[str],
    checkpoint_by_user: Dict[str, Dict[str, object]],
) -> dict[str, AccountPollRuntime]:
    runtime: dict[str, AccountPollRuntime] = {}
    for username in targets:
        uid = client.get_user_id_with_retry(username)
        since_id = str((checkpoint_by_user.get(username) or {}).get("since_id") or "0")
        runtime[username] = AccountPollRuntime(user_id=uid, since_id=since_id)
        print(f"[init] @{username} user_id={uid} since_id={since_id!r}", flush=True)
    return runtime


def _run_pipeline_for_events(
    events: list[TweetEvent],
    username: str,
    graph: Any,
) -> None:
    for ev in events:
        try:
            out = invoke_for_tweet(ev, graph=graph)
            extra = f" err={out.get('error')}" if out.get("error") else ""
            print(
                f"[pipeline] @{username} id={ev.id} status={out.get('status')}{extra}",
                flush=True,
            )
        except Exception as e:
            print(f"[pipeline] @{username} id={ev.id} failed: {e}", flush=True)


def _poll_one_account(
    cfg: AppConfig,
    username: str,
    rt: AccountPollRuntime,
    client: XClient,
    graph: Any,
    ckpt: Dict[str, Dict[str, object]],
    checkpoints: PollCheckpointStore,
) -> None:
    try:
        events, msg, _user_id, since_id = poll_timeline_events(
            client,
            username,
            user_id=rt.user_id,
            since_id=rt.since_id,
            max_results=int(cfg.poll.max_results),
            seen_ids=rt.seen_ids,
        )
    except Exception as e:
        print(f"[poll] @{username} 本轮失败（已跳过，下轮重试）: {e}", flush=True)
        return

    rt.since_id = str(since_id) if since_id is not None else rt.since_id
    print(msg, flush=True)
    _run_pipeline_for_events(events, username, graph)
    if since_id:
        ckpt[username] = {"since_id": str(since_id)}
        checkpoints.save(ckpt)


def main() -> int:
    cfg = load_config()
    targets = cfg.poll.targets
    interval = float(cfg.poll.interval_sec)
    checkpoints = PollCheckpointStore(cfg.poll.checkpoint_file)

    client = create_x_client()
    feishu_client = FeishuClient.from_config(cfg.feishu) if cfg.feishu.enabled else None
    graph = build_pipeline_graph_from_app(cfg, feishu_client=feishu_client)

    ckpt = checkpoints.load()
    account_rt = _bootstrap_accounts(client, targets, ckpt)

    while True:
        for username in targets:
            _poll_one_account(cfg, username, account_rt[username], client, graph, ckpt, checkpoints)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
