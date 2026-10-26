#!/usr/bin/env bash
# 코드 수집 결과 받기(2026-10-23) — GitHub 자동 수집(.github/workflows/collect.yml)이 candidates 브랜치에 둔 후보를 drafts/ 로 가져온다.
#   bash tools/fetch_candidates.sh [판 id]
# 그 판 것이고 3시간 안에 모은 것이면 사용(exit 0) → 판 담당은 collect.py·gnews_scan.py 를 다시 돌리지 않아도 됨(토큰·시간 절약).
# 없거나 오래됐으면 exit 3 → 예전처럼 python3 tools/collect.py && python3 tools/gnews_scan.py 를 직접 실행.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ED="${1:-}"
git fetch -q origin +candidates:refs/remotes/origin/candidates 2>/dev/null || { echo "candidates 브랜치 없음 → 직접 수집"; exit 3; }
meta="$(git show origin/candidates:meta.json 2>/dev/null)" || { echo "meta.json 없음 → 직접 수집"; exit 3; }
ok=$(ED="$ED" python3 -c '
import json,os,sys,datetime
m=json.loads(sys.stdin.read()); ed=os.environ.get("ED")
age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(m["collected_at"])).total_seconds()/3600
print("ok" if age<=3 and (not ed or m.get("edition")==ed) else "old", m.get("edition"), round(age,1), m.get("items"), m.get("sources_ok"))
' <<<"$meta")
set -- $ok
if [ "$1" != "ok" ]; then echo "자동 수집 결과가 이 판 것이 아니거나 오래됨(판 $2, ${3}시간 전) → 직접 수집"; exit 3; fi
mkdir -p drafts/candidates drafts/gnews
for f in candidates/latest.json candidates/latest.md gnews/latest.json gnews/latest.md; do
  git show "origin/candidates:$f" > "drafts/$f" 2>/dev/null || rm -f "drafts/$f"
done
echo "자동 수집 결과 사용: 판 $2 · ${3}시간 전 · 후보 $4건 · 소스 $5 성공 → drafts/candidates/latest.md"
