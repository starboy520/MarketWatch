"""setuptools 安装配置。"""

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="news-agent",
    version="0.1.0",
    description="MarketWatch: X timeline + LangGraph + DeepSeek + Feishu (see docs/)",
    long_description=README,
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    packages=find_packages(
        where=".",
        include=["ingestion*", "pipeline*"],
    ),
    package_data={
        "pipeline.prompts": ["triage_system.txt", "translate_system.txt"],
    },
    install_requires=["requests>=2.28"],
    extras_require={
        "dev": ["pytest", "setuptools>=61"],
        # LangChain / LangGraph 1.x（LTS）；上限 <2 避免未来大版本静默破坏
        "pipeline": [
            "langgraph>=1.0.0,<2",
            "langchain>=1.0.0,<2",
            "langchain-core>=1.0.0,<2",
            "langchain-openai>=1.0.0,<2",
            "langchain-deepseek>=1.0.0,<2",
        ],
    },
)
