# -*- coding: utf-8 -*-
"""Google News RSS 레이더(2026-10-18): 우리 소스가 놓친 사건 찾기 + 화제성(보도 매체 수) 점수.

  python3 tools/gnews_scan.py                    # tools/gnews_keywords.json 검색어, 최근 18시간
  python3 tools/gnews_scan.py --hours 12 --edition 2026-10-18-pm
  python3 tools/gnews_scan.py --record 2026-10-18-pm '[{"google_title":"…","outlet":"…","source_url":"…","our_title":"…"}]'
      → 판마다 실제로 쓴 '놓친 기사'를 /cursor/stores/<봇>/gnews_reports.json 에 한 줄 추가(없으면 [] 로 만듦)

- ko(hl=ko, gl=TH)·en(hl=en-US, gl=TH) 검색 + 'when:1d', pubDate 가 --hours 안쪽인 항목만.
- 제목이 비슷한 항목을 '사건'으로 묶고, 사건마다 서로 다른 매체 수 = hotness(화제성).
- 우리가 이미 모은 것과 비교: drafts/candidates/latest.json(tools/collect.py 결과, 후보 + also) +
  data/<판>.json 기사(headline·title_th·url·also) — 직전 판과 --edition 판. 같은 링크(GN 링크 또는 풀린 원문 URL)
  이거나 제목이 비슷하면 '우리 것(covered)', 아니면 'missed'.
- missed 사건은 원문 URL 을 googlenewsdecoder 로 풀어 본다. 못 풀면 매체 이름 + 제목만(편집자가 원문 검색).
- 결과: drafts/gnews/<시각>.json·latest.json·latest.md (drafts/ 는 .gitignore) + 화면에 짧은 요약.
- **발견용일 뿐**: 피드 제목·내용을 사이트에 다시 게시하지 않는다. 기사는 원 매체 페이지를 열어 직접 쓴다(README).
- 가져오기 실패는 판을 막지 않는다: 검색어마다 1번 다시 시도, 그래도 안 되면 로그만 남기고 빈 결과로 exit 0.
"""
import argparse, difflib, html, json, os, pathlib, re, sys, time, traceback
import urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONF = ROOT / "tools" / "gnews_keywords.json"
OUTDIR = ROOT / "drafts" / "gnews"
REPORTS = pathlib.Path(os.environ.get("GNEWS_REPORTS",
                       "/cursor/stores/store-7f8a67fb-8a1e-4410-b2ae-b38500b36be0/gnews_reports.json"))
BKK = timezone(timedelta(hours=7))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
LOCALE = {"ko": "hl=ko&gl=TH&ceid=TH:ko", "en": "hl=en-US&gl=TH&ceid=TH:en"}
# 제목 비교 때 뺄 흔한 낱말(검색어 자체·조사·영어 기능어) — 이것만 겹쳐서 같은 사건으로 묶이지 않게
STOP = set("""태국 태국의 태국서 태국에서 방콕 방콕서 방콕에서 파타야 파타야서 파타야에서 스리라차 비자 한국 한국인 위해 관련 대한 이번 오늘 기자
종합 속보 단독 사진 영상 뉴스 the a an of in on at to for and or with from by as is are was be after over amid new news
thailand thai bangkok pattaya visa says said its it this that will has have more than into up""".split())


