"""시세 공급원이 지켜야 할 약속. 조회 기능만 있고 주문 기능은 없다."""

from abc import ABC, abstractmethod

from ..rules import Bar


class PriceProvider(ABC):
    name: str = ""
    is_practice: bool = False

    @abstractmethod
    def daily_bars(self, symbol: str) -> list[Bar]:
        """최근 1년 이상의 일별 시세. 마지막 항목이 가장 최근 거래일."""
