# -*- coding: utf-8 -*-
"""'🇰🇷 오늘의 한국 주요 뉴스'(판 필드 korea_top 최대 10건 / 독립 파일 data/korea.json 10건) 후보 수집 — 한국 언론(한국어) Google News KR RSS.

  python3 tools/fetch_korea.py <판 id> [--decode]
    → raw/<id>/korea/top.xml, q_*.xml(원본 RSS), raw/<id>/korea/korea.json(후보 목록) 저장 + 후보 출력
    --decode : 후보의 실제 기사 URL 풀기(googlenewsdecoder, 느림 — 고른 6건만 쓰려면 생략하고 아래 decode 사용)
  python3 tools/fetch_korea.py <판 id> --decode-only "제목 일부" …   # 고른 항목만 실제 URL 풀기

  python3 tools/fetch_korea.py --standalone [--no-decode] [--force]
    → 판과 무관한 독립 파일 data/korea.json + data/korea.js(window.KOREA_NEWS) 를 직접 만든다(LLM 없음, 결정적).
      GitHub Actions(.github/workflows/korea.yml)가 2시간마다 실행. 아래 '독립 모드' 참고.
      항목 10건이 이전과 같고 updated_at 이 5시간 안이면 파일을 건드리지 않음(커밋 안 생김). --force 면 항상 씀.

수집 순서(우선순위): ① 태국 사는 한국인에게 직접 영향(태국 비자·입국, 인천↔방콕 항공, 원·바트 환율,
한-태 관계, 외교부·대사관 안전 공지) ② 그날 한국 전체 주요 뉴스(Google News 한국 '주요 뉴스').
편집 파일에서 KR(headline, source, url, published, badge) 최대 10개로 적는다(headline 은 한국어 원제를 TRANSLATION_RULES
제목 규칙대로 짧게만 다듬고, 없는 내용을 지어내지 않는다). 최근 36시간 안의 기사만.
"""
import sys, re, json, pathlib, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
BKK = timezone(timedelta(hours=7))
TOP = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
# 교민 관련 검색(우선) — 결과가 없으면 넘어감
QUERIES = ["태국 비자 when:2d", "태국 한국인 when:2d", "원 바트 환율 when:2d", "방콕 항공편 when:2d",
           "한국 태국 외교 when:2d", "외교부 태국 when:3d", "원달러 환율 when:1d"]


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()


def items(data, kind):
    out = []
    for it in ET.fromstring(data).iter("item"):
        t = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and t.endswith(" - " + src):
            t = t[: -len(" - " + src)]
        d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(BKK)
        out.append(dict(kind=kind, title=t, source=src, gn_url=it.findtext("link"), published=d.isoformat(timespec="seconds")))
    return out


# ---------------------------------------------------------------- 독립 모드(--standalone)
# 지금 한국에서 가장 화제인 전국 뉴스 10건을 규칙으로 고른다(태국·교민 가중치 없음, 같은 입력 → 같은 결과).
#  ① Google News 한국 '대한민국' 주제 피드(KR_TOPIC, 한국 관련으로 Google 이 분류한 기사 묶음, 위일수록 화제)
#  ② Google News 한국 '주요 뉴스'(TOP) 상위 15개 — 세계·IT 등도 섞여 있으므로 ①과 같은 사건이거나
#     한국 관련 낱말(KR_WORDS)이 묶음 제목에 있을 때만 후보
#  점수 = ②주요 뉴스 순위 점수(50−3×순위) + ①대한민국 순위 점수(20−0.4×순위) (+둘 다면 5) + 묶음 매체 수(≤5) − 경과시간×0.5
#  36시간 넘은 기사·칼럼/사설/포토·보도자료 매체 제외, 같은 사건(제목 글자 2-gram 유사도)은 하나만.
KR_TOPIC = "https://news.google.com/rss/topics/CAAqIQgKIhtDQkFTRGdvSUwyMHZNRFp4WkRNU0FtdHZLQUFQAQ?hl=ko&gl=KR&ceid=KR:ko"
KR_WORDS = re.compile(r"한국|韓|국내|북한|北|김정은|김여정|이 대통령|李|尹|청와대|대통령실|국회|여야|민주당|국민의힘|우리 정부|국무총리|"
                      r"검찰|공소청|경찰|특검|법원|대법|헌재|서울|부산|인천|대구|광주|대전|제주|경기|강원|코스피|원화|환율|"
                      r"합참|국방부|국군|기상청|아시안게임|대표팀")
