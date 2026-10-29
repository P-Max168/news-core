# -*- coding: utf-8 -*-
"""판 공백 감시(GitHub Actions 용, 2026-10-11) — 상자·Grok Bot 루틴 실행기와 다른 고장점.
  .github/workflows/edition-watch.yml 이 GitHub 서버에서 매시간 부름. 상자(/workspace)·실행기를 전혀 쓰지 않음(표준 라이브러리만).
  이유: 10-05~10-11 정기 07:08·18:08 빌드와 07:38·18:38 대체 루틴이 같은 실행기를 써서 같이 멈췄고(6일), 그 사이 경보도 상자 안 파일에만 남았음.

'기대 판' 정의(방콕 시각, UTC+7):
  예정 시각 = 아침판 06:40 (-am), 저녁판 17:40 (-pm) 시작(2026-10-23 변경, 전 07:08·18:08). 허용 = 예정 + 90분 → 아침판 08:10, 저녁판 19:10 까지.
  기대 판 = 허용 시각이 이미 지난 판 중 가장 최근 것.  예) 08:37 → 전날 -pm, 08:38 → 오늘 -am, 19:38 → 오늘 -pm
  라이브 https://tnews.pmaxone.com/data/index.json 의 latest 가 기대 판보다 앞(옛 판)이면 = 공백(예정보다 90분 넘게 늦음).
  generated 는 그 latest 판 data/<id>.json 의 generated(없으면 index.json editions[] 의 generated) — 보고용.

알림 = GitHub 이슈(라벨 edition-gap). 같은 공백(= 같은 라이브 latest)에 열린 이슈가 있으면 새로 안 엶(댓글도 안 씀).
  정상으로 돌아오면 열린 edition-gap 이슈에 '복구' 댓글 달고 닫음. 라이브 latest 가 바뀌었는데 또 늦으면 옛 이슈 닫고 새 이슈 하나.
종료 코드: 0 = 정상 또는 이미 알린 공백(조용), 1 = 새 공백(이슈 열었거나 --dry-run 이면 열 예정), 2 = 라이브를 못 읽음.

  python3 tools/edition_watch.py --dry-run                         # 라이브 확인만, 이슈 안 엶(본문 출력)
  python3 tools/edition_watch.py --dry-run --now "2026-10-11 09:00" --latest 2026-10-05-am --generated 2026-10-05T07:23:46+07:00   # 부숴 보기
  (--now/--latest/--generated 흉내는 --dry-run 일 때만 받음 — 진짜 이슈를 가짜 값으로 열지 않게)"""
import datetime as dt, json, os, pathlib, random, re, sys, time, urllib.error, urllib.request

BKK = dt.timezone(dt.timedelta(hours=7))
SITE = "https://tnews.pmaxone.com/"
REPO = os.environ.get("GITHUB_REPOSITORY", "P-Max168/thai-news-kr")
SLOTS = [("am", 6, 40), ("md", 11, 40), ("pm", 17, 40)]   # 2026-10-27 맥스님: 하루 3판
# 언어판(R-zh-5, 2026-10-18): site/<lang>.json 의 site_url·watch_slots(예 zh 시험 = [["md", 13, 0]]). 한국판은 위 값 그대로
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import siteconf
    _C = siteconf.load()
    if _C.get("lang", "ko") != "ko":
        SITE = _C.get("site_url", SITE)
        REPO = os.environ.get("GITHUB_REPOSITORY", _C.get("repo", REPO))
        SLOTS = [tuple(x) for x in _C.get("watch_slots", SLOTS)]
except Exception as _e:   # 설정을 못 읽으면 한국판 기본값(감시는 계속)
    print("siteconf 못 읽음 — 기본값:", _e, file=sys.stderr)
LIMIT_MIN = 90
LABEL = "edition-gap"
MENTION = "@P-Max168"


