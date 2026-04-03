#!/usr/bin/env bash
# 一键：创建虚拟环境 → 升级 pip → 安装依赖（见 docs/setup.md）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv}"
PYTHON="${PYTHON:-python3}"
# dev：含 pytest；minimal：仅运行时（requirements.txt）
MODE="${MODE:-dev}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到解释器: $PYTHON" >&2
  exit 1
fi

if [[ ! -d "$VENV" ]]; then
  echo "创建虚拟环境: $VENV"
  "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install -U pip wheel setuptools

case "$MODE" in
  minimal)
    echo "安装运行时依赖（requirements.txt）…"
    pip install -r requirements.txt
    ;;
  dev)
    echo "安装开发依赖（requirements-dev.txt，含 pytest）…"
    pip install -r requirements-dev.txt
    ;;
  *)
    echo "未知 MODE=$MODE，请使用 dev 或 minimal" >&2
    exit 1
    ;;
esac

echo
echo "完成。请在本终端执行："
echo "  source \"$ROOT/$VENV/bin/activate\""
echo "然后：cp config.example.toml config.toml，按 docs/配置与安全.md 填写密钥，运行 python main.py"
echo "运行测试：pytest -q"
