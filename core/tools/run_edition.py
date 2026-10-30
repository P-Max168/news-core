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

  picker "base_add" (2026-10-30 P1, 설계서 '기사 고르기 통합 v1' — 모든 채널 같은 2단계):
    ① 기본 목록 = 코드(code_picks, 후보가 cand_max_age_min 분보다 묵었으면 그 자리에서 다시 수집) 또는 base_cmd(VN vn_picks)
       → ops/base/<id>.json (본문 없이 기록)
    ② 그록 추가 ops/grok-add/<id>.json 을 tools/grok_add.py 가 검사(최대 4건·수집처 매체·24시간·같은 사건·큰 사건 angle·boost)
    ③ 그록 추가(must_keep) → boost → 기본 목록 순으로 합쳐 제미나이에 넘김(select = 판 기사 수, 그록 추가분 포함)
    ④ ops/last-run.json selection = {path: code|code+grok|code+grok-big, base, adds, boost, dropped, big_event}
    edition.grok_add = {max: 4, sources: [수집처 목록 파일 또는 https 주소]}. 마감은 발행 예약 시각 그 자체(그 전에 올라온 파일만 씀).
"""
import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import siteconf  # noqa: E402

BKK = timezone(timedelta(hours=7))
OPS = ROOT / "ops"
FAIL = OPS / "edition-fail.json"
C = siteconf.load()
E = dict(picker="grok_file", pool=30, select=0, claim=True, publisher="grok", deploy="pages", live_check="pages",
         video_feed=False, candidates_from="own", pre_cmd="", post_cmd="", picker_cmd="", deploy_cmd="", live_timeout=900, metrics_line=False, after_deploy_cmd="",
         base_cmd="", grok_add={}, cand_max_age_min=60)
E.update(C.get("edition") or {})
SLOT_ORDER = [s for s in C.get("slots") or ["am", "md", "pm"] if s in ("am", "md", "pm")]
T0 = time.time()   # 이번 실행 시작 — 이보다 오래된 edition-fail.json 은 지난 실행의 기록
PICKS_EARLY_MIN = 15   # 그록 picks 가 하한보다 이만큼 일찍 와 있어도 그 판으로 만든다


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
    # gemini_edition 등 하위가 '이번 실행에서' 먼저 썼으면 그대로. 지난 판·지난 실행의 기록(커밋돼 남은 것)은 덮어씀 —
    # 안 그러면 비상 발행이 엉뚱한 판의 실패를 읽는다(2026-10-30).
    if FAIL.exists() and FAIL.stat().st_mtime >= T0 - 1:
        return
    rec = dict(at=datetime.now(BKK).isoformat(timespec="seconds"), edition=eid, error=error, **extra)
    FAIL.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def push_fail_record(eid):
    """실패 기록(edition-fail.json·usage)만 origin/main 위에 커밋·push. 원장 파일은 절대 올리지 않음. 실패해도 조용히.
    (2026-10-30) 작업 폴더의 HEAD 를 push 하면 저장 단계에서 못 올린 판 커밋까지 같이 나가(Pages 채널은 push = 배포)
    '실패로 기록된 판이 라이브에 뜨는' 일이 생긴다 → 임시 worktree(origin/main)에서 기록 파일만 올린다."""
    files = [f for f in ("ops/edition-fail.json", "ops/gemini-usage.jsonl") if (ROOT / f).exists()]
    if not files:
        return False
    wt = pathlib.Path(tempfile.mkdtemp(prefix="edition-fail-"))
    try:
        for i in range(1, 5):
            sh("git worktree remove --force '%s' 2>/dev/null; rm -rf '%s'; git fetch -q origin main && git worktree add -q --detach '%s' origin/main" % (wt, wt, wt))
            if not (wt / "ops").exists():
                (wt / "ops").mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.copy2(ROOT / f, wt / f)
            r = subprocess.run("git add %s && (git diff --cached --quiet || git commit -q -m 'ops: edition-fail %s') && git push -q origin HEAD:main"
                               % (" ".join(files), eid), cwd=wt, shell=True, capture_output=True, text=True)
            if r.returncode == 0:
                return True
            log("실패 기록 push 재시도(%d): %s" % (i, (r.stderr or "")[-200:])); time.sleep(i * 5)
    except Exception as ex:
        log("실패 기록 push 못 함:", ex)
    finally:
        sh("git worktree remove --force '%s' 2>/dev/null; rm -rf '%s'; git worktree prune" % (wt, wt))
    return False


def claim(cmd, eid):
    if not E["claim"]:
        return 0
    return sh([sys.executable, "tools/edition_claim.py", cmd, E["publisher"], eid]).returncode


def fetch_candidates():
    src = "origin" if E["candidates_from"] == "own" else "https://github.com/P-Max168/thai-news-kr"
    (ROOT / "drafts" / "candidates").mkdir(parents=True, exist_ok=True)
    sh("git fetch -q %s +candidates:refs/remotes/cand/candidates && git show cand/candidates:candidates/latest.json > drafts/candidates/latest.json" % src)


PICKS_RE = re.compile(r"^ops/picks/(\d{4}-\d{2}-\d{2}-(?:am|md|pm))\.json$")


def pushed_picks_id():
    """push 이벤트(그록 picks 커밋): 그 push 에서 추가·수정된 ops/picks/<id>.json 의 id. 하한보다 2~3분 일찍 올려도 그 판을 만들게.
    (2026-10-30) 예전엔 HEAD~1..HEAD 를 봤는데, checkout 이 ref_name(최신 main)이라 picks push 뒤 다른 커밋(시세·한국뉴스)이
    끼면 picks 가 안 보여 판을 놓쳤다 → 이벤트 페이로드(push 에 든 모든 커밋의 파일 목록)를 먼저 본다."""
    ids = []
    try:
        ev = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        for c in ev.get("commits") or []:
            for f in (c.get("added") or []) + (c.get("modified") or []):
                m = PICKS_RE.match(f)
                if m:
                    ids.append(m.group(1))
    except Exception:
        pass
    if not ids:
        sha = os.environ.get("GITHUB_SHA") or "HEAD"
        r = sh("git diff --name-only %s~1 %s -- 'ops/picks/*.json'" % (sha, sha), capture=True)
        ids = [m.group(1) for m in (PICKS_RE.match(l.strip()) for l in r.stdout.splitlines()) if m]
    return sorted(ids)[-1] if ids else ""


def waiting_picks_id(now):
    """그록 picks 가 저장소에 있는데 아직 판이 없는 오늘 판(하한 PICKS_EARLY_MIN 분 전부터). picks push 실행이 대기열에서
    밀려 취소되거나(concurrency) 늦어도, 다음 예약·감시·수동 실행이 그 picks 로 판을 만들게(2026-10-30)."""
    if E["picker"] != "grok_file":
        return ""
    fl, day, hm = floors(), now.strftime("%Y-%m-%d"), now.hour * 60 + now.minute
    best = ""
    for s in SLOT_ORDER:
        h, m = fl.get(s, (0, 0))
        eid = "%s-%s" % (day, s)
        if hm >= h * 60 + m - PICKS_EARLY_MIN and (OPS / "picks" / (eid + ".json")).exists() and not (ROOT / "data" / (eid + ".json")).exists():
            best = eid
    return best


def decide_edition(a, now):
    if a.edition:
        if (ROOT / "data" / (a.edition + ".json")).exists():   # 발행된 판은 절대 다시 만들지 않음(덮어쓰기 금지) — 배포 확인만
            return None, "이미 있음: %s — 지정해도 다시 만들지 않음|REDEPLOY:%s" % (a.edition, a.edition)
        return a.edition, ""
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        pid = pushed_picks_id()
        if pid:
            if (ROOT / "data" / (pid + ".json")).exists():
                return None, "이미 있음: %s — picks 다시 올려도 다시 만들지 않음(다시 만들려면 Run workflow 로 판 지정)" % pid
            return pid, ""
    s = a.slot or slot_for(now)
    eid = "%s-%s" % (now.strftime("%Y-%m-%d"), s) if s else ""
    wp = "" if a.slot else waiting_picks_id(now)
    if wp and wp > eid:   # 하한 조금 전이거나 지난 판이 이미 있어도, 판 없는 그록 picks 가 있으면 그 판
        log("판 없는 그록 picks 발견:", wp)
        eid = wp
    if not eid:
        return None, "하한 전(지금 %s BKK) — 판 고르기 건너뜀" % now.strftime("%H:%M")
    if (ROOT / "data" / (eid + ".json")).exists():
        return None, "이미 있음: %s — 할 일 없음|REDEPLOY:%s" % (eid, eid)
    if E["claim"] and not a.dry:
        if sh("git ls-remote origin 'refs/heads/claim/%s/*'" % eid, capture=True).stdout.strip():
            return None, "담당 표시 있음(%s) — 대비 실행 건너뜀" % eid
        if sh([sys.executable, "tools/publisher_guard.py"], env={"TNK_PUBLISHER": E["publisher"]}).returncode:
            return None, "임시 발행 담당 기간 — 자동 판 건너뜀"
    return eid, ""


SEL = {}   # base_add 고르기 결과(last-run.json selection)


def ensure_fresh_candidates(now=None):
    """후보 목록이 cand_max_age_min 분보다 묵었으면 이 실행 안에서 다시 수집(2026-10-30: 10-30 점심판 후보가 09:07 수집분 그대로였음 —
    11:17 수집 예약이 안 돎). 수집기·수집처 목록이 있는 채널(KR)만. 실패하면 묵은 목록 그대로(판은 계속)."""
    lf = ROOT / "drafts" / "candidates" / "latest.json"
    now = now or datetime.now(BKK)
    try:
        gen = datetime.fromisoformat(json.loads(lf.read_text(encoding="utf-8"))["generated"])
        age = (now - (gen if gen.tzinfo else gen.replace(tzinfo=BKK))).total_seconds() / 60
    except Exception:
        age = 1e9
    if age <= int(E["cand_max_age_min"]):
        log("후보 목록 %.0f분 전 수집 — 그대로 씀" % age); return age
    srcf = ROOT / "tools" / "sources.json"
    if not srcf.exists() and E.get("cand_sources_url"):   # ZH: 한국판 수집처 목록을 받아 같은 수집기로
        try:
            srcf = ROOT / "drafts" / "sources.json"
            with urllib.request.urlopen(urllib.request.Request(E["cand_sources_url"], headers={"User-Agent": "news-core run_edition"}), timeout=20) as r:
                srcf.write_bytes(r.read())
        except Exception as ex:
            log("수집처 목록 못 받음(%s)" % str(ex)[:60]); srcf = ROOT / "tools" / "sources.json"
    if not ((ROOT / "tools" / "collect.py").exists() and srcf.exists()):
        log("후보 목록 %.0f분 묵음 — 이 채널엔 수집기·수집처 목록이 없어 그대로 씀" % age); return age
    log("후보 목록 %.0f분 묵음 — 지금 다시 수집" % age)
    r = sh([sys.executable, "tools/collect.py", "--hours", "14", "--timeout", "12", "--workers", "16", "--sources", str(srcf),
            "--out", str(ROOT / "drafts" / "candidates")])
    if r.returncode:
        log("다시 수집 실패(exit %d) — 묵은 목록으로 계속" % r.returncode)
    return age


def make_base_add(eid):
    """picker base_add: 기본 목록 + 그록 추가 → 합친 picks 파일 경로(drafts/merged, 커밋 안 됨). 실패면 None."""
    import grok_add
    target = int(E["select"] or 25)
    bf = OPS / "base" / (eid + ".json")
    bf.parent.mkdir(parents=True, exist_ok=True)
    if E["base_cmd"]:   # VN: 사이트 전용 수집·본문(vn_picks) — 마지막 출력 줄 = 본문 포함 picks 파일
        r = sh(E["base_cmd"].replace("{eid}", eid), capture=True)
        print(r.stdout[-2000:], r.stderr[-2000:])
        last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        if r.returncode or not last or not os.path.exists(last[-1]):
            return None
        base_doc = json.loads(pathlib.Path(last[-1]).read_text(encoding="utf-8"))
    else:
        try:
            fetch_candidates()
        except Exception as ex:
            log("후보 목록 못 받음:", ex)
        ensure_fresh_candidates()
        r = sh([sys.executable, "tools/code_picks.py", eid, "--pool", str(E["pool"]), "--select", str(target), "--out", str(bf)])
        if r.returncode or not bf.exists():
            return None
        base_doc = json.loads(bf.read_text(encoding="utf-8"))
    bf.write_text(json.dumps(dict(base_doc, picks=[{k: v for k, v in p.items() if k != "text"} for p in base_doc.get("picks") or []]),
                             ensure_ascii=False, indent=1) + "\n", encoding="utf-8")   # 기록(본문 빼고 — 저작권)
    cand = {}
    try:   # 후보 목록 url → 항목(그록 boost 가 기본 목록 밖 후보를 가리킬 때 끌어올림)
        cj = json.loads((ROOT / "drafts" / "candidates" / "latest.json").read_text(encoding="utf-8"))
        for tv in (cj.get("topics") or {}).values():
            for x in (tv.get("items") if isinstance(tv, dict) else tv) or []:
                cand.setdefault(x.get("url"), x)
    except Exception:
        pass
    res = grok_add.load(eid, base_doc.get("picks") or [], E.get("grok_add") or {}, cand=cand)
    doc = grok_add.merge(base_doc, res, target)
    SEL.update(path=grok_add.path_label(res), base=len(base_doc.get("picks") or []), adds=len(res["adds"]), boost=doc["grok_add"]["boost"],
               big_event=res["big_event"], grok_file=res["found"], dropped=res["dropped"][:10], select=target)
    log("고르기: %s · 기본 %d · 그록 추가 %d · boost %d · 뺀 것 %d%s" % (SEL["path"], SEL["base"], SEL["adds"], SEL["boost"], len(res["dropped"]),
                                                               "" if res["found"] else " (그록 파일 없음 — 코드 목록만)"))
    for d in res["dropped"]:
        log("  그록 추가 뺌:", d.get("why"), d.get("url"))
    mf = ROOT / "drafts" / "merged" / (eid + ".json")
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(mf)


def make_picks(eid):
    """picks 파일 경로를 돌려준다. 없으면 None."""
    if E["picker"] == "base_add":
        return make_base_add(eid)
    pf = OPS / "picks" / (eid + ".json")
    if E["picker"] in ("grok_file", "code"):
        try:   # 후보 목록은 그록 picks 일 때도 받는다 — gemini_edition 이 picks 에 빠진 제목·매체·시각을 채우는 데 씀(옛 yml 과 같음). 실패해도 계속
            fetch_candidates()
        except Exception as ex:
            log("후보 목록 못 받음(계속):", ex)
    if E["picker"] in ("grok_file", "code") and pf.exists():
        return str(pf)
    if E["picker"] == "cmd" and E["picker_cmd"]:
        r = sh(E["picker_cmd"].replace("{eid}", eid), capture=True)
        print(r.stdout[-2000:], r.stderr[-2000:])
        if r.returncode:
            return None
        last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        return last[-1] if last and os.path.exists(last[-1]) else (str(pf) if pf.exists() else None)
    r = sh([sys.executable, "tools/code_picks.py", eid, "--pool", str(E["pool"]), "--select", str(E["select"] or 20)])
    return str(pf) if r.returncode == 0 and pf.exists() else None


def redeploy_if_stale(eid, env):
    """이미 저장된 판이 라이브에 없으면(배포 실패 뒤 재실행) deploy_cmd 만 다시. 라이브가 맞으면 아무것도 안 함."""
    local_n = len(json.loads((ROOT / "data" / (eid + ".json")).read_text(encoding="utf-8"))["stories"])
    url = C["site_url"].rstrip("/") + "/data/%s.json?_=%d" % (eid, int(time.time()))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (run_edition redeploy check)", "Cache-Control": "no-cache"}), timeout=20) as r:
            d = json.load(r)
            if len(d.get("stories") or []) == local_n and d.get("generated") == local_generated(eid):
                log("라이브도 %s(%d건) — 재배포 불필요" % (eid, local_n)); print("skip=1"); return 0
    except Exception as ex:
        log("라이브에 %s 없음(%s) — 저장된 판을 다시 배포" % (eid, str(ex)[:60]))
    if sh(E["deploy_cmd"], env=env).returncode:
        write_fail(eid, "redeploy_cmd_failed", stage="deploy"); push_fail_record(eid); return 5
    if not live_check(eid, local_n):
        write_fail(eid, "live_mismatch_after_redeploy", stage="verify"); push_fail_record(eid); return 5
    log("재배포 완료:", eid); return 0


def local_generated(eid):
    return json.loads((ROOT / "data" / (eid + ".json")).read_text(encoding="utf-8")).get("generated")


def live_check(eid, local_n):
    """라이브 data/<판>.json 이 저장본과 같은지 — 기사 수와 generated(설계서 2-1 ③: 같은 판 id 라도 다른 실행이 만든 것이면 다름)."""
    gen = local_generated(eid)
    url = C["site_url"].rstrip("/") + "/data/%s.json?_=%d" % (eid, int(time.time()))
    deadline = time.time() + int(E["live_timeout"])
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (run_edition live check)", "Cache-Control": "no-cache"}), timeout=20) as r:
                d = json.load(r)
            n = len(d.get("stories") or [])
            if n == local_n and (not gen or d.get("generated") == gen):
                log("라이브 대조 OK: %s %d건 generated %s" % (eid, n, gen)); return True
            log("라이브 %d건·%s ≠ 저장 %d건·%s — 반영 대기" % (n, d.get("generated"), local_n, gen))
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
        if "|REDEPLOY:" in why:   # 저장은 됐는데 배포가 안 된 판(Codex P1, 2026-10-29): Cloudflare 채널은 라이브 대조 뒤 배포만 다시 — 제미나이 호출 없음
            why, done_eid = why.split("|REDEPLOY:")
            log(why)
            if E["deploy"] == "cloudflare" and E["deploy_cmd"] and not a.dry:
                return redeploy_if_stale(done_eid, env)
            print("skip=1"); return 0
        log(why); print("skip=1"); return 0
    log("판:", eid)
    if not os.environ.get("GEMINI_API_KEY") and not a.dry:
        # (2026-10-30) 예전엔 초록 skip — 운영 규칙(초록 skip 은 하한 전·이미 있음·담당 표시뿐)과 어긋나 키가 빠져도 아무도 모름 → 실패로
        write_fail(eid, "missing_GEMINI_API_KEY"); push_fail_record(eid)
        log("GEMINI_API_KEY 없음 — 판 못 만듦(저장소 Secret 확인). 비상 발행이 edition-fail.json 을 보고 메움"); return 3

    if not a.dry and claim("claim", eid):
        log("담당 표시 HOLD — 다른 담당이 이미 맡음"); print("skip=1"); return 0

    picks = make_picks(eid)
    if not picks:
        write_fail(eid, "no_picks")
        if not a.dry:
            push_fail_record(eid); claim("release", eid)
        log("후보 없음(picks 실패) — 비상 발행이 이어받음"); return 3

    cmd = [sys.executable, "tools/gemini_edition.py", eid, picks]
    if E["select"] and E["picker"] != "base_add":   # base_add 는 합친 picks 파일 안의 select(판 기사 수)를 씀
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
    if SEL:
        rec["selection"] = SEL
    try:   # 사실 대조로 뺀 기사(gemini_edition 실행 기록 마지막 줄)
        last = (OPS / "gemini-usage.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
        fd = json.loads(last).get("factcheck_drops")
        if fd and json.loads(last).get("edition") == eid:
            rec["factcheck_drops"] = fd
    except Exception:
        pass
    (OPS / "last-run.json").write_text(json.dumps(dict(metrics=rec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if E.get("metrics_line"):   # VN 형식 한 줄(KR·ZH 는 deploy.sh 안 tools/metrics.py 가 씀)
        with open(OPS / "metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 6 저장: deploy.sh = 담당 확인·커밋·push(원장 파일 제외)·Pages 확인. Cloudflare 채널은 push 까지만(live check none) 하고 deploy_cmd.
    if a.no_deploy:
        log("--no-deploy: 저장·배포 생략"); return 0
    lc = "none" if E["deploy"] in ("cloudflare", "none") else E["live_check"]   # deploy=none: 시험 저장소(저장까지만)
    r = sh("bash tools/deploy.sh", env=dict(env, TNK_LIVE_CHECK=lc))
    if r.returncode == 4:   # deploy.sh 담당 확인: 그사이 다른 담당(Claude 비상 take)이 이 판을 가져감 → 실패 아님, 넘겨줌
        claim("release", eid)
        log("다른 담당이 %s 를 가져감 — 이 실행은 배포하지 않고 끝(실패 기록 없음)" % eid); print("skip=1"); return 0
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

    if E["after_deploy_cmd"] and os.environ.get("AFTER_DEPLOY_OFF") == "1":   # 저장소 변수 AFTER_DEPLOY_OFF=1 (옛 ZH1_MIRROR=off)
        log("after_deploy_cmd 꺼짐(AFTER_DEPLOY_OFF=1)")
    elif E["after_deploy_cmd"]:   # 예: zh1 한국어 검수 미러 — 판은 이미 나갔으므로 실패해도 경고만
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
