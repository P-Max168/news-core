# -*- coding: utf-8 -*-
"""관리자 승인함용 목록 만들기: PENDING_APPROVAL.md 표 → data/pending.json (+ data/pending.js)
  python3 tools/pending.py
- PENDING_APPROVAL.md 가 원본(사람이 읽는 곳). 사이트 #approve(운영자만)는 data/pending.json 을 읽어 보여 줄 뿐 — 자동 승인·자동 게시 없음.
- 저장소가 공개라 PENDING_APPROVAL.md 와 같은 내용만 넣는다(개인 정보·비밀번호 금지).
- 뉴스 정기 실행과 무관(판 데이터·index 를 건드리지 않음)."""
import json, pathlib, re, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent


def parse(md):
    items = []
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.fullmatch(r"\d+", cells[0]):
            continue
        items.append({"id": "p" + cells[0], "no": int(cells[0]), "kind": cells[1], "body": cells[2], "where": cells[3], "status": cells[4]})
    return items


DRAFT_DIRS = [ROOT / "drafts" / "discussion", pathlib.Path("/workspace/thai-news-portal/drafts/discussion")]


def discussion_items(start_no):
    """💬 오늘의 질문 + 운영자 첫 댓글 초안(drafts/discussion/<판>.json, .gitignore) 중 아직 게시 안 된 것 → 승인함 대기 항목(판마다 1개).
    2026-10-05(Max 07:32 D): 10-05 아침판 초안 18건을 승인함에 '대기'로. 게시 안 됨 = 초안 approved 가 true 아님 · applied_at 없음 ·
    판 데이터에 그 기사 discussion.approved 없음. 게시되면(discussion.py apply) 다음 pending.py 실행에서 저절로 빠짐.
    초안 폴더 = 이 저장소 drafts/ → 없으면 정본(/workspace/thai-news-portal) drafts/ 를 읽기만 함."""
    ddir = next((d for d in DRAFT_DIRS if d.is_dir()), None)
    out = []
    if not ddir:
        return out
    for f in sorted(ddir.glob("20*.json")):
        eid = f.stem; dp = ROOT / "data" / (eid + ".json")
        if not dp.exists():
            continue
        try:
            dr = json.loads(f.read_text(encoding="utf-8")); ed = json.loads(dp.read_text(encoding="utf-8"))
        except Exception:
            continue
        pub = {s["id"] for s in ed.get("stories", []) if (s.get("discussion") or {}).get("approved") is True}
        sids = {s["id"] for s in ed.get("stories", [])}
        wait = [x for x in dr if x.get("question") and x.get("operator_comment") and x.get("approved") is not True
                and not x.get("applied_at") and x.get("id") in sids and x.get("id") not in pub]
        if not wait:
            continue
        lines = " ".join("%d) [%s] 💬 %s / 🗨️ %s" % (i, x["id"], x["question"].strip(), x["operator_comment"].strip()) for i, x in enumerate(wait, 1))
        out.append({"id": "dq-" + eid, "no": start_no + len(out), "kind": "운영자 글(💬 오늘의 질문 초안)",
                    "body": "**%s %s — 💬 오늘의 질문 + 운영자 첫 댓글 초안 %d건(아직 화면에 안 나옴)** %s" % (ed.get("edition_label", ""), eid, len(wait), lines),
                    "where": "판 %s 기사 댓글 위 — OK 하면 봇이 `python3 tools/discussion.py apply` 로 게시(자동 게시 없음)" % eid, "status": "대기"})
    return out


def main():
    md = (ROOT / "PENDING_APPROVAL.md").read_text(encoding="utf-8")
    items = parse(md)
    items += discussion_items(max([x["no"] for x in items] or [0]) + 1)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%dT%H:%M:%S+07:00")
    doc = {"_readme": "관리자 승인함(#approve) 목록 — tools/pending.py 가 PENDING_APPROVAL.md 에서 만듦. 승인은 민구님이 고르고 봇이 다음 실행에 반영(자동 승인 없음)",
           "updated_at": now, "items": items}
    js = json.dumps(doc, ensure_ascii=False, indent=1)
    old = (ROOT / "data/pending.json").read_text(encoding="utf-8") if (ROOT / "data/pending.json").exists() else ""
    if json.loads(old or "{}").get("items") == items:
        print("pending: 그대로 (%d건)" % len(items)); return
    (ROOT / "data/pending.json").write_text(js + "\n", encoding="utf-8")
    (ROOT / "data/pending.js").write_text("window.TN_PENDING = " + json.dumps(doc, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("pending: %d건 → data/pending.json" % len(items))


if __name__ == "__main__":
    main()
