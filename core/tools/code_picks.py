# -*- coding: utf-8 -*-
"""코드 고르기(2026-10-25 Claude, 맥스님 14:44 결정 '모든 뉴스판 구조 통일 — 고르기도 코드+제미나이, 그록은 감시만').

    python3 tools/code_picks.py <판 id> [--candidates drafts/candidates/latest.json] [--pool 30] [--select 20] [--out ops/picks/<판 id>.json]

후보 목록(collect.py 가 만드는 candidates/latest.json)에서 제미나이에게 넘길 후보 pool 건을 코드로 고른다 — AI·토큰 0.
  1) Google News 중계 주소는 뺌(원문 주소가 아니라 제미나이 단계에서 어차피 빠짐)
  2) 최근 판(data/index.json 의 최근 6판)에 실린 원문 주소·같은 제목은 뺌
  3) 순서: 여러 매체가 함께 보도한 기사(also 많은 것) → 외국인·비자 → 나머지, 그 안에서 매체를 번갈아 최신순
     (한 매체에 몰리지 않게 — 베트남판·KSTAR 와 같은 방식)
결과 picks 파일에 "picker": "code", "select": N 을 적음 → tools/gemini_edition.py 가 제미나이에게 후보 pool 건 중 최대 N 건을 고르게 함.
"""
import argparse, difflib, json, pathlib, re, sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
BKK = timezone(timedelta(hours=7))


def norm(t):
    return re.sub(r"\W+", "", (t or "").lower())


def recent(n=6):
    urls, titles = set(), []
    try:
        idx = json.loads((ROOT / "data" / "index.json").read_text(encoding="utf-8"))
        for e in (idx.get("editions") or [])[:n]:
            d = json.loads((ROOT / "data" / (e["id"] + ".json")).read_text(encoding="utf-8"))
            for s in d.get("stories", []):
                urls.add(s.get("url")); titles.append(norm(s.get("title_th")))
                for a in s.get("also") or []:
                    urls.add(a.get("url"))
    except Exception:
        pass
    return urls, titles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eid"); ap.add_argument("--candidates", default=str(ROOT / "drafts" / "candidates" / "latest.json"))
    ap.add_argument("--pool", type=int, default=30); ap.add_argument("--select", type=int, default=20); ap.add_argument("--out")
    ap.add_argument("--hours", type=float, default=16, help="이보다 오래된 후보는 뺌(판 시각 기준)")
    a = ap.parse_args()
    cj = json.loads(pathlib.Path(a.candidates).read_text(encoding="utf-8"))
    used_urls, used_titles = recent()
    now = datetime.now(BKK)
    seen, rows = set(), []
    for tid, tv in (cj.get("topics") or {}).items():
        for x in (tv.get("items") if isinstance(tv, dict) else tv) or []:
            u = str(x.get("url") or "")
            if not u.startswith("http") or "news.google.com" in u or u in seen or u in used_urls:
                continue
            try:
                pub = datetime.fromisoformat(str(x.get("published")).replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=BKK)
            except Exception:
                continue
            if now - pub > timedelta(hours=a.hours) or pub - now > timedelta(hours=1):
                continue
            nt = norm(x.get("title"))
            if not nt or any(t and difflib.SequenceMatcher(None, nt, t).ratio() > .85 for t in used_titles):
                continue
            seen.add(u)
            also = [dict(source=al.get("outlet") or al.get("source"), url=al["url"]) for al in x.get("also") or []
                    if isinstance(al, dict) and str(al.get("url", "")).startswith("http") and "news.google.com" not in al["url"]]
            rows.append(dict(url=u, source=x.get("outlet") or "", title=x.get("title") or "", published=pub.isoformat(timespec="seconds"),
                             also=also, _visa="visa" in (x.get("topics") or [tid]), _ts=pub.timestamp()))
    # 같은 사건 다른 매체(제목이 아주 비슷)는 하나만 — also 가 더 많은 쪽을 남김
    rows.sort(key=lambda r: (-len(r["also"]), -r["_ts"]))
    uniq = []
    for r in rows:
        if any(difflib.SequenceMatcher(None, norm(r["title"]), norm(q["title"])).ratio() > .85 for q in uniq):
            continue
        uniq.append(r)
    multi = [r for r in uniq if len(r["also"]) >= 1]
    visa = [r for r in uniq if r not in multi and r["_visa"]]
    rest = [r for r in uniq if r not in multi and r not in visa]
    order = multi + visa
    by = {}
    for r in sorted(rest, key=lambda r: -r["_ts"]):
        by.setdefault(r["source"], []).append(r)
    while any(by.values()):
        for k in list(by):
            if by[k]:
                order.append(by[k].pop(0))
    picks = [{k: v for k, v in r.items() if not k.startswith("_")} for r in order[:a.pool]]
    out = pathlib.Path(a.out or ROOT / "ops" / "picks" / (a.eid + ".json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(edition=a.eid, picker="code", select=a.select, picks=picks), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("code_picks %s: 후보 %d건(원문 주소) → 넘김 %d건(여러 매체 %d · 비자 %d) → %s" % (a.eid, len(rows), len(picks), len(multi), len(visa), out))
    return 0 if len(picks) >= 4 else 3


if __name__ == "__main__":
    sys.exit(main())
