# MarketWatch

X（Twitter）时间线轮询 → **DeepSeek** 相关性/情绪分析 → 英文正文可选 **中译** → **飞书** IM 推送。编排基于 **LangGraph**。

---

## 快速开始

- **Python 3.10+**
- 依赖：`pip install -r requirements.txt` 与 `pip install -e ".[pipeline]"`
- 配置：`cp config.example.toml config.toml`，按 **[docs/配置与安全.md](docs/配置与安全.md)** 填写密钥与 **X Bearer**（必填其一：`[x] public_bearer_token` 或 `NEWS_AGENT_X_BEARER`）
- 运行：`python main.py`

---

## 文档（均在 `docs/`）

|  |  |
|--|--|
| [docs/README.md](docs/README.md) | 文档索引 |
| [docs/配置与安全.md](docs/配置与安全.md) | 密钥、环境变量、X Bearer |
| [docs/项目架构.md](docs/项目架构.md) | 入口、`ingestion` / `pipeline`、数据流 |
| [docs/bloomberg_twitter_agent_design.md](docs/bloomberg_twitter_agent_design.md) | 产品与设计边界 |
| [docs/LangGraph 状态机设计.md](docs/LangGraph%20状态机设计.md) | 编排层状态机说明 |

Triage 系统提示见 **`pipeline/prompts/triage_system.txt`**；模型 JSON 经 `TweetTriageAnalyzer._normalize_payload` 写入 **`PipelineState.analysis`**（`pipeline/state.py`）。产品级终态 JSON 示例见 [docs/bloomberg_twitter_agent_design.md](docs/bloomberg_twitter_agent_design.md) §5。

---

## 仓库结构（概要）

| 路径 | 说明 |
|------|------|
| `main.py` | 轮询入口：checkpoint、`invoke_for_tweet` |
| `ingestion/` | X 客户端、时间线、`TweetEvent`、飞书、配置 |
| `pipeline/` | LangGraph：相关性 → 翻译 → 卡片 → 发布；`pipeline/prompts/` 为 LLM 系统提示 |
| `tests/` | pytest |

---

## 免责声明

自动分析仅供参考，不构成投资建议。
