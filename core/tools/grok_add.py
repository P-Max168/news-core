# -*- coding: utf-8 -*-
"""그록 추가 기사(ops/grok-add/<판 id>.json) 읽기·검사 (2026-10-30 Claude, 설계서 '기사 고르기 통합 v1' 3절).

모든 채널 공통 흐름: 코드가 기본 목록(후보 pool 건)을 만들고, 그록은 코드가 놓친 중요 기사를 최대 4건 보탠다.
그록을 믿는 게 아니라 이 코드가 규칙을 강제한다:
  1. 최대 4건(넘으면 뒤에서부터 뺌)
  2. 기사 주소가 그 채널 수집처 목록(site json edition.grok_add.sources)의 매체여야 함 — X·블로그·유튜브·Google News 중계 주소 금지
  3. 24시간 안에 나온 기사, 최근 6판에 실린 주소는 뺌
  4. 평소에는 같은 사건 1건(기본 목록·다른 추가분과 제목이 거의 같으면 뺌)
  5. big_event 가 있으면 같은 사건 4건까지 허용 — 단 angle(현장/정부 발표/교통·생활/외국인·관광객 …)이 서로 달라야 함
  6. boost: 이미 기본 목록에 있는 기사 → 새로 넣지 않고 기본 목록 맨 앞으로(4건에 안 셈)
  7. 이미 기본 목록에 있는 주소를 add 에 넣었으면 boost 로 바꿈

    python3 tools/grok_add.py check <판 id>          # 그록이 올린 파일을 지금 규칙으로 검사(무엇이 빠질지·이유) — 그록·사람용
    python3 tools/grok_add.py check <판 id> --file x.json
"""
import argparse, difflib, json, pathlib, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
BKK = timezone(timedelta(hours=7))
MAX_ADD = 4
MAX_AGE_H = 24
BAD_HOSTS = ("news.google.com", "x.com", "twitter.com", "t.co", "youtube.com", "youtu.be", "facebook.com", "fb.watch",
             "instagram.com", "tiktok.com", "threads.net", "pantip.com", "blogspot.", "wordpress.com", "medium.com", "line.me")


def norm_host(h):
    h = (h or "").lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _walk_strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _walk_strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_strings(v)


def _publishable(x):
    """수집처 목록에서 운영 발행이 막힌 항목(production: false · disabled)을 뺀다(코덱스 리뷰: VnExpress International 은 RSS 약관상 발행 제외)."""
    if isinstance(x, dict):
        if x.get("production") is False or x.get("disabled"):
            return {}
        return {k: _publishable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_publishable(v) for v in x]
    return x


def source_domains(paths):
    """수집처 목록 파일들 → 허용 도메인 집합. 파일 안의 모든 http 주소와 'site:도메인'(Google News 검색 소스)을 모은다.
    경로가 https:// 로 시작하면 받아 온다(ZH 처럼 한국판 수집처를 같이 쓰는 채널)."""
    doms = set()
    for p in paths or []:
        try:
            if str(p).startswith("https://"):
                with urllib.request.urlopen(urllib.request.Request(p, headers={"User-Agent": "news-core grok_add"}), timeout=20) as r:
                    j = json.loads(r.read().decode("utf-8"))
            else:
                j = json.loads((ROOT / p).read_text(encoding="utf-8"))
        except Exception as ex:
            print("grok_add: 수집처 목록 못 읽음 %s (%s)" % (p, str(ex)[:60]), file=sys.stderr)
            continue
        for s in _walk_strings(_publishable(j)):
            for u in re.findall(r"https?://[^\s\"'<>]+", s):
                h = norm_host(urlparse(u).netloc)
                if h and "news.google.com" not in h:
                    doms.add(h)
            for d in re.findall(r"site:([a-z0-9.-]+\.[a-z]{2,})", s, re.I):
                doms.add(norm_host(d))
    return doms


def host_ok(url, doms):
    h = norm_host(urlparse(url).netloc)
    if not h or any(b in h for b in BAD_HOSTS):
        return False
    if not doms:   # 목록을 못 읽었으면 막지 않음(금지 호스트만 거름) — 기록에 남김
        return True
    return any(h == d or h.endswith("." + d) or d.endswith("." + h) for d in doms)


def _norm_title(t):
    return re.sub(r"\W+", "", (t or "").lower())


def _similar(a, b, r=0.85):
    a, b = _norm_title(a), _norm_title(b)
    return bool(a and b) and difflib.SequenceMatcher(None, a, b).ratio() > r


def _pub(x):
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=BKK)
    except Exception:
        return None