def log(msg):
    line = "%s gnews_scan: %s" % (datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, file=sys.stderr)
    try:
        OUTDIR.mkdir(parents=True, exist_ok=True)
        with open(OUTDIR / "scan.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def domain(u):
    h = urllib.parse.urlparse(u if "//" in u else "//" + u).netloc.lower().split(":")[0]
    for p in ("www.", "m.", "amp."):
        if h.startswith(p):
            h = h[len(p):]
    return h


def nurl(u):
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").replace("http://", "https://")


def toks(t):
    t = html.unescape(t or "").lower()
    out = set()
    for w in re.findall(r"[0-9a-z]+(?:[.,][0-9]+)?|[가-힣]+|[\u0E00-\u0E7F]+", t):
        if re.fullmatch(r"[가-힣]+", w) and len(w) > 2:   # 한국어 조사 떼기(대충): 은/는/이/가/을/를/의/에/서/로/과/와/도
            w = re.sub(r"(에서|으로|에게|까지|부터|은|는|이|가|을|를|의|에|서|로|과|와|도)$", "", w)
        if len(w) >= 2 and w not in STOP:
            out.add(w)
    return out


def similar(a, b, ta=None, tb=None):
    """제목 유사도 0~1: 글자 비교(SequenceMatcher)와 낱말 겹침(작은 쪽 기준) 중 큰 값."""
    na, nb = re.sub(r"[\W_]+", "", a.lower()), re.sub(r"[\W_]+", "", b.lower())
    if not na or not nb:
        return 0.0
    r = 0.0
    sm = difflib.SequenceMatcher(None, na, nb)
    if sm.real_quick_ratio() > 0.55 and sm.quick_ratio() > 0.55:
        r = sm.ratio()
    ta, tb = ta if ta is not None else toks(a), tb if tb is not None else toks(b)
    if len(ta) >= 2 and len(tb) >= 2:
        inter = len(ta & tb)
        if inter >= 2:
            r = max(r, inter / min(len(ta), len(tb)))
    return r


def fetch(url, timeout=25):
    last = None
    for attempt in (1, 2):   # 1번 다시 시도
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 판을 막지 않음
            last = e
            if attempt == 1:
                time.sleep(3)
    raise last


def search(lang, q, hours, now, req=None, bad=None):
    u = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d") + "&" + LOCALE[lang]
    root = ET.fromstring(fetch(u))
    out = []
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "").strip()
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None else ""
        surl = src.get("url", "") if src is not None else ""
        if outlet:
            title = re.sub(r"\s+-\s+" + re.escape(outlet) + r"\s*$", "", title)
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate")).astimezone(BKK)
        except Exception:  # noqa: BLE001
            continue
        if pub < now - timedelta(hours=hours) or pub > now + timedelta(hours=1):
            continue
        if req and not req.search(title):   # 제목에 태국 관련 낱말이 없으면(예: 방콕 IMF 회의 계기 한국 경제 기사) 버림
            continue
        if bad and (bad(title) or bad(outlet) or bad(domain(surl))):   # 성인·스팸·SNS·제외 매체
            continue
        out.append(dict(title=title, outlet=outlet or domain(surl), outlet_domain=domain(surl), gn_link=it.findtext("link") or "",
                        published=pub, lang=lang, query=q))
    return out


def our_corpus(edition):
    """우리 쪽: collect.py 후보(+also) + 판 기사. [{title, url, outlet, kind}]"""
    items, used = [], []
    cand = ROOT / "drafts" / "candidates" / "latest.json"
    if cand.exists():
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
            used.append("candidates %s (%s건)" % (d.get("generated", "?"), d.get("candidates", "?")))
            seen = set()
            for t in d.get("topics", {}).values():
                for i in t.get("items", []):
                    if i["url"] in seen:
                        continue
                    seen.add(i["url"])
                    items.append(dict(title=i["title"], url=i["url"], outlet=i.get("outlet", ""), kind="candidate"))
                    for a in i.get("also", []):
                        items.append(dict(title=a.get("title") or i["title"], url=a.get("url", ""), outlet=a.get("outlet", ""),
                                          kind="candidate"))
        except Exception as e:  # noqa: BLE001
            log("후보 파일 읽기 실패: %s" % e)
    else:
        log("drafts/candidates/latest.json 없음 — tools/collect.py 를 먼저 돌리면 비교가 정확해짐")
    eds = []
    try:
        eds.append(json.loads((ROOT / "data" / "index.json").read_text(encoding="utf-8")).get("latest"))
    except Exception:  # noqa: BLE001
        pass
    if edition:
        eds.append(edition)
    for e in dict.fromkeys(x for x in eds if x):
        f = ROOT / "data" / ("%s.json" % e)
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        used.append("data/%s.json (%d건)" % (e, len(d.get("stories", []))))
        for s in d.get("stories", []):
            for t in (s.get("headline", ""), s.get("title_th", ""), s.get("title_en", "")):
                if t:
                    items.append(dict(title=t, url=s.get("url", ""), outlet=s.get("source", ""), kind="edition:" + e,
                                      our_title=s.get("headline", "")))
            for a in s.get("also", []) or []:
                items.append(dict(title="", url=a.get("url", ""), outlet=a.get("source", ""), kind="edition:" + e,
                                  our_title=s.get("headline", "")))
    for i in items:
        i["_t"] = toks(i["title"])
        i["_u"] = nurl(i["url"])
    return items, used


def group(items, thr):
    events = []
    for it in sorted(items, key=lambda x: x["published"]):
        it["_t"] = toks(it["title"])
        best, bs = None, 0.0
        for ev in events:
            s = max(similar(it["title"], m["title"], it["_t"], m["_t"]) for m in ev["items"][:8])
            if s > bs:
                best, bs = ev, s
        if best and bs >= thr:
            best["items"].append(it)
        else:
            events.append(dict(items=[it]))
    return events


