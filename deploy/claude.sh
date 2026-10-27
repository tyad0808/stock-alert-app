#!/usr/bin/env bash
# 아침 브리핑 뉴스 요약용 Claude 키 넣기 (root 로 실행): bash /opt/stock-alert/app/deploy/claude.sh
#
#  1. Claude API 키를 입력받아 .env 에 저장한다 (화면에 안 보임, 채팅에 붙여넣지 말 것)
#  2. 오늘 브리핑을 새로 만들어 본다
set -euo pipefail

APP_DIR=/opt/stock-alert/app
VENV=/opt/stock-alert/venv
ENV_FILE=$APP_DIR/.env
APP_USER=stockalert

say() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

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

say "1/2 Claude 키 입력"
echo "Claude 콘솔에서 만든 키(sk-ant- 로 시작)를 마우스 오른쪽 버튼으로 붙여넣고 Enter. (화면에 안 보이는 게 정상)"
read -r -s -p "Claude 키: " KEY; echo
KEY=$(printf '%s' "$KEY" | tr -d '[:space:]')
case "$KEY" in sk-ant-*) ;; *) fail "sk-ant- 로 시작하는 키가 아닙니다. 다시 실행하세요." ;; esac
set_env ANTHROPIC_API_KEY "$KEY"
unset KEY
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"
systemctl restart stock-alert
echo "저장했습니다."

say "2/2 오늘 브리핑 만들어 보기 (1분쯤 걸립니다)"
(cd "$APP_DIR" && runuser -u "$APP_USER" -- "$VENV/bin/python" -m app.briefing --force) \
  || fail "브리핑을 만들지 못했습니다. 이 화면을 캡처해서 보내주세요."
echo
echo "폰 앱의 [브리핑] 탭에서 확인해 보세요. 내일부터는 매일 08:50 에 자동으로 만들어집니다."
