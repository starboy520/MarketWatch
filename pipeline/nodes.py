"""StateGraph 节点：DeepSeek LLM、飞书、重试。"""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Optional

from ingestion.config import LlmConfig
from ingestion.feishu import FeishuClient
from ingestion.timeutil import format_created_at_bjt
from pipeline.state import PipelineState

_EMPTY_MARKET_IMPACT: dict[str, Any] = {
    "direction": "neutral",
    "sectors": [],
    "stocks": [],
    "mapping_confidence": "low",
}


def _neutral_sentiment(*, conf: float = 0.0, rationale: str = "") -> dict[str, Any]:
    return {"label": "neutral", "confidence": conf, "rationale_short": rationale}


def _llm_failure_update(exc: Exception) -> dict[str, Any]:
    """LLM 调用异常时返回的 State 片段（与 ``node_relevance_filter`` 错误分支一致）。"""
    return {
        "analysis": {
            "is_relevant": False,
            "china_related": False,
            "themes": [],
            "keywords": [],
            "confidence": 0.0,
            "sentiment": _neutral_sentiment(),
        },
        "market_impact": dict(_EMPTY_MARKET_IMPACT),
        "status": "filtered",
        "error": f"llm: {exc}",
    }


def _analysis_stub_no_llm() -> dict[str, Any]:
    """未配置 LLM 时占位 analysis（一律放行严格门闩）。"""
    return {
        "is_relevant": True,
        "china_related": False,
        "themes": [],
        "keywords": [],
        "confidence": 1.0,
        "sentiment": _neutral_sentiment(conf=0.5, rationale="stub_no_llm"),
    }


# ---- Prefilter（Stage A，可选）----


def node_prefilter(state: PipelineState) -> dict[str, Any]:
    """
    轻量预筛：明显过短、纯 URL 等可在此丢弃。
    复杂业务规则请放在 LLM（Relevance_Filter）。
    """
    text = (state.get("raw_text") or "").strip()
    if len(text) < 8:
        return {"status": "filtered", "error": "prefilter: text too short"}
    return {"status": "prefilter_pass"}


# ---- Relevance_Filter + DeepSeek（Stage B）----


def make_relevance_filter(
    *,
    llm: Optional[LlmConfig] = None,
    confidence_threshold: float = 0.7,
) -> Callable[[PipelineState], dict[str, Any]]:
    """
    **工厂函数**：返回 LangGraph 真正注册的那个「节点函数」。

    为什么这样写
    ------------
    - ``StateGraph.add_node("relevance_filter", fn)`` 需要的 ``fn`` 签名固定为：
      ``(state: PipelineState) -> dict``，**不能再多参数**，所以不能写成
      ``relevance_filter(state, llm, threshold)``。
    - 但我们在**构图时**就要注入 ``llm``、置信度阈值、以及（可选）建好的
      ``TweetTriageAnalyzer``。做法是：外层 ``make_relevance_filter(...)`` 在
      **调用时**读配置并创建 ``analyzer``；内层 ``node_relevance_filter`` 只接收
      ``state``，通过**闭包**读到外层的 ``analyzer`` 和 ``confidence_threshold``。
    - 最后 ``return node_relevance_filter`` 把内层函数交给 ``add_node``，每次图运行
      到该节点时，LangGraph 会调用 ``node_relevance_filter(current_state)``。

    若 ``llm`` 未配置，则内层走占位 ``analysis``，仍返回统一结构（含空 ``market_impact`` 供卡片用）。

    放行规则：仅当 ``is_relevant`` 且 ``confidence`` ≥ ``confidence_threshold``。
    """
    analyzer = None  # 可选 ``TweetTriageAnalyzer``，在 llm 启用时创建
    if llm is not None and llm.enabled:
        from pipeline.deepseek import TweetTriageAnalyzer

        analyzer = TweetTriageAnalyzer(llm)

    def node_relevance_filter(state: PipelineState) -> dict[str, Any]:
        raw = state.get("raw_text") or ""
        author = state.get("author_username") or ""

        if analyzer is not None:
            try:
                tr = analyzer.analyze(
                    raw_text=raw,
                    author_username=author,
                    created_at=format_created_at_bjt(
                        state.get("created_at") if isinstance(state.get("created_at"), str) else None
                    ),
                    source=state.get("source"),
                )
                analysis = tr.analysis
            except Exception as e:
                return _llm_failure_update(e)
        else:
            analysis = _analysis_stub_no_llm()

        market_impact = dict(_EMPTY_MARKET_IMPACT)
        conf = float(analysis.get("confidence") or 0.0)
        ok = bool(analysis.get("is_relevant")) and conf >= confidence_threshold
        if not ok:
            return {
                "analysis": analysis,
                "market_impact": market_impact,
                "status": "filtered",
            }
        return {
            "analysis": analysis,
            "market_impact": market_impact,
            "status": "llm_done",
        }

    return node_relevance_filter


# ---- Market_Retriever（知识库占位；LLM 已写 market_impact 时可只做标注）----


def node_market_retriever(state: PipelineState) -> dict[str, Any]:
    """
    TODO: 用 Leaders_DB / 向量库收窄 stocks，覆盖或修正 LLM 的 market_impact。
    当前：保留 State 中已有 ``market_impact``，补充 ``market_map`` 元数据。
    """
    analysis = state.get("analysis") or {}
    mi = state.get("market_impact") or dict(_EMPTY_MARKET_IMPACT)
    market_map = {
        "candidates": [],
        "from_themes": analysis.get("themes") or [],
        "source": "llm_triage",
    }
    return {
        "market_map": market_map,
        "market_impact": mi,
        "status": "mapped",
    }


# ---- body_translate（英文 → 中文，供飞书展示）----


