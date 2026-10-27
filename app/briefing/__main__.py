"""서버에서 매일 오전 8시 50분에 실행한다:  python -m app.briefing  (다시 만들기: --force)"""

import sys

from .. import config
from ..db import DB
from .build import run

if __name__ == "__main__":
    data = run(DB(config.DATA_DIR / "app.db"), force="--force" in sys.argv)
    if data is None:
        print("오늘 브리핑이 이미 있습니다 (다시 만들려면 --force)")
        raise SystemExit(0)
    print(f"{data['date']} 브리핑을 만들었습니다")
    for key in ("account", "zones", "issues", "schedule"):
        part = data.get(key)
        if isinstance(part, dict) and "error" in part:
            print(f"  ✖ {key}: {part['error']}")
        elif isinstance(part, dict):
            for w in part.get("warnings", []):
                print(f"  ! {key}: {w}")
