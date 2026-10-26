"""Temporary publisher handoff. Coordination guard, not an authentication system.

All publishers must fetch main before running this guard. Default actor is grok;
the temporary operator explicitly sets TNK_PUBLISHER=codex. No network or writes.
"""
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]


def permitted(config, actor, now):
    # 2026-10-23 맥스님: Claude 는 상시 비상 발행자. 판마다 tools/edition_claim.py 로 중복을 막는다.
    if actor == "claude":
        return True
    start = datetime.fromisoformat(config["starts"])
    end = datetime.fromisoformat(config["expires"])
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Invalid publisher handoff interval")
    active = start <= now < end
    return actor == config["owner"] if active else actor == "grok"


def main():
    # Other-language repositories keep their own publisher arrangements.
    lang = (ROOT / "site/LANG").read_text(encoding="utf-8").strip()
    if lang != "ko":
        return 0
    actor = os.environ.get("TNK_PUBLISHER", "grok")
    path = ROOT / "ops/publisher.json"
    if not path.exists():
        if actor == "grok":
            return 0
        raise ValueError("Temporary publisher requires an active handoff")
    config = json.loads(path.read_text(encoding="utf-8"))
    if not permitted(config, actor, datetime.now(timezone.utc)):
        print("PUBLISHER HOLD: actor=%s owner=%s expires=%s" %
              (actor, config["owner"], config["expires"]), file=sys.stderr)
        return 4
    print("PUBLISHER OK: " + actor)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as exc:
        print("PUBLISHER FAIL: " + str(exc), file=sys.stderr)
        sys.exit(4)
