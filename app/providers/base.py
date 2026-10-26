"""시세 공급원이 지켜야 할 약속. 조회 기능만 있고 주문 기능은 없다."""

from abc import ABC, abstractmethod

from ..rules import Bar


class PriceProvider(ABC):
    name: str = ""
    is_practice: bool = False

    @abstractmethod
    def daily_bars(self, symbol: str) -> list[Bar]:
        """최근 1년 이상의 일별 시세. 마지막 항목이 가장 최근 거래일."""

    def holdings(self) -> list[dict]:
        """내 계좌 보유 종목: [{symbol, name, qty, avg_price}] (평단은 달러)."""
        return []

    def fx_rate(self) -> float | None:
        """원/달러 환율. 3분할 계산기의 주수 계산용."""
        return None
