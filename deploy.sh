#!/usr/bin/env bash
# 工厂管理系统 - 部署脚本（Linux / macOS）
# 只构建运行环境，不启动服务。
set -euo pipefail

cd "$(dirname "$0")"
PY="venv/bin/python"

echo "============================================================"
echo " Factory Management System - Deploy (Linux/macOS)"
echo "============================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Install Python 3 first." >&2
    exit 1
fi

if [ ! -x "$PY" ]; then
    echo "[1/6] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[1/6] Virtual environment found."
fi

echo "[2/6] Installing dependencies..."
"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install -r requirements.txt

if [ ! -f .env ]; then
    echo "[3/6] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[3/6] .env found."
fi

echo "[4/6] Ensuring database exists..."
"$PY" scripts/ensure_database.py

echo "[5/6] Applying database migrations..."
"$PY" -m flask db upgrade

echo "[6/6] Loading seed data..."
"$PY" scripts/seed.py

echo
echo "[OK] Environment is ready."
echo "     Run ./run_system.sh to start the server."
