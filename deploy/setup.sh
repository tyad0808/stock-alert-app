#!/usr/bin/env bash
# 원칙 알림 서버 설치 스크립트 (iwinv · Ubuntu 24.04, root 로 실행)
#
# 사용법: bash /opt/stock-alert/app/deploy/setup.sh 주소
#   예:   bash /opt/stock-alert/app/deploy/setup.sh alert.broadstore.co.kr
#
# 하는 일
#  1. 시간대(한국), 보안 업데이트 자동 설치, 비상용 메모리(스왑)
#  2. 파이썬 실행 환경, Caddy(HTTPS 자동) 설치
#  3. 앱 전용 계정(stockalert) 생성, 데이터 폴더 준비, .env 만들기 (앱 비밀번호 입력)
#  4. 앱을 서비스로 등록 (재부팅해도 자동 시작, 멈추면 자동 재시작)
#  5. 15분마다 시세 확인, 매일 새벽 4시 기록 백업
#  6. 방화벽(22, 80, 443 만 열기), 비밀번호 무작위 대입 공격 차단(fail2ban)
#
# 여러 번 실행해도 안전하다 (이미 된 단계는 건너뛴다).
set -euo pipefail

DOMAIN="${1:-}"
APP_DIR=/opt/stock-alert/app
VENV=/opt/stock-alert/venv
DATA_DIR=/var/lib/stock-alert
APP_USER=stockalert

say() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "root 로 실행하세요."
[ -n "$DOMAIN" ] || fail "주소를 함께 적어 주세요. 예: bash $0 alert.broadstore.co.kr"
[ -f "$APP_DIR/requirements.txt" ] || fail "$APP_DIR 에 앱 코드가 없습니다. 안내서의 '코드 내려받기' 단계를 먼저 하세요."
grep -q 'Ubuntu' /etc/os-release || fail "Ubuntu 에서만 동작하는 스크립트입니다."

export DEBIAN_FRONTEND=noninteractive

say "1/7 시간대를 한국으로 맞추고 기본 프로그램을 설치합니다"
timedatectl set-timezone Asia/Seoul
apt-get update -y
apt-get upgrade -y
apt-get install -y curl git ufw fail2ban unattended-upgrades sqlite3 python3 python3-venv \
  ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https
# 보안 업데이트를 매일 자동으로 설치
echo 'APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";' > /etc/apt/apt.conf.d/20auto-upgrades

say "2/7 비상용 메모리(스왑 1GB)를 만듭니다"
if ! swapon --show | grep -q .; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  echo "이미 스왑이 있습니다. 건너뜁니다."
fi

say "3/7 파이썬 실행 환경을 만듭니다"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
"$VENV/bin/python" --version

say "4/7 Caddy(HTTPS 자동 발급)를 설치합니다"
if ! command -v caddy >/dev/null; then
  # 공식 저장소(최신판)를 먼저 시도하고, 안 되면 Ubuntu 기본 저장소의 Caddy 를 쓴다
  if curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
     && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list \
     && apt-get update -y && apt-get install -y caddy; then
    echo "Caddy 공식 저장소에서 설치했습니다."
  else
    echo "공식 저장소 접속 실패. Ubuntu 기본 저장소의 Caddy 를 설치합니다."
    rm -f /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
  fi
fi
caddy version

say "5/7 앱 계정, 데이터 폴더, 설정 파일(.env)을 준비합니다"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
# 코드는 root 소유(앱이 자기 코드를 고칠 수 없게), 데이터만 앱 계정 소유
mkdir -p "$DATA_DIR/backups"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"

