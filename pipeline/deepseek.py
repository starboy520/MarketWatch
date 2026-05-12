"""DeepSeek 推文分析：LangChain 1.x + ``langchain_deepseek``，类封装。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ingestion.config import LlmConfig
from ingestion.timeutil import format_created_at_bjt

from .prompts import TRIAGE_SYSTEM_PROMPT, TRANSLATE_SYSTEM_PROMPT


def _log_llm_io(
    *,
    model: str,
    user_message: str,
    assistant_text: str,
    tag: str = "llm",
) -> None:
    """每次调用打印 user 入参与模型原始输出，便于排查。"""
    print(
        f"[{tag}] model={model}\n"
        f"[{tag}] --- input: user ---\n{user_message}\n"
        f"[{tag}] --- output ---\n{assistant_text if assistant_text.strip() else '(空)'}\n",
        flush=True,
    )


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in content
        ).strip()
    return str(content).strip()


@dataclass(frozen=True)
class TriageResult:
    """与下游 State.analysis 对齐的归一化结果（不含 market_impact）。"""

    analysis: dict[str, Any]


class BaseDeepSeekChatClient(ABC):
    """
    DeepSeek（LangChain ``init_chat_model``）共用逻辑：密钥校验、温度、``BaseChatModel`` 懒加载。

    子类通过实现 ``_create_llm`` 区分 ``model_kwargs``（如 JSON 模式）等差异。
    """

    def __init__(self, cfg: LlmConfig, *, temperature: float = 0.2) -> None:
        if not cfg.enabled:
            raise ValueError("LlmConfig.api_key 为空，无法调用 DeepSeek")
        self._cfg = cfg
        self._temperature = temperature
        self._llm: Optional[BaseChatModel] = None

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = self._create_llm()
        return self._llm

    @abstractmethod
    def _create_llm(self) -> BaseChatModel:
        ...

    def _init_deepseek_model(self, **extra: Any) -> BaseChatModel:
        """统一传入 model / provider / endpoint / 温度 / 超时；``extra`` 多为 ``model_kwargs``。"""
        return init_chat_model(
            self._cfg.model,
            model_provider="deepseek",
            api_key=self._cfg.api_key,
            base_url=self._cfg.base_url.rstrip("/"),
            temperature=self._temperature,
            timeout=self._cfg.timeout_sec,
            **extra,
        )


class TweetTriageAnalyzer(BaseDeepSeekChatClient):
    """
    封装 DeepSeek 调用：配置、模型懒加载、解析与归一化。

    每次 ``analyze`` 会在标准输出打印本轮 **user 输入** 与 **assistant 原始输出**。
    """

    def _create_llm(self) -> BaseChatModel:
        return self._init_deepseek_model(
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return json.loads(text)

    @staticmethod
    def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
        """将模型 JSON 转为 graph/card 使用的 analysis 形状。"""
        inner = data.get("analysis")
        if not isinstance(inner, dict):
            inner = {}

        themes = inner.get("themes")
        if not isinstance(themes, list):
            themes = []

        keywords = inner.get("keywords")
        if not isinstance(keywords, list):
            keywords = []

        sent_raw = inner.get("sentiment")
        if isinstance(sent_raw, dict):
            label = str(sent_raw.get("label") or "neutral").lower()
            sent_conf = float(sent_raw.get("confidence") or 0.0)
            rationale_short = str(sent_raw.get("rationale_short") or sent_raw.get("rationale") or "")
        else:
            label = str(sent_raw or "neutral").lower()
            if label not in ("positive", "negative", "neutral", "mixed"):
                label = "neutral"
            sent_conf = 1.0 if label != "neutral" else 0.5
            rationale_short = str(inner.get("rationale") or "")

        return {
            "is_relevant": bool(data.get("is_relevant", False)),
            "china_related": bool(data.get("china_related", False)),
            "confidence": float(data.get("confidence") or 0.0),
            "themes": [str(t) for t in themes],
            "keywords": [str(k) for k in keywords],
            "sentiment": {
                "label": label,
                "confidence": sent_conf,
                "rationale_short": rationale_short,
            },
        }

    def analyze(
        self,
        *,
        raw_text: str,
        author_username: str,
        created_at: str | None = None,
        source: str | None = None,
    ) -> TriageResult:
        meta_lines: list[str] = []
        if created_at:
            meta_lines.append(f"发布时间：{format_created_at_bjt(created_at) or created_at}")
        if source:
            meta_lines.append(f"事件来源：{source}")
        meta_block = ("\n" + "\n".join(meta_lines) + "\n") if meta_lines else "\n"
        user_msg = (
            f"作者 @{author_username}{meta_block}"
            f"推文正文：\n{raw_text[:8000]}"
        )
        resp = self.llm.invoke(
            [
                SystemMessage(content=TRIAGE_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ]
        )
        raw = _message_text(getattr(resp, "content", None))
        _log_llm_io(
            model=self._cfg.model,
            user_message=user_msg,
            assistant_text=raw,
        )
        data = self._parse_json_object(raw)
        if not isinstance(data, dict):
            raise ValueError(f"期望 JSON 对象，得到: {type(data)}")
        return TriageResult(analysis=self._normalize_payload(data))


class TweetBodyZhTranslator(BaseDeepSeekChatClient):
    """英译中（纯文本）：不使用 ``json_object`` 响应格式。"""

    def _create_llm(self) -> BaseChatModel:
        return self._init_deepseek_model()

    def translate(self, raw_text: str) -> str:
        text = raw_text.strip()
        if not text:
            return ""
        user_msg = f"请翻译以下全文：\n\n{text[:6000]}"
        resp = self.llm.invoke(
            [
                SystemMessage(content=TRANSLATE_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ]
        )
        out = _message_text(getattr(resp, "content", None))
        _log_llm_io(
            model=self._cfg.model,
            user_message=user_msg,
            assistant_text=out,
            tag="llm-translate",
        )
        return out


def triage_tweet(
    cfg: LlmConfig,
    *,
    raw_text: str,
    author_username: str,
    created_at: str | None = None,
    source: str | None = None,
    temperature: float = 0.2,
) -> TriageResult:
    """便捷函数：单次分析（内部新建 ``TweetTriageAnalyzer``）。"""
    return TweetTriageAnalyzer(cfg, temperature=temperature).analyze(
        raw_text=raw_text,
        author_username=author_username,
        created_at=created_at,
        source=source,
    )
