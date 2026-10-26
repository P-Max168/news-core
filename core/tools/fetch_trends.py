# -*- coding: utf-8 -*-
"""DEPRECATED: X trend collection is disabled; historical raw files are retained.

  python3 tools/fetch_trends.py <판 id> [개수=15]
    → raw/<판 id>/trends/trends24-<HHMM>.html 저장(원본)
    → raw/<판 id>/trends/trends.json  {fetched, block_time, kept[], filtered[{tag,matched}], url}
    → 화면에 kept 목록 출력. 이것을 보고 tools/editions/<id>.py 의 trends.items 에
       {tag, ko, desc, verified} 로 한국어 번역·설명을 붙인다(README 참고).
- 가장 최근 시간대 블록(보통 1시간 단위)을 쓰고, 부족하면 다음 블록에서 중복 없이 채운다.
- 차단 목록: tools/trend_blocklist.txt (newslib.blocked 와 같은 규칙). 걸린 태그는 버리고 개수만 기록.
"""
import sys, re, json, html, pathlib, urllib.request
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import newslib

URL = "https://trends24.in/thailand/"
BKK = timezone(timedelta(hours=7))


def parse(h):
    blocks = []
    for m in re.finditer(r'data-timestamp=([\d.]+)>.*?<ol class=trend-card__list>(.*?)</ol>', h, flags=re.S):
        ts = datetime.fromtimestamp(float(m.group(1)), BKK)
        tags = [html.unescape(t).strip() for t in re.findall(r'class=trend-link>(.*?)</a>', m.group(2), flags=re.S)]
        blocks.append((ts, tags))
    return blocks


def main():
    raise SystemExit("X 트렌드 수집은 중단되었습니다. 기존 raw/<id>/trends 자료만 보존합니다.")

    eid = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    out = newslib.ROOT / "raw" / eid / "trends"
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(BKK)
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})
    h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    (out / ("trends24-%s.html" % now.strftime("%H%M"))).write_text(h, encoding="utf-8")
    blocks = parse(h)
    if not blocks:
        raise SystemExit("trends24 구조가 바뀐 듯: 블록을 찾지 못함")
    kept, filtered, seen = [], [], set()
    for ts, tags in blocks[:3]:
        for t in tags:
            k = t.lower()
            if k in seen:
                continue
            seen.add(k)
            hit = newslib.blocked(t)
            if hit:
                filtered.append({"tag": t, "matched": hit})
                continue
            if len(kept) < n:
                kept.append(t)
        if len(kept) >= n:
            break
    res = {"url": URL, "fetched": now.isoformat(timespec="seconds"),
           "block_time": blocks[0][0].isoformat(timespec="seconds"),
           "kept": kept, "filtered": filtered}
    (out / "trends.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("fetched:", res["fetched"], "| 최신 블록:", res["block_time"])
    print("필터됨(성인·선정적):", len(filtered), [f["tag"] for f in filtered])
    for i, t in enumerate(kept, 1):
        print("%2d. %s" % (i, t))


if __name__ == "__main__":
    main()
