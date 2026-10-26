#!/usr/bin/env bash
# 정본 체크아웃(/workspace/thai-news-portal) 상태 검사 — 2026-10-05.
#   bash tools/canon_guard.sh <부른 곳>        예) bash tools/canon_guard.sh ship · am-build · pm-build · korea-update · regress
# 왜: 10-05 07:49 일회성 점검이 정본에서 DEV_LOG 를 직접 커밋(03fcb13, push 안 함) → 08:30 ship.sh 가 push 는 했지만 정본 pull 이
#     DEV_LOG.md 충돌로 rebase 중간에 멈춤(ship exit 1). 예전 preflight.sh 는 이런 rebase 를 말없이 abort·stash 하고 넘어갔음.
#   → 정본은 '받기(pull)만' 하는 곳. 판 빌드(07:08·18:08, deploy.sh 가 같은 실행에서 바로 push)만 커밋함.
# 검사: ① rebase/merge/cherry-pick/revert 중 ② main 브랜치 아님 ③ origin/main 보다 앞섬(올리지 않은 커밋) ④ 바뀐 파일·추적 안 된 파일(.gitignore 제외)
# 하나라도 있으면: 'CANON GUARD FAIL: …' 출력, /workspace/logs/canon-alert.txt 에 한 줄 + automation.log 에 'ALERT canon …' 한 줄, exit 1.
#   아무것도 고치지 않음(abort·stash·reset 안 함) — 사람이 보고 정리. 정상이면 'CANON GUARD OK'(exit 0).
# 환경 변수(시험용, TNK_TEST=1 일 때만): CANON_DIR(기본 /workspace/thai-news-portal), TNK_LOGDIR(기본 /workspace/logs), CANON_NO_FETCH=1(fetch 생략)
# (2026-10-05 09:xx) 시험용 덮어쓰기(CANON_DIR·TNK_LOGDIR·CANON_NO_FETCH)는 TNK_TEST=1 이 같이 있을 때만 씀.
#   10-05 08:43 부숴 보기에서 export 한 CANON_DIR=/tmp/cg/canon 이 셸에 남아 08:51 배포의 정본 검사가 가짜 정본을 봤음 → 이제 TNK_TEST 없으면 무시(경고) + 진짜 경로.
#   예외: CANON_DIR 이 진짜 정본 경로 그대로면(preflight.sh 가 정본 안에서 넘김) 그대로 씀.
set -uo pipefail
WHO="${1:-manual}"
REAL_C=/workspace/thai-news-portal; REAL_LOG=/workspace/logs
# 언어판(R-zh-4, 2026-10-18): 부른 저장소의 site/LANG 이 ko 가 아니면 그 언어판 정본(/workspace/thai-news-<lang>-portal)을 검사. 없으면 한국판 그대로
_L="$(cat "$(dirname "$0")/../site/LANG" 2>/dev/null | tr -d '[:space:]')"; [ -n "$_L" ] && [ "$_L" != "ko" ] && REAL_C="/workspace/thai-news-$_L-portal"
C="$REAL_C"; LOGDIR="$REAL_LOG"; NOFETCH=0
if [ "${TNK_TEST:-}" = "1" ]; then
  C="${CANON_DIR:-$REAL_C}"; LOGDIR="${TNK_LOGDIR:-$REAL_LOG}"; NOFETCH="${CANON_NO_FETCH:-0}"
else
  if [ -n "${CANON_DIR:-}" ] && [ "$(realpath -m "$CANON_DIR")" != "$(realpath -m "$REAL_C")" ]; then echo "경고: CANON_DIR=$CANON_DIR 무시(TNK_TEST=1 없음) → 진짜 정본 $REAL_C 검사" >&2; fi
  if [ -n "${TNK_LOGDIR:-}" ] && [ "$(realpath -m "$TNK_LOGDIR")" != "$(realpath -m "$REAL_LOG")" ]; then echo "경고: TNK_LOGDIR=$TNK_LOGDIR 무시(TNK_TEST=1 없음) → $REAL_LOG" >&2; fi
  [ -n "${CANON_NO_FETCH:-}" ] && echo "경고: CANON_NO_FETCH 무시(TNK_TEST=1 없음)" >&2
fi
mkdir -p "$LOGDIR" 2>/dev/null || true
now() { TZ=Asia/Bangkok date '+%m-%d %H:%M:%S'; }
[ -d "$C/.git" ] || { echo "CANON GUARD SKIP: 정본 없음($C)"; exit 0; }
G=$(git -C "$C" rev-parse --git-dir 2>/dev/null); case "$G" in /*) ;; *) G="$C/$G";; esac
BAD=()
[ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ] && BAD+=("rebase 진행 중")
[ -f "$G/MERGE_HEAD" ] && BAD+=("merge 진행 중")
[ -f "$G/CHERRY_PICK_HEAD" ] && BAD+=("cherry-pick 진행 중")
[ -f "$G/REVERT_HEAD" ] && BAD+=("revert 진행 중")
b=$(git -C "$C" symbolic-ref --short -q HEAD || echo DETACHED)
[ "$b" = "main" ] || BAD+=("브랜치 $b(main 아님)")
[ "$NOFETCH" = "1" ] || timeout 60 git -C "$C" fetch -q origin main 2>/dev/null || true
ahead=$(git -C "$C" rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
[ "$ahead" = "0" ] || BAD+=("origin 보다 ${ahead}커밋 앞섬(정본에 직접 커밋함: $(git -C "$C" log --format='%h %s' origin/main..HEAD 2>/dev/null | head -3 | cut -c1-60 | tr '\n' ';'))")
dirty=$(git -C "$C" status --porcelain --untracked-files=all 2>/dev/null)
[ -z "$dirty" ] || BAD+=("바뀐/추적 안 된 파일 $(echo "$dirty" | wc -l)개: $(echo "$dirty" | head -5 | tr '\n' ';')")
if [ ${#BAD[@]} -eq 0 ]; then echo "CANON GUARD OK ($WHO · $C · HEAD $(git -C "$C" rev-parse --short HEAD) · ahead 0 · 깨끗)"; exit 0; fi
msg=$(IFS='|'; echo "${BAD[*]}")
echo "$(now) $WHO 정본 $C: $msg — 아무것도 안 고침, 사람이 정리 뒤 다시 실행" >> "$LOGDIR/canon-alert.txt"
echo "$(now) ALERT canon $WHO $msg" >> "$LOGDIR/automation.log"
echo "CANON GUARD FAIL: $msg  (기록: $LOGDIR/canon-alert.txt · automation.log) — 멈춤. 이 실행의 보고에 이 줄을 그대로 적을 것"
exit 1