def recent_urls(n=6):
    urls = set()
    try:
        idx = json.loads((ROOT / "data" / "index.json").read_text(encoding="utf-8"))
        for e in (idx.get("editions") or [])[:n]:
            d = json.loads((ROOT / "data" / (e["id"] + ".json")).read_text(encoding="utf-8"))
            for s in d.get("stories") or []:
                urls.add(s.get("url"))
                for a in s.get("also") or []:
                    urls.add(a.get("url"))
    except Exception:
        pass
    return urls


def _big_today(eid):
    """오늘 다른 판에서 큰 사건 특집을 쓴 횟수(data/<날짜>-am|md|pm.json 의 big_event 기사)."""
    n = 0
    for s in ("am", "md", "pm"):
        e = "%s-%s" % (eid[:10], s)
        if e == eid:
            continue
        try:
            d = json.loads((ROOT / "data" / (e + ".json")).read_text(encoding="utf-8"))
            n += any(x.get("big_event") for x in d.get("stories") or [])
        except Exception:
            pass
    return n


def load(eid, base, conf=None, now=None, path=None, cand=None):
    """그록 추가 파일을 검사해 결과 dict:
      adds[] (기본 목록 앞에 넣을 picks 항목, must_keep=True), boost_urls[], promote[](후보 목록에만 있던 boost 기사), dropped[{url, why}],
      big_event(key|""), found(bool), file
    base = 기본 목록 picks [{url,title,…}]. cand = 후보 목록 {url: 항목} — 그록은 후보 전체(latest.md)를 보고 boost 하므로
    기본 목록(상위 pool 건)에 없는 후보도 boost 할 수 있다 → 기본 목록 맨 앞으로 끌어올림(4건에 안 셈)."""
    conf = dict(conf or {})
    now = now or datetime.now(BKK)
    pf = pathlib.Path(path) if path else ROOT / "ops" / "grok-add" / (eid + ".json")
    res = dict(found=False, file=str(pf.relative_to(ROOT)) if str(pf).startswith(str(ROOT)) else str(pf), adds=[], boost_urls=[], promote=[], dropped=[], big_event="")
    cand = cand or {}
    if not pf.exists():
        return res
    try:
        g = json.loads(pf.read_text(encoding="utf-8"))
    except Exception as ex:
        res["dropped"].append(dict(url="", why="파일 형식 오류: %s" % str(ex)[:80]))
        return res
    if not isinstance(g, dict):   # [] · null 같은 모양이면 판을 멈추지 않고 코드 목록만(코덱스 리뷰)
        res["dropped"].append(dict(url="", why="파일 모양 오류(객체가 아님)"))
        return res
    g["add"] = [x for x in (g.get("add") if isinstance(g.get("add"), list) else []) if isinstance(x, (dict, str))]
    g["boost"] = [x if isinstance(x, dict) else {"url": str(x)} for x in (g.get("boost") if isinstance(g.get("boost"), list) else [])]
    res["found"] = True
    cutoff = conf.get("_cutoff")   # run_edition 이 판 마감(발행 예약 시각)을 넣어 줌
    sub = conf.get("_submitted")   # 파일이 저장소에 올라온 시각(git) — 없으면 파일의 at
    if cutoff is not None:
        sub = sub or _pub(g.get("at"))
        if sub is None or sub > cutoff:
            res["dropped"].append(dict(url="", why="마감(%s) 뒤에 올라온 파일(%s) — 이번 판은 코드 목록만" % (
                cutoff.strftime("%H:%M"), sub.strftime("%H:%M") if sub else "시각 모름")))
            res["late"] = True
            return res
    if str(g.get("edition") or eid) != eid:
        res["dropped"].append(dict(url="", why="edition 값이 다름(%s)" % g.get("edition")))
        return res
    max_add = int(conf.get("max", MAX_ADD))
    doms = source_domains(conf.get("sources") or [])
    base_urls = {b.get("url") for b in base}
    used = recent_urls()
    big = g.get("big_event") if isinstance(g.get("big_event"), dict) else None
    big_key = re.sub(r"[^a-z0-9-]", "", str((big or {}).get("key") or "").lower())[:60] if big else ""
    if big and not big_key:
        res["dropped"].append(dict(url="", why="big_event 에 key 없음 — 큰 사건 예외 안 씀"))
    if big_key and int(conf.get("big_per_day", 1)) <= _big_today(eid):
        res["dropped"].append(dict(url="", why="큰 사건은 채널당 하루 %d회 — 오늘 이미 씀, 평소 규칙으로" % int(conf.get("big_per_day", 1))))
        big_key = ""
    res["big_event"] = big_key
    angles = set()
    for b in g.get("boost") or []:
        u = str((b or {}).get("url") or "")
        if u in base_urls:
            res["boost_urls"].append(u)
        elif u in cand and host_ok(u, doms) and u not in used and not any(p["url"] == u for p in res["promote"]):
            c = cand[u]
            pub = _pub(c.get("published"))
            if pub and now - pub <= timedelta(hours=MAX_AGE_H):
                res["promote"].append(dict(url=u, source=str(c.get("outlet") or c.get("source") or "")[:60], title=str(c.get("title") or "")[:300],
                                           published=pub.isoformat(timespec="seconds"), memo="[그록 boost] X에서 뜨는 중", also=c.get("also") or []))
            else:
                res["dropped"].append(dict(url=u, why="boost 후보가 24시간 지남"))
        elif u:
            res["dropped"].append(dict(url=u, why="boost 인데 후보 목록에 없는 주소(Google News 중계·다른 주소?)"))
    for a in g.get("add") or []:
        a = a if isinstance(a, dict) else {"url": str(a)}
        u = str(a.get("url") or "")
        why = ""
        pub = _pub(a.get("published"))
        if not u.startswith("http"):
            why = "주소 없음"
        elif not host_ok(u, doms):
            why = "수집처 목록에 없는 매체/금지 주소(%s)" % norm_host(urlparse(u).netloc)
        elif u in base_urls:
            res["boost_urls"].append(u); continue   # 이미 기본 목록에 있음 → 앞으로만
        elif u in used:
            why = "최근 6판에 실린 기사"
        elif not a.get("title") or not a.get("source"):
            why = "title·source 없음"
        elif not pub:
            why = "published 없음/형식 오류"
        elif now - pub > timedelta(hours=MAX_AGE_H) or pub - now > timedelta(hours=1):
            why = "24시간 지난 기사(%s)" % pub.isoformat(timespec="minutes")
        elif len(res["adds"]) >= max_add:
            why = "최대 %d건 초과" % max_add
        elif big_key:
            ang = str(a.get("angle") or "").strip()
            if not ang:
                why = "큰 사건인데 angle 없음"
            elif ang in angles:
                why = "큰 사건 angle 중복(%s)" % ang
            else:
                angles.add(ang)
        else:
            if any(_similar(a.get("title"), b.get("title")) for b in base):
                why = "기본 목록에 같은 사건"
            elif any(_similar(a.get("title"), x.get("title")) for x in res["adds"]):
                why = "추가분끼리 같은 사건"
        if why:
            res["dropped"].append(dict(url=u, why=why)); continue
        res["adds"].append(dict(url=u, source=str(a.get("source"))[:60], title=str(a.get("title"))[:300],
                                published=pub.isoformat(timespec="seconds"),
                                memo=("[그록 추가] %s" % str(a.get("why") or "")[:300]).strip(), must_keep=True, picked_by="grok",
                                big_event=big_key, angle=str(a.get("angle") or "")[:40]))
    res["boost_urls"] = list(dict.fromkeys(res["boost_urls"]))
    return res