def write_gap_marker(latest, expected_ed, now, reason):
    """ops/edition-gap.json + ops/LATEST_GAP.md — 맥스님·그록이 바로 읽는 표식."""
    root = pathlib.Path(__file__).resolve().parent.parent
    ops = root / "ops"; ops.mkdir(exist_ok=True)
    rec = dict(at=now.isoformat(timespec="seconds"), latest=latest, expected=expected_ed, reason=reason, site=SITE)
    (ops / "edition-gap.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 판 공백", "", "- 시각(BKK): %s" % rec["at"], "- 라이브 latest: `%s`" % latest,
             "- 기대 판: `%s`" % expected_ed, "- 이유: %s" % reason, "- 사이트: %s" % SITE, ""]
    (ops / "LATEST_GAP.md").write_text("\n".join(lines), encoding="utf-8")
    with open(ops / "edition-gap.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def expected(now):
    """(기대 판 id, 예정 시각, 허용 시각) — 허용(예정+90분)이 now 이하인 가장 최근 판"""
    best = None
    for back in (0, 1):
        d = (now - dt.timedelta(days=back)).date()
        for slot, h, m in SLOTS:
            sched = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=BKK)
            dl = sched + dt.timedelta(minutes=LIMIT_MIN)
            if dl <= now and (best is None or dl > best[2]):
                best = ("%s-%s" % (d.isoformat(), slot), sched, dl)
    return best


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url + ("&" if "?" in url else "?") + "_=%d" % random.randrange(10**9),
                                         headers={"Cache-Control": "no-cache", "User-Agent": "edition-watch"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:  # noqa
            last = "%s: %s" % (type(e).__name__, e)
            if i < tries - 1:
                time.sleep(3 * (i + 1))
    return None, last


def live():
    idx, err = get_json(SITE + "data/index.json")
    if idx is None:
        return None, None, "index.json 읽기 실패(%s)" % err
    latest = idx.get("latest")
    if not latest:
        return None, None, "index.json 에 latest 없음"
    gen = None
    ed, _ = get_json(SITE + "data/%s.json" % latest, tries=2)
    if ed:
        gen = ed.get("generated")
    if not gen:
        for e in idx.get("editions") or []:
            if e.get("id") == latest:
                gen = e.get("generated")
    return latest, gen, None


def gh(method, path, body=None):
    tok = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "edition-watch", "X-GitHub-Api-Version": "2022-11-28"}
    if tok:
        headers["Authorization"] = "Bearer " + tok
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request("https://api.github.com" + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8")
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def open_gap_issues():
    st, js = gh("GET", "/repos/%s/issues?state=open&labels=%s&per_page=50" % (REPO, LABEL))
    if st != 200 or not isinstance(js, list):
        return None, "열린 이슈 목록 못 읽음(%s %s)" % (st, js if not isinstance(js, list) else "")
    out = []
    for it in js:
        if it.get("pull_request"):
            continue
        m = re.search(r"<!-- edition-gap latest=(\S+) expected=(\S+) -->", it.get("body") or "")
        out.append((it["number"], m.group(1) if m else None, m.group(2) if m else None, it.get("title")))
    return out, None


def gap_list(latest, upto):
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(am|md|pm)$", latest or "")
    order = [s[0] for s in SLOTS]   # 한국판 am→pm, zh 시험 md 하나(하루 1판)
    if not m or m.group(2) not in order:
        return []
    d, slot, out = dt.date.fromisoformat(m.group(1)), m.group(2), []
    for _ in range(120):
        i = order.index(slot)
        if i + 1 < len(order):
            slot = order[i + 1]
        else:
            slot, d = order[0], d + dt.timedelta(days=1)
        ed = "%s-%s" % (d.isoformat(), slot)
        if ed > upto:
            break
        out.append(ed)
    return out


def main(argv):
    dry = "--dry-run" in argv
    def opt(name):
        if name in argv:
            if not dry:
                print("거부: %s 흉내는 --dry-run 일 때만" % name); sys.exit(2)
            return argv[argv.index(name) + 1]
        return None
    real_now = dt.datetime.now(BKK)
    now = real_now
    if opt("--now"):
        now = dt.datetime.strptime(opt("--now"), "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
    ed, sched, dl = expected(now)
    if opt("--latest"):
        latest, gen, err = opt("--latest"), opt("--generated"), None
    else:
        latest, gen, err = live()
    checked = real_now.strftime("%Y-%m-%d %H:%M:%S") + " (방콕)" + ("  [--now 흉내 %s]" % now.strftime("%Y-%m-%d %H:%M") if opt("--now") else "")
    print("확인 시각: %s" % checked)
    print("기대 판: %s (예정 %s, 허용 %s 방콕)" % (ed, sched.strftime("%m-%d %H:%M"), dl.strftime("%m-%d %H:%M")))
    if err:
        print("‼️ 라이브를 못 읽음: %s" % err); return 2
    print("라이브 latest: %s · generated: %s" % (latest, gen))
    issues, ierr = open_gap_issues()
    if latest >= ed:
        print("정상: 라이브 latest 가 기대 판 이상 — 조용히 끝(이슈 안 엶)")
        for num, il, ie, _t in (issues or []):
            msg = "복구 확인: %s 라이브 latest = %s (기대 %s 이상). edition-watch 가 자동으로 닫음." % (checked, latest, ed)
            if dry:
                print("[dry-run] 열린 공백 이슈 #%d 에 댓글·닫기 예정: %s" % (num, msg))
            else:
                gh("POST", "/repos/%s/issues/%d/comments" % (REPO, num), {"body": msg})
                st, _ = gh("PATCH", "/repos/%s/issues/%d" % (REPO, num), {"state": "closed", "state_reason": "completed"})
                print("열린 공백 이슈 #%d 닫음(%s)" % (num, st))
        return 0
    late = int((now - sched).total_seconds() // 60)
    missing = gap_list(latest, ed)
    title = "‼️ 판 공백: 라이브 최신 %s, 기대 판 %s (%d판 빠짐)" % (latest, ed, len(missing))
    body = "\n".join([
        "%s 태국 뉴스 한눈에 — 예정 판이 라이브에 없어요(예정 + %d분 지남)." % (MENTION, LIMIT_MIN),
        "",
        "- 확인 시각: %s" % checked,
        "- 라이브 latest: `%s`" % latest,
        "- 라이브 generated: `%s`" % gen,
        "- 기대 판: `%s` (예정 %s, 허용 %s 방콕) — 예정보다 %d분 늦음" % (ed, sched.strftime("%m-%d %H:%M"), dl.strftime("%m-%d %H:%M"), late),
        "- 빠진 판 %d개: %s" % (len(missing), ", ".join(missing) if len(missing) <= 14 else ", ".join(missing[:14]) + " …"),
        "",
        "확인할 것: 상자의 /workspace/logs/automation.log 에 07:08·18:08 START 줄이 있는지(없으면 예약 실행이 상자에 안 온 것).",
        "지난 판은 자동으로 다시 만들지 않아요(옛 뉴스를 지금 판처럼 올리지 않음). 이 감시는 GitHub Actions 에서 돌아서 상자·루틴 실행기가 멈춰도 알려요.",
        "같은 공백(같은 라이브 latest)이면 이 이슈 하나만 쓰고, 정상으로 돌아오면 자동으로 닫혀요.",
        "",
        "<!-- edition-gap latest=%s expected=%s -->" % (latest, ed),
    ])
    if issues is None:
        print("주의: %s — 중복 확인 못 함" % ierr)
        issues = []
    same = [i for i in issues if i[1] == latest]
    if same:
        write_gap_marker(latest, ed, now, "이미 알린 공백(이슈 #%d)" % same[0][0])
        print("이미 알린 공백: 열린 이슈 #%d (latest=%s, 처음 기대 %s) — 새 이슈 안 엶" % (same[0][0], same[0][1], same[0][2]))
        return 0
    write_gap_marker(latest, ed, now, "예정보다 %d분 늦음" % late)
    print("공백: 예정보다 %d분 늦음 — 새 이슈 %s" % (late, "열 예정(dry-run, 안 엶)" if dry else "엶"))
    print("---- 이슈 제목 ----\n%s\n---- 이슈 본문 ----\n%s\n----" % (title, body))
    if dry:
        for num, il, ie, _t in issues:
            print("[dry-run] 다른 공백의 옛 이슈 #%d(latest=%s) 닫을 예정" % (num, il))
        return 1
    gh("POST", "/repos/%s/labels" % REPO, {"name": LABEL, "color": "d73a4a", "description": "판 공백 감시(edition-watch)"})  # 이미 있으면 422 — 무시
    st, js = gh("POST", "/repos/%s/issues" % REPO, {"title": title, "body": body, "labels": [LABEL]})
    if st != 201:
        print("‼️ 이슈 열기 실패: %s %s" % (st, js)); return 2
    print("이슈 열림: #%s %s" % (js.get("number"), js.get("html_url")))
    for num, il, ie, _t in issues:
        gh("POST", "/repos/%s/issues/%d/comments" % (REPO, num), {"body": "라이브 latest 가 %s 로 바뀌었고 새 공백은 #%s 에서 이어서 봐요." % (latest, js.get("number"))})
        gh("PATCH", "/repos/%s/issues/%d" % (REPO, num), {"state": "closed"})
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
