#!/usr/bin/env bash
# 공유 코드 동기화(R-zh-4, 2026-10-18) — 설명은 tools/dev/sync_core.py 맨 위.  bash tools/dev/sync_core.sh <한국판 커밋|HEAD> <언어판 폴더> [--dry]
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python3 tools/dev/sync_core.py "$@"
