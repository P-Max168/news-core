#!/usr/bin/env python3
"""광고 정책 점검(애드센스 준비, 2026-10-03) — 판의 기사 중 광고를 옆에 두면 안 되는 민감한 기사 찾기.
사용: python3 tools/adsafe.py [판 id ...]   (없으면 최신 판)
- 화면과 같은 기준표(assets/adsafe.js 의 RULES JSON — 낱말 묶음 점수 + 맥락 점수, 3점 이상 = 광고 숨김)로 제목·요약·태그를 검사.
  걸린 기사는 그대로 보이고, 그 바로 옆 광고(기사 사이·메인 큰 배너·한국 뉴스 사이·지역 광고)만 안 보임. 이유 한 줄도 같이 출력.
- 판 데이터 기사에 "ad_safe": false/true 를 넣으면 낱말 검사보다 우선(편집자가 직접 정함).
- 함께 점검: 요약이 너무 길지 않은지(원문 통째 옮기기 방지 — 저작권), 원문 링크가 있는지.
끝 상태 0 = 문제 없음(민감 기사·긴 요약은 '참고'로만 알림), 1 = 원문 링크 없는 기사가 있음."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_js = open(os.path.join(ROOT, "assets", "adsafe.js"), encoding="utf-8").read()
RULES = json.loads(_js.split("/*RULES*/", 1)[1].split("/*END*/", 1)[0])   # 화면과 같은 표

def _hit(t, g):
    for w in g.get("except") or []: t = t.replace(w, " ")
    return next((w for w in g["words"] if w in t), None)

def score(s):
    """assets/adsafe.js score() 와 같은 계산 → (점수, 숨김?, 이유 목록)"""
    if s.get("ad_safe") is False: return RULES["hide_at"], True, ["편집자 ad_safe:false"]
    if s.get("ad_safe") is True: return 0, False, ["편집자 ad_safe:true"]
    allt = " ".join([s.get("headline", "")] + list(s.get("summary") or []) + list(s.get("tags") or []))
    title = s.get("headline", ""); pts = 0; why = []; strong = in_title = False
    for g in RULES["groups"]:
        w = _hit(allt, g)
        if not w: continue
        pts += g["pts"]; why.append("%s +%d('%s')" % (g["label"], g["pts"], w))
        if g["pts"] >= 2:
            strong = True; in_title = in_title or bool(_hit(title, g))
    if why:
        for c in RULES["context"]:
            if c.get("strong") and not strong: continue
            on = in_title if c["id"] == "title" else (s.get("topic") in c["topics"] or any(x in c["topics"] for x in s.get("secondary") or [])) if c.get("topics") else bool(_hit(allt, c)) if c.get("words") else False
            if on: pts += c["pts"]; why.append("%s %+d" % (c["label"], c["pts"]))
    return pts, pts >= RULES["hide_at"], why
MAX_SUMMARY = 700   # 요약 글자 수(합) — 넘으면 '참고'로 알림(원문 통째 옮기기처럼 보이지 않게 줄일지 편집자가 판단). 지금까지 188개 기사 중앙값 322자

def check(ed):
    d = json.load(open(os.path.join(ROOT, "data", ed + ".json"), encoding="utf-8"))
    stories = d.get("stories") or d.get("articles") or []
    risky, fix, long_ = [], [], []
    for s in stories:
        pts, flag, why = score(s)
        if flag: risky.append((s.get("id"), "%d점: %s" % (pts, " · ".join(why)), s.get("headline", "")[:60]))
        n = len("".join(s.get("summary") or []))
        if n > MAX_SUMMARY: long_.append((s.get("id"), "요약 %d자(>%d) — 줄일지 검토" % (n, MAX_SUMMARY)))
        if not str(s.get("url") or "").startswith("http"):
            fix.append((s.get("id"), "원문 링크 없음"))
    print("[%s] 기사 %d개 · 광고 건너뜀(민감) %d개 · 고칠 것 %d개" % (ed, len(stories), len(risky), len(fix)))
    for i, w, h in risky: print("  참고 %-6s %s — %s" % (i, h, w))
    for i, w in long_: print("  참고 %-6s %s" % (i, w))
    for i, w in fix: print("  고칠 것 %-6s %s" % (i, w))
    return not fix

if __name__ == "__main__":
    eds = sys.argv[1:] or [json.load(open(os.path.join(ROOT, "data", "index.json"), encoding="utf-8"))["latest"]]
    ok = all([check(e) for e in eds])
    sys.exit(0 if ok else 1)
