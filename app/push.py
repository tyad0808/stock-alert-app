"""폰 알림(웹 푸시). 실시간 알림은 보내지 않고, 매일 오전 9시 브리핑 도착만 알린다.

서버에서 매일 9시에 실행한다:  python -m app.push   (시험 알림: python -m app.push --test)
"""

import base64
import json
import sys
from datetime import datetime, timedelta

from . import config
from .db import DB, KST

VAPID_FILE = config.DATA_DIR / "vapid.pem"  # 이 서버만 알림을 보낼 수 있게 하는 열쇠 (처음 한 번 자동 생성)
COUNT_KINDS = {"buy": "매수권장", "review": "매수검토", "profit": "수익", "loss": "손실"}


def _vapid():
    from py_vapid import Vapid02

    if VAPID_FILE.exists():
        return Vapid02.from_file(str(VAPID_FILE))
    v = Vapid02()
    v.generate_keys()
    VAPID_FILE.parent.mkdir(parents=True, exist_ok=True)
    v.save_key(str(VAPID_FILE))
    VAPID_FILE.chmod(0o600)
    return v


def public_key() -> str:
    """폰이 알림을 신청할 때 쓰는 공개 열쇠."""
    from cryptography.hazmat.primitives import serialization

    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _send_one(sub: dict, payload: str) -> bool:
    """한 기기에 보낸다. 기기가 알림을 끊었으면 False (목록에서 지운다)."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(subscription_info=sub, data=payload, vapid_private_key=_vapid(),
                vapid_claims={"sub": config.PUSH_CONTACT}, ttl=6 * 3600, timeout=15)
        return True
    except WebPushException as e:
        if e.response is not None and e.response.status_code in (404, 410):
            return False
        raise


def send_all(db: DB, title: str, body: str, url: str = "/#/brief", send=_send_one) -> dict:
    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    sent = removed = failed = 0
    for sub in db.push_subs():
        try:
            if send(sub, payload):
                sent += 1
            else:
                db.remove_push_sub(sub["endpoint"])
                removed += 1
        except Exception as e:  # noqa: BLE001 — 한 기기가 실패해도 나머지는 보낸다
            print(f"알림 보내기 실패: {e}")
            failed += 1
    return {"sent": sent, "removed": removed, "failed": failed}


def morning_message(db: DB, now: datetime | None = None) -> tuple[str, str]:
    """9시 알림 문구. 브리핑이 없으면 서버 이상을 알린다 (생존 확인)."""
    now = now or datetime.now(KST)
    today = now.date().isoformat()
    b = db.briefing(today)
    if not b:
        return "⚠ 오늘 브리핑이 없습니다", "서버가 브리핑을 만들지 못했습니다. 앱을 열어 확인해 주세요."
    counts = {}
    for a in db.alerts_since((now - timedelta(days=1)).isoformat(timespec="seconds")):
        if a["kind"] in COUNT_KINDS:
            counts[a["kind"]] = counts.get(a["kind"], 0) + 1
    parts = [f"{COUNT_KINDS[k]} {counts[k]}" for k in COUNT_KINDS if k in counts]
    issues = b.get("issues") or {}
    with_news = sum(1 for s in issues.get("stocks", []) if s.get("items"))
    body = ("밤사이 새 알림 · " + " · ".join(parts)) if parts else "밤사이 새 알림 없음"
    if b.get("market_day"):
        body += f"\nTop 10 이슈 {with_news}종목"
    return f"{now.month}/{now.day} 아침 브리핑", body


if __name__ == "__main__":
    database = DB(config.DATA_DIR / "app.db")
    if "--test" in sys.argv:
        title, body = "시험 알림", "알림이 잘 옵니다 👍"
    else:
        title, body = morning_message(database)
    result = send_all(database, title, body)
    print(f"{title} — 보냄 {result['sent']}, 끊긴 기기 정리 {result['removed']}, 실패 {result['failed']}")
