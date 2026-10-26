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

## 1. 주소 연결 (가비아, 브라우저에서)

인트라넷 때와 같은 화면입니다.

1. 가비아 로그인 → **My가비아** → **도메인** → `broadstore.co.kr` 의 **관리**
2. **DNS 정보 → DNS 관리** → **레코드 수정**
3. **레코드 추가** → 아래처럼 입력 → **저장**

   | 타입 | 호스트 | 값/위치 | TTL |
   |---|---|---|---|
   | A | `alert` | `49.247.139.240` | 600 |

> ⚠️ 이미 있는 다른 레코드(`@`, `www`, `intranet` 등)는 **절대 고치거나 지우지 마세요.**

---

## 2. 서버 접속 (내 PC 의 PowerShell)

```powershell
ssh root@49.247.139.240
```

- `Are you sure you want to continue connecting (yes/no)?` → `yes`
- `password:` → 새 서버의 **root 비밀번호** (입력해도 안 보이는 게 정상)
- 앞부분이 `root@stock-alert:~#` 처럼 바뀌면 접속 성공

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

지금은 **연습용 데이터**로 움직입니다. 키움 연결은 다음 단계에서 안내합니다.

---

## 자주 쓰는 명령어 (서버에서)

| 하고 싶은 일 | 명령어 |
|---|---|
| 새 코드로 업데이트 | `bash /opt/stock-alert/app/deploy/update.sh` |
| 앱 상태 보기 | `systemctl status stock-alert --no-pager` |
| 최근 기록 보기 | `journalctl -u stock-alert -n 30 --no-pager` |
| 시세 확인 지금 1번 | `systemctl start stock-alert-check` |
| 백업 지금 1번 | `systemctl start stock-alert-backup` |
