"""뉴스 제목을 종목별 사실 1~3줄로 요약한다 (Claude API).

원칙: 사실만. 의견·예측·추천 문장은 만들지 않게 지시하고, 그래도 들어가면 OPINION 으로 한 번 더 걸러낸다.
요약마다 원문 링크가 반드시 붙는다 (모델이 고른 원문 번호로만 링크를 단다).
"""

import json
import re

from .. import config

MAX_ITEMS = 3

# 이런 표현이 들어간 줄은 버린다 (의견·예측·추천)
OPINION = re.compile(
    r"매수|매도|사야|팔아야|기회|유망|추천|전망이 밝|전망이 어둡|전망된다|예상된다|기대된다|기대감|우려된다|"
    r"것으로 보인다|할 것이다|호재|악재|저평가|고평가|목표가|투자 의견|상승할|하락할|오를|내릴"
)

SYSTEM = """너는 미국 주식 뉴스 제목을 한국어로 정리하는 편집자다. 규칙을 반드시 지킨다.

1. 제목에 적힌 사실만 쓴다. 제목에 없는 내용, 배경 설명, 숫자를 지어내지 않는다.
2. 의견·예측·평가·추천을 쓰지 않는다. "기회", "전망이 밝다", "우려", "기대", "매수", "매도", "호재", "악재", "~할 것" 같은 표현 금지.
   제목 자체가 의견이나 전망(애널리스트 의견, 목표가, "사야 할까" 같은 질문, 순위·추천 기사)이면 그 제목은 쓰지 않는다.
3. 종목마다 가장 중요한 사실 최대 3개. 같은 사건을 다룬 제목은 하나로 합친다. 쓸 만한 사실이 없으면 items 를 비운다.
4. 한 줄은 60자 이내의 평서문(~했다, ~발표)으로 쓴다. 회사 이름은 한국어 이름을 쓴다.
5. sources 에는 그 줄의 근거가 된 제목 번호(id)를 적는다. 근거 없는 줄은 쓰지 않는다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "sources": {"type": "array", "items": {"type": "integer"}},
                            },
                            "required": ["text", "sources"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["symbol", "items"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stocks"],
    "additionalProperties": False,
}


class SummaryError(RuntimeError):
    pass


def is_opinion(text: str) -> bool:
    return bool(OPINION.search(text))


def _call_claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=120)
    try:
        response = client.beta.messages.create(
            model=config.BRIEFING_MODEL,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise SummaryError("Claude 키가 올바르지 않습니다") from None
    except anthropic.PermissionDeniedError:
        raise SummaryError("Claude 키에 사용 권한이 없습니다 (결제 등록 확인)") from None
    except anthropic.RateLimitError:
        raise SummaryError("Claude 사용량 한도를 넘었습니다") from None
    except anthropic.APIStatusError as e:
        raise SummaryError(f"Claude 응답 오류 {e.status_code}") from None
    except anthropic.APIConnectionError:
        raise SummaryError("Claude 서버에 연결할 수 없습니다") from None
    if response.stop_reason == "refusal":
        raise SummaryError("Claude 가 요약을 거절했습니다")
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise SummaryError("Claude 응답이 비어 있습니다")
    return text


def summarize(news_by_symbol: dict[str, list[dict]], names: dict[str, str], call=_call_claude) -> dict[str, list[dict]]:
    """{종목: [뉴스 제목]} → {종목: [{text, link}]}. 키가 없거나 뉴스가 없으면 빈 결과."""
    if not config.ANTHROPIC_API_KEY or not any(news_by_symbol.values()):
        return {}
    sources, lines = {}, []
    for symbol, items in news_by_symbol.items():
        if not items:
            continue
        lines.append(f"\n[{symbol} · {names.get(symbol, symbol)}]")
        for it in items:
            sid = len(sources) + 1
            sources[sid] = (symbol, it["link"])
            lines.append(f"{sid}. {it['title']}")
    prompt = "다음은 종목별 최근 뉴스 제목이다. 규칙대로 정리해라.\n" + "\n".join(lines)
    try:
        data = json.loads(call(prompt))
    except ValueError:
        raise SummaryError("Claude 응답 형식 오류") from None

    result: dict[str, list[dict]] = {}
    for st in data.get("stocks", []):
        symbol = st.get("symbol", "")
        if symbol not in news_by_symbol:
            continue
        for item in st.get("items", [])[:MAX_ITEMS]:
            text = str(item.get("text", "")).strip()
            # 그 종목의 원문 번호만 인정한다. 근거가 없거나 의견 표현이 있으면 버린다
            links = [sources[s][1] for s in item.get("sources", []) if s in sources and sources[s][0] == symbol]
            if not text or not links or is_opinion(text):
                continue
            result.setdefault(symbol, []).append({"text": text, "link": links[0]})
    return result
