"""연습용 데이터. 실제 시세가 아니다.

키움 연결 전에 화면과 알림 규칙을 확인하려고 만든 가짜 가격이다.
종목마다 1년치 과거 가격과 앞으로 60일치 "미래" 가격을 미리 정해두고,
"하루 진행" 버튼을 누를 때마다 하루씩 앞으로 간다. 그래서 알림이 언제 울리는지 직접 볼 수 있다.
"""

import math
import random
from datetime import date, timedelta

from ..rules import Bar
from .base import PriceProvider

HISTORY_DAYS = 252
FUTURE_DAYS = 60
TOTAL_DAYS = HISTORY_DAYS + FUTURE_DAYS
TODAY = date(2026, 10, 23)  # 연습 시작일 (금요일)

# 종목별 가격 흐름: (거래일 번호, 가격). 사이 값은 이어서 그린다.
# 0~251은 과거 1년, 251이 연습 시작일, 252~311은 "하루 진행"으로 보게 될 미래.
SCRIPTS: dict[str, list[tuple[int, float]]] = {
    # 고점 대비 -33%에서 시작 → -38%까지 더 빠짐 → -28%로 회복 → 다시 -36%
    "NVDA": [(0, 150), (90, 200), (251, 134), (275, 124), (290, 144), (311, 128)],
    # 고점 근처
    "MSFT": [(0, 420), (200, 520), (251, 500), (311, 510)],
    # -12% → -18%
    "AAPL": [(0, 210), (120, 260), (251, 229), (311, 213)],
    # -22% → -31%까지 잠깐 → -24%로 회복
    "GOOGL": [(0, 160), (150, 210), (251, 164), (280, 145), (311, 160)],
    # -8%
    "AMZN": [(0, 180), (180, 240), (251, 221), (311, 226)],
    # -41%에서 시작 → -47% → -53%까지 깊어짐
    "META": [(0, 600), (60, 780), (251, 460), (270, 413), (300, 367), (311, 372)],
    # 계속 신고가
    "AVGO": [(0, 220), (251, 340), (311, 365)],
    # -28% → 며칠 만에 -34% (중간에 오류 데이터 하루 포함)
    "TSLA": [(0, 260), (100, 420), (251, 302), (258, 277), (311, 285)],
    # -6%
    "BRK.B": [(0, 460), (220, 500), (251, 470), (311, 480)],
    # -31% → -26%로 회복해 구간 이탈 → 다시 -32%로 재진입
    "TSM": [(0, 170), (110, 240), (251, 166), (268, 178), (295, 163), (311, 165)],
    # Top 10 밖 보유 종목: 평단 대비 +26% → +9%로 내려옴 → 다시 +23%
    "PLTR": [(0, 40), (200, 95), (251, 88), (280, 76), (311, 86)],
}

# 연습용 보유 종목 (평단은 달러). 실제 계좌가 아니다.
HOLDINGS = [
    # 평단 $160 → -16%에서 시작, -22%까지 빠지며 손실 -20% 알림
    {"symbol": "NVDA", "name": "엔비디아", "qty": 20, "avg_price": 160.0},
    # 평단 $440 → +14% (수익 +10% 구간)
    {"symbol": "MSFT", "name": "마이크로소프트", "qty": 10, "avg_price": 440.0},
    # 평단 $280 → +21%에서 +30%까지 올라감
    {"symbol": "AVGO", "name": "브로드컴", "qty": 15, "avg_price": 280.0},
    # Top 10 밖 종목도 보유 중이면 계속 알림
    {"symbol": "PLTR", "name": "팔란티어", "qty": 50, "avg_price": 70.0},
]

FX_RATE = 1400.0  # 연습용 고정 환율

# 이상값 필터 확인용: 이 날은 가격이 잘못 들어온 것처럼 만든다
BAD_DATA_DAYS = {"TSLA": 262}


def _trading_dates() -> list[str]:
    """연습 시작일이 251번째가 되도록 주말을 뺀 날짜를 만든다."""
    days, d = [], TODAY
    while len(days) < HISTORY_DAYS:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    d = TODAY + timedelta(days=1)
    while len(days) < TOTAL_DAYS:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return [x.isoformat() for x in days]


def _default_script(symbol: str) -> list[tuple[int, float]]:
    """따로 정해두지 않은 종목(ETF 등)은 이름으로 정해지는 완만한 흐름을 만든다."""
    rng = random.Random("script:" + symbol)
    base = rng.uniform(40, 500)
    return [(0, base), (rng.randint(60, 200), base * rng.uniform(1.1, 1.5)),
            (251, base * rng.uniform(0.85, 1.3)), (311, base * rng.uniform(0.8, 1.3))]


def _series(symbol: str, dates: list[str]) -> list[Bar]:
    points = SCRIPTS.get(symbol) or _default_script(symbol)
    rng = random.Random(symbol)
    bars = []
    for i, day in enumerate(dates):
        # 가까운 두 점 사이를 로그 스케일로 잇는다
        for (d0, p0), (d1, p1) in zip(points, points[1:]):
            if d0 <= i <= d1:
                t = (i - d0) / (d1 - d0)
                base = math.exp(math.log(p0) + t * (math.log(p1) - math.log(p0)))
                break
        # 정해둔 점에서는 흔들림 없이 그 가격 그대로
        noise = 0 if any(i == d for d, _ in points) else rng.uniform(-0.012, 0.012)
        close = base * (1 + noise)
        if BAD_DATA_DAYS.get(symbol) == i:
            close = close * 0.35
        high = close * (1 + rng.uniform(0, 0.004))
        bars.append(Bar(date=day, close=round(close, 2), high=round(high, 2)))
    return bars


class SampleProvider(PriceProvider):
    name = "연습용 데이터"
    is_practice = True

    def __init__(self, offset: int = 0):
        self.offset = max(0, min(offset, FUTURE_DAYS))
        self._dates = _trading_dates()

    def daily_bars(self, symbol: str) -> list[Bar]:
        end = HISTORY_DAYS + self.offset
        return _series(symbol, self._dates)[:end]

    def holdings(self) -> list[dict]:
        return [dict(h) for h in HOLDINGS]

    def fx_rate(self) -> float:
        return FX_RATE

    @property
    def can_advance(self) -> bool:
        return self.offset < FUTURE_DAYS
