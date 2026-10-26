# -*- coding: utf-8 -*-
"""trends24.in 해시태그 목록을 '기사 카드'로 만든 것(source/url 이 trends24)을 판 데이터에서 뺀다.
  python3 tools/strip_trend_cards.py          # data/*.json|js + tools/editions/*.py 정리 후 index 재생성
트렌드는 판의 trends 상자(trends.items)에만 둔다 — tools/TRANSLATION_RULES.md (2026-10-03 Mingoo 요청).
trends 상자 자체(data["trends"])는 건드리지 않는다. newslib.validate 도 이런 카드를 막는다."""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import newslib  # noqa: E402


def is_trend_card(s):
    return "trends24" in (s.get("source", "") + " " + s.get("url", "")).lower()


def strip_data():
    n = 0
    for p in sorted((ROOT / "data").glob("20*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        bad = [s["id"] for s in d.get("stories", []) if is_trend_card(s)]
        if not bad:
            continue
        d["stories"] = [s for s in d["stories"] if not is_trend_card(s)]
        if isinstance(d.get("highlights"), list):
            assert not set(bad) & set(d["highlights"]), (p.name, "highlights 에 트렌드 카드")
        if isinstance(d.get("briefing"), list):
            d["briefing"] = [b for b in d["briefing"] if b.get("story_id") not in bad]
        eid = p.stem
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        (p.with_suffix(".js")).write_text("window.NEWS_DATA = window.NEWS_DATA || {};\nwindow.NEWS_DATA[%s] = %s;\n" % (
            json.dumps(eid), json.dumps(d, ensure_ascii=False)), encoding="utf-8")
        print("data:", eid, "삭제", bad); n += len(bad)
    return n


BLOCK = re.compile(r'^dict\(id="[^"]+",.*?\n tags=\[[^\]]*\]\),\n', re.S | re.M)


def strip_editions():
    for p in sorted((ROOT / "tools/editions").glob("20*.py")):
        src = p.read_text(encoding="utf-8")
        out, removed = [], []
        pos = 0
        for m in BLOCK.finditer(src):
            blk = m.group(0)
            if re.search(r'^ source="trends24\.in"', blk, re.M):
                out.append(src[pos:m.start()]); pos = m.end(); removed.append(re.match(r'dict\(id="([^"]+)"', blk).group(1))
        if removed:
            out.append(src[pos:])
            p.write_text("".join(out), encoding="utf-8")
            print("editions:", p.name, "삭제", removed)


if __name__ == "__main__":
    strip_data(); strip_editions(); newslib.build_index()
