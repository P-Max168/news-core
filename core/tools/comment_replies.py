# -*- coding: utf-8 -*-
"""승인된 운영자 답글(독자 댓글 아래)을 정적 파일로 반영. Firestore 쓰기·관리자 로그인 없음.

  python3 tools/comment_replies.py apply <approved.json>
      → approved:true 인 항목만 data/op_replies.json 에 합침(키=부모 댓글 comment_id).
        입력(초안 drafts/replies 와 같음):
        { "checked_at": "...", "items": [
            { "comment_id", "edition", "article_id", "reply_draft"|"text", "approved": true }, ...
          ] }
        또는 목록 자체. approved 필드가 없으면 목록 전체를 승인으로 봄.
        이미 있는 키는 덮어씀. approved:false 항목은 무시(기존 값은 그대로).
  python3 tools/comment_replies.py show
      → 지금 게시된 정적 답글 목록
  python3 tools/comment_replies.py remove <comment_id> [comment_id…]
      → 해당 키만 data/op_replies.json 에서 삭제(민구님 지시 있을 때만)

화면: assets/social.js 가 data/op_replies.json 을 읽어 부모 독자 댓글 아래에
'운영자' 배지 답글로 보여 줌. Firestore 댓글/답글과 별개.
배포: apply 뒤 bash tools/dev/ship.sh "…" (push 금지 구간·정본 규칙 준수).
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "op_replies.json"
BKK = timezone(timedelta(hours=7))


def now_bkk():
    return datetime.now(BKK).isoformat(timespec="seconds")


def load_store():
    if not OUT.exists():
        return {}
    raw = json.loads(OUT.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        # 옛/다른 형식 [{comment_id,...}] → 키 맵
        out = {}
        for x in raw:
            cid = (x or {}).get("comment_id")
            if cid:
                out[cid] = x
        return out
    return {}


def save_store(d):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def parse_items(path):
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("items", [])
    elif isinstance(raw, list):
        items = raw
    else:
        raise SystemExit("형식 오류: 목록 또는 {items:[…]} 필요")
    ok = [x for x in items if x.get("approved", True) is True]
    return ok


def apply(path):
    items = parse_items(path)
    store = load_store()
    n_new = n_upd = n_skip = 0
    for x in items:
        cid = (x.get("comment_id") or "").strip()
        text = (x.get("reply_draft") or x.get("text") or "").strip()
        ed = (x.get("edition") or "").strip()
        aid = (x.get("article_id") or x.get("articleId") or "").strip()
        if not cid or not text:
            print("경고: comment_id/text 비어 있음(건너뜀):", cid or "(없음)", file=sys.stderr)
            n_skip += 1
            continue
        if len(text) > 500:
            print("경고: 500자 초과 → 앞 500자만:", cid, file=sys.stderr)
            text = text[:500]
        entry = {
            "text": text,
            "edition": ed,
            "articleId": aid,
            "approved": True,
            "applied_at": now_bkk(),
        }
        if cid in store:
            n_upd += 1
        else:
            n_new += 1
        store[cid] = entry
    save_store(store)
    print("적용: 신규 %d · 갱신 %d · 건너뜀 %d → %s (총 %d건)" % (n_new, n_upd, n_skip, OUT, len(store)))


def show():
    store = load_store()
    if not store:
        print("(비어 있음)", OUT)
        return
    for i, (cid, x) in enumerate(sorted(store.items()), 1):
        print("%d. [%s / %s] %s\n   🗨️ %s\n   applied_at=%s\n" % (
            i, x.get("edition") or "?", x.get("articleId") or "?", cid,
            (x.get("text") or "")[:200], x.get("applied_at") or ""))


def remove(ids):
    store = load_store()
    n = 0
    for cid in ids:
        if cid in store:
            del store[cid]
            n += 1
            print("삭제:", cid)
        else:
            print("없음:", cid)
    save_store(store)
    print("삭제 %d건 → 총 %d건" % (n, len(store)))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "apply":
        apply(a[1])
    elif len(a) >= 1 and a[0] == "show":
        show()
    elif len(a) >= 2 and a[0] == "remove":
        remove(a[1:])
    else:
        sys.exit(__doc__)
