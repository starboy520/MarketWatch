# MarketWatch

X（Twitter）时间线（可选 **财联社电报**，`[sources.cls_telegraph]`）→ **DeepSeek** 相关性/情绪分析 → 英文正文可选 **中译** → **飞书** IM 推送。编排基于 **LangGraph**。

---

## 快速开始

- **Python 3.10+**
- 环境：一键脚本与步骤见 **[docs/本地环境搭建.md](docs/本地环境搭建.md)**（`./scripts/setup_env.sh`）
- 依赖：亦可手动 `pip install -r requirements.txt`（已含 `-e ".[pipeline]"` 与 LangGraph / LangChain 栈）
- 配置：`cp config.example.toml config.toml`，按 **[docs/密钥与配置说明.md](docs/密钥与配置说明.md)** 填写密钥与 **X Bearer**（必填其一：`[x] public_bearer_token` 或 `NEWS_AGENT_X_BEARER`）；财联社见 `config.example.toml` 中 `[sources.cls_telegraph]`
- 运行：`python main.py`

---

## 文档（均在 `docs/`）

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | 文档索引 |
| [docs/密钥与配置说明.md](docs/密钥与配置说明.md) | 密钥、环境变量、X Bearer |
| [docs/架构与数据流说明.md](docs/架构与数据流说明.md) | 入口、`ingestion` / `pipeline`、数据流 |
| [docs/产品愿景与设计边界.md](docs/产品愿景与设计边界.md) | 产品与设计边界 |
| [docs/LangGraph编排说明.md](docs/LangGraph编排说明.md) | LangGraph 编排层说明 |
| [docs/知识库与龙头映射设计.md](docs/知识库与龙头映射设计.md) | 龙头/板块静态映射与 `market_retriever` 对接 |
| [docs/知识库龙头映射-实施开发说明.md](docs/知识库龙头映射-实施开发说明.md) | 该功能的开发任务、配置与测试清单 |

Triage 系统提示见 **`pipeline/prompts/triage_system.txt`**；模型 JSON 经 `TweetTriageAnalyzer._normalize_payload` 写入 **`PipelineState.analysis`**（`pipeline/state.py`）。产品级终态 JSON 示例见 [docs/产品愿景与设计边界.md](docs/产品愿景与设计边界.md) §5。

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
