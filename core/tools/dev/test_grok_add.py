# -*- coding: utf-8 -*-
"""grok_add(그록 추가 검사·합치기) 시험 (2026-10-30). 네트워크·제미나이 안 씀.

    python3 tools/dev/test_grok_add.py
"""
import json, pathlib, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import grok_add as g  # noqa: E402

BKK = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 31, 17, 50, tzinfo=BKK)
FAIL = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


tmp = pathlib.Path(tempfile.mkdtemp())
src = tmp / "sources.json"
src.write_text(json.dumps({"sources": [{"url": "https://www.khaosod.co.th/rss"}, {"url": "https://www.matichon.co.th/feed"},
                                       {"url": "https://news.google.com/rss/search?q=site:thaiheadlines.com"}]}), encoding="utf-8")
CONF = {"max": 4, "sources": [str(src)]}
BASE = [dict(url="https://www.khaosod.co.th/a1", title="น้ำท่วมภูเก็ต ดินสไลด์", source="Khaosod", published="2026-10-31T15:00:00+07:00"),
        dict(url="https://www.matichon.co.th/b2", title="ปภ.โอนเงินเยียวยาน้ำท่วม", source="Matichon", published="2026-10-31T14:00:00+07:00")]
P = "2026-10-31T16:40:00+07:00"


def run(doc, name="t.json"):
    f = tmp / name
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return g.load("2026-10-31-pm", BASE, CONF, now=NOW, path=f)


def add(url, title, pub=P, **kw):
    return dict(url=url, source="X", title=title, published=pub, why="X 확산", **kw)


ok(g.source_domains([str(src)]) >= {"khaosod.co.th", "matichon.co.th", "thaiheadlines.com"}, "수집처 도메인(site: 포함) 읽기")

r = g.load("2026-10-31-pm", BASE, CONF, now=NOW, path=tmp / "none.json")
ok(not r["found"] and not r["adds"] and g.path_label(r) == "code", "파일 없음 → 코드 목록만")

r = run(dict(edition="2026-10-31-pm", add=[
    add("https://www.khaosod.co.th/n1", "ไฟไหม้โรงงานระยอง"),
    add("https://x.com/abc/status/1", "X 글"),
    add("https://news.google.com/rss/articles/xyz", "구글 중계"),
    add("https://unknownblog.example.com/p", "모르는 매체"),
    add("https://www.matichon.co.th/old", "เก่า", pub="2026-10-29T10:00:00+07:00"),
    add("https://www.khaosod.co.th/a1", "기본 목록에 있는 주소"),
    add("https://www.matichon.co.th/n2", "น้ำท่วมภูเก็ต ดินสไลด์!"),
], boost=[{"url": "https://www.matichon.co.th/b2"}, {"url": "https://www.khaosod.co.th/nope"}]))
urls = [a["url"] for a in r["adds"]]
why = {d["url"]: d["why"] for d in r["dropped"]}
ok(urls == ["https://www.khaosod.co.th/n1"], "통과는 수집처·24시간·새 사건 1건뿐: %s" % urls)
ok("x.com" in why.get("https://x.com/abc/status/1", "") or "금지" in why.get("https://x.com/abc/status/1", ""), "X 주소 뺌")
ok("https://news.google.com/rss/articles/xyz" in why, "Google News 중계 뺌")
ok("수집처" in why.get("https://unknownblog.example.com/p", ""), "수집처에 없는 매체 뺌")
ok("24시간" in why.get("https://www.matichon.co.th/old", ""), "24시간 지난 기사 뺌")
ok("기본 목록에 같은 사건" in why.get("https://www.matichon.co.th/n2", ""), "기본 목록과 같은 사건 뺌")
ok(set(r["boost_urls"]) == {"https://www.matichon.co.th/b2", "https://www.khaosod.co.th/a1"}, "boost + 기본 목록 주소 add → boost: %s" % r["boost_urls"])
ok(r["adds"][0]["must_keep"] and r["adds"][0]["picked_by"] == "grok", "추가분 must_keep·picked_by 표시")

