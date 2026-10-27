# 서버 설치 안내서 (iwinv · Ubuntu 24.04)

원칙 알림 앱을 `https://alert.broadstore.co.kr` 로 여는 순서입니다.
명령어는 **한 줄씩** 복사해서 붙여넣고 Enter 를 누르세요.

| 항목 | 값 |
|---|---|
| 서버 | iwinv `stock-alert` (KR1-Lite, vgna_1_n, Ubuntu 24.04) |
| 공인 IP | `49.247.139.240` |
| 주소 | `alert.broadstore.co.kr` |

> ⚠️ 인트라넷 서버(`49.247.133.38`)가 아니라 **새로 만든 서버**에서 하는 작업입니다.
> KR1-Lite 존은 iwinv 웹 방화벽(ELCAP)을 지원하지 않아서, 설치 스크립트가 서버 자체 방화벽을 켭니다.

---

## 1. 주소 연결 (iwinv 콘솔, 브라우저에서)

도메인은 가비아에서 샀지만 네임서버가 `ns1.iwinv.kr` 이라서, 주소 설정은 **iwinv 콘솔**에서 합니다.

1. iwinv 콘솔 → **DNS** → `broadstore.co.kr` 선택 → **레코드 수정**
2. **레코드 추가** → 아래처럼 입력 → **수정**

   | 이름 | 타입 | 값 |
   |---|---|---|
   | `alert` | A | `49.247.139.240` |

> ⚠️ 이미 있는 다른 레코드(`@`, `dev`, `intranet`, `quote`, `*` 등)는 **절대 고치거나 지우지 마세요.**
> `*` 레코드 때문에 새 줄이 반영되기 전에는 `alert` 주소가 자사몰로 연결됩니다. 반영까지 몇 분 기다리세요.

---

## 2. 서버 접속 (내 PC 의 PowerShell)

```powershell
ssh root@49.247.139.240
```

- `Are you sure you want to continue connecting (yes/no)?` → `yes`
- `password:` → 새 서버의 **root 비밀번호** (입력해도 안 보이는 게 정상)
- 맨 끝이 `root@...:~#` 처럼 바뀌면 접속 성공 (서버 이름 부분은 다를 수 있음)

---

## 3. 코드 내려받기 (서버에서)

저장소가 비공개라서, 서버 전용 "읽기 전용 열쇠"(Deploy key)를 만들어 GitHub 에 등록합니다.

**3-1. 열쇠 만들기**
```bash
apt-get update && apt-get install -y git
```
```bash
ssh-keygen -t ed25519 -N "" -f /root/.ssh/stock_deploy -C stock-alert-server
```
```bash
cat /root/.ssh/stock_deploy.pub
```
`ssh-ed25519 AAAA... stock-alert-server` 로 시작하는 한 줄 전체를 복사하세요.

> 이 한 줄은 공개해도 되는 "자물쇠" 쪽입니다. `.pub` 없는 파일은 열쇠이니 절대 밖으로 꺼내지 마세요.

**3-2. GitHub 에 등록 (브라우저에서)**
1. https://github.com/tyad0808/stock-alert-app → **Settings** → 왼쪽 **Deploy keys** → **Add deploy key**
2. Title: `iwinv 서버`, Key: 복사한 줄 붙여넣기
3. **Allow write access 는 체크하지 마세요** (서버는 읽기만)
4. **Add key**

**3-3. 내려받기 (서버에서)**
```bash
git clone -b claude/stage-1 -c core.sshCommand="ssh -i /root/.ssh/stock_deploy -o StrictHostKeyChecking=accept-new" git@github.com:tyad0808/stock-alert-app.git /opt/stock-alert/app
```
`Receiving objects: 100%` 가 나오면 성공입니다.

---

## 4. 설치 (서버에서, 5~10분)

주소 연결이 끝났는지 먼저 확인합니다.
```bash
getent hosts alert.broadstore.co.kr
```
`49.247.139.240  alert.broadstore.co.kr` 이 나오면 준비 완료. 아무것도 안 나오면 1번이 아직 반영 전이니 조금 기다리세요.

```bash
bash /opt/stock-alert/app/deploy/setup.sh alert.broadstore.co.kr
```

중간에 **앱 비밀번호**를 두 번 묻습니다 (8자 이상, 입력해도 안 보임). 폰에서 앱에 들어갈 때 쓰는 비밀번호입니다.

