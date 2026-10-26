#!/usr/bin/env bash
# 기록(알림 이력, 3분할 계획) 백업. 매일 새벽 4시 자동 실행, 14일치 보관
set -euo pipefail
DATA_DIR=/var/lib/stock-alert
[ -f "$DATA_DIR/app.db" ] || { echo "아직 기록이 없습니다."; exit 0; }
sqlite3 "$DATA_DIR/app.db" ".backup $DATA_DIR/backups/app-$(date +%F).db"
find "$DATA_DIR/backups" -name 'app-*.db' -mtime +14 -delete
echo "백업 완료: $DATA_DIR/backups/app-$(date +%F).db"