if [ ! -f "$APP_DIR/.env" ]; then
  echo
  echo "앱에 들어갈 때 쓸 비밀번호를 정합니다 (8자 이상). 입력해도 화면에 안 보이는 게 정상입니다."
  while true; do
    read -r -s -p "앱 비밀번호: " PW1; echo
    read -r -s -p "한 번 더: " PW2; echo
    if [ "$PW1" != "$PW2" ]; then echo "두 번 입력한 비밀번호가 다릅니다. 다시 입력하세요."
    elif [ "${#PW1}" -lt 8 ]; then echo "8자 이상으로 정해 주세요."
    else break; fi
  done
  SECRET=$("$VENV/bin/python" -c "import secrets; print(secrets.token_hex(32))")
  cat > "$APP_DIR/.env" <<ENV
# 운영 서버 설정 (이 파일은 깃에 올라가지 않는다)
APP_PASSWORD=$PW1
APP_SECRET=$SECRET
DATA_DIR=$DATA_DIR

# 시세 공급원: sample(연습용 데이터) / kiwoom(키움 연결 후)
DATA_SOURCE=sample

# 키움 REST API — 조회 전용. 키를 넣은 뒤 DATA_SOURCE=kiwoom 으로 바꾸고 재시작
KIWOOM_APP_KEY=
KIWOOM_APP_SECRET=
ENV
  unset PW1 PW2
  echo ".env 를 새로 만들었습니다 (로그인 유지용 비밀값 자동 생성)."
else
  echo ".env 가 이미 있어 그대로 둡니다."
fi
chown root:"$APP_USER" "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"

say "6/7 앱 서비스, 15분마다 시세 확인, 매일 백업을 등록합니다"
# 공통 보안 설정: 시스템 파일을 고치지 못하게, 데이터 폴더만 쓰기 허용
HARDEN="NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR"

cat > /etc/systemd/system/stock-alert.service <<UNIT
[Unit]
Description=Stock alert app
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=3
$HARDEN

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/stock-alert-check.service <<UNIT
[Unit]
Description=Stock alert price check

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python -m app.checker
$HARDEN
UNIT

cat > /etc/systemd/system/stock-alert-check.timer <<UNIT
[Unit]
Description=Stock alert price check every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
UNIT

cat > /etc/systemd/system/stock-alert-backup.service <<UNIT
[Unit]
Description=Stock alert DB backup

[Service]
Type=oneshot
User=$APP_USER
ExecStart=/bin/bash $APP_DIR/deploy/backup.sh
$HARDEN
UNIT

cat > /etc/systemd/system/stock-alert-backup.timer <<UNIT
[Unit]
Description=Stock alert DB backup every day 04:00

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
UNIT

# 작업 기록(로그)이 디스크를 채우지 않게 최대 100MB
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald

systemctl daemon-reload
systemctl enable --now stock-alert.service
systemctl enable --now stock-alert-check.timer
systemctl enable --now stock-alert-backup.timer

say "7/7 HTTPS(Caddy)와 방화벽을 설정합니다"
cat > /etc/caddy/Caddyfile <<CADDY
# $DOMAIN 으로 들어온 요청을 앱(내부 8000번)으로 전달. HTTPS 인증서는 자동 발급·갱신
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8000
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		-Server
	}
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy || systemctl restart caddy

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban

sleep 2
OUT_IP=$(curl -fsS --max-time 10 https://api.ipify.org || echo "확인 실패")
STATUS=$(systemctl is-active stock-alert || true)

cat <<DONE

==================================================
 설치 완료
==================================================
 앱 서비스 상태     : $STATUS
 접속 주소          : https://$DOMAIN
 키움에 등록할 IP   : $OUT_IP

 다음 할 일
 1) 키움 포털 → 계좌 APP KEY 관리 → IP 주소등록 에 위 IP 추가
 2) 폰 크롬에서 https://$DOMAIN 접속 → 로그인
    (주소 연결 직후에는 HTTPS 인증서 발급에 1~2분 걸릴 수 있음)
 3) 크롬 메뉴 ⋮ → "홈 화면에 추가"
 지금은 연습용 데이터로 움직입니다. 키움 연결은 다음 단계에서 합니다.
==================================================
DONE
