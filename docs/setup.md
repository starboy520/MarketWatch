# 本地环境搭建（虚拟环境 + 依赖）

## 前提

- **Python 3.10+**（3.10 会使用 `tomli` 读 `config.toml`；3.11+ 使用标准库 `tomllib`）
- macOS / Linux 下自带 `bash`；Windows 可用 Git Bash 或 WSL 运行脚本

## 一键脚本（推荐）

在项目根目录执行：

```bash
chmod +x scripts/setup_env.sh   # 首次需要
./scripts/setup_env.sh
```

默认 **`MODE=dev`**：安装 `requirements-dev.txt`（含 `pytest` + `requirements.txt` 里的编排栈）。

仅装运行时（不装 pytest）：

```bash
MODE=minimal ./scripts/setup_env.sh
```

自定义虚拟环境目录或解释器：

```bash
VENV=.venv PYTHON=python3.12 ./scripts/setup_env.sh
```

脚本结束后需**激活**虚拟环境（每个新终端都要执行一次）：

```bash
source .venv/bin/activate
```

## 手动步骤（与脚本等价）

```bash
cd /path/to/news_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel setuptools
pip install -r requirements-dev.txt   # 或 pip install -r requirements.txt
```

`requirements.txt` 会通过 `-e ".[pipeline]"` 做**可编辑安装**，并装上 LangGraph / LangChain / DeepSeek 相关依赖（见 `setup.py`）。

## 配置与运行

1. `cp config.example.toml config.toml`
2. 按 **[配置与安全.md](./配置与安全.md)** 填写 X Bearer、飞书、LLM 等（密钥勿提交 Git）
3. `python main.py`
4. 可选：`pytest -q`

## 常见问题

- **PEP 668 externally-managed-environment**：请始终在虚拟环境里 `pip install`，不要对系统 Python 全局安装。
- **只开发采集层、暂不跑 LangGraph**：可用 `MODE=minimal` 仍会装 pipeline 栈（`main.py` 需要）。若需极简环境，需改入口，本仓库默认以 `main.py` 全链路为准。
