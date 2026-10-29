#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""공통 발행 실행기 (news-core S2, 2026-10-29 Claude — 설계서 3-3).

KR·ZH 의 gemini-edition.yml bash 80줄과 VN 의 pipeline/run_vn.py 를 하나로 합쳤다. 채널 차이는 전부 site/<lang>.json 의 "edition" 키로.
순서(고정):
  0 설정 → 1 판 id(하한·이미 있음·담당 표시) → 2 후보(picks) → 3~5 제미나이(원장 예약·검증·상한·격리는 gemini_edition.py 안)
  → 6 저장 commit+push(tools/deploy.sh) → 7 배포(Pages 는 push 가 곧 배포, Cloudflare 는 deploy_cmd) → 8 라이브 대조 → 9 담당 해제·기록
  실패: ops/edition-fail.json 쓰고 그 파일만 push, exit ≠ 0  (3 = 판 생성 실패, 4 = 저장 실패, 5 = 배포·라이브 대조 실패, 1 = 설정·사용법)

  python3 tools/run_edition.py                      # 예약 실행: 지금 시각으로 판 결정
  python3 tools/run_edition.py --edition 2026-11-01-md   # 판 지정(그록 picks push·수동 실행)
  python3 tools/run_edition.py --now "2026-11-01 00:05" --dry    # 시험(제미나이 안 부름, push 안 함)

site/<lang>.json "edition" 키(없으면 기본값 = 한국판 지금 동작):
  picker: "grok_file" (ops/picks/<id>.json 이 있으면 그것, 없으면 code_picks) | "code" | "cmd"(picker_cmd 실행, 마지막 출력 줄 = picks 파일 경로)
  picker_cmd, pre_cmd(판 전 곁 데이터 갱신 등), post_cmd(저장 전 추가 산출물)
  pool, select(0 = 그록 picks 그대로), floor_minutes: {am: [6,40], md: [11,40], pm: [17,40]} (없으면 watch_slots)
  claim: true(담당 표시 사용, KR·ZH) | false(VN)   publisher: "grok"
  deploy: "pages" | "cloudflare" | "none"(시험: 저장까지만)   deploy_cmd(cloudflare 일 때 push 뒤 실행)   live_check: "pages" | "curl" | "none"
  video_feed: true(md 판 뒤 ops/video 생성)   candidates_from: "own" | "kr"(한국판 candidates 브랜치)
  after_deploy_cmd(배포·대조 뒤, 예: zh1 미러), metrics_line: true(VN 형식 ops/metrics.jsonl 한 줄), stale_slots(edition_stale 목표 시각)
