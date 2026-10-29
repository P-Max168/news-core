# -*- coding: utf-8 -*-
"""판 담당 표시(2026-10-23, ops/SYSTEM_PLAN.md 2절) — "누가 이 판을 만들기 시작했는지"를 저장소에 남긴다.

원격 브랜치 이름 하나로 표시한다: refs/heads/claim/<판 id>/<누구>  (예: claim/2026-10-27-am/grok)
- main 을 건드리지 않으므로 Pages 재배포도, push 금지 구간 규칙도 상관없다. 파일 커밋도 없다.
- Claude 비상 발행 예약 작업은 07:00·18:00 에 이 표시를 보고, 없으면 바로 비상 발행, 있으면 기다린다.

  python3 tools/edition_claim.py claim <누구> <판 id>     # 시작 표시. 다른 담당이 이미 있으면 HOLD(exit 4)
  python3 tools/edition_claim.py check <누구> <판 id>     # 배포 직전 확인. 다른 담당이 '나중에' 가져갔으면 HOLD(exit 4)
  python3 tools/edition_claim.py status <판 id>           # 누가 표시했는지 출력
  python3 tools/edition_claim.py take <누구> <판 id>      # 비상 인수(Claude 07:30 재확인용): 다른 담당이 있어도 표시
  python3 tools/edition_claim.py release <누구> <판 id>   # 발행 성공·최종 실패 뒤 내 표시 삭제(Claude 비상 차단 해제)
누구 = grok | codex | claude.
규칙: 한 판에 담당이 둘이면, claude 표시가 있으면 claude 가 이긴다(비상 인수). 그 외에는 먼저 표시한 쪽.
3일 지난 claim 브랜치는 claim 할 때 함께 지운다.
시험: TNK_CLAIM_DRY=1 이면 push·삭제를 하지 않고 할 일만 출력한다.
"""
import os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))
ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(am|md|pm|early)$")
ACTORS = ("grok", "codex", "claude")
DRY = os.environ.get("TNK_CLAIM_DRY") == "1"


def git(*a, check=True):
    r = subprocess.run(["git", *a], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(a), r.stderr.strip()[:300]))
    return r.stdout


def claims():
    """{판 id: [누구, ...]} — 원격 claim/ 브랜치 목록"""
    out = {}
    for line in git("ls-remote", "--heads", "origin", "refs/heads/claim/*").splitlines():
        ref = line.split("\t")[-1]
        m = re.match(r"refs/heads/claim/([^/]+)/([a-z]+)$", ref)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def push(ref, delete=False):
    spec = (":" if delete else "HEAD:") + ref
    if DRY:
        print("DRY push", spec); return
    git("push", "-q", "origin", spec)


def winner(names):
    if "claude" in names:
        return "claude"
    return names[0] if names else None


def prune(all_claims):
    cut = (datetime.now(BKK) - timedelta(days=3)).date().isoformat()
    for ed, names in all_claims.items():
        m = ID_RE.match(ed)
        if m and m.group(1) < cut:
            for n in names:
                try:
                    push("refs/heads/claim/%s/%s" % (ed, n), delete=True)
                except RuntimeError as e:
                    print("정리 실패(무시):", e, file=sys.stderr)


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    cmd = argv[1]
    if cmd == "status":
        ed = argv[2]
        print("%s: %s" % (ed, ", ".join(claims().get(ed, [])) or "표시 없음"))
        return 0
    if len(argv) < 4 or argv[2] not in ACTORS or not ID_RE.match(argv[3]):
        print("사용법: claim|check|take|release <grok|codex|claude> <YYYY-MM-DD-am|pm|md>", file=sys.stderr); return 2
    actor, ed = argv[2], argv[3]
    allc = claims()
    names = allc.get(ed, [])
    others = [n for n in names if n != actor]
    if cmd == "claim":
        if others:
            print("CLAIM HOLD: %s 는 이미 %s 가 맡음 — 판을 만들지 말 것" % (ed, ", ".join(others)), file=sys.stderr)
            return 4
        if actor not in names:
            push("refs/heads/claim/%s/%s" % (ed, actor))
        print("CLAIM OK: %s → %s" % (ed, actor))
        prune(allc)
        return 0
    if cmd == "take":
        if actor not in names:
            push("refs/heads/claim/%s/%s" % (ed, actor))
        print("CLAIM TAKE: %s → %s (기존: %s)" % (ed, actor, ", ".join(others) or "없음"))
        return 0
    if cmd == "check":
        w = winner(names)
        if w and w != actor:
            print("CLAIM HOLD: %s 는 %s 가 맡음 — 배포하지 말 것" % (ed, w), file=sys.stderr)
            return 4
        print("CLAIM OK: %s" % ed)
        return 0
    if cmd == "release":
        # 내 표시만 지움. 다른 담당(claude) 표시는 건드리지 않음.
        if actor in names:
            push("refs/heads/claim/%s/%s" % (ed, actor), delete=True)
            print("CLAIM RELEASE: %s ← %s" % (ed, actor))
        else:
            print("CLAIM RELEASE: %s — %s 표시 없음" % (ed, actor))
        return 0
    print("모르는 명령:", cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except RuntimeError as e:
        # 표시를 못 남겨도 판 만들기는 막지 않는다(표시는 비상 발행 판단용). 대신 크게 알림.
        print("CLAIM WARN: %s" % e, file=sys.stderr)
        sys.exit(0)
