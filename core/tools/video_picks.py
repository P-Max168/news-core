#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build ops/video/<YYYY-MM-DD>.json from that day's am + md editions.

Deterministic, no paid API. Input for YouTube Tower Mac mini job (15:30 BKK).

Schema (matches pipeline load_edition / ops_video README):
  { "date", "channel"?, "editions":["YYYY-MM-DD-am","YYYY-MM-DD-md"],
    "items":[{"edition","id","order","angle"}] }

Usage:
  python3 tools/video_picks.py [--date YYYY-MM-DD] [--limit N] [--dry-run]
  python3 tools/video_picks.py 2026-10-28-md   # date inferred from edition id
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parent.parent
SLOTS = ("am", "md")
# Prefer diaspora-relevant topics first; unknown topics get mid rank.
TOPIC_RANK = {
    "visa": 0,
    "weather": 1,
    "east": 2,
    "south": 3,
    "north": 3,
    "society": 4,
    "bangkok": 5,
    "life": 6,
    "poleco": 7,
    "travel": 8,
    "ent": 9,
    "kr": 9,
}
ANGLE_MAX = 48
DEFAULT_LIMIT = 14


def site_channel() -> str:
    name = ROOT.name.lower()
    if name.startswith("vn") or "-vn" in name:
        return "vn"
    if "zh" in name:
        return "zh"
    return "tnews"


def has_hangul(text: str) -> bool:
    return any("\uac00" <= c <= "\ud7a3" for c in (text or ""))


def norm_hl(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").lower())


def angle_from_headline(headline: str) -> str:
    h = re.sub(r"\s+", " ", (headline or "").strip())
    if len(h) <= ANGLE_MAX:
        return h
    cut = h[: ANGLE_MAX + 1]
    # Prefer break at punctuation / space near the end.
    for sep in ("…", " co ", "·", ",", " ", "·"):
        pass
    for i in range(len(cut) - 1, max(20, len(cut) - 16), -1):
        if cut[i] in " …·,、·|":
            return cut[:i].rstrip(" …·,、") + "…"
    if " " in cut:
        return cut.rsplit(" ", 1)[0] + "…"
    return cut[:ANGLE_MAX].rstrip() + "…"


def load_edition(date: str, slot: str) -> dict | None:
    path = ROOT / "data" / f"{date}-{slot}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def story_score(story: dict, index: int) -> tuple:
    topic = (story.get("topic") or "").lower()
    return (TOPIC_RANK.get(topic, 50), index)


def pick_from_edition(ed: dict, date: str, slot: str, taken_norms: list[str], budget: int) -> list[dict]:
    eid = ed.get("id") or f"{date}-{slot}"
    stories = list(ed.get("stories") or [])
    ranked = sorted(enumerate(stories), key=lambda pair: story_score(pair[1], pair[0]))
    out = []
    for _, st in ranked:
        if len(out) >= budget:
            break
        sid = st.get("id")
        hl = (st.get("headline") or "").strip()
        if not sid or not hl or not has_hangul(hl):
            continue
        nh = norm_hl(hl)
        if not nh:
            continue
        if any(SequenceMatcher(None, nh, prev).ratio() > 0.85 for prev in taken_norms):
            continue
        taken_norms.append(nh)
        out.append(
            {
                "edition": eid,
                "id": sid,
                "angle": angle_from_headline(hl),
                "_slot": slot,
            }
        )
    return out


def build(date: str, limit: int, allow_partial: bool) -> dict:
    missing = []
    editions_data = {}
    for slot in SLOTS:
        ed = load_edition(date, slot)
        if ed is None:
            missing.append(f"{date}-{slot}")
        else:
            editions_data[slot] = ed
    if missing and not allow_partial:
        raise SystemExit(
            f"missing edition file(s): {', '.join(missing)} "
            f"(need data/<date>-am.json and data/<date>-md.json). "
            f"Use --allow-partial to proceed with what exists."
        )
    if not editions_data:
        raise SystemExit(f"no am/md edition data for {date}")

    # Split budget across available slots (am gets ceil half when both present).
    n_slots = len(editions_data)
    base = limit // n_slots
    rem = limit - base * n_slots
    budgets = {}
    for i, slot in enumerate(s for s in SLOTS if s in editions_data):
        budgets[slot] = base + (1 if i < rem else 0)

    taken: list[str] = []
    items: list[dict] = []
    # am first, then md — pipeline also ranks am before md.
    for slot in SLOTS:
        if slot not in editions_data:
            continue
        items.extend(pick_from_edition(editions_data[slot], date, slot, taken, budgets[slot]))

    # If under limit (sparse edition), fill from remaining stories in slot order.
    if len(items) < limit:
        for slot in SLOTS:
            if slot not in editions_data or len(items) >= limit:
                continue
            extra = pick_from_edition(
                editions_data[slot], date, slot, taken, limit - len(items)
            )
            # pick_from_edition skips already-taken; may return empty.
            items.extend(extra)

    ordered = []
    for i, it in enumerate(items[:limit], start=1):
        ordered.append(
            {
                "edition": it["edition"],
                "id": it["id"],
                "order": i,
                "angle": it["angle"],
            }
        )

    edition_ids = [f"{date}-{s}" for s in SLOTS if s in editions_data]
    return {
        "date": date,
        "channel": site_channel(),
        "editions": edition_ids,
        "items": ordered,
    }


def parse_date(raw: str | None) -> str:
    if not raw:
        # Bangkok "today"
        from datetime import datetime, timedelta, timezone

        bkk = timezone(timedelta(hours=7))
        return datetime.now(bkk).strftime("%Y-%m-%d")
    raw = raw.strip()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:-(?:am|md|pm))?", raw)
    if not m:
        raise SystemExit(f"bad date/edition id: {raw!r} (want YYYY-MM-DD or YYYY-MM-DD-am|md|pm)")
    return m.group(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "date_or_edition",
        nargs="?",
        default=None,
        help="YYYY-MM-DD or edition id like 2026-10-28-md",
    )
    ap.add_argument("--date", dest="date_flag", default=None, help="YYYY-MM-DD (overrides positional)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"max items (default {DEFAULT_LIMIT})")
    ap.add_argument("--allow-partial", action="store_true", help="ok if only am or only md exists")
    ap.add_argument("--dry-run", action="store_true", help="print JSON, do not write")
    ap.add_argument(
        "--out",
        default=None,
        help="output path (default ops/video/<date>.json)",
    )
    args = ap.parse_args()
    date = parse_date(args.date_flag or args.date_or_edition)
    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")

    payload = build(date, args.limit, args.allow_partial)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    out = pathlib.Path(args.out) if args.out else ROOT / "ops" / "video" / f"{date}.json"
    if args.dry_run:
        sys.stdout.write(text)
        print(f"# dry-run would write {out} ({len(payload['items'])} items)", file=sys.stderr)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} items={len(payload['items'])} editions={payload['editions']}")


if __name__ == "__main__":
    main()
