"""
财联社电报：nodeapi telegraphList / refreshTelegraphList / updateTelegraphList。

逻辑与根目录 ``cls_telegraph_crawler.py`` 一致，改为产出 ``TweetEvent`` 并写入 checkpoint，
供 ``main.py`` 与 X 时间线并行轮询。HTTP 使用 ``requests``，可走 ``[x].fetch_proxy``。
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

import requests

from ingestion.config import ClsTelegraphConfig
from ingestion.models import SOURCE_CLS_TELEGRAPH, TweetEvent

CLS_DETAIL_URL = "https://www.cls.cn/detail/{id}"


def _wall_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _format_time(ctime: object) -> str:
    """ctime 为 Unix 秒；统一按 UTC 瞬时再转到北京时间，与运行机器时区无关。"""
    if ctime is None:
        return ""
    try:
        ts = int(ctime)
        utc = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))
        return utc.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return str(ctime)


def _js_string(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return str(v)


def cls_sign(params: Dict[str, Any]) -> str:
    body = "&".join(f"{k}={_js_string(params[k])}" for k in sorted(params.keys()))
    sha1_hex = hashlib.sha1(body.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1_hex.encode("ascii")).hexdigest()


def _seen_ids_list(ckpt: Dict[str, str]) -> List[str]:
    raw = (ckpt.get("seen_ids") or "").strip()
    return [x for x in raw.split(",") if x]


def _seen_set(ckpt: Dict[str, str]) -> Set[str]:
    return set(_seen_ids_list(ckpt))


def _add_seen_id(ckpt: Dict[str, str], item_id: str, max_n: int) -> None:
    lst = [x for x in _seen_ids_list(ckpt) if x != item_id]
    lst.append(item_id)
    if len(lst) > max_n:
        lst = lst[-max_n:]
    ckpt["seen_ids"] = ",".join(lst)


def _row_to_event(row: Dict[str, Any]) -> Optional[TweetEvent]:
    iid = row.get("id")
    if iid is None:
        return None
    title = (row.get("title") or "").strip()
    brief = (row.get("brief") or "").strip()
    if not title and not brief:
        return None
    if title and brief:
        text = f"{title}\n{brief}"
    else:
        text = title or brief
    ctime = row.get("ctime")
    created = _format_time(ctime)
    sid = str(iid)
    permalink = CLS_DETAIL_URL.format(id=sid)
    payload = {
        "id": sid,
        "title": title,
        "brief": brief,
        "ctime": ctime,
        "time": created,
        "permalink": permalink,
        "received_at": _wall_now(),
        "received_ts": int(time.time()),
    }
    return TweetEvent(
        id=sid,
        text=text,
        author_username="cls",
        permalink=permalink,
        created_at=created or None,
        raw_json=json.dumps(payload, ensure_ascii=False),
        source=SOURCE_CLS_TELEGRAPH,
        lang="zh",
    )


class ClsTelegraphPoller:
    """一轮轮询可能产出 0~N 条 ``TweetEvent``；checkpoint 切片由调用方持久化。"""

    def __init__(self, cfg: ClsTelegraphConfig, *, proxy: Optional[str] = None) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers["User-Agent"] = cfg.user_agent
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(params)
        p.setdefault("app", self._cfg.app)
        p.setdefault("os", self._cfg.os_name)
        p.setdefault("sv", self._cfg.sv)
        p["sign"] = cls_sign(p)
        url = f"{self._cfg.base_url}{path}?{urlencode(p)}"
        resp = self._session.get(url, timeout=self._cfg.timeout_sec)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError(f"CLS 期望 JSON 对象: {data!r}")
        return data

    def _consider_emit(
        self,
        item_id: object,
        item: Dict[str, Any],
        seen: Set[str],
        ckpt: Dict[str, str],
        out: List[TweetEvent],
    ) -> None:
        sid = str(item_id).strip()
        if not sid or sid in seen:
            return
        row = dict(item)
        row["id"] = item_id
        ev = _row_to_event(row)
        if ev is None:
            return
        seen.add(sid)
        _add_seen_id(ckpt, sid, self._cfg.max_seen_ids)
        out.append(ev)

    def _bump_cursor_from_roll(self, roll: List[Dict[str, Any]], ckpt: Dict[str, str]) -> None:
        ts = [int(r["ctime"]) for r in roll if r.get("ctime") is not None]
        if not ts:
            return
        mx = max(ts)
        cur = ckpt.get("refresh_last_time")
        cur_i = int(cur) if cur and str(cur).isdigit() else None
        if cur_i is None:
            ckpt["refresh_last_time"] = str(mx)
        else:
            ckpt["refresh_last_time"] = str(max(cur_i, mx))

    def _ingest_roll_data(
        self,
        roll: List[Dict[str, Any]],
        seen: Set[str],
        ckpt: Dict[str, str],
        out: List[TweetEvent],
    ) -> None:
        for row in roll:
            iid = row.get("id")
            if iid is not None:
                self._consider_emit(iid, row, seen, ckpt, out)
        self._bump_cursor_from_roll(roll, ckpt)

    def _fetch_telegraph_list(self, last_time: int, rn: int = 20) -> Dict[str, Any]:
        return self._get(
            "/nodeapi/telegraphList",
            {
                "refresh_type": 1,
                "rn": rn,
                "lastTime": last_time,
                "last_time": last_time,
            },
        )

    def _fetch_refresh(self, last_time: Optional[int]) -> Dict[str, Any]:
        return self._get(
            "/nodeapi/refreshTelegraphList",
            {"lastTime": last_time if last_time is not None else int(time.time())},
        )

    def _fetch_update_telegraph_list(self, last_time: int, rn: int = 20) -> Dict[str, Any]:
        return self._get(
            "/nodeapi/updateTelegraphList",
            {
                "rn": rn,
                "lastTime": last_time,
                "subscribedColumnIds": "",
                "hasFirstVipArticle": "0",
            },
        )

    def poll(
        self,
        ckpt_slice: Dict[str, str],
        *,
        log_lines: Optional[List[str]] = None,
    ) -> tuple[List[TweetEvent], str]:
        """
        ``ckpt_slice`` 读写键：``bootstrapped`` ``0|1``，``refresh_last_time``，``seen_ids``。
        """
        ckpt: Dict[str, str] = dict(ckpt_slice)
        seen = _seen_set(ckpt)
        events: List[TweetEvent] = []
        logs: List[str] = log_lines if log_lines is not None else []

        def log(msg: str) -> None:
            logs.append(f"[{_wall_now()}] [cls] {msg}")

        boot = ckpt.get("bootstrapped") == "1"
        if not boot:
            now = int(time.time())
            log(f"telegraphList 首屏 lastTime={now}")
            data = self._fetch_telegraph_list(now)
            err = data.get("errno", data.get("error"))
            if err not in (0, None, "0"):
                msg = f"telegraphList 失败 errno={err} {data!r}"
                log(msg)
                ckpt_slice.clear()
                ckpt_slice.update(ckpt)
                return [], "\n".join(logs) + f"\n{msg}"
            roll = (data.get("data") or {}).get("roll_data") or []
            for row in roll:
                iid = row.get("id")
                if iid is not None:
                    self._consider_emit(iid, row, seen, ckpt, events)
            article_ctimes = [int(r["ctime"]) for r in roll if r.get("ctime") is not None]
            if article_ctimes:
                ckpt["refresh_last_time"] = str(max(article_ctimes))
            else:
                ckpt["refresh_last_time"] = str(now)
            ckpt["bootstrapped"] = "1"
            log(
                f"首屏 roll={len(roll)} 新发事件={len(events)} refresh游标={ckpt['refresh_last_time']}"
            )
            ckpt_slice.clear()
            ckpt_slice.update(ckpt)
            return events, "\n".join(logs)

        cur_raw = ckpt.get("refresh_last_time")
        cur = int(cur_raw) if cur_raw and str(cur_raw).isdigit() else int(time.time())
        log(f"refreshTelegraphList lastTime={cur}")
        data = self._fetch_refresh(cur)
        lmap = data.get("l") or {}
        if not isinstance(lmap, dict):
            lmap = {}
        max_ctime = cur
        for iid_s, item in lmap.items():
            if not isinstance(item, dict):
                continue
            try:
                iid = int(iid_s)
            except (TypeError, ValueError):
                continue
            self._consider_emit(iid, item, seen, ckpt, events)
            ct = item.get("ctime")
            if ct is not None:
                max_ctime = max(max_ctime, int(ct))
        a_val = data.get("a")
        if a_val is not None:
            try:
                max_ctime = max(max_ctime, int(a_val))
            except (TypeError, ValueError):
                pass
        ckpt["refresh_last_time"] = str(max_ctime)
        log(
            f"refresh l条目={len(lmap)} 新发事件={len(events)} 下次lastTime={ckpt['refresh_last_time']}"
        )

        now2 = int(time.time())
        log(f"telegraphList(顶栏) lastTime={now2}")
        t0 = self._fetch_telegraph_list(now2)
        err0 = t0.get("errno", t0.get("error"))
        if err0 in (0, None, "0"):
            roll0 = (t0.get("data") or {}).get("roll_data") or []
            self._ingest_roll_data(roll0, seen, ckpt, events)
            log(f"顶栏 roll={len(roll0)}")
        else:
            log(f"顶栏失败 errno={err0}")

        cur_u = int(ckpt["refresh_last_time"]) if ckpt.get("refresh_last_time") else now2
        log(f"updateTelegraphList lastTime={cur_u}")
        udata = self._fetch_update_telegraph_list(cur_u)
        if udata.get("error") in (0, None, "0"):
            d = udata.get("data") or {}
            un = d.get("update_num") or 0
            roll_u = d.get("roll_data") or []
            if un > 0 and roll_u:
                self._ingest_roll_data(roll_u, seen, ckpt, events)
            log(f"update update_num={un} roll={len(roll_u)}")
        else:
            log(f"update 失败 error={udata.get('error')}")

        ckpt_slice.clear()
        ckpt_slice.update(ckpt)
        return events, "\n".join(logs)


def run_cli() -> None:
    """独立 CLI（与旧 ``cls_telegraph_crawler.py`` 行为类似：JSON 行输出到 stdout）。"""
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="财联社电报：JSON 行输出（调试）")
    ap.add_argument("-i", "--interval", type=float, default=20.0)
    ap.add_argument("-n", "--iterations", type=int, default=None)
    args = ap.parse_args()

    cfg = ClsTelegraphConfig(
        enabled=True,
        base_url="https://www.cls.cn",
        timeout_sec=20.0,
        user_agent="Mozilla/5.0 (compatible; TelegraphPoll/1.0)",
        app="CailianpressWeb",
        os_name="web",
        sv="8.4.6",
        max_seen_ids=5000,
    )
    poller = ClsTelegraphPoller(cfg)
    ckpt: Dict[str, str] = {}
    try:
        while True:
            events, _ = poller.poll(ckpt)
            for ev in events:
                print(
                    json.dumps(
                        {
                            "id": ev.id,
                            "title": ev.text.split("\n", 1)[0],
                            "brief": ev.text.split("\n", 1)[1] if "\n" in ev.text else "",
                            "permalink": ev.permalink,
                            "created_at": ev.created_at,
                        },
                        ensure_ascii=False,
                    )
                )
                sys.stdout.flush()
            if args.iterations is not None:
                args.iterations -= 1
                if args.iterations < 0:
                    break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
