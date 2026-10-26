# -*- coding: utf-8 -*-
"""최신 판 늦음 검사(2026-10-05) — 라이브 사이트의 최신 판이 예정보다 30분 넘게 늦으면 /workspace/logs/edition-stale.txt 에 한 줄.
  python3 tools/edition_stale.py            # 상태 출력 + 늦으면 한 줄 기록(같은 판은 한 번만)
  python3 tools/edition_stale.py --now "2026-10-05 07:45"   # 시험(방콕 시각 흉내)
예정(2026-10-23 변경): 게시 목표 아침판 07:00, 저녁판 18:00 (방콕, 시작 06:40·17:40). 30분 지나도(= 07:30 / 18:30) 라이브 data/index.js 의 latest 가 그 판이 아니면 '늦음'.
읽기만 함(사이트·저장소를 바꾸지 않음), 휴대폰 알림 없음 — Max 가 다음 검수에서 이 파일을 봄. tools/preflight.sh 가 매번 부름.
종료 코드: 0 = 정상, 1 = 늦음(기록함), 2 = 라이브를 못 읽음(기록함).
(2026-10-11) 여러 판 공백 경보: 라이브 최신과 기대 판 사이에 빠진 판이 2개 이상이면(= '1판 늦음'이 아니라 공백)
  /workspace/logs/edition-gaps.txt 를 새로 씀(확인 시각·라이브 최신·기대 판·다음 예정 판·빠진 판 id 목록) + edition-stale.txt 에 '‼️ 여러 판 공백' 한 줄(예전 '늦음' 줄도 그대로),
  마지막 출력 줄도 '‼️ 여러 판 공백 N판'(preflight 의 automation.log 줄에 남음). 종료 코드는 그대로 1(늦음). 빌드는 하지 않음(경보·기록만).
  1판 늦음은 예전 그대로(edition-stale.txt 한 줄). 공백이 풀리면 edition-gaps.txt 는 지우지 않음(마지막 공백 기록으로 남음, 안의 확인 시각 참고).
  시험: TNK_TEST=1 TNK_LOGDIR=/tmp/x python3 tools/edition_stale.py --now "2026-10-11 07:45" --latest 2026-10-05-am"""
import datetime as dt, json, os, random, re, sys, urllib.request

BKK = dt.timezone(dt.timedelta(hours=7))
SITE = os.environ.get("TNK_SITE", "https://tnews.pmaxone.com/")
LOG = os.path.join(os.environ.get("TNK_LOGDIR", "/workspace/logs") if os.environ.get("TNK_TEST") == "1" else "/workspace/logs", "edition-stale.txt")   # 덮어쓰기는 TNK_TEST=1 일 때만(2026-10-05)
SLOTS = [("am", 7, 0), ("pm", 18, 0)]   # 2026-10-23: 게시 목표 07:00·18:00(시작 06:40·17:40)
GRACE = 30
GAPS = os.path.join(os.path.dirname(LOG), "edition-gaps.txt")


def expected(now):
    """지금 라이브에 있어야 할 가장 최근 판 id 와 그 판의 '늦음 기준 시각'"""
    cands = []
    for back in (0, 1):
        d = (now - dt.timedelta(days=back)).date()
        for slot, h, m in SLOTS:
            due = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=BKK) + dt.timedelta(minutes=GRACE)
            if due <= now:
                cands.append((due, "%s-%s" % (d.isoformat(), slot)))
    due, ed = max(cands)
    return ed, due


