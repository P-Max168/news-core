# -*- coding: utf-8 -*-
"""💬 오늘의 질문 + 운영자 첫 댓글(정적 내용, Firestore 아님) 초안·적용 도구.

  python3 tools/discussion.py draft <판 id>
      → drafts/discussion/<판 id>.json (올리지 않음, .gitignore) 에 그 판의 모든 기사(빠짐없이 전부):
        [{id, title(한국어 제목), topic, reader_fit:""(A|B|C), question:"", operator_comment:"", approved:false}]
        question·operator_comment 는 정기 실행(편집자)이 직접 채운다 — 자연스러운 한국어, 정직한 운영자 목소리,
        tools/TRANSLATION_RULES.md 준수, 기사에 없는 사실 단정 금지, 절대 독자(사용자)인 척하지 않는다.
        독자 = 태국의 한국인 교민·여행자. 쓰기 전에 기사마다 reader_fit 을 A(누구나 화제)/B(외국인도 해당 행정)/
        C(태국 국민 전용 행정·혜택)로 정한다. C 는 독자·운영자가 직접 할 일처럼 쓰지 않음('신청하셨나요?'·'여러분 빨리 가세요' 금지)
        → 간접 영향·주변 태국인 직원/이웃·본 것·중립 의견을 묻는다(TRANSLATION_RULES.md 'A/B/C 3단계', 운영자 답글도 같음).
        이미 채운 초안 파일이 있으면 덮어쓰지 않는다(--force 로 새로).
  python3 tools/discussion.py show <판 id>              # 초안을 사람이 읽기 좋게 출력(채팅으로 보여 줄 때)
  python3 tools/discussion.py apply <판 id> <approved.json>
      → 운영자(Mingoo)가 채팅에서 OK 한 항목만 적용. approved.json = 초안과 같은 모양 목록
        (approved 가 true 인 항목만, approved 필드가 없으면 목록 전체를 승인으로 봄).
        ※ apply 는 그 판의 오늘의 질문 전체를 이 파일 내용으로 바꾼다 — 일부만 새로 승인했으면
          이미 적용된 tools/discussions/<판 id>.json 항목도 같이 넣을 것(안 넣으면 빠짐).
        tools/discussions/<판 id>.json 에 저장(판을 다시 만들어도 newslib.write_edition 이 자동으로 다시 합침)
        + data/<판 id>.json|js 의 기사에 discussion={question, operator_comment, approved:true} 반영.
  python3 tools/discussion.py clear <판 id>             # 그 판의 오늘의 질문 모두 빼기
  python3 tools/discussion.py mark-applied <판 id> [--at ISO]  # 게시된 항목을 초안 파일에 approved:true + applied_at 로 표시(글 그대로)
화면: approved 가 true 인 것만, 그 기사 댓글 위에 '💬 오늘의 질문' 상자 + '운영자' 배지 고정 댓글.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import newslib  # noqa: E402

DRAFTS = ROOT / "drafts" / "discussion"
APPLIED = ROOT / "tools" / "discussions"
# 기사 수 제한 없음(2026-10-03 운영자 결정: 판의 모든 기사에 질문 + 운영자 첫 댓글).
# 초안 순서: 주요 뉴스 → 외국인·비자 → 지역 → 생활·여행 → 나머지(판 순서)
PRI = ["visa", "east", "bangkok", "north", "south", "life", "travel", "weather", "society", "poleco", "ent"]


def load(eid):
    p = ROOT / "data" / (eid + ".json")
    return json.loads(p.read_text(encoding="utf-8"))


def candidates(d):
    hl = d.get("highlights", [])
    st = d["stories"]
    def rank(s):
        t = newslib.topics_of(s)
        return (0 if s["id"] in hl else 1, min(PRI.index(x) if x in PRI else 99 for x in t), st.index(s))
    return sorted(st, key=rank)   # 모든 기사(자르지 않음)


def draft(eid, force=False):
    d = load(eid)
    DRAFTS.mkdir(parents=True, exist_ok=True)
    fn = DRAFTS / (eid + ".json")
    if fn.exists() and not force:
        old = json.loads(fn.read_text(encoding="utf-8"))
        if any(x.get("question") for x in old):
            print("이미 채운 초안이 있음(덮어쓰지 않음):", fn); return fn
    items = [dict(id=s["id"], title=s["headline"], topic=newslib.topics_of(s)[0], reader_fit="", question="", operator_comment="", approved=False)
             for s in candidates(d)]
    fn.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print("초안 %d건 → %s (question·operator_comment 를 채우고 approved 는 false 로 둘 것)" % (len(items), fn))
    return fn


def show(eid):
    items = json.loads((DRAFTS / (eid + ".json")).read_text(encoding="utf-8"))
    for i, x in enumerate(items, 1):
        print("%d. [%s%s] %s\n   💬 질문: %s\n   🗨️ 운영자: %s\n" % (i, x["id"], ("·" + x["reader_fit"]) if x.get("reader_fit") else "", x["title"], x.get("question") or "(비어 있음)", x.get("operator_comment") or "(비어 있음)"))


def merge_into(d, items):
    """items(승인된 것) → d["stories"][*]["discussion"]. 반환: 적용 건수"""
    by = {s["id"]: s for s in d["stories"]}
    n = 0
    for x in items:
        s = by.get(x["id"])
        if not s:
            print("경고: 기사 id 없음(건너뜀):", x["id"], file=sys.stderr); continue
        q, c = (x.get("question") or "").strip(), (x.get("operator_comment") or "").strip()
        if not q or not c:
            print("경고: 질문/운영자 댓글이 비어 있음(건너뜀):", x["id"], file=sys.stderr); continue
        s["discussion"] = dict(question=q, operator_comment=c, approved=True); n += 1
    return n


def apply(eid, approved_path):
    items = json.loads(pathlib.Path(approved_path).read_text(encoding="utf-8"))
    if isinstance(items, dict):
        items = items.get("items", [])
    ok = [x for x in items if x.get("approved", True) is True]
    d = load(eid)
    for s in d["stories"]:
        s.pop("discussion", None)
    n = merge_into(d, ok)
    APPLIED.mkdir(parents=True, exist_ok=True)
    keep = [dict(id=x["id"], question=x["question"].strip(), operator_comment=x["operator_comment"].strip(), approved=True)
            for x in ok if x.get("question") and x.get("operator_comment")]
    (APPLIED / (eid + ".json")).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    newslib.write_edition(d, merge_discussions=False, keep_generated=True)
    print("적용:", n, "건 →", eid)
    mark_applied(eid, newslib.build_stamp())


def mark_applied(eid, at):
    """초안 파일(drafts/discussion/<판>.json, .gitignore)에도 '게시됨' 표시 — 게시된 항목만 approved:true + applied_at(실제 적용 시각).
    2026-10-05(Max 06:55 승인): 06:09 게시 59건 뒤에도 초안이 approved:false 로 남아 '대기'처럼 보였음. 글(question·operator_comment)은 그대로.
    게시 여부 = tools/discussions/<판>.json 에 같은 id·같은 글이 있는 것. 초안 파일이 없으면(개발 폴더) 아무것도 안 함."""
    fn = DRAFTS / (eid + ".json"); af = APPLIED / (eid + ".json")
    if not fn.exists() or not af.exists():
        print("초안 표시: 건너뜀(초안 또는 적용 파일 없음)", eid); refresh_inbox(); return 0
    items = json.loads(fn.read_text(encoding="utf-8"))
    ap = {x["id"]: x for x in json.loads(af.read_text(encoding="utf-8"))}
    n = 0
    for x in items:
        a = ap.get(x.get("id"))
        if a and (x.get("question") or "").strip() == a["question"] and (x.get("operator_comment") or "").strip() == a["operator_comment"]:
            if x.get("approved") is not True or not x.get("applied_at"):
                x["approved"] = True; x["applied_at"] = x.get("applied_at") or at; n += 1
    fn.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print("초안 표시: %d건 approved:true + applied_at=%s → %s" % (n, at, fn))
    refresh_inbox()
    return n


def refresh_inbox():
    """승인함 목록(data/pending.json) 다시 만들기 — 게시된 질문 묶음이 '대기'에 남지 않게(2026-10-05 D). 실패해도 apply 는 그대로"""
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "pending.py")], capture_output=True, text=True)
    print("승인함 목록:", (r.stdout or r.stderr).strip()[:120])


def clear(eid):
    d = load(eid)
    for s in d["stories"]:
        s.pop("discussion", None)
    f = APPLIED / (eid + ".json")
    if f.exists():
        f.unlink()
    newslib.write_edition(d, merge_discussions=False, keep_generated=True)
    print("오늘의 질문 모두 뺌:", eid)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "draft":
        draft(a[1], "--force" in a)
    elif len(a) >= 2 and a[0] == "show":
        show(a[1])
    elif len(a) >= 3 and a[0] == "apply":
        apply(a[1], a[2])
    elif len(a) >= 2 and a[0] == "mark-applied":   # 이미 게시한 판 정리: mark-applied <판 id> [--at 실제 적용 시각(ISO)]
        mark_applied(a[1], a[a.index("--at") + 1] if "--at" in a else newslib.build_stamp())
    elif len(a) >= 2 and a[0] == "clear":
        clear(a[1])
    else:
        sys.exit(__doc__)
