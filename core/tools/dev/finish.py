# -*- coding: utf-8 -*-
"""개발 항목 마무리 기록: backups/<태그>/README.md(3줄) + BACKUPS.md 한 줄 + DEV_LOG.md 한 줄.
  python3 tools/dev/finish.py <태그> "<바뀐 것>" "<왜>" "<그 시점까지 들어간 것(백업 목록용)>" "<확인 여부: 완료(확인됨)… | 미확인…>"
사진 = backups/<태그>/*.jpg 를 자동으로 링크."""
import sys, pathlib, datetime, subprocess
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
tag, what, why, upto, chk = sys.argv[1:6]
import re as _re
if _re.fullmatch(r"[0-9a-f]{7,40}", upto.strip()) or len(upto) < 15:
    sys.exit("finish.py: '그 시점까지 들어간 것'은 커밋 해시가 아니라 한글 설명으로(민구님이 사진·설명을 보고 시점을 고름) — 예: '③d 직전 화면: …까지 + …, …는 없음'")
d = ROOT / "backups" / tag; d.mkdir(parents=True, exist_ok=True)
undo = "`git checkout %s -- .` → `git checkout origin/main -- data/` → 커밋 → push (force 금지, BACKUPS.md 맨 위 설명 참고)" % tag
(d / "README.md").write_text("- 바뀐 것: %s\n- 왜: %s\n- 되돌리는 법: %s\n" % (what, why, undo), encoding="utf-8")
pics = sorted(p.name for p in d.glob("*.jpg"))
links = " ".join("[%s](backups/%s/%s)" % (p.replace(".jpg", ""), tag, p) for p in pics) or "—"
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
t_from_tag = "%s-%s %s:%s" % (tag[11:13], tag[13:15], tag[16:18], tag[18:20])
with open(ROOT / "BACKUPS.md", "a", encoding="utf-8") as f:
    f.write("| `%s` | %s | %s | %s | ① `git checkout %s -- .` ② `git checkout origin/main -- data/`(뉴스는 최신 유지) ③ 커밋 → push(force 금지) |\n" % (tag, t_from_tag, upto, links, tag))
with open(ROOT / "DEV_LOG.md", "a", encoding="utf-8") as f:
    f.write("- %s · %s · `%s` · %s\n" % (now.strftime("%H:%M"), what, tag, chk))
print("기록함:", tag, len(pics), "장")
