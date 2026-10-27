"""설정값. 숫자는 기획서 10장 확정 사항을 그대로 옮겼다."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """.env 파일이 있으면 환경변수로 읽는다. 이미 설정된 값은 덮어쓰지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")

# 1년 고점 대비 하락 알림: -5%부터 5%p마다 끝까지
ZONE_START = 5
ZONE_STEP = 5

# 단계: (이 구간부터, 키, 이름). 깊은 것부터 적는다.
#   매수검토 -5·-10·-15%, 매수권장 -20%부터 5%p마다 계속
TIERS = [
    (20, "buy", "매수권장"),
    (5, "review", "매수검토"),
]

# 내 종목 알림: 평단 대비 수익 +10%마다, 손실 -20%마다
PROFIT_STEP = 10
LOSS_STEP = 20

# 3분할 매수 비율
SPLIT_RATIOS = (30, 30, 40)

# 경계선 여유: 구간 기준보다 2%p 이상 되돌아와야 "구간을 벗어났다"고 본다 (Top 10·내 종목 공통)
HYSTERESIS = 2

# 알림 기록·브리핑은 이 기간만 보관 (오래된 것은 매일 자동 정리)
KEEP_DAYS = 180

# 1년 = 최근 252 거래일
WINDOW_DAYS = 252

# 이상값 필터: 하루 등락이 이 비율 이상이면 알림 대신 "데이터 확인 필요"
OUTLIER_DAILY_CHANGE = 0.5

DATA_SOURCE = os.environ.get("DATA_SOURCE", "sample")
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
APP_SECRET = os.environ.get("APP_SECRET", "")

# 키움 REST API (조회 전용). DATA_SOURCE=kiwoom 일 때 쓴다
KIWOOM_APP_KEY = os.environ.get("KIWOOM_APP_KEY", "")
KIWOOM_APP_SECRET = os.environ.get("KIWOOM_APP_SECRET", "")

# 아침 브리핑: 뉴스 요약은 Claude API (키가 없으면 공시만 보여준다)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BRIEFING_MODEL = os.environ.get("BRIEFING_MODEL", "claude-opus-5-5")
# 미국 공시(SEC)는 연락처가 담긴 이름으로 요청해야 한다
# 폰 알림을 보내는 쪽 연락처 (알림 서비스 규칙상 필요)
PUSH_CONTACT = os.environ.get("PUSH_CONTACT", "https://alert.broadstore.co.kr")
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "stock-alert-app (+https://alert.broadstore.co.kr)")


def load_watchlist() -> list[dict]:
    data = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    return data["stocks"]
