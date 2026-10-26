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

# 매수 검토 알림: 1년 고점 대비 -30%부터 5%p마다 끝까지
BUY_ZONE_START = 30
BUY_ZONE_STEP = 5

# 1년 = 최근 252 거래일
WINDOW_DAYS = 252

# 이상값 필터: 하루 등락이 이 비율 이상이면 알림 대신 "데이터 확인 필요"
OUTLIER_DAILY_CHANGE = 0.5

DATA_SOURCE = os.environ.get("DATA_SOURCE", "sample")
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
APP_SECRET = os.environ.get("APP_SECRET", "")


def load_watchlist() -> list[dict]:
    data = json.loads((ROOT / "config" / "watchlist.json").read_text(encoding="utf-8"))
    return data["stocks"]