T6 = ["ไฟไหม้โรงงานระยอง", "สนามบินดอนเมืองปิด", "วีซ่าใหม่ต่างชาติ", "แผ่นดินไหวเชียงราย", "รถไฟตกราง", "ค่าไฟขึ้นมกราคม"]
many = [add("https://www.khaosod.co.th/m%d" % i, T6[i]) for i in range(6)]
r = run(dict(edition="2026-10-31-pm", add=many))
ok(len(r["adds"]) == 4 and sum("최대" in d["why"] for d in r["dropped"]) == 2, "최대 4건")

big = dict(edition="2026-10-31-pm", big_event={"key": "Phuket-Flood 1031", "reason": "푸껫 전역 침수"}, add=[
    add("https://www.khaosod.co.th/b1", "น้ำท่วมภูเก็ต หนัก", angle="현장"),
    add("https://www.matichon.co.th/b3", "น้ำท่วมภูเก็ต หนัก", angle="정부 발표"),
    add("https://www.khaosod.co.th/b4", "น้ำท่วมภูเก็ต หนัก", angle="현장"),
    add("https://www.khaosod.co.th/b5", "น้ำท่วมภูเก็ต หนัก")])
r = run(big)
ok(r["big_event"] == "phuket-flood1031" and len(r["adds"]) == 2, "큰 사건: 같은 사건 허용, angle 중복·없음은 뺌 (%d건)" % len(r["adds"]))
ok(g.path_label(r) == "code+grok-big", "경로 표시 code+grok-big")

r = run(dict(edition="2026-11-01-am", add=[add("https://www.khaosod.co.th/z", "อื่น")]))
ok(not r["adds"] and "edition" in r["dropped"][0]["why"], "다른 판 id 파일은 안 씀")

base_doc = dict(edition="2026-10-31-pm", picker="code", select=20, picks=BASE)
r = run(dict(edition="2026-10-31-pm", add=[add("https://www.khaosod.co.th/n1", "ไฟไหม้โรงงานระยอง")], boost=[{"url": BASE[1]["url"]}]))
doc = g.merge(base_doc, r, 25)
ok([p["url"] for p in doc["picks"]] == ["https://www.khaosod.co.th/n1", BASE[1]["url"], BASE[0]["url"]], "합치기 순서: 추가 → boost → 기본")
ok(doc["select"] == 25 and doc["picker"] == "code" and doc["grok_add"]["adds"] == 1, "합친 문서 select·기록")

# ---- 코덱스 리뷰 반영(2026-10-30)
src2 = tmp / "site.json"
src2.write_text(json.dumps({"sources": [{"url": "https://e.vnexpress.net/rss", "production": False}, {"url": "https://thanhnien.vn/rss"}]}), encoding="utf-8")
d2 = g.source_domains([str(src2)])
ok("thanhnien.vn" in d2 and "e.vnexpress.net" not in d2, "production:false 수집처는 허용 목록에서 뺌")
for bad in ([], None, {"edition": "2026-10-31-pm", "boost": ["https://www.khaosod.co.th/a"], "add": "x"}):
    try:
        r = run(bad, "bad.json"); okk = not r["adds"]
    except Exception as ex:
        okk = False; print("  예외:", ex)
    ok(okk, "이상한 파일 모양도 예외 없이 코드 목록만: %r" % (bad,))
cut = datetime(2026, 10, 31, 18, 5, tzinfo=BKK)
doc = dict(edition="2026-10-31-pm", add=[add("https://www.khaosod.co.th/n1", "ไฟไหม้โรงงานระยอง")])
r = run(doc, "late.json") if False else None
f = tmp / "late.json"; f.write_text(json.dumps(doc), encoding="utf-8")
r = g.load("2026-10-31-pm", BASE, dict(CONF, _cutoff=cut, _submitted=datetime(2026, 10, 31, 18, 20, tzinfo=BKK)), now=NOW, path=f)
ok(not r["adds"] and r.get("late"), "마감 뒤 올라온 파일은 안 씀")
r = g.load("2026-10-31-pm", BASE, dict(CONF, _cutoff=cut, _submitted=datetime(2026, 10, 31, 17, 55, tzinfo=BKK)), now=NOW, path=f)
ok(len(r["adds"]) == 1, "마감 전 파일은 씀")

print("\n결과:", "모두 통과" if not FAIL else "실패 %d: %s" % (len(FAIL), FAIL))
sys.exit(1 if FAIL else 0)
