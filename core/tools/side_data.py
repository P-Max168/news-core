#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""곁 데이터 갱신 공통 실행기(news-core, 2026-10-30) — 헤더 시세 칩·'오늘의 한국 주요 뉴스'·'中国要闻' 처럼 판과 무관하게 2시간마다 갱신하는 파일.
예전엔 채널마다 korea.yml(KR)·china.yml(ZH) 100줄이 거의 같은 내용으로 따로 있었고 VN 은 판을 만들 때만 갱신했다 → 워크플로 템플릿 side-data.yml 하나 +
이 스크립트 + site/<lang>.json "side" 키로 통일.

site/<lang>.json "side":
  cmds : 차례로 실행할 명령(하나가 실패해도 나머지는 계속, 끝에 빨간색). "{force}" 는 --force 일 때 "--force"
  files: 커밋할 파일(바뀐 것만). 판 저장(deploy.sh)은 이 파일을 커밋하지 않고 원격 것을 받는다(충돌 방지)
  label: 커밋 메시지 머리(예 "korea: 한국 주요 뉴스·시세"). 시세 파일만 바뀌면 "ticker: 시세"
  pip  : 먼저 설치할 파이썬 패키지(예 googlenewsdecoder)
판 저장 시간대(watch_slots 의 시작 시각부터 +61분)에 걸리면 그 끝까지 기다렸다가 실행 — 판 push 와 겹치지 않게(예전 korea.yml 과 같음).
시각: 템플릿 cron 은 UTC "9 */2" = 07:09·09:09… BKK — 환율 API(open.er-api) 가 07:02 BKK 에 갱신된 뒤 첫 실행이 오늘 환율을 받게(설계 10-30 (c)).

  python3 tools/side_data.py [--force] [--no-wait] [--dry]
종료: 0 = 정상(커밋 없음 포함), 1 = 명령 중 하나 이상 실패(성공한 쪽은 이미 커밋됨), 2 = push 실패
"""
import argparse, json, os, pathlib, subprocess, sys, time
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import siteconf  # noqa: E402

BKK = timezone(timedelta(hours=7))
C = siteconf.load()
S = C.get("side") or {}
WAIT_MIN = int(S.get("wait_minutes", 61))   # 판 시작(하한) 뒤 이만큼은 push 안 함


def log(*a):
    print("[side_data]", *a, flush=True)


def sh(cmd, check=False, capture=False):
    log("$", cmd)
    r = subprocess.run(cmd, cwd=ROOT, shell=True, capture_output=capture, text=True)
    if check and r.returncode:
        raise SystemExit("명령 실패(%d): %s" % (r.returncode, cmd))
    return r


def wait_seconds(now):
    """지금이 어느 판의 저장 시간대(시작~+WAIT_MIN)면 그 끝까지 남은 초, 아니면 0."""
    for slot, h, m in C.get("watch_slots") or []:
        start = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        end = start + timedelta(minutes=WAIT_MIN)
        if start <= now < end:
            return int((end - now).total_seconds()) + 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true"); ap.add_argument("--no-wait", action="store_true"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    cmds, files = S.get("cmds") or [], S.get("files") or []
    if not cmds or not files:
        log("site/%s.json 에 side.cmds·side.files 없음 — 할 일 없음" % C["lang"]); return 0
    if not a.no_wait:
        w = wait_seconds(datetime.now(BKK))
        if w:
            log("판 저장 시간대 %s BKK → %ds 대기" % (datetime.now(BKK).strftime("%H:%M"), w)); time.sleep(w)
    log("시작: %s BKK · 사이트 %s" % (datetime.now(BKK).strftime("%F %H:%M"), C["lang"]))
    failed = []
    for c in cmds:
        c = c.replace("{force}", "--force" if a.force else "")
        if sh(c).returncode:
            failed.append(c)
    if a.dry:
        sh("git status --short -- " + " ".join(files)); log("DRY — 커밋·push 안 함"); return 1 if failed else 0
    sh("git add -- " + " ".join(f for f in files if (ROOT / f).exists()))
    if sh("git diff --cached --quiet").returncode == 0:
        log("변경 없음 — 커밋 안 함"); return 1 if failed else 0
    main_files = [f for f in files if "ticker" not in f]
    only_ticker = sh("git diff --cached --quiet -- " + " ".join(main_files)).returncode == 0 if main_files else True
    label = "ticker: 시세" if only_ticker else (S.get("label") or "side: 곁 데이터")
    sh('git commit -q -m "%s %s BKK"' % (label, datetime.now(BKK).strftime("%m-%d %H:%M")), check=True)
    for i in range(1, 6):   # push 는 pull --rebase 뒤(force 금지). 곁 데이터는 원격 것이 이기면 그대로 둬도 됨(-X theirs)
        if sh("git pull --rebase -X theirs -q origin main && git push -q origin HEAD:main").returncode == 0:
            log("push 완료", sh("git rev-parse --short HEAD", capture=True).stdout.strip())
            return 1 if failed else 0
        sh("git rebase --abort 2>/dev/null; true"); time.sleep(i * 15)
    log("push 실패"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
