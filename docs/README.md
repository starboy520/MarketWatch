# 文档索引

| 文档 | 说明 |
|------|------|
| [本地环境搭建.md](./本地环境搭建.md) | 虚拟环境、依赖安装、一键脚本 `scripts/setup_env.sh` |
| [密钥与配置说明.md](./密钥与配置说明.md) | `config.toml`、环境变量、密钥与 **X Bearer**（无代码内硬编码） |
| [架构与数据流说明.md](./架构与数据流说明.md) | 以 `main.py` 为入口的模块、数据流与 LangGraph 节点 |
| [产品愿景与设计边界.md](./产品愿景与设计边界.md) | 产品背景、分层边界、风险与非目标 |
| [LangGraph编排说明.md](./LangGraph编排说明.md) | 编排层 State、节点与条件边的设计说明 |
| [知识库与龙头映射设计.md](./知识库与龙头映射设计.md) | theme/关键词 → 板块与龙头（静态表、无向量）及 `market_retriever` 对接步骤 |
| [知识库龙头映射-实施开发说明.md](./知识库龙头映射-实施开发说明.md) | 按当前代码拆解的实现任务、配置、测试与验收清单 |

Triage 提示词在 `pipeline/prompts/`；归一化后的 `analysis` 形状见 `pipeline/state.py` 与 `pipeline/deepseek.py`（`_normalize_payload`）。含 `market_impact` 等字段的终态 JSON 示例见 [产品愿景与设计边界.md](./产品愿景与设计边界.md) §5。

**文件名变更（便于检索）**：`setup.md` → `本地环境搭建.md`；`配置与安全.md` → `密钥与配置说明.md`；`项目架构.md` → `架构与数据流说明.md`；`bloomberg_twitter_agent_design.md` → `产品愿景与设计边界.md`；`LangGraph 状态机设计.md` → `LangGraph编排说明.md`；`knowledge_leaders_design.md` → `知识库与龙头映射设计.md`。
