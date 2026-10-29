#!/usr/bin/env python3
"""news-core → 사이트 동기화. 기본은 DRY-RUN(아무것도 push/PR 안 함).
사용: python3 sync.py --site vn --clone /tmp/vn-news-kr [--apply]
--apply: 브랜치 push + PR 생성 + (보호 영역 아니면) auto-merge. 3단계 이후에만 사용.
끄기: 사이트 저장소에 .core-skip 파일 또는 Actions 변수 CORE_SYNC=off.
"""
import argparse, difflib, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile
CORE = pathlib.Path(__file__).resolve().parent
M = json.load(open(CORE / "core.json"))

def sh(cmd, cwd, check=False, env=None):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=600, env=env)
    if check and p.returncode: raise SystemExit(f"FAIL: {cmd}\n{p.stdout[-2000:]}{p.stderr[-2000:]}")
    return p

def skip(site, clone):
    if (clone / ".core-skip").exists(): return ".core-skip 파일"
    p = sh(f"gh variable get CORE_SYNC -R {M['sites'][site]['repo']}", clone)
    if p.returncode == 0 and p.stdout.strip().lower() == "off": return "CORE_SYNC=off"
    return None

def build_html(root):
    for c in M["html_build_cmds"]: sh(c, root)
    return {str(p.relative_to(root)): p.read_text(errors="replace") for p in root.rglob("*.html") if ".git" not in p.parts}

def html_diff(a, b):
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out += list(difflib.unified_diff((a.get(k) or "").splitlines(), (b.get(k) or "").splitlines(), k, k, lineterm=""))
    return out

def protected(changed_text):
    hits = set()
    for cat, pats in M["protected_patterns"].items():
        if any(p.lower() in changed_text.lower() for p in pats): hits.add(cat)
    return sorted(hits)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--site", required=True); ap.add_argument("--clone", required=True)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--stage", type=int, default=M["stage"])
    ap.add_argument("--pr-body", default="")
    ap.add_argument("--pull", action="store_true", help="당겨오기 모드(2026-10-29): 검사 통과 시 --clone 작업 폴더에 공통 파일을 직접 복사(커밋·PR은 호출한 워크플로가)")
    a = ap.parse_args()
    clone = pathlib.Path(a.clone).resolve(); r = {"site": a.site, "dry_run": not (a.apply or a.pull)}
    why = skip(a.site, clone)
    if why: r["skipped"] = why; print(json.dumps(r, ensure_ascii=False)); return
    if a.pull: a.stage = max(a.stage, 3)   # 당겨오기는 코어가 사이트보다 앞선 상태가 정상 — 2단계 '0줄' 게이트는 안 씀
    with tempfile.TemporaryDirectory() as td:
        before, after = pathlib.Path(td, "before"), pathlib.Path(td, "after")
        shutil.copytree(clone, before, ignore=shutil.ignore_patterns(".git")); shutil.copytree(clone, after, ignore=shutil.ignore_patterns(".git"))
        file_diff, changed = [], []
        for f in M["files"]:
            s, d = CORE / f["src"], after / f["dst"]
            old = d.read_text(errors="replace") if d.exists() else ""
            new = s.read_text(errors="replace")
            if old != new:
                changed.append(f["dst"]); file_diff += list(difflib.unified_diff(old.splitlines(), new.splitlines(), f["dst"], f["dst"], lineterm=""))
                shutil.copy2(s, d)
        r["files_changed"] = changed; r["file_diff_lines"] = len(file_diff)
        # 워크플로 템플릿(core/workflows/*.yml): 사이트 cron 줄(CORE-PULL-KEEP 블록)은 지키고 나머지만 갱신
        wf_changed = sync_workflows(after)
        r["workflows_changed"] = wf_changed; changed += wf_changed
        # 검사: py_compile
        pyc = [p for p in (after / "tools").glob("*.py")]
        bad = [str(p.name) for p in pyc if sh(f"python3 -m py_compile '{p}'", after).returncode]
        r["py_compile"] = "ok" if not bad else f"fail {bad}"
        # preflight: 상자용(실행 기록·pull)이라 시험 모드로 문법만 + 시험 실행
        r["preflight_syntax"] = "ok" if sh("bash -n tools/preflight.sh", after).returncode == 0 else "fail"
        # site_build 건조 실행
        p = sh("python3 tools/site_build.py --root . --check", after); r["site_build_check"] = "ok" if p.returncode == 0 else "fail"
        # test_pwa: 로컬 서버 띄워 실행
        pb, pa = run_pwa(before), run_pwa(after)
        new_fail = sorted(set(pa) - set(pb))
        r["test_pwa"] = "ok" if not new_fail else f"fail(새 실패) {new_fail}"
        if pb: r["test_pwa_known_fail"] = pb  # 변경 전부터 있던 실패(사이트 고유), 막지 않음
        # HTML 전후 비교
        hd = html_diff(build_html(before), build_html(after)); r["html_diff_lines"] = len(hd)
        if a.stage <= 2: r["html_gate"] = "pass" if not hd and not file_diff else "fail(2단계는 0줄이어야 함)"
        else:
            unexplained = [l for l in hd if l.startswith(("+++", "---")) and l.split()[-1] not in a.pr_body]
            r["html_gate"] = "pass" if not unexplained else f"fail: PR 설명에 없는 차이 {sorted(set(unexplained))[:10]}"
        r["protected"] = protected("\n".join(changed + file_diff))
    ok = r["py_compile"] == "ok" and r["preflight_syntax"] == "ok" and r["site_build_check"] == "ok" and r["test_pwa"] in ("ok", "skip") and r["html_gate"] == "pass"
    r["checks_pass"] = ok
    if a.pull:
        if ok and changed:
            for f in M["files"]:
                d = clone / f["dst"]; d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(CORE / f["src"], d)
            sync_workflows(clone)
            r["pulled"] = changed
        elif not changed: r["pulled"] = "변경 없음"
    if a.apply and changed and ok:
        if os.environ.get("CORE_STAGE_LOCK") != "unlocked": r["apply"] = "잠김(CORE_STAGE_LOCK). 3단계 전에는 PR 안 만듦"
        else: r["apply"] = open_pr(a.site, clone, r, a.pr_body)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)

