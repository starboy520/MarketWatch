"""
LangGraph StateGraph：采集 TweetEvent → DeepSeek 分析 → 飞书。
（当前跳过 ``market_retriever``：relevance_filter → body_translate → card_renderer → feishu_publisher。）

relevance_filter 放行：仅当 ``is_relevant`` 且 ``confidence`` ≥ 阈值。

依赖：pip install -e ".[pipeline]"（LangGraph / LangChain 1.x）
密钥：环境变量 DEEPSEEK_API_KEY 或 config.toml [llm] api_key
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ingestion.config import AppConfig, LlmConfig
from ingestion.feishu import FeishuClient
from ingestion.models import TweetEvent
from pipeline import nodes
from pipeline.state import PipelineState


@dataclass
class PipelineCompileConfig:
    """构图参数。"""

    enable_prefilter: bool = False
    relevance_confidence_threshold: float = 0.7
    max_feishu_retries: int = 4
    feishu_client: Optional[FeishuClient] = None
    feishu_dry_run: bool = True
    use_memory_checkpointer: bool = True
    llm: Optional[LlmConfig] = None

    @classmethod
    def from_app(cls, app: AppConfig, *, feishu_client: Optional[FeishuClient]) -> PipelineCompileConfig:
        """由 ``load_config()`` 结果推导编译选项（飞书未启用则 dry_run + 无 client）。"""
        return replace(
            cls(),
            feishu_client=feishu_client,
            feishu_dry_run=feishu_client is None,
            llm=app.llm if app.llm.enabled else None,
        )


def tweet_event_to_state(ev: TweetEvent) -> PipelineState:
    """从采集层 ``TweetEvent`` 填入初始 State（字段与之一一对应，见 ``pipeline.state`` 文档）。"""
    return ev.pipeline_initial_state()


class _EdgeRouter:
    """条件边：与各节点写入的 ``status`` / ``publish_status`` 约定对齐。"""

    @staticmethod
    def after_prefilter(state: PipelineState) -> Literal["filtered", "continue"]:
        if state.get("status") == "filtered":
            return "filtered"
        return "continue"

    @staticmethod
    def after_relevance(state: PipelineState) -> Literal["filtered", "continue"]:
        """与 ``nodes.make_relevance_filter`` 一致：仅 ``status == filtered`` 时中断。"""
        if state.get("status") == "filtered":
            return "filtered"
        return "continue"

    @staticmethod
    def after_feishu(state: PipelineState) -> Literal["done", "retry", "dead"]:
        st = state.get("publish_status") or "ok"
        if st == "ok":
            return "done"
        if st == "retry":
            return "retry"
        return "dead"

    @staticmethod
    def after_retry_backoff(state: PipelineState) -> Literal["dead", "again"]:
        if state.get("status") == "dead_letter":
            return "dead"
        return "again"


class TweetPipelineCompiler:
    """
    将 ``PipelineCompileConfig`` 编译为可 ``invoke`` 的 LangGraph 应用。

    节点注册与边连接拆成私有方法，避免 ``build_*`` 单函数过长、职责混杂。
    """

    __slots__ = ("_cfg",)

    def __init__(self, cfg: PipelineCompileConfig) -> None:
        self._cfg = cfg

    def compile(self) -> Any:
        g = StateGraph(PipelineState)
        self._register_nodes(g)
        self._wire_entry_and_relevance(g)
        self._wire_publish_and_retry(g)
        checkpointer = MemorySaver() if self._cfg.use_memory_checkpointer else None
        return g.compile(checkpointer=checkpointer)

    def _register_nodes(self, g: StateGraph) -> None:
        cfg = self._cfg
        g.add_node("prefilter", nodes.node_prefilter)
        g.add_node(
            "relevance_filter",
            nodes.make_relevance_filter(
                llm=cfg.llm,
                confidence_threshold=cfg.relevance_confidence_threshold,
            ),
        )
        g.add_node("body_translate", nodes.make_body_translate_node(llm=cfg.llm))
        g.add_node("card_renderer", nodes.node_card_renderer)
        g.add_node(
            "feishu_publisher",
            nodes.make_feishu_publisher(cfg.feishu_client, dry_run=cfg.feishu_dry_run),
        )
        g.add_node("retry_backoff", nodes.make_retry_backoff(max_retries=cfg.max_feishu_retries))

    def _wire_entry_and_relevance(self, g: StateGraph) -> None:
        r = _EdgeRouter
        if self._cfg.enable_prefilter:
            g.add_edge(START, "prefilter")
            g.add_conditional_edges(
                "prefilter",
                r.after_prefilter,
                {"filtered": END, "continue": "relevance_filter"},
            )
        else:
            g.add_edge(START, "relevance_filter")

        g.add_conditional_edges(
            "relevance_filter",
            r.after_relevance,
            {"filtered": END, "continue": "body_translate"},
        )
        # 预留：relevance_filter → market_retriever → body_translate → card_renderer
        g.add_edge("body_translate", "card_renderer")
        g.add_edge("card_renderer", "feishu_publisher")

    def _wire_publish_and_retry(self, g: StateGraph) -> None:
        r = _EdgeRouter
        g.add_conditional_edges(
            "feishu_publisher",
            r.after_feishu,
            {"done": END, "retry": "retry_backoff", "dead": END},
        )
        g.add_conditional_edges(
            "retry_backoff",
            r.after_retry_backoff,
            {"dead": END, "again": "feishu_publisher"},
        )


def build_pipeline_graph_from_app(cfg: AppConfig, *, feishu_client: Optional[FeishuClient]) -> Any:
    """用 ``load_config()`` 结果一键构图。"""
    return TweetPipelineCompiler(PipelineCompileConfig.from_app(cfg, feishu_client=feishu_client)).compile()


def build_pipeline_graph(cfg: Optional[PipelineCompileConfig] = None) -> Any:
    """编译 StateGraph；默认 MemorySaver。"""
    return TweetPipelineCompiler(cfg or PipelineCompileConfig()).compile()


def invoke_for_tweet(
    ev: TweetEvent,
    *,
    graph: Any = None,
    cfg: Optional[PipelineCompileConfig] = None,
) -> PipelineState:
    """单条 TweetEvent 跑完全图。"""
    app = graph if graph is not None else build_pipeline_graph(cfg)
    result: PipelineState = app.invoke(
        tweet_event_to_state(ev),
        config={"configurable": {"thread_id": f"{ev.source}:{ev.id}"}},
    )
    return result
