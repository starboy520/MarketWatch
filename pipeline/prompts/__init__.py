"""LLM 系统提示：与代码分离，便于单独审阅与版本管理。"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8").strip()


TRIAGE_SYSTEM_PROMPT = _read("triage_system.txt")
TRANSLATE_SYSTEM_PROMPT = _read("translate_system.txt")
