#!/usr/bin/env bash
# 판 빌드 전 점검(2026-10-05) — 정기 실행(2026-10-23부터 06:40·17:40, 전 07:08·18:08)과 대체 루틴의 **맨 처음**에 실행.
#   bash tools/preflight.sh <작업이름>              예: bash tools/preflight.sh am-build
#   bash tools/preflight.sh end <작업이름> ok|fail [메모]   (작업 끝에 한 줄 — 실행 기록 닫기)
# 왜: 10-04 07:08 아침판이 안 만들어졌을 때 상자(box)에 '실행이 시작은 됐는지' 증거가 하나도 없었음(DEV_LOG 10-05 원인 조사).
#     → 앞으로는 시작·끝을 /workspace/logs/automation.log 에 남기고, 빌드를 막을 수 있는 상자 쪽 문제를 먼저 스스로 고친다.
# 하는 일(정본 체크아웃 = 이 파일이 있는 저장소):
#   1) 실행 기록 START 한 줄          2) 10분 넘은 git 잠금 파일 지움(git 프로세스가 살아 있으면 안 지움)
#   3) 정본 검사(tools/canon_guard.sh: rebase/merge 중·main 아님·앞섬·바뀐/추적 안 된 파일 → 고치지 않고 FAIL + /workspace/logs/canon-alert.txt)  4) main 브랜치로
#   6) fetch + pull --rebase(3번 재시도)   7) 디스크 ≥2GB·메모리 여유 ≥500MB·인터넷(github·news.google) 확인
#   8) python3·playwright·node 확인        9) 오늘 판 상태(있는지) 한 줄
#  10) 라이브 최신 판 30분 넘게 늦음 → /workspace/logs/edition-stale.txt 한 줄(tools/edition_stale.py, 빌드는 안 막음)
# 끝: 문제 없으면 'PREFLIGHT OK'(exit 0), 고칠 수 없는 문제면 'PREFLIGHT FAIL: 이유'(exit 1) — 이때 판 빌드를 하지 말고 Max 에게 알림.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
LOGDIR=/workspace/logs; [ "${TNK_TEST:-}" = "1" ] && LOGDIR="${TNK_LOGDIR:-/workspace/logs}"   # 시험 덮어쓰기는 TNK_TEST=1 일 때만(2026-10-05)
LOG="$LOGDIR/automation.log"; mkdir -p "$LOGDIR" 2>/dev/null || true
now() { TZ=Asia/Bangkok date '+%m-%d %H:%M:%S'; }
jlog() { echo "$(now) $*" >> "$LOG" 2>/dev/null || true; }

if [ "${1:-}" = "end" ]; then
  jlog "END   ${2:-?} ${3:-?} ${4:-}"; echo "기록: END ${2:-?} ${3:-?}"; exit 0
fi
JOB="${1:-manual}"
jlog "START $JOB pid=$$ head=$(git rev-parse --short HEAD 2>/dev/null)"
FIX=(); FAIL=()
say() { echo "· $*"; }

# 2) 오래된 잠금
if ! pgrep -x git >/dev/null 2>&1; then
  for f in .git/index.lock .git/HEAD.lock .git/refs/heads/main.lock .git/shallow.lock .git/packed-refs.lock; do
    if [ -e "$f" ] && [ -n "$(find "$f" -mmin +10 2>/dev/null)" ]; then rm -f "$f" && FIX+=("오래된 잠금 $f 지움"); fi
  done
fi
# 3) 정본 상태 검사(2026-10-05 바꿈): rebase/merge 중 · main 아님 · origin 보다 앞섬 · 바뀐/추적 안 된 파일 → 고치지 않고 바로 멈춤 + 알림
#    (예전엔 멈춘 rebase 를 말없이 abort·변경을 stash 하고 넘어갔음 → 10-05 08:30 정본 DEV_LOG 충돌을 아무도 못 봄. tools/canon_guard.sh)
#    헤더 시세·한국 뉴스 파일 4개만 먼저 원격 것으로 되돌림(Actions 가 정답, 예전과 같음)
for f in data/korea.json data/korea.js data/ticker.json data/ticker.js; do git checkout -q -- "$f" 2>/dev/null || true; done
if ! CANON_DIR="$(pwd)" bash tools/canon_guard.sh "$JOB"; then
  echo "PREFLIGHT FAIL: 정본 상태(위 CANON GUARD 줄) — 판 빌드 하지 말고 Max 에게 알림"; jlog "FAIL  $JOB 정본 상태(canon-alert.txt)"; exit 1