SKIP_TITLE = re.compile(r"^\s*[\[〈<(]\s*(칼럼|사설|기고|포토|사진|영상|오피니언|광고|인터뷰|시론|만평|카드뉴스)\s*[\]〉>)]|\[(칼럼|사설|기고|포토|오피니언)\]")
SKIP_SOURCE = re.compile(r"정책브리핑|고용노동부|내 손안에 서울|브런치|보도자료|\.go\.kr$|GameGPU")
SOURCE_NAMES = {"ytn.co.kr": "YTN", "v.daum.net": "다음뉴스", "newspim.com": "뉴스핌", "edaily.co.kr": "이데일리",
                "wikitree.co.kr": "위키트리", "kita.net": "한국무역협회", "news.kbs.co.kr": "KBS 뉴스", "imnews.imbc.com": "MBC 뉴스",
                "news.sbs.co.kr": "SBS 뉴스", "yna.co.kr": "연합뉴스", "hani.co.kr": "한겨레", "khan.co.kr": "경향신문",
                "chosun.com": "조선일보", "donga.com": "동아일보", "joongang.co.kr": "중앙일보", "hankyung.com": "한국경제",
                "mk.co.kr": "매일경제", "news1.kr": "뉴스1", "newsis.com": "뉴시스", "nocutnews.co.kr": "노컷뉴스"}
CLUSTER_RE = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>(?:&nbsp;|\s)*<font[^>]*>(.*?)</font>', re.S)


def clean_title(t, src=""):
    """가벼운 정리만: ' - 언론사'·' | 언론사' 꼬리, (종합N보) 꼬리, 공백. 내용은 바꾸지 않는다."""
    import html as _h
    t = _h.unescape(t or "").replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    for s in filter(None, [src, SOURCE_NAMES.get(src, "")]):
        for sep in (" - ", " | ", " : "):
            if t.endswith(sep + s):
                t = t[: -len(sep + s)].strip()
    t = re.sub(r"\s+[-|]\s+[^-|]{1,20}(뉴스|일보|신문|방송|TV|경제|news|\.com|\.co\.kr|\.kr|\.net)$", "", t, flags=re.I)
    t = re.sub(r"\s*[\[(](종합|종합\s*\d+보|\d+보|상보|일문일답)[\])]\s*$", "", t)
    return t.strip(" -|")


def nice_source(src):
    src = (src or "").strip()
    return SOURCE_NAMES.get(src, src)