def merge(base_doc, res, select):
    """기본 목록 picks 문서 + 검사 결과 → 제미나이에 넘길 picks 문서. 순서: 그록 추가 → boost → 나머지 기본 목록."""
    base = list(base_doc.get("picks") or [])
    boost = [b for u in res["boost_urls"] for b in base if b.get("url") == u] + list(res.get("promote") or [])
    rest = [b for b in base if b.get("url") not in set(res["boost_urls"])]
    picks = res["adds"] + boost + rest
    doc = dict(base_doc, picks=picks, picker="code", select=int(select or base_doc.get("select") or 20))
    doc["grok_add"] = dict(adds=len(res["adds"]), boost=len(boost), dropped=res["dropped"], big_event=res["big_event"], found=res["found"])
    return doc


def path_label(res):
    if not res.get("adds"):
        return "code"
    return "code+grok-big" if res.get("big_event") else "code+grok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"]); ap.add_argument("eid"); ap.add_argument("--file")
    ap.add_argument("--base", help="기본 목록 picks 파일(없으면 ops/base/<판 id>.json, 그것도 없으면 빈 목록)")
    a = ap.parse_args()
    import siteconf
    conf = (siteconf.load().get("edition") or {}).get("grok_add") or {}
    bp = pathlib.Path(a.base) if a.base else ROOT / "ops" / "base" / (a.eid + ".json")
    base = json.loads(bp.read_text(encoding="utf-8")).get("picks", []) if bp.exists() else []
    res = load(a.eid, base, conf, path=a.file)
    print(json.dumps(dict(found=res["found"], adds=[x["url"] for x in res["adds"]], boost=res["boost_urls"], big_event=res["big_event"],
                          dropped=res["dropped"], path=path_label(res)), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
