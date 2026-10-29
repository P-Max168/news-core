#!/usr/bin/env bash
# 백업 태그: 지금 origin/main 에 backup-YYYYMMDD-HHMM-<이름> 태그를 만들고 push(되돌리기용). 출력 = 태그 이름
#   사용: bash tools/dev/tag.sh <짧은 이름>   예) tag.sh error-report → backup-20261005-0204-error-report
#   (2026-10-05) 이름 자리에 이미 완성된 태그(backup-YYYYMMDD-HHMM-…)를 넣으면 'backup-날짜-backup-날짜-…' 중복 이름이 생겼음
#   → 이름은 영문 소문자·숫자·하이픈만, 'backup-' 로 시작하거나 날짜(8자리-4자리)가 들어 있으면 거부(태그 안 만듦)
set -euo pipefail
cd "$(dirname "$0")/../.."
N="${1:-}"
if [ -z "$N" ]; then echo "사용: bash tools/dev/tag.sh <짧은 이름>  (예: error-report)" >&2; exit 2; fi
if [[ "$N" == backup-* ]] || [[ "$N" =~ [0-9]{8}-[0-9]{4} ]] || ! [[ "$N" =~ ^[a-z0-9][a-z0-9-]{1,40}$ ]]; then
  echo "태그 이름 거부: '$N' — 짧은 이름만(영문 소문자·숫자·하이픈, 'backup-'·날짜 빼고). 예: error-report" >&2; exit 2
fi
git fetch -q origin main
T="backup-$(TZ=Asia/Bangkok date +%Y%m%d-%H%M)-$N"
if git rev-parse -q --verify "refs/tags/$T" >/dev/null || git ls-remote --exit-code --tags origin "refs/tags/$T" >/dev/null 2>&1; then
  echo "이미 있는 태그: $T (1분 뒤 다시 또는 다른 이름)" >&2; exit 3
fi
git tag -a "$T" -m "백업: $N 변경 전 라이브 상태" origin/main
git push -q origin "$T"
echo "$T"