def slot_list(after, upto):
    """after(제외) 다음부터 upto(포함)까지 예정 판 id 목록(최대 60일). after 를 못 읽으면 None"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(am|pm)$", after or "")
    u = re.match(r"(\d{4}-\d{2}-\d{2})-(am|pm)$", upto)
    if not m or not u:
        return None
    d, slot = dt.date.fromisoformat(m.group(1)), m.group(2)
    out = []
    for _ in range(120):
        if slot == "am":
            slot = "pm"
        else:
            slot, d = "am", d + dt.timedelta(days=1)
        ed = "%s-%s" % (d.isoformat(), slot)
        if ed > upto:
            break
        out.append(ed)
    return out


def next_slot(ed):
    d, slot = ed.rsplit("-", 1)
    if slot == "am":
        return d + "-pm"
    return (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat() + "-am"


def live_latest():
    url = SITE + "data/index.js?_=%d" % random.randrange(10**9)
    last = None
    for i in range(3):   # 일시 실패면 다시(2초·4초)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=15) as r:
                txt = r.read().decode("utf-8", "replace")
            m = re.search(r'"latest"\s*:\s*"([^"]+)"', txt)
            if m:
                return m.group(1), None
            last = "index.js 에 latest 없음"
        except Exception as e:   # noqa
            last = "%s: %s" % (type(e).__name__, e)
        if i < 2:
            import time; time.sleep(2 * (i + 1))
    return None, last


def already(key):
    try:
        with open(LOG, encoding="utf-8") as f:
            return any(key in line for line in f)
    except FileNotFoundError:
        return False


def write(line, key):
    if already(key):
        return False
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return True


def main():
    now = dt.datetime.now(BKK)
    if "--now" in sys.argv:
        now = dt.datetime.strptime(sys.argv[sys.argv.index("--now") + 1], "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
    ed, due = expected(now)
    if "--latest" in sys.argv and os.environ.get("TNK_TEST") == "1":   # 시험: 라이브 최신 흉내(TNK_TEST=1 일 때만)
        latest, err = sys.argv[sys.argv.index("--latest") + 1], None
    else:
        latest, err = live_latest()
    stamp = now.strftime("%m-%d %H:%M")
    if latest is None:
        key = "[읽기실패 %s]" % ed
        w = write("%s 최신 판 확인 못 함 %s — 라이브 data/index.js 를 3번 못 읽음(%s). 기대 판 %s" % (stamp, key, err, ed), key)
        print("확인 못 함:", err, "(기록함)" if w else "(이미 기록됨)"); return 2
    if latest >= ed:
        print("정상: 라이브 최신 판 %s (기대 %s 이상)" % (latest, ed)); return 0
    late = int((now - due).total_seconds() // 60) + GRACE
    missing = slot_list(latest, ed) or []
    if len(missing) >= 2:   # 여러 판 공백(2026-10-11) — 바로 경보·목록 기록, 빌드는 안 함
        checked = os.popen("TZ=Asia/Bangkok date '+%Y-%m-%d %H:%M:%S %Z'").read().strip() or now.strftime("%Y-%m-%d %H:%M")
        os.makedirs(os.path.dirname(GAPS), exist_ok=True)
        with open(GAPS, "w", encoding="utf-8") as f:
            f.write("# 여러 판 공백 경보(tools/edition_stale.py)\n")
            f.write("확인 시각: %s (방콕)%s\n" % (checked, " [--now 시험 %s]" % now.strftime("%Y-%m-%d %H:%M") if "--now" in sys.argv else ""))
            f.write("라이브 최신: %s\n기대 판(지금 라이브에 있어야 함): %s\n다음 예정 판: %s\n" % (latest, ed, next_slot(ed)))
            f.write("빠진 판 %d개:\n" % len(missing))
            for x in missing:
                f.write("  %s\n" % x)
            f.write("조치: 자동 재생성 안 함(옛 판을 지금 판처럼 올리지 않음). 07:38·18:38 대체 루틴은 기대 판 하나만 예전대로. Max·운영자 판단 필요\n")
        key = "[공백 %s~%s]" % (missing[0], ed)
        w = write("%s ‼️ 여러 판 공백 %s — %d판 빠짐(라이브 최신 = %s, 기대 = %s). 목록: %s" % (stamp, key, len(missing), latest, ed, GAPS), key)
        gapmsg = "‼️ 여러 판 공백 %d판: 라이브 %s, 기대 %s, 빠진 판 %s… 목록 %s %s" % (len(missing), latest, ed, ",".join(missing[:3]), GAPS, "(기록함)" if w else "(이미 기록됨)")
    else:
        gapmsg = None
    key = "[늦음 %s]" % ed
    w = write("%s 최신 판 늦음 %s — 예정보다 %d분 지남, 라이브 최신 = %s. 07:38·18:38 대체 루틴이 다시 만들어야 함(이유는 /workspace/logs/automation.log 의 START/FAIL 줄 참고 — START 가 없으면 예약 실행이 상자에 안 온 것)" % (stamp, key, late, latest), key)
    print("늦음: 기대 %s, 라이브 %s, %d분 지남 %s" % (ed, latest, late, "(기록함)" if w else "(이미 기록됨)"))
    if gapmsg:   # 예전 '늦음' 줄은 그대로 남기고, 마지막 줄 = 공백 경보(preflight 가 마지막 줄을 automation.log 에 남김)
        print(gapmsg)
    return 1


if __name__ == "__main__":
    sys.exit(main())