def sync_workflows(root):
    """core/workflows/<name>.yml → <root>/.github/workflows/<name>.yml. 사이트의 cron 블록(# CORE-PULL-KEEP 다음부터 다음 빈 줄/키까지)은 보존."""
    out = []
    wd = CORE / "core" / "workflows"
    if not wd.exists(): return out
    for src in sorted(wd.glob("*.yml")):
        dst = root / ".github" / "workflows" / src.name
        new = src.read_text()
        if dst.exists():
            old = dst.read_text()
            mk = re.compile(r"(^[ \t]*#[ \t]*CORE-PULL-KEEP[^\n]*\n)((?:[ \t]*- cron:[^\n]*\n)+)", re.M)
            mo, mn = mk.search(old), mk.search(new)
            if mo and mn: new = new[:mn.start(2)] + mo.group(2) + new[mn.end(2):]
            if old == new: continue
        dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(new); out.append(".github/workflows/" + src.name)
    return out

def run_pwa(root):
    if not (root / "tools/test_pwa.py").exists(): return []
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8799"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time; time.sleep(1)
        p = subprocess.run([sys.executable, "tools/test_pwa.py", "http://127.0.0.1:8799/"], cwd=root, capture_output=True, text=True, timeout=300)
        return [l.strip() for l in (p.stdout + p.stderr).splitlines() if l.strip().startswith("FAIL:")] + ([] if p.returncode == 0 or "FAIL:" in p.stdout else [f"exit {p.returncode}"])
    except Exception as e: return [f"error {e}"]
    finally: srv.terminate()

def open_pr(site, clone, r, body):
    repo = M["sites"][site]["repo"]; br = "core-sync/" + hashlib.sha1("".join(r["files_changed"]).encode()).hexdigest()[:8]
    sh(f"git checkout -B {br}", clone, True)
    for f in M["files"]: shutil.copy2(CORE / f["src"], clone / f["dst"])
    sh("git add -A tools && git commit -m 'core-sync: news-core 반영'", clone, True); sh(f"git push -f origin {br}", clone, True)
    b = (body or "") + "\n\n```json\n" + json.dumps(r, ensure_ascii=False, indent=1) + "\n```"
    p = subprocess.run(["gh", "pr", "create", "-R", repo, "-H", br, "-t", f"core-sync ({site})", "-b", b], cwd=clone, capture_output=True, text=True)
    if r["protected"]: return f"PR만 생성, 자동 합치기 중지(맥스 확인 필요: {r['protected']}) {p.stdout.strip()}"
    sh(f"gh pr merge -R {repo} {br} --squash --auto", clone); return f"auto-merge 설정 {p.stdout.strip()}"

if __name__ == "__main__": main()
