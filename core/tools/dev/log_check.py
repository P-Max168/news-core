# -*- coding: utf-8 -*-
"""DEV_LOG.md·BACKUPS.md 병합 뒤 점검(2026-10-05) — 문제 있으면 exit 1.
  python3 tools/dev/log_check.py [저장소]
왜: .gitattributes 의 union 병합은 충돌 없이 양쪽 줄을 다 남기지만, 한쪽이 '이미 있는 줄을 고친' 경우 옛 줄도 같이 되살아남
    (10-05 가게 클론 rebase 에서 정본이 07:22·07:26 으로 고친 줄의 옛 07:35·07:45 판이 다시 붙었음). 충돌 표시가 남는 것도 막음.
검사: ① 충돌 표시(<<<<<<< ======= >>>>>>>) ② 똑같은 기록 줄 두 번 ③ 같은 줄의 옛 판·고친 판이 같이 있음(시각 뺀 본문이 다른 줄 본문의 앞부분)"""
import re, sys, pathlib
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2])
ENTRY = re.compile(r"^(?:- |\| `)(?:\d\d-\d\d \d\d:\d\d · )?")
bad = []
for name in ("DEV_LOG.md", "BACKUPS.md"):
    p = root / name
    if not p.exists(): continue
    lines = p.read_text(encoding="utf-8").split("\n")
    for i, l in enumerate(lines, 1):
        if re.match(r"^(<<<<<<<|=======$|>>>>>>>)", l): bad.append("%s:%d 충돌 표시 %s" % (name, i, l[:20]))
    ent = [(i, l) for i, l in enumerate(lines, 1) if (l.startswith("- ") or l.startswith("| `")) and len(l) > 40]
    seen = {}
    for i, l in ent:
        if l in seen: bad.append("%s:%d 같은 줄 두 번(%d줄과) %s" % (name, i, seen[l], l[:60]))
        else: seen[l] = i
    if name == "DEV_LOG.md":
        body = [(i, re.sub(r"^- \d\d-\d\d \d\d:\d\d · ", "", l), l) for i, l in ent if re.match(r"^- \d\d-\d\d \d\d:\d\d · ", l)]
        by = {}
        for i, b, l in body: by.setdefault(b[:120], []).append((i, b, l))
        for k, grp in by.items():
            if len(grp) < 2: continue
            for i, b, l in grp:
                for j, b2, l2 in grp:
                    if i != j and l != l2 and len(b) > 60 and b2.startswith(b):
                        bad.append("DEV_LOG.md:%d 옛 줄이 되살아남(고친 판 %d줄) %s" % (i, j, l[:60]))
for b in bad: print("FAIL", b)
print("log_check: %s (%s)" % ("OK" if not bad else "문제 %d건" % len(bad), root))
sys.exit(1 if bad else 0)
