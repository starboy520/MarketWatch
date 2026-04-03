# 文档索引

| 文档 | 说明 |
|------|------|
| [setup.md](./setup.md) | 虚拟环境、依赖安装、一键脚本 `scripts/setup_env.sh` |
| [配置与安全.md](./配置与安全.md) | `config.toml`、环境变量、密钥与 **X Bearer**（无代码内硬编码） |
| [项目架构.md](./项目架构.md) | 以 `main.py` 为入口的模块、数据流与 LangGraph 节点 |
| [bloomberg_twitter_agent_design.md](./bloomberg_twitter_agent_design.md) | 产品背景、分层边界、风险与非目标 |
| [LangGraph 状态机设计.md](./LangGraph%20状态机设计.md) | 编排层 State、节点与条件边的设计说明 |

Triage 提示词在 `pipeline/prompts/`；归一化后的 `analysis` 形状见 `pipeline/state.py` 与 `pipeline/deepseek.py`（`_normalize_payload`）。设计文档 §5 为含 `market_impact` 等字段的终态示例。
