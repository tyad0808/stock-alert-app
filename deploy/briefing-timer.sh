#!/usr/bin/env bash
# 아침 브리핑을 매일 08:50 에 만들고, 09:00 에 폰으로 알리도록 등록한다 (setup.sh, update.sh 가 부른다). 여러 번 실행해도 안전하다.
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

# 09:00 폰 알림 (브리핑이 없으면 "서버 확인 필요" 알림 → 생존 확인)
cat > /etc/systemd/system/stock-alert-push.service <<UNIT
[Unit]
Description=Stock alert morning push
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python -m app.push
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR
UNIT

cat > /etc/systemd/system/stock-alert-push.timer <<UNIT
[Unit]
Description=Stock alert morning push every day 09:00

[Timer]
OnCalendar=*-*-* 09:00:00

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now stock-alert-briefing.timer >/dev/null
systemctl enable --now stock-alert-push.timer >/dev/null
echo "폰 알림: 매일 09:00"
echo "아침 브리핑: 매일 08:50 자동 작성 (다음 실행 $(systemctl show stock-alert-briefing.timer -p NextElapseUSecRealtime --value))"
