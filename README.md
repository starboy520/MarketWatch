# news-agent

从 **X（Twitter）** Web GraphQL 拉取时间线、标准化为 **`TweetEvent`**，经 **LangGraph**（DeepSeek 分析 → 飞书 IM）。产品目标与模块边界见仓库内 [bloomberg_twitter_agent_design.md](bloomberg_twitter_agent_design.md)。  
LLM 分析侧的预期 JSON 结构见 [llm_schema.py](llm_schema.py)。

---

## 环境要求

- **Python 3.10+**（与 `setup.py` 中 `python_requires` 一致）
- 可访问 **PyPI**（安装依赖）
- X 采集使用 **Web GraphQL（guest token + public bearer）**，可能受风控/网络影响；必要时在 `config.toml` 的 `[x]` 中配置 `fetch_proxy`。

---

## 在新机器上从零部署

### 1. 获取代码

将本仓库复制到目标目录（示例：`/opt/news_agent`）。若使用 Git：

```bash
git clone <你的仓库地址> news_agent
cd news_agent
```

### 2. 创建并启用虚拟环境

建议使用独立 venv，避免污染系统 Python（Linux/macOS）：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖与项目本身

升级 pip 后按 `requirements.txt` 安装（会执行可编辑安装 `-e .`，并安装 `setup.py` 里声明的依赖）：

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Pipeline（LangGraph / DeepSeek）需额外：

```bash
pip install -e ".[pipeline]"
```

仅开发联调（含 `pytest`）时：

```bash
pip install -r requirements-dev.txt
```

等价写法：

```bash
pip install -e ".[dev]"
```

### 4. 环境变量与配置

当前推荐使用 `config.toml`（见根目录 `config.example.toml`）。

也支持用环境变量 `NEWS_AGENT_CONFIG` 指定配置文件路径（默认读取 `./config.toml`）。

**不要在仓库或日志中提交明文 Token。** 生产环境建议用密钥管理服务或部署平台提供的 Secret 注入上述变量。

飞书：`FeishuClient.from_config(load_config().feishu)`，`[feishu]` 里填 **`app_id` + `app_secret` + `receive_id`**（应用 IM，见 [飞书调用流程](https://open.feishu.cn/document/server-docs/api-call-guide/calling-process/get-)）。另可选 `receive_id_type`、`openapi_base`、`timeout_sec`。环境变量可覆盖：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_RECEIVE_ID`、`FEISHU_RECEIVE_ID_TYPE`。

DeepSeek：环境变量 **`DEEPSEEK_API_KEY`** 或 `config.toml` 中 `[llm] api_key`。

### 5. 验证安装

```bash
python -c "import ingestion; print('ingestion OK')"
```

可验证 X 采集客户端能否创建（仍可能因网络或风控报错，属预期）：

```bash
python -c "from ingestion import create_x_client; create_x_client(); print('X client OK')"
```

配置好 `[feishu]` 后，可用 **pytest** 或交互方式试发（勿在生产环境随意执行）：

```bash
python -m pytest tests/test_feishu.py -q
```

```bash
python -c "from ingestion.config import load_config; from ingestion.feishu import FeishuClient; c=FeishuClient.from_config(load_config().feishu); c.send_text('news-agent 连通性测试')"
```

常驻进程：配置好 `config.toml` 后执行 **`python main.py`**（轮询 `poll.targets` 并跑 pipeline）。

---

## 仓库结构（简要）

| 路径 | 作用 |
|------|------|
| `main.py` | 常驻入口：多账号时间线轮询 + checkpoint + `invoke_for_tweet`（LangGraph） |
| `ingestion/` | 采集：X 客户端、时间线轮询、标准化 `TweetEvent`、配置、飞书客户端、checkpoint |
| `pipeline/` | 编排：LangGraph（DeepSeek 相关性 → 卡片 → 飞书发布） |
| `ingestion/feishu.py` | 飞书：应用 tenant_access_token + IM 文本 |
| `llm_schema.py` | 分析结果 TypedDict / 示例 JSON（设计文档 §5） |
| `setup.py` | 包元数据与 `install_requires` / `extras_require["pipeline"]` |
| `requirements.txt` / `requirements-dev.txt` | 安装入口 |

---

## 生产部署注意点

1. **固定 Python 与依赖版本**：可在稳定环境中执行 `pip freeze > requirements-lock.txt`，部署时用锁定文件安装，减少环境漂移。
2. **进程与调度**：用 systemd、supervisor、Kubernetes 等托管 **`python main.py`**，并配置日志轮转。
3. **可观测与合规**：日志中对 Token 脱敏；对外提醒「自动分析不构成投资建议」等文案见设计文档。

---

## 设计文档

- **以 `main.py` 为入口的代码架构与数据流**（轮询 → LangGraph → 飞书）：[docs/项目架构.md](docs/项目架构.md)
- 产品背景、非目标、风险与分阶段实施建议：[bloomberg_twitter_agent_design.md](bloomberg_twitter_agent_design.md)
