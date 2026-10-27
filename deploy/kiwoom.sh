#!/usr/bin/env bash
# 키움 연결 (root 로 실행): bash /opt/stock-alert/app/deploy/kiwoom.sh
#
#  1. 키움 앱 키·시크릿 키를 입력받아 .env 에 저장한다 (화면에 안 보임, 채팅에 붙여넣지 말 것)
#  2. 조회가 되는지 점검한다 (로그인, 환율, 보유 종목, Top 10 시세)
#  3. 점검이 통과하면, 연습용 데이터를 지우고 실제 키움 데이터로 바꾼다
#
# 키만 다시 넣고 싶을 때도 그대로 다시 실행하면 된다.
set -euo pipefail

APP_DIR=/opt/stock-alert/app
VENV=/opt/stock-alert/venv
ENV_FILE=$APP_DIR/.env
APP_USER=stockalert

say() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }
as_app() { (cd "$APP_DIR" && runuser -u "$APP_USER" -- "$VENV/bin/python" "$@"); }

# .env 의 KEY=값 한 줄을 바꾼다 (없으면 추가). 값은 환경변수로 넘겨서 특수문자도 안전하게
set_env() {
  KEY="$1" VALUE="$2" "$VENV/bin/python" - "$ENV_FILE" <<'PY'
import os, sys
path, key, value = sys.argv[1], os.environ["KEY"], os.environ["VALUE"]
lines = open(path, encoding="utf-8").read().splitlines()
for i, line in enumerate(lines):
    if line.split("=", 1)[0].strip() == key:
        lines[i] = f"{key}={value}"
        break
else:
    lines.append(f"{key}={value}")
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

[ "$(id -u)" -eq 0 ] || fail "root 로 실행하세요."
[ -f "$ENV_FILE" ] || fail ".env 가 없습니다. setup.sh 를 먼저 실행하세요."

say "1/3 키움 키 입력"
if grep -q '^KIWOOM_APP_KEY=.\+' "$ENV_FILE"; then
  read -r -p "이미 저장된 키가 있습니다. 새로 입력할까요? (y/n): " ANSWER
else
  ANSWER=y
fi
if [ "$ANSWER" = "y" ]; then
  echo "키움에서 받은 파일을 열어 복사한 뒤, 마우스 오른쪽 버튼으로 붙여넣고 Enter. (화면에 안 보이는 게 정상)"
  read -r -s -p "앱 키(App Key): " KEY; echo
  read -r -s -p "시크릿 키(Secret Key): " SECRET; echo
  KEY=$(printf '%s' "$KEY" | tr -d '[:space:]')
  SECRET=$(printf '%s' "$SECRET" | tr -d '[:space:]')
  [ -n "$KEY" ] && [ -n "$SECRET" ] || fail "키가 비어 있습니다. 다시 실행하세요."
  set_env KIWOOM_APP_KEY "$KEY"
  set_env KIWOOM_APP_SECRET "$SECRET"
  unset KEY SECRET
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  echo "저장했습니다 (글자 수만 확인: 앱 키 $(grep '^KIWOOM_APP_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '\n' | wc -c)자)."
fi

say "2/3 키움 조회 점검"
if ! as_app -m app.providers.kiwoom; then
  fail "점검에 실패했습니다. 이 화면을 캡처해서 보내주세요. (아직 연습용 데이터 그대로입니다)"
fi

if grep -q '^DATA_SOURCE=kiwoom' "$ENV_FILE"; then
  systemctl restart stock-alert
  echo "이미 키움 데이터를 쓰고 있습니다. 앱을 다시 시작했습니다."
  exit 0
fi

say "3/3 실제 키움 데이터로 바꾸기"
read -r -p "연습용 알림 기록을 지우고 실제 데이터로 바꿀까요? (y/n): " ANSWER
[ "$ANSWER" = "y" ] || { echo "바꾸지 않았습니다. 나중에 다시 실행하면 됩니다."; exit 0; }

systemctl start stock-alert-backup.service
systemctl stop stock-alert
as_app -c "from app import config; from app.db import DB; DB(config.DATA_DIR / 'app.db').reset()"
set_env DATA_SOURCE kiwoom
systemctl start stock-alert
sleep 3
systemctl is-active stock-alert >/dev/null || fail "앱이 켜지지 않았습니다. journalctl -u stock-alert -n 30 --no-pager 결과를 보내주세요."

cat <<DONE

==================================================
 키움 연결 완료
==================================================
 이제 실제 시세와 내 계좌(조회만)로 움직입니다.
 폰에서 앱을 새로고침해 보세요.
 연습용 버튼(하루 진행 등)은 사라집니다.
==================================================
DONE