def should_translate_en_to_zh(raw_text: str, tweet_lang: str | None) -> bool:
    """
    是否应对正文调用大模型英译中。
    - ``lang == en`` 时一定尝试；
    - 无语言码或 ``und`` 等时，用「拉丁字母占比 + 排除明显含大量汉字」启发式。
    """
    raw = raw_text.strip()
    if len(raw) < 8:
        return False
    lang = (tweet_lang or "").strip().lower()
    if lang.startswith("zh") or lang in ("ja", "ko"):
        return False
    if lang == "en":
        return True
    if lang not in ("", "und", "qam", "qst"):
        return False
    cjk = sum(1 for c in raw if "\u4e00" <= c <= "\u9fff")
    n = len(raw)
    if cjk >= 8 or (n > 0 and cjk / n >= 0.08):
        return False
    alpha = sum(1 for c in raw if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    return alpha >= 20 and alpha / max(n, 1) >= 0.35


def make_body_translate_node(*, llm: Optional[LlmConfig] = None) -> Callable[[PipelineState], dict[str, Any]]:
    """在 ``card_renderer`` 之前写入 ``raw_text_zh``（仅当判定为英文且 LLM 可用）。"""

    translator = None
    if llm is not None and llm.enabled:
        from pipeline.deepseek import TweetBodyZhTranslator

        translator = TweetBodyZhTranslator(llm)

    def node_body_translate(state: PipelineState) -> dict[str, Any]:
        raw = state.get("raw_text") or ""
        lang = state.get("tweet_lang")
        if not should_translate_en_to_zh(raw, lang if isinstance(lang, str) else None):
            return {}
        if translator is None:
            return {}
        try:
            zh = translator.translate(raw)
            if zh.strip():
                return {"raw_text_zh": zh.strip()}
        except Exception:
            pass
        return {}

    return node_body_translate


# ---- Card_Renderer ----


def node_card_renderer(state: PipelineState) -> dict[str, Any]:
    """飞书文本：摘要 + 链接 + 情绪与映射（可后续改为交互卡片 JSON）。"""
    aid = state.get("tweet_id", "")
    link = state.get("permalink") or ""
    text = (state.get("raw_text") or "")[:600]
    author = state.get("author_username") or ""
    analysis = state.get("analysis") or {}
    mi = state.get("market_impact") or {}
    sent = analysis.get("sentiment") or {}
    themes = analysis.get("themes") or []
    keywords = analysis.get("keywords") or []
    created_raw = state.get("created_at")
    created = format_created_at_bjt(created_raw if isinstance(created_raw, str) else None) or created_raw
    src = state.get("source") or ""
    zh_block: list[str] = []
    raw_zh = state.get("raw_text_zh")
    if isinstance(raw_zh, str) and raw_zh.strip():
        zh_block = ["", "【中文译文】", raw_zh.strip()[:3500], ""]

    lines = [
        f"🐦 @{author} · 推文 {aid}",
        f"时间：{created or '—'} | 来源：{src or '—'}",
        f"相关度置信度：{analysis.get('confidence', 0):.2f} | 主题：{', '.join(str(t) for t in themes) or '—'}",
        f"关键词：{', '.join(str(k) for k in keywords) or '—'}",
        f"情绪：{sent.get('label', '?')}（{sent.get('confidence', 0):.2f}） {sent.get('rationale_short', '')}",
        f"市场叙事：{mi.get('direction', '?')} | 映射置信：{mi.get('mapping_confidence', '?')}",
        f"板块：{mi.get('sectors', [])}",
        f"标的：{mi.get('stocks', [])}",
        "",
        "【原文摘录】",
        text,
        *zh_block,
        "链接：",
        link,
        "",
        "（自动分析，不构成投资建议。）",
    ]
    return {"feishu_payload": "\n".join(lines), "status": "card_ready"}


# ---- Feishu_Publisher + 重试辅助 ----


def _is_transient_publish_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if any(x in msg for x in ("429", "503", "502", "504", "timeout", "connection")):
        return True
    return False


def make_feishu_publisher(feishu: Optional[FeishuClient], *, dry_run: bool = False):
    """返回闭包节点：注入 FeishuClient；dry_run 时不实际请求。"""

    def node_feishu_publisher(state: PipelineState) -> dict[str, Any]:
        payload = state.get("feishu_payload")
        if payload is None:
            return {
                "status": "error",
                "error": "feishu: missing feishu_payload",
                "publish_status": "failed",
            }
        text = payload if isinstance(payload, str) else str(payload)
        if dry_run or feishu is None:
            return {"status": "published", "publish_status": "ok", "error": None}
        try:
            feishu.send_text(text)
        except Exception as e:
            return {
                "publish_status": "retry" if _is_transient_publish_error(e) else "failed",
                "error": f"feishu: {e}",
            }
        return {"status": "published", "publish_status": "ok", "error": None}

    return node_feishu_publisher


def make_retry_backoff(*, max_retries: int, base_delay_sec: float = 1.0):
    """
    指数退避 + jitter。`retry_count` 每经过一次本节点 +1；
    若已超过 ``max_retries`` 则 ``dead_letter`` 并结束（由图条件边接 END）。
    """

    def node_retry_backoff(state: PipelineState) -> dict[str, Any]:
        n = int(state.get("retry_count") or 0) + 1
        if n > max_retries:
            return {
                "retry_count": n,
                "status": "dead_letter",
                "publish_status": "failed",
                "error": (state.get("error") or "") + " | max feishu retries exceeded",
            }
        delay = min(base_delay_sec * (2 ** (n - 1)), 60.0)
        time.sleep(delay + random.uniform(0, 0.5))
        return {"retry_count": n}

    return node_retry_backoff
