#!/usr/bin/env bash
# 工厂管理系统 - 运行脚本（Linux / macOS）
# 只启动 Waitress 服务，并尝试用默认浏览器打开页面。
set -euo pipefail

cd "$(dirname "$0")"
PY="venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "[ERROR] Virtual environment not found. Run ./deploy.sh first." >&2
    exit 1
fi

# 无图形界面（如纯服务器/SSH）时不要尝试打开浏览器，只打印访问地址。
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    if [ "${OPEN_BROWSER:-1}" != "0" ]; then
        echo "[INFO] No GUI display detected; setting OPEN_BROWSER=0."
        export OPEN_BROWSER=0
    fi
fi

echo "============================================================"
echo " Factory Management System - Running"
echo "============================================================"
echo " Press Ctrl+C to stop the server."
echo "============================================================"
echo

exec "$PY" start_server.py
