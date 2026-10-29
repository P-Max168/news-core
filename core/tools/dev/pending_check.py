# -*- coding: utf-8 -*-
"""'게시된 질문은 승인함 대기에 없음' 점검 (2026-10-05 Max 06:28 ①).
승인함(#approve)이 '대기'로 보여 주는 것 = data/pending.json 의 items 뿐(tools/pending.py 가 PENDING_APPROVAL.md 표에서 만듦,
assets/pages.js apLoad). drafts/discussion/*.json(.gitignore, approved:false 그대로 = 초안 원본)은 승인함이 읽지 않는다.
→ 게시된(판 데이터 discussion.approved=true) 질문·운영자 댓글이 승인함 대기 항목에 들어 있으면 실패.
  python3 tools/dev/pending_check.py [사이트 URL]           # 라이브 점검
  python3 tools/dev/pending_check.py --break-test [URL]     # 일부러 깨뜨린 목록(게시된 질문 1건을 대기에 끼움)으로 실패가 뜨는지"""
import json, sys, time, urllib.request

def get(base, path):
    with urllib.request.urlopen(base.rstrip("/") + "/" + path + "?_=" + str(int(time.time())), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def published(base):
    idx = get(base, "data/index.json")
    out = []
    for e in idx.get("editions", []):
        try: d = get(base, "data/%s.json" % e["id"])
        except Exception: continue
        for s in d.get("stories", []):
            q = s.get("discussion") or {}
            if q.get("approved") is True and q.get("question"):
                out.append((e["id"], s["id"], q["question"].strip(), (q.get("operator_comment") or "").strip()))
    return out

def check(pending_doc, pub):
    """반환 (ok, 상세). 대기 항목 글(kind·body·where)에 게시된 질문/운영자 댓글 글이 있거나, '오늘의 질문'+게시된 판 id 가 같이 있으면 실패"""
    items = pending_doc.get("items", []) if isinstance(pending_doc, dict) else []
    eds = sorted({p[0] for p in pub})
    hits = []
    for it in items:
        t = " ".join(str(it.get(k, "")) for k in ("kind", "body", "where"))
        for ed, sid, q, c in pub:
            if (q and q in t) or (c and len(c) > 15 and c in t):
                hits.append("#%s ← %s/%s" % (it.get("no"), ed, sid))
        if "오늘의 질문" in t:
            for ed in eds:
                if ed in t or ed[5:].replace("-", "/", 1) in t:
                    hits.append("#%s ← 오늘의 질문 %s(이미 게시)" % (it.get("no"), ed))
    return (not hits), {"대기 항목": len(items), "게시된 질문": len(pub), "게시된 판": len(eds), "겹침": sorted(set(hits))[:8]}

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    base = a[0] if a else "https://tnews.pmaxone.com/"
    base = base.split("?")[0]
    pub = published(base); doc = get(base, "data/pending.json")
    if "--break-test" in sys.argv and pub:
        ed, sid, q, c = pub[0]
        doc = dict(doc, items=list(doc.get("items", [])) + [{"id": "p99", "no": 99, "kind": "운영자 글(오늘의 질문)", "body": "💬 " + q, "where": "%s %s" % (ed, sid), "status": "대기"}])
    ok, info = check(doc, pub)
    print(("통과" if ok else "실패") + " · 게시된 질문은 승인함 대기에 없음 — " + json.dumps(info, ensure_ascii=False))
    sys.exit(0 if ok else 1)
