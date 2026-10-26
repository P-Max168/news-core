# -*- coding: utf-8 -*-
"""판 'generated'(업데이트 시각) 점검 — 2026-10-05: 10-05 아침판이 손으로 쓴 예정 시각 07:55 로 나감(실제 07:23).
실패: ① generated 가 지금보다 미래(1분 넘게) ② 그 generated 값을 처음 담은 커밋 시각(아직 커밋 전이면 파일 수정 시각)·판 파일을 처음 만든 커밋 시각 중 가까운 쪽과 15분 넘게 차이.
  python3 tools/gen_time_check.py [판 id]            # 기본 = data/index.json 의 latest (저장소 안 파일 기준)
  python3 tools/gen_time_check.py --break-test       # 시험: 미래 값 → 실패 · 20분 차이 → 실패 · 맞는 값 → 통과
regress(tools/dev/regress.py)·verify_live(tools/verify_live.py) 가 같이 씀."""
import json, pathlib, subprocess, sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
BKK = timezone(timedelta(hours=7))
TOL = timedelta(minutes=15)


def judge(generated, ref, now=None, ref_kind="커밋"):
    """순수 판정. generated(str) · ref(datetime, 만든/커밋 시각) · now(datetime). 반환 (ok, 설명)"""
    now = now or datetime.now(BKK)
    try:
        g = datetime.fromisoformat(generated)
    except Exception:
        return False, "generated 형식 오류: %r" % (generated,)
    if g.tzinfo is None:
        return False, "generated 에 시간대 없음: %s" % generated
    if g > now + timedelta(minutes=1):
        return False, "generated %s 가 미래(지금 %s)" % (generated, now.astimezone(BKK).strftime("%m-%d %H:%M:%S"))
    if ref is None:
        return None, "비교할 %s 시각 없음(generated %s)" % (ref_kind, generated)
    d = abs(g - ref)
    ok = d <= TOL
    return ok, "generated %s · %s %s · 차이 %d분%s" % (generated, ref_kind, ref.astimezone(BKK).isoformat(timespec="seconds"), d.total_seconds() // 60, "" if ok else " (15분 넘음)")


def git(*a, root=ROOT):
    return subprocess.run(["git", "-C", str(root)] + list(a), capture_output=True, text=True).stdout


def ref_time(eid, generated, root=ROOT):
    """그 generated 값을 처음 담은 커밋 시각. 없으면(커밋 전) 파일 수정 시각."""
    f = "data/%s.json" % eid
    for line in reversed(git("log", "--format=%H %cI", "--", f, root=root).split("\n")):
        if not line.strip(): continue
        h, t = line.split(" ", 1)
        try:
            if json.loads(git("show", "%s:%s" % (h, f), root=root)).get("generated") == generated:
                return datetime.fromisoformat(t.strip()), "커밋 " + h[:7]
        except Exception:
            continue
    p = root / f
    if p.exists():
        return datetime.fromtimestamp(p.stat().st_mtime, BKK), "파일 수정"
    return None, "커밋"


def check(eid=None, generated=None, root=ROOT, index_generated=None):
    """eid 없으면 index latest. generated 를 주면(라이브 값) 그 값으로 판정. index_generated 를 주면 판 값과 같아야 함."""
    root = pathlib.Path(root)
    if eid is None:
        eid = json.loads((root / "data/index.json").read_text(encoding="utf-8"))["latest"]
    if generated is None:
        generated = json.loads((root / "data" / (eid + ".json")).read_text(encoding="utf-8")).get("generated", "")
    ref, kind = ref_time(eid, generated, root)
    # 판을 처음 만든 커밋(파일이 처음 생긴 커밋)도 기준 — 나중에 실제 시각으로 '고쳐 넣은' 값은 고친 커밋이 아니라 처음 만든 시각과 맞아야 함
    first = [l for l in git("log", "--format=%H %cI", "--", "data/%s.json" % eid, root=root).split("\n") if l.strip()]
    if first and ref is not None:
        h, t = first[-1].split(" ", 1); ft = datetime.fromisoformat(t.strip())
        try:
            g = datetime.fromisoformat(generated)
            if abs(g - ft) < abs(g - ref): ref, kind = ft, "처음 만든 커밋 " + h[:7]
        except Exception:
            pass
    ok, msg = judge(generated, ref, ref_kind=kind)
    if index_generated is not None and index_generated != generated:
        ok, msg = False, msg + " · index.json generated %s ≠ 판 %s" % (index_generated, generated)
    return ok, "판 %s · %s" % (eid, msg)


def break_test():
    now = datetime(2026, 10, 5, 7, 30, tzinfo=BKK); built = datetime(2026, 10, 5, 7, 23, 46, tzinfo=BKK)
    cases = [("미래 값(07:55, 지금 07:30)", "2026-10-05T07:55:00+07:00", built, False),
             ("20분 차이(만든 07:23:46, generated 07:03:46)", "2026-10-05T07:03:46+07:00", built, False),
             ("맞는 값(07:23:46)", "2026-10-05T07:23:46+07:00", datetime(2026, 10, 5, 7, 23, 59, tzinfo=BKK), True)]
    allok = True
    for name, g, ref, want in cases:
        ok, msg = judge(g, ref, now=now)
        good = (ok is want)
        allok &= good
        print("%s · %s → %s — %s" % ("기대대로" if good else "‼️ 기대와 다름", name, "통과" if ok else "실패", msg))
    return allok


if __name__ == "__main__":
    if "--break-test" in sys.argv:
        sys.exit(0 if break_test() else 1)
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    ok, msg = check(a[0] if a else None)
    print(("통과" if ok else "실패" if ok is False else "참고") + " · 판 generated 시각 — " + msg)
    sys.exit(0 if ok is not False else 1)
