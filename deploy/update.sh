#!/usr/bin/env bash
# 새 코드로 업데이트 (root 로 실행): bash /opt/stock-alert/app/deploy/update.sh
# GitHub 의 최신 코드를 받고, 부품을 맞추고, 업데이트 전에 기록을 백업한 뒤 재시작한다.
set -euo pipefail

APP_DIR=/opt/stock-alert/app
VENV=/opt/stock-alert/venv

[ "$(id -u)" -eq 0 ] || { echo "root 로 실행하세요."; exit 1; }
cd "$APP_DIR"

echo "▶ 업데이트 전 기록 백업"
systemctl start stock-alert-backup.service

echo "▶ 최신 코드 받기"
git pull --ff-only

echo "▶ 부품 설치"
"$VENV/bin/pip" install --quiet -r requirements.txt

echo "▶ 재시작"
systemctl restart stock-alert
sleep 2
systemctl is-active stock-alert && echo "✔ 업데이트 완료 ($(git log -1 --format='%h %s'))"