def make_bad(extra=None):
    """버릴 항목 판정: tools/trend_blocklist.txt(성인·선정) + sources.json exclude_outlets + SNS·커뮤니티(collect.py 와 같은 기준)."""
    pats = [re.compile(r"pantip|thailove|facebook|tiktok|youtube|instagram|twitter|x\.com|blockdit|lemon8|threads", re.I)]
    if extra:   # gnews_keywords.json exclude(도박·스팸 등)
        pats.append(re.compile(extra, re.I))
    try:
        pats += [re.compile(r"^(?:%s)$" % x, re.I) for x in json.loads((ROOT / "tools" / "sources.json").read_text(encoding="utf-8")).get("exclude_outlets", [])]
    except Exception:  # noqa: BLE001
        pass
    try:
        for ln in (ROOT / "tools" / "trend_blocklist.txt").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                pats.append(re.compile(ln[3:] if ln.startswith("re:") else re.escape(ln), re.I))
    except Exception:  # noqa: BLE001
        pass
    return lambda t: bool(t) and any(p.search(t) for p in pats)


def decode(gn_link):
    try:
        from googlenewsdecoder import gnewsdecoder
        r = gnewsdecoder(gn_link, interval=1)
        if (r.get("success") or r.get("status")) and r.get("decoded_url"):
            return r["decoded_url"]
    except Exception as e:  # noqa: BLE001
        log("URL 풀기 실패: %s" % e)
    return ""


def record(edition, items_json):
    items = json.loads(items_json)
    keys = ("google_title", "outlet", "source_url", "our_title")
    items = [{k: str(i.get(k, "")) for k in keys} for i in items]
    REPORTS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(REPORTS.read_text(encoding="utf-8")) if REPORTS.exists() and REPORTS.read_text().strip() else []
    data = [d for d in data if d.get("edition") != edition] + [dict(edition=edition, items=items)]
    REPORTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("기록: %s %d건 → %s (총 %d판)" % (edition, len(items), REPORTS, len(data)))


def ensure_reports():
    try:
        if not REPORTS.exists():
            REPORTS.parent.mkdir(parents=True, exist_ok=True)
            REPORTS.write_text("[]\n", encoding="utf-8")
    except OSError as e:
        log("보고 파일 만들기 실패(%s): %s" % (REPORTS, e))