def bigrams(t):
    t = re.sub(r"[^0-9A-Za-z가-힣一-鿿]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def sim(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / max(1, min(len(A), len(B)))


def feed_items(data, feed):
    import html as _h
    out = []
    for pos, it in enumerate(ET.fromstring(data).iter("item")):
        src = (it.findtext("source") or "").strip()
        desc = it.findtext("description") or ""
        cl = [(u, clean_title(_h.unescape(re.sub("<[^>]+>", "", t)), _h.unescape(s)), _h.unescape(s)) for u, t, s in CLUSTER_RE.findall(desc)]
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(BKK)
        except Exception:
            continue
        out.append(dict(feed=feed, pos=pos, title=clean_title(it.findtext("title"), src), source=src,
                        gn_url=(it.findtext("link") or "").strip(), published=d, cluster=cl,
                        ids={u.split("/articles/")[-1].split("?")[0] for u, _, _ in cl} | {(it.findtext("link") or "").split("/articles/")[-1].split("?")[0]}))
    return out


def same_story(a, b):
    if a["ids"] & b["ids"]:
        return True
    ta = [a["title"]] + [c[1] for c in a["cluster"][:3]]
    tb = [b["title"]] + [c[1] for c in b["cluster"][:3]]
    return any(sim(x, y) >= 0.5 for x in ta for y in tb if len(x) > 8 and len(y) > 8)


def pick_top(kr, top, now, n=10):
    stories = []
    for it in kr[:50]:
        stories.append(dict(rep=it, kr=it["pos"], top=None, members=[it]))
    for it in top[:15]:
        st = next((s for s in stories if any(same_story(it, m) for m in s["members"])), None)
        if st:
            if st["top"] is None:
                st["top"] = it["pos"]; st["members"].append(it); st["rep"] = it   # 주요 뉴스 쪽 대표 제목 사용
        elif KR_WORDS.search(" ".join([it["title"]] + [c[1] for c in it["cluster"]])):
            stories.append(dict(rep=it, kr=None, top=it["pos"], members=[it]))
    scored = []
    for s in stories:
        r = s["rep"]
        age = (now - r["published"]).total_seconds() / 3600
        newest = max(m["published"] for m in s["members"])
        age = min(age, (now - newest).total_seconds() / 3600)
        if age > 36 or age < -1 or SKIP_TITLE.search(r["title"]) or SKIP_SOURCE.search(r["source"]) or len(r["title"]) < 8 \
                or blocked(r["title"]):
            continue
        sc = (50 - 3 * s["top"] if s["top"] is not None else 0) + (20 - 0.4 * s["kr"] if s["kr"] is not None else 0)
        if s["kr"] is not None and s["top"] is not None:
            sc += 5
        sc += min(5, len({c[2] for m in s["members"] for c in m["cluster"]}))
        sc -= 0.5 * max(0.0, age)
        scored.append((round(sc, 3), s["top"] if s["top"] is not None else 99, s["kr"] if s["kr"] is not None else 99, s))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    chosen = []
    for sc, _, _, s in scored:
        if any(sim(s["rep"]["title"], c["rep"]["title"]) >= 0.45 or any(same_story(m, cm) for m in s["members"] for cm in c["members"]) for c in chosen):
            continue
        s["score"] = sc; chosen.append(s)
        if len(chosen) == n:
            break
    return chosen


def decode_url(gn):
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        return None
    for attempt in range(2):
        try:
            r = gnewsdecoder(gn, interval=1)
            if (r.get("status") or r.get("success")) and r.get("decoded_url", "").startswith("http") and "news.google.com" not in r["decoded_url"]:
                return r["decoded_url"]
        except Exception as e:
            print("decode 실패:", e, file=sys.stderr)
    return None


def blocked(text):
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from newslib import blocked as b   # 성인·선정적 차단 목록(tools/trend_blocklist.txt) 공유
        return b(text)
    except Exception:
        return None


def standalone():
    now = datetime.now(BKK)
    kr = feed_items(fetch(KR_TOPIC), "kr")
    top = feed_items(fetch(TOP), "top")
    print("피드: 대한민국 %d건, 주요 %d건" % (len(kr), len(top)))
    chosen = pick_top(kr, top, now)
    if len(chosen) < 6:   # 보통 10건. 6건도 못 채우면 수집 이상으로 보고 기존 파일 유지(워크플로 실패로 표시)
        sys.exit("후보가 6건 미만(%d) — 파일을 바꾸지 않음" % len(chosen))
    if len(chosen) < 10:
        print("주의: 후보 %d건만(10건 미만)" % len(chosen), file=sys.stderr)
    items = []
    for s in chosen:
        r = s["rep"]
        url = None if "--no-decode" in sys.argv else decode_url(r["gn_url"])
        items.append(dict(title=r["title"], source=nice_source(r["source"]), time=r["published"].isoformat(timespec="seconds"),
                          url=url or r["gn_url"]))
        print("%6.1f | 대한민국 %-4s 주요 %-4s | %s | %s | %s" % (s["score"], s["kr"], s["top"], items[-1]["time"][5:16], items[-1]["source"], items[-1]["title"]))
    jf, js = ROOT / "data" / "korea.json", ROOT / "data" / "korea.js"
    if jf.exists() and "--force" not in sys.argv:
        try:
            old = json.loads(jf.read_text(encoding="utf-8"))
            same = [(i["title"], i["url"]) for i in old.get("items", [])] == [(i["title"], i["url"]) for i in items]
            fresh = now - datetime.fromisoformat(old["updated_at"]) < timedelta(hours=5)
            if same and fresh:
                print("변경 없음 — data/korea.json 그대로(updated_at %s)" % old["updated_at"]); return
        except Exception:
            pass
    doc = dict(updated_at=now.replace(microsecond=0).isoformat(), items=items)
    txt = json.dumps(doc, ensure_ascii=False, indent=1)
    jf.write_text(txt + "\n", encoding="utf-8")
    js.write_text("/* tools/fetch_korea.py --standalone 이 만듦 — 직접 고치지 말 것 */\nwindow.KOREA_NEWS = " + txt + ";\n", encoding="utf-8")
    print("저장:", jf, js, doc["updated_at"])


def main():
    if "--standalone" in sys.argv:
        # 2026-10-05: 상자(box)의 정본 체크아웃에서 한국 뉴스 갱신을 돌릴 때는 먼저 정본 상태 검사(rebase 중·앞섬·바뀐 파일이면 멈춤·알림).
        #   GitHub Actions(korea.yml)는 새 체크아웃에서 돌고 같은 실행에서 바로 push 하므로 검사 안 함.
        import os, subprocess
        if not os.environ.get("GITHUB_ACTIONS") and ROOT.resolve() == pathlib.Path(os.environ.get("CANON_DIR", "/workspace/thai-news-portal") if os.environ.get("TNK_TEST") == "1" else "/workspace/thai-news-portal").resolve():
            r = subprocess.run(["bash", str(ROOT / "tools" / "canon_guard.sh"), "korea-update"])
            if r.returncode != 0:
                sys.exit("한국 뉴스 갱신 안 함 — 정본 상태(위 CANON GUARD 줄)")
        return standalone()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    eid = sys.argv[1]
    out = ROOT / "raw" / eid / "korea"
    out.mkdir(parents=True, exist_ok=True)
    fn = out / "korea.json"
    if "--decode-only" in sys.argv:
        pats = sys.argv[sys.argv.index("--decode-only") + 1:]
        cands = json.loads(fn.read_text(encoding="utf-8"))
        decode([c for c in cands if any(p in c["title"] for p in pats)])
        fn.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    cands = []
    for i, q in enumerate(QUERIES):
        try:
            data = fetch("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&hl=ko&gl=KR&ceid=KR:ko")
            (out / ("q_%d.xml" % i)).write_bytes(data)
            cands += items(data, "교민:" + q.replace(" when:", " ~"))[:8]
        except Exception as e:
            print("검색 실패:", q, e, file=sys.stderr)
    data = fetch(TOP)
    (out / "top.xml").write_bytes(data)
    cands += items(data, "주요")
    now = datetime.now(BKK)
    seen, res = set(), []
    for c in cands:
        if c["title"] in seen or now - datetime.fromisoformat(c["published"]) > timedelta(hours=36):
            continue
        seen.add(c["title"]); res.append(c)
    if "--decode" in sys.argv:
        decode(res)
    fn.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in res:
        print("%s | %-14s | %s | %s" % (c["published"][5:16], c["kind"][:14], c["source"], c["title"]))
    print("저장:", fn, len(res), "건")


def decode(cs):
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        print("googlenewsdecoder 없음(pip install googlenewsdecoder) — gn_url 그대로 사용 가능", file=sys.stderr); return
    for c in cs:
        if c.get("url"):
            continue
        try:
            r = gnewsdecoder(c["gn_url"], interval=1)
            if r.get("status") or r.get("success"):
                c["url"] = r["decoded_url"]; print("URL:", c["title"][:40], "→", c["url"])
        except Exception as e:
            print("decode 실패:", c["title"][:40], e, file=sys.stderr)


if __name__ == "__main__":
    main()
