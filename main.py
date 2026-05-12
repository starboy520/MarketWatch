"""
轮询多数据源（X 时间线、财联社电报等）→ 标准化 ``TweetEvent`` → 去重 → LangGraph → 飞书。

用法：
  cp config.example.toml config.toml
  pip install -e ".[pipeline]"
  # 按 docs/密钥与配置说明.md 填写 [x]、飞书、[llm]；财联社见 [sources.cls_telegraph]
  python main.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, MutableMapping

from ingestion.checkpoints import JsonDict, PollCheckpointStore
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
    x_checkpoint: MutableMapping[str, Dict[str, str]],
) -> dict[str, AccountPollRuntime]:
    runtime: dict[str, AccountPollRuntime] = {}
    for username in targets:
        uid = client.get_user_id_with_retry(username)
        since_id = str((x_checkpoint.get(username) or {}).get("since_id") or "0")
        runtime[username] = AccountPollRuntime(user_id=uid, since_id=since_id)
        print(f"[init] @{username} user_id={uid} since_id={since_id!r}", flush=True)
    return runtime


def _run_pipeline_for_events(
    events: list[TweetEvent],
    label: str,
    graph: Any,
) -> None:
    for ev in events:
        try:
            out = invoke_for_tweet(ev, graph=graph)
            extra = f" err={out.get('error')}" if out.get("error") else ""
            print(
                f"[pipeline] {label} id={ev.id} source={ev.source} status={out.get('status')}{extra}",
                flush=True,
            )
        except Exception as e:
            print(f"[pipeline] {label} id={ev.id} failed: {e}", flush=True)


def _poll_one_account(
    cfg: AppConfig,
    username: str,
    rt: AccountPollRuntime,
    client: XClient,
    graph: Any,
    x_checkpoint: MutableMapping[str, Dict[str, str]],
    checkpoints: PollCheckpointStore,
    ckpt_full: JsonDict,
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
    _run_pipeline_for_events(events, f"@{username}", graph)
    if since_id:
        x_checkpoint[username] = {"since_id": str(since_id)}
        checkpoints.save(ckpt_full)


def _normalize_cls_ckpt_slot(ckpt_full: JsonDict) -> Dict[str, str]:
    """返回 ``ckpt_full[\"cls_telegraph\"]`` 本体（str→str），供 ``ClsTelegraphPoller.poll`` 原地更新。"""
    slot = ckpt_full.setdefault("cls_telegraph", {})
    if not isinstance(slot, dict):
        slot = {}
        ckpt_full["cls_telegraph"] = slot
    normalized = {str(k): str(v) if v is not None else "" for k, v in slot.items()}
    slot.clear()
    slot.update(normalized)
    return slot


def main() -> int:
    cfg = load_config()
    targets = cfg.poll.targets
    interval = float(cfg.poll.interval_sec)
    checkpoints = PollCheckpointStore(cfg.poll.checkpoint_file)

    ckpt_full = checkpoints.load()
    x_ckpt = ckpt_full["x"]
    if not isinstance(x_ckpt, dict):
        x_ckpt = {}
        ckpt_full["x"] = x_ckpt

    client = create_x_client()
    feishu_client = FeishuClient.from_config(cfg.feishu) if cfg.feishu.enabled else None
    graph = build_pipeline_graph_from_app(cfg, feishu_client=feishu_client)

    account_rt = _bootstrap_accounts(client, targets, x_ckpt)

    cls_poller = None
    if cfg.sources.cls_telegraph.enabled:
        from ingestion.sources.cls_telegraph import ClsTelegraphPoller

        cls_poller = ClsTelegraphPoller(
            cfg.sources.cls_telegraph,
            proxy=cfg.x.fetch_proxy,
        )
        print("[init] 财联社电报采集已启用（checkpoint 键 cls_telegraph）", flush=True)

    while True:
        for username in targets:
            _poll_one_account(
                cfg,
                username,
                account_rt[username],
                client,
                graph,
                x_ckpt,
                checkpoints,
                ckpt_full,
            )
        if cls_poller is not None:
            cls_slot = _normalize_cls_ckpt_slot(ckpt_full)
            try:
                events, msg = cls_poller.poll(cls_slot)
                print(msg, flush=True)
                checkpoints.save(ckpt_full)
                _run_pipeline_for_events(events, "cls", graph)
            except Exception as e:
                print(f"[poll] cls 本轮失败（已跳过，下轮重试）: {e}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