fi
# 4) main
b=$(git symbolic-ref --short -q HEAD || echo DETACHED)
if [ "$b" != "main" ]; then git checkout -q main 2>/dev/null && FIX+=("브랜치 $b → main") || FAIL+=("main 으로 못 바꿈(지금 $b)"); fi
# 5) (2026-10-05) 올리지 않은 변경 stash 는 없앰 — 3) 의 정본 검사가 멈추고 알림
# 6) 원격과 맞추기
ok=""
for i in 1 2 3; do
  if git fetch -q origin main 2>/dev/null && git pull -q --rebase --autostash origin main 2>/dev/null; then ok=1; break; fi
  git rebase --abort >/dev/null 2>&1 || true; sleep $((i * 10))
done
[ -n "$ok" ] || FAIL+=("git pull --rebase 3번 실패(인터넷·충돌)")
behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
[ "$behind" = "0" ] || FAIL+=("원격보다 ${behind}개 뒤처짐")
# Check after pulling so a resumed Grok routine sees the temporary handoff.
if ! python3 tools/publisher_guard.py; then
  jlog "HOLD  $JOB publisher handoff"; exit 4
fi
# 판 담당 표시(2026-10-23): am-build·pm-build·md-build 면 원격에 claim/<판 id>/<누구> 를 남김 → Claude 비상 발행 확인(07:00·18:00)이 봄.
#   다른 담당(특히 Claude 비상 발행)이 이미 맡았으면 여기서 멈춤(exit 4). 표시 실패는 판을 막지 않음(CLAIM WARN).
if [[ "$JOB" =~ ^([a-z][a-z]-)?(am|pm|md)-build$ ]]; then   # 언어판 lang_build 는 zh-md-build 처럼 언어가 붙음(10-26 고침)
  ED="$(TZ=Asia/Bangkok date +%F)-${BASH_REMATCH[2]}"
  if ! python3 tools/edition_claim.py claim "${TNK_PUBLISHER:-grok}" "$ED"; then
    jlog "HOLD  $JOB claim $ED"; exit 4
  fi
fi
# 7) 자원·인터넷
free_gb=$(df -Pk . | awk 'NR==2{printf "%d", $4/1048576}')
[ "${free_gb:-0}" -ge 2 ] || FAIL+=("디스크 여유 ${free_gb}GB(<2GB)")
mem_mb=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 9999)
[ "${mem_mb:-0}" -ge 500 ] || FAIL+=("메모리 여유 ${mem_mb}MB(<500MB)")
for u in https://github.com https://news.google.com/rss; do
  c=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$u" || echo 000)
  case "$c" in 2*|3*) ;; *) FAIL+=("인터넷 $u → $c");; esac
done
# 8) 도구
command -v python3 >/dev/null || FAIL+=("python3 없음")
python3 -c "import playwright" 2>/dev/null || FAIL+=("python playwright 없음")
command -v node >/dev/null || FIX+=("node 없음(주제 계산은 간단 매핑으로 대체됨)")
# 9) 오늘 판 상태
d=$(TZ=Asia/Bangkok date +%F); h=$(TZ=Asia/Bangkok date +%H)
st="오늘 아침판 ${d}-am: $([ -f data/${d}-am.json ] && echo 있음 || echo 없음)"
# 10) 라이브 최신 판이 게시 목표(07:00·18:00, 2026-10-23 변경)보다 30분 넘게 늦었는지 — 늦으면 /workspace/logs/edition-stale.txt 에 한 줄(빌드를 막지는 않음, 2026-10-05)
stale="$(timeout 60 python3 tools/edition_stale.py 2>&1 | tail -n1)"; say "라이브 판: $stale"; st="$st · 라이브: ${stale:0:80}"
[ "$h" -ge 18 ] && st="$st · 저녁판 ${d}-pm: $([ -f data/${d}-pm.json ] && echo 있음 || echo 없음)"

for x in "${FIX[@]}"; do say "고침: $x"; done
say "상태: 브랜치 $(git symbolic-ref --short -q HEAD) · HEAD $(git rev-parse --short HEAD) · 디스크 ${free_gb}GB · 메모리 ${mem_mb}MB · $st"
if [ ${#FAIL[@]} -eq 0 ]; then
  echo "PREFLIGHT OK"; jlog "OK    $JOB $(IFS=';'; echo "${FIX[*]}") | $st"; exit 0
fi
msg=$(IFS=';'; echo "${FAIL[*]}")
echo "PREFLIGHT FAIL: $msg"; jlog "FAIL  $JOB $msg"; exit 1
