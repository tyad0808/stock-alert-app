"""시세 공급원. 설정(DATA_SOURCE)에 따라 하나를 고른다."""

from .. import config
from .base import PriceProvider


def get_provider(db) -> PriceProvider:
    if config.DATA_SOURCE == "sample":
        from .sample import SampleProvider

        return SampleProvider(offset=int(db.get_meta("practice_offset", "0")))
    raise ValueError(
        f"알 수 없는 시세 공급원: {config.DATA_SOURCE} (키움 연결은 2단계에서 추가 예정)"
    )
