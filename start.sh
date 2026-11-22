#!/usr/bin/env bash
# 工厂管理系统 - 一键脚本（Linux / macOS）
# 先部署环境，再启动服务。
set -euo pipefail

cd "$(dirname "$0")"

echo "============================================================"
echo " Factory Management System - One-click Start"
echo "============================================================"
echo " Step 1: deploy environment"
echo " Step 2: start server"
echo "============================================================"
echo

./deploy.sh
./run_system.sh