"""
import argparse, json, os, pathlib, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import siteconf  # noqa: E402

BKK = timezone(timedelta(hours=7))
OPS = ROOT / "ops"
FAIL = OPS / "edition-fail.json"
C = siteconf.load()
E = dict(picker="grok_file", pool=30, select=0, claim=True, publisher="grok", deploy="pages", live_check="pages",
         video_feed=False, candidates_from="own", pre_cmd="", post_cmd="", picker_cmd="", deploy_cmd="", live_timeout=900, metrics_line=False, after_deploy_cmd="")
E.update(C.get("edition") or {})
SLOT_ORDER = [s for s in C.get("slots") or ["am", "md", "pm"] if s in ("am", "md", "pm")]


def log(*a):
    print("[run_edition]", *a, flush=True)


def sh(cmd, env=None, check=False, capture=False):
    log("$", cmd if isinstance(cmd, str) else " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, shell=isinstance(cmd, str), env=dict(os.environ, **(env or {})),
                       capture_output=capture, text=True)
    if check and r.returncode:
        raise SystemExit("명령 실패(%d): %s" % (r.returncode, cmd))
    return r


def floors():
    """슬롯 → (시, 분) 하한. edition.floor_minutes > watch_slots > 기본."""
    f = E.get("floor_minutes")
    if f:
        return {k: (int(v[0]), int(v[1])) for k, v in f.items()}
    ws = C.get("watch_slots") or [["am", 6, 40], ["md", 11, 40], ["pm", 17, 40]]
    return {s: (int(h), int(m)) for s, h, m in ws}


def slot_for(now):
    """하한 이후의 가장 최근 슬롯. 첫 슬롯 하한 전이면 None(자정·새벽 예약이 아침판을 선점하던 10/29 사고 방지)."""
    fl = floors()
    hm = now.hour * 60 + now.minute
    cur = None
    for s in SLOT_ORDER:
        h, m = fl.get(s, (0, 0))
        if hm >= h * 60 + m:
            cur = s
    return cur


def write_fail(eid, error, **extra):
    OPS.mkdir(exist_ok=True)
    if FAIL.exists():   # gemini_edition 등 하위가 먼저 썼으면 그대로
        return
    rec = dict(at=datetime.now(BKK).isoformat(timespec="seconds"), edition=eid, error=error, **extra)
    FAIL.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def push_fail_record(eid):
    """실패 기록(edition-fail.json·usage)만 커밋·push. 원장 파일은 절대 올리지 않음. 실패해도 조용히."""
    try:
        sh("git add ops/edition-fail.json ops/gemini-usage.jsonl 2>/dev/null; git diff --cached --quiet || git commit -q -m 'ops: edition-fail %s'" % eid)
        for i in range(1, 5):
            if sh("git pull --rebase --autostash -q origin main && git push -q origin HEAD:main").returncode == 0:
                return True
            sh("git rebase --abort 2>/dev/null; true"); time.sleep(i * 5)
    except Exception as ex:
        log("실패 기록 push 못 함:", ex)
    return False


def claim(cmd, eid):
    if not E["claim"]:
        return 0
    return sh([sys.executable, "tools/edition_claim.py", cmd, E["publisher"], eid]).returncode


def fetch_candidates():
    src = "origin" if E["candidates_from"] == "own" else "https://github.com/P-Max168/thai-news-kr"
    (ROOT / "drafts" / "candidates").mkdir(parents=True, exist_ok=True)
    sh("git fetch -q %s +candidates:refs/remotes/cand/candidates && git show cand/candidates:candidates/latest.json > drafts/candidates/latest.json" % src)


def pushed_picks_id():
    """push 이벤트(그록 picks 커밋): 마지막 커밋에서 바뀐 ops/picks/<id>.json 의 id. 하한보다 2~3분 일찍 올려도 그 판을 만들게(예전 yml 과 같음)."""
    r = sh("git diff --name-only HEAD~1 HEAD -- 'ops/picks/*.json'", capture=True)
    ids = [re.sub(r"^ops/picks/(.*)\.json$", r"\1", l.strip()) for l in r.stdout.splitlines() if l.strip()]
    return ids[-1] if ids else ""


def decide_edition(a, now):
    if a.edition:
        return a.edition, ""
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        pid = pushed_picks_id()
        if pid:
            if (ROOT / "data" / (pid + ".json")).exists():
                return None, "이미 있음: %s — picks 다시 올려도 다시 만들지 않음(다시 만들려면 Run workflow 로 판 지정)" % pid
            return pid, ""
    s = a.slot or slot_for(now)
    if not s:
        return None, "하한 전(지금 %s BKK) — 판 고르기 건너뜀" % now.strftime("%H:%M")
    eid = "%s-%s" % (now.strftime("%Y-%m-%d"), s)
    if (ROOT / "data" / (eid + ".json")).exists():
        return None, "이미 있음: %s — 할 일 없음" % eid
    if E["claim"] and not a.dry:
        if sh("git ls-remote origin 'refs/heads/claim/%s/*'" % eid, capture=True).stdout.strip():
            return None, "담당 표시 있음(%s) — 대비 실행 건너뜀" % eid
        if sh([sys.executable, "tools/publisher_guard.py"], env={"TNK_PUBLISHER": E["publisher"]}).returncode:
            return None, "임시 발행 담당 기간 — 자동 판 건너뜀"
    return eid, ""


def make_picks(eid):
    """picks 파일 경로를 돌려준다. 없으면 None."""
    pf = OPS / "picks" / (eid + ".json")
    if E["picker"] in ("grok_file", "code") and pf.exists():
        return str(pf)
    if E["picker"] == "cmd" and E["picker_cmd"]:
        r = sh(E["picker_cmd"].replace("{eid}", eid), capture=True)
        print(r.stdout[-2000:], r.stderr[-2000:])
        if r.returncode:
            return None
        last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        return last[-1] if last and os.path.exists(last[-1]) else (str(pf) if pf.exists() else None)
    fetch_candidates()
    r = sh([sys.executable, "tools/code_picks.py", eid, "--pool", str(E["pool"]), "--select", str(E["select"] or 20)])
    return str(pf) if r.returncode == 0 and pf.exists() else None


def live_check(eid, local_n):
    """라이브 data/index.json 의 latest 가 이 판이고 기사 수가 같은지(설계서 2-1 ③). 못 붙는 환경이면 건너뜀."""
    url = C["site_url"].rstrip("/") + "/data/%s.json?_=%d" % (eid, int(time.time()))
    deadline = time.time() + int(E["live_timeout"])
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (run_edition live check)", "Cache-Control": "no-cache"}), timeout=20) as r:
                d = json.load(r)
            n = len(d.get("stories") or [])
            if n == local_n:
                log("라이브 대조 OK: %s %d건" % (eid, n)); return True
            log("라이브 %d건 ≠ 저장 %d건 — 반영 대기" % (n, local_n))
        except Exception as ex:
            log("라이브 아직:", str(ex)[:80])
        if time.time() > deadline:
            return False
        time.sleep(20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition"); ap.add_argument("--slot", choices=["am", "md", "pm"]); ap.add_argument("--now", help="시험용 'YYYY-MM-DD HH:MM' (BKK)")
    ap.add_argument("--dry", action="store_true", help="제미나이 안 부름·push 안 함"); ap.add_argument("--no-deploy", action="store_true")
    a = ap.parse_args()
    now = datetime.strptime(a.now, "%Y-%m-%d %H:%M").replace(tzinfo=BKK) if a.now else datetime.now(BKK)
    t0 = time.time(); OPS.mkdir(exist_ok=True)
    env = {"TNK_LANG": C["lang"]}
    if E["claim"]:   # 담당 표시를 쓰는 채널(KR·ZH)만. VN 처럼 담당 개념이 없으면 deploy.sh 는 기본(grok)으로 검사 → 표시 없음 = OK
        env["TNK_PUBLISHER"] = E["publisher"]
    log("사이트 %s · picker=%s deploy=%s claim=%s" % (C["lang"], E["picker"], E["deploy"], E["claim"]))

    if E["pre_cmd"]:
        sh(E["pre_cmd"], env=env)   # 곁 데이터(시세·한국 뉴스 등). 실패해도 판은 계속

    eid, why = decide_edition(a, now)
    if not eid:
        log(why); print("skip=1"); return 0
    log("판:", eid)
    if not os.environ.get("GEMINI_API_KEY") and not a.dry:
        log("GEMINI_API_KEY 없음 — 자동 판 건너뜀(비상 발행이 메움)"); print("skip=1"); return 0

    if not a.dry and claim("claim", eid):
        log("담당 표시 HOLD — 다른 담당이 이미 맡음"); print("skip=1"); return 0

    picks = make_picks(eid)
    if not picks:
        write_fail(eid, "no_picks"); push_fail_record(eid) if not a.dry else None; claim("release", eid)
        log("후보 없음(picks 실패) — 비상 발행이 이어받음"); return 3

    cmd = [sys.executable, "tools/gemini_edition.py", eid, picks]
    if E["select"]:
        cmd += ["--select", str(E["select"])]
    if os.environ.get("GEMINI_MODEL"):
        cmd += ["--model", os.environ["GEMINI_MODEL"]]
    if a.dry:
        cmd.append("--dry")
    r = sh(cmd, env=env)
    if r.returncode:
        write_fail(eid, "gemini_edition_exit_%d" % r.returncode)
        if not a.dry:
            push_fail_record(eid)
        claim("release", eid)
        log("판 생성 실패 exit", r.returncode); return 3
    if a.dry:
        log("DRY 끝(판 생성·push 없음)"); return 0

    sh([sys.executable, "tools/share_kit.py", eid], env=env)                      # 공유 카드, 실패해도 계속
    if E["video_feed"] and eid.endswith("-md"):
        sh([sys.executable, "tools/video_picks.py", "--date", eid[:-3]], env=env)  # YouTube Tower 입력, 실패해도 계속
    if E["post_cmd"]:
        sh(E["post_cmd"].replace("{eid}", eid), env=env)
    local_n = len(json.loads((ROOT / "data" / (eid + ".json")).read_text(encoding="utf-8"))["stories"])
    # 기록은 저장(commit) 전에 써야 같은 커밋에 들어간다(news.pmaxone.com 모음 페이지가 ops/last-run.json 을 읽음)
    rec = dict(at=datetime.now(timezone.utc).isoformat(), edition=eid, published=local_n, seconds=round(time.time() - t0, 1),
               event=os.environ.get("GITHUB_EVENT_NAME", "local"), site=C["lang"], picker=E["picker"])
    (OPS / "last-run.json").write_text(json.dumps(dict(metrics=rec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if E.get("metrics_line"):   # VN 형식 한 줄(KR·ZH 는 deploy.sh 안 tools/metrics.py 가 씀)
        with open(OPS / "metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 6 저장: deploy.sh = 담당 확인·커밋·push(원장 파일 제외)·Pages 확인. Cloudflare 채널은 push 까지만(live check none) 하고 deploy_cmd.
    if a.no_deploy:
        log("--no-deploy: 저장·배포 생략"); return 0
    lc = "none" if E["deploy"] in ("cloudflare", "none") else E["live_check"]   # deploy=none: 시험 저장소(저장까지만)
    r = sh("bash tools/deploy.sh", env=dict(env, TNK_LIVE_CHECK=lc))
    if r.returncode:
        write_fail(eid, "deploy_sh_exit_%d" % r.returncode, stage="save"); push_fail_record(eid); claim("release", eid)
        log("저장(push) 실패 — 배포 안 함"); return 4
    sha = sh("git rev-parse --short HEAD", capture=True).stdout.strip()

    # 7 배포(그 커밋으로)
    if E["deploy"] == "cloudflare" and E["deploy_cmd"]:
        r = sh(E["deploy_cmd"], env=env)
        if r.returncode:
            write_fail(eid, "deploy_cmd_exit_%d" % r.returncode, stage="deploy", sha=sha); push_fail_record(eid); claim("release", eid)
            log("배포 실패(저장은 됨 %s)" % sha); return 5

    # 8 라이브 대조
    ok = True
    if E["live_check"] != "none" and E["deploy"] != "none":
        ok = live_check(eid, local_n)
        if not ok:
            write_fail(eid, "live_mismatch", stage="verify", sha=sha, local=local_n); push_fail_record(eid)

    if E["after_deploy_cmd"]:   # 예: zh1 한국어 검수 미러 — 판은 이미 나갔으므로 실패해도 경고만
        if sh(E["after_deploy_cmd"].replace("{eid}", eid), env=env).returncode:
            log("경고: after_deploy_cmd 실패(판은 이미 배포됨)")

    # 9 담당 해제
    claim("release", eid)
    rec.update(sha=sha, live_ok=ok, seconds=round(time.time() - t0, 1))
    print(json.dumps(rec, ensure_ascii=False))
    return 0 if ok else 5


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as ex:
        write_fail("?", "%s:%s" % (type(ex).__name__, ex))
        raise