def write(result, now):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    js = json.dumps(result, ensure_ascii=False, indent=1)
    lines = ["# Google News 레이더 %s (최근 %sh, 검색 %d/%d 성공, 항목 %d · 사건 %d · missed %d)" % (
        now.strftime("%Y-%m-%d %H:%M BKK"), result["hours"], result["queries_ok"], result["queries_total"],
        result["items"], len(result["events"]), len(result["missed"])), "",
        "※ 발견용 — 피드 제목·내용을 사이트에 옮기지 않는다. 쓰려면 원 매체 페이지를 열어 직접 확인하고 쓴다.", "",
        "## 놓친 사건(missed) — 화제성 순"]
    for e in result["missed"][:20]:
        lines.append("- [%d곳] %s — %s  \n  원문: %s" % (e["hotness"], e["google_title"], e["outlet"],
                                                     e["source_url"] or "(못 풂 — 매체·제목으로 검색)"))
    lines += ["", "## 우리가 이미 가진 사건 — 화제성"]
    for e in result["covered"][:25]:
        lines.append("- [%d곳] %s ↔ 우리: %s (%s)" % (e["hotness"], e["google_title"], e["matched_title"][:70], e["matched_kind"]))
    md = "\n".join(lines) + "\n"
    for name in (now.strftime("%Y%m%d-%H%M"), "latest"):
        (OUTDIR / (name + ".json")).write_text(js, encoding="utf-8")
        (OUTDIR / (name + ".md")).write_text(md, encoding="utf-8")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float)
    ap.add_argument("--edition", help="비교에 넣을 판 id(data/<id>.json, 기본은 data/index.json 의 latest)")
    ap.add_argument("--group", type=float, default=0.5, help="같은 사건으로 묶는 제목 유사도(기본 0.5)")
    ap.add_argument("--match", type=float, default=0.5, help="우리 것과 같다고 볼 제목 유사도(기본 0.5)")
    ap.add_argument("--decode-max", type=int, default=15, help="원문 URL 을 풀어 볼 missed 사건 수(기본 15)")
    ap.add_argument("--record", nargs=2, metavar=("EDITION", "ITEMS_JSON"))
    a = ap.parse_args()
    ensure_reports()
    if a.record:
        return record(*a.record)
    now = datetime.now(BKK)
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    hours = a.hours or conf.get("hours", 18)
    req = {l: re.compile(r, re.I) for l, r in (conf.get("require") or {}).items()}
    bad = make_bad(conf.get("exclude"))
    queries = [(l, q) for l in ("ko", "en") for q in conf.get(l, [])]
    items, fails = [], []
    for lang, q in queries:
        try:
            items += search(lang, q, hours, now, (req or {}).get(lang), bad)
        except Exception as e:  # noqa: BLE001
            fails.append("%s:%s (%s)" % (lang, q, e))
            log("검색 실패(2번 시도) %s:%s — %s" % (lang, q, e))
    result = dict(generated=now.isoformat(timespec="seconds"), hours=hours, queries_total=len(queries),
                  queries_ok=len(queries) - len(fails), failed=fails, items=0, compared_with=[], events=[], missed=[], covered=[])
    # 같은 GN 링크(여러 검색어에 걸림)는 하나로
    uniq = {}
    for it in items:
        uniq.setdefault(it["gn_link"] or (it["outlet"] + it["title"]), it)
    items = list(uniq.values())
    result["items"] = len(items)
    if not items:
        log("항목 0개 — 빈 결과(판은 그대로 진행)")
        print(write(result, now))
        return
    ours, used = our_corpus(a.edition)
    result["compared_with"] = used
    by_url = {}
    for o in ours:
        if o["_u"]:
            by_url.setdefault(o["_u"], o)
    events = group(items, a.group)
    out = []
    for ev in events:
        its = ev["items"]
        outlets = sorted({i["outlet"] for i in its if i["outlet"]})
        rep = max(its, key=lambda i: len(i["title"]))   # 대표 = 가장 긴(자세한) 제목
        match, ms = None, 0.0
        for i in its:
            o = by_url.get(nurl(i["gn_link"]))
            if o:
                match, ms = o, 1.0
                break
        if not match:
            for i in its:
                for o in ours:
                    if not o["title"]:
                        continue
                    s = similar(i["title"], o["title"], i["_t"], o["_t"])
                    if s > ms:
                        match, ms = o, s
        e = dict(google_title=rep["title"], outlet=rep["outlet"], outlet_domain=rep["outlet_domain"], lang=rep["lang"],
                 hotness=len(outlets), outlets=outlets, published=min(i["published"] for i in its).isoformat(timespec="minutes"),
                 queries=sorted({i["lang"] + ":" + i["query"] for i in its}), gn_link=rep["gn_link"], source_url="",
                 members=[dict(title=i["title"], outlet=i["outlet"], gn_link=i["gn_link"]) for i in its])
        if match and ms >= a.match:
            e.update(status="covered", matched_title=match.get("our_title") or match["title"], matched_kind=match["kind"],
                     matched_url=match["url"], match_score=round(ms, 2))
        else:
            e.update(status="missed")
        out.append(e)
    out.sort(key=lambda e: (-e["hotness"], e["published"]), reverse=False)
    missed = [e for e in out if e["status"] == "missed"]
    for e in missed[:a.decode_max]:
        e["source_url"] = decode(e["gn_link"])
        if e["source_url"] and nurl(e["source_url"]) in by_url:   # 풀어 보니 우리 후보에 있던 원문
            o = by_url[nurl(e["source_url"])]
            e.update(status="covered", matched_title=o.get("our_title") or o["title"], matched_kind=o["kind"],
                     matched_url=o["url"], match_score=1.0)
    result["events"] = out
    result["missed"] = [e for e in out if e["status"] == "missed"]
    result["covered"] = [e for e in out if e["status"] == "covered"]
    write(result, now)
    print("Google News 레이더: 항목 %d · 사건 %d · missed %d · covered %d (검색 %d/%d 성공) → %s/latest.{json,md}" % (
        len(items), len(out), len(result["missed"]), len(result["covered"]), result["queries_ok"], len(queries), OUTDIR))
    print("비교 대상: " + ("; ".join(used) or "없음(collect.py 먼저)"))
    print("놓친 사건(화제성 순, 상위 8):")
    for e in result["missed"][:8]:
        print("  [%d곳] %s — %s | %s" % (e["hotness"], e["google_title"][:90], e["outlet"],
                                       e["source_url"] or "원문 못 풂: 매체·제목으로 검색"))
    print("우리 것 화제성(상위 8):")
    for e in result["covered"][:8]:
        print("  [%d곳] %s ↔ %s" % (e["hotness"], e["google_title"][:60], e["matched_title"][:50]))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 어떤 오류든 판을 막지 않는다
        log("예상 못 한 오류 — 빈 결과로 끝냄\n" + traceback.format_exc())
        try:
            OUTDIR.mkdir(parents=True, exist_ok=True)
            (OUTDIR / "latest.json").write_text(json.dumps(dict(generated=datetime.now(BKK).isoformat(timespec="seconds"),
                                                                error=True, events=[], missed=[], covered=[]),
                                                           ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    sys.exit(0)
