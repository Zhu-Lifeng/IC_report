#!/usr/bin/env bash
# VPS 端部署脚本：拉取最新代码 → 安装依赖 → 重启服务
# 由 GitHub Actions 通过 SSH 调用，也可手动 `bash deploy/deploy.sh`
set -euo pipefail

APP_DIR=/opt/ic_report
BRANCH=main

cd "$APP_DIR"

echo "==> 拉取最新代码 ($BRANCH)"
git fetch --all --prune
# reset --hard 只影响被 git 跟踪的文件；data/ 和 uploads/ 已 ignore，不受影响
git reset --hard "origin/$BRANCH"

echo "==> 安装/更新依赖"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> 重启服务"
sudo systemctl restart ic_report

echo "==> 部署完成: $(git rev-parse --short HEAD)"