끝나면 `설치 완료` 상자와 함께 **키움에 등록할 IP** 가 표시됩니다.

---

## 5. 키움에 서버 IP 등록 (브라우저에서)

키움 포털 → **계좌 APP KEY 관리** → **IP 주소등록** 칸에 4번에서 나온 IP 입력 → **추가**

---

## 6. 폰에 설치

1. 안드로이드 폰 크롬에서 `https://alert.broadstore.co.kr`
2. 4번에서 정한 앱 비밀번호로 로그인
3. 크롬 오른쪽 위 **⋮ → 홈 화면에 추가** → 홈 화면에 "원칙 알림" 아이콘이 생기면 완료

처음 접속 때 "안전하지 않음"이 잠깐 보이면 1~2분 뒤 새로고침 (인증서 발급 중).

여기까지는 **연습용 데이터**로 움직입니다.

---

## 7. 키움 연결 (서버에서)

준비물: 키움에서 받은 **앱 키·시크릿 키 파일** (5번의 서버 IP 등록도 끝나 있어야 합니다)

먼저 새 코드를 받습니다.
```bash
bash /opt/stock-alert/app/deploy/update.sh
```
그다음 키움 연결을 실행합니다.
```bash
bash /opt/stock-alert/app/deploy/kiwoom.sh
```

1. `앱 키(App Key):` → 키 파일을 열어 복사 → 검은 창에서 마우스 오른쪽 버튼(붙여넣기) → Enter (화면에 안 보이는 게 정상)
2. `시크릿 키(Secret Key):` → 같은 방법
3. 점검 결과가 `✔` 로 쭉 나오고 `모두 정상` 이면, `실제 데이터로 바꿀까요?` 에 `y`
4. `키움 연결 완료` 가 나오면 폰에서 앱을 새로고침

> ⚠️ 키는 **채팅창에 절대 붙여넣지 마세요.** 이 스크립트만 서버 `.env` 에 저장합니다.
> `✖` 가 나오면 그 화면을 캡처해서 보내주세요. 이때는 연습용 데이터 그대로 유지됩니다.

---

## 8. 아침 브리핑 (서버에서)

새 코드를 받으면(`update.sh`) 매일 **08:50** 브리핑이 자동으로 만들어집니다. 폰 앱 **[브리핑]** 탭에서 봅니다.

- Claude 키가 없어도 계좌·매수권장/검토·공시·실적 일정과, 영어 뉴스 제목의 **무료 자동 번역**이 나옵니다.
- 한국어 요약(같은 사건 합치기, 더 꼼꼼한 의견 거르기)을 원하면 Claude 키를 넣습니다 (유료, 선택).
  ```bash
  bash /opt/stock-alert/app/deploy/claude.sh
  ```
  `Claude 키:` → 키를 마우스 오른쪽 버튼으로 붙여넣기 → Enter (화면에 안 보이는 게 정상)

> ⚠️ Claude 키도 **채팅창에 절대 붙여넣지 마세요.**

**9시 폰 알림 켜기 (폰에서)**: 앱 오른쪽 위 ⚙ 설정 → **폰 알림** → [이 폰에서 알림 받기] → 크롬이 묻으면 **허용**. [시험 알림 보내기]로 확인.
브리핑이 만들어지지 않은 날에는 "오늘 브리핑이 없습니다" 알림이 옵니다 (서버 이상 신호).

---

## 자주 쓰는 명령어 (서버에서)

| 하고 싶은 일 | 명령어 |
|---|---|
| 새 코드로 업데이트 | `bash /opt/stock-alert/app/deploy/update.sh` |
| 앱 상태 보기 | `systemctl status stock-alert --no-pager` |
| 최근 기록 보기 | `journalctl -u stock-alert -n 30 --no-pager` |
| 키움 연결 점검만 | `cd /opt/stock-alert/app && runuser -u stockalert -- /opt/stock-alert/venv/bin/python -m app.providers.kiwoom` |
| 시험 폰 알림 | `cd /opt/stock-alert/app && runuser -u stockalert -- /opt/stock-alert/venv/bin/python -m app.push --test` |
| 브리핑 지금 다시 만들기 | `cd /opt/stock-alert/app && runuser -u stockalert -- /opt/stock-alert/venv/bin/python -m app.briefing --force` |
| 시세 확인 지금 1번 | `systemctl start stock-alert-check` |
| 백업 지금 1번 | `systemctl start stock-alert-backup` |
