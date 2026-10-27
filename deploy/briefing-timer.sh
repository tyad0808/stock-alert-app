#!/usr/bin/env bash
# 아침 브리핑을 매일 오전 8시 50분에 만들도록 등록한다 (setup.sh, update.sh 가 부른다). 여러 번 실행해도 안전하다.
set -euo pipefail

APP_DIR=/opt/stock-alert/app
VENV=/opt/stock-alert/venv
DATA_DIR=/var/lib/stock-alert
APP_USER=stockalert

cat > /etc/systemd/system/stock-alert-briefing.service <<UNIT
[Unit]
Description=Stock alert morning briefing
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python -m app.briefing
TimeoutStartSec=600
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR
UNIT

cat > /etc/systemd/system/stock-alert-briefing.timer <<UNIT
[Unit]
Description=Stock alert morning briefing every day 08:50

[Timer]
OnCalendar=*-*-* 08:50:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now stock-alert-briefing.timer >/dev/null
echo "아침 브리핑: 매일 08:50 자동 작성 (다음 실행 $(systemctl show stock-alert-briefing.timer -p NextElapseUSecRealtime --value))"
