#!/usr/bin/env bash
# 새 판을 만든 뒤 GitHub Pages 에 배포하고 라이브 페이지를 검증한다.
#   bash tools/deploy.sh
# - raw/, archive/, screenshots/, 캐시·비밀 파일은 .gitignore 로 제외(절대 올리지 않음)
# - 커밋 메시지: "edition <최신 판 id>"
# - force-push 하지 않는다. 원격이 앞서 있으면 rebase 후 일반 push.
set -euo pipefail
cd "$(dirname "$0")/.."
# Refuse publication by the other operator during an explicit handoff.
python3 tools/publisher_guard.py
# 실행 기록(2026-10-05): 끝나면 /workspace/logs/automation.log 에 deploy ok/fail 한 줄(tools/preflight.sh end) — 실패 원인 추적용, 동작에는 영향 없음
_deploy_end() { local c=$?; bash tools/preflight.sh end deploy "$([ $c -eq 0 ] && echo ok || echo fail)" "exit=$c $(git rev-parse --short HEAD 2>/dev/null)" >/dev/null 2>&1 || true; }
trap _deploy_end EXIT

LIVE_URL="${LIVE_URL:-https://tnews.pmaxone.com/}"
# 언어판(R-zh-4, 2026-10-18): site/LANG 이 ko 가 아니면 라이브 주소 = site/<lang>.json site_url, 판 빌드 전에 data/site.js·index.html 언어 적용(tools/site_build.py)
SITE_LANG="$(cat site/LANG 2>/dev/null | tr -d '[:space:]')"; SITE_LANG="${SITE_LANG:-ko}"
if [ "$SITE_LANG" != "ko" ]; then
  LIVE_URL="$(python3 tools/siteconf.py | python3 -c 'import json,sys;print(json.load(sys.stdin)["site_url"])')"
  python3 tools/site_build.py
fi
TIMEOUT="${DEPLOY_TIMEOUT:-900}"   # 라이브 반영 대기(초)

LATEST=$(python3 -c 'import json;print(json.load(open("data/index.json",encoding="utf-8"))["latest"])')
[ -n "$LATEST" ] || { echo "data/index.json 에 latest 없음" >&2; exit 1; }
[ -f "data/$LATEST.json" ] && [ -f "data/$LATEST.js" ] || { echo "data/$LATEST.json|js 없음" >&2; exit 1; }
echo "최신 판: $LATEST"
# 판 담당 확인(2026-10-23): 이 판을 다른 담당(예: Claude 비상 인수)이 가져갔으면 배포하지 않음
python3 tools/edition_claim.py check "${TNK_PUBLISHER:-grok}" "$LATEST" || { echo "다른 담당이 $LATEST 를 맡아 배포 중단" >&2; exit 4; }

# 안전장치: 제외 대상이 실수로 추적되고 있으면 중단
if git ls-files | grep -qE '^(raw|archive|screenshots)/'; then
  echo "오류: raw/ archive/ screenshots/ 가 git 에 추적되고 있음. 배포 중단." >&2; exit 1
fi

git checkout -q main
# 🇰🇷 data/korea.json|js · 💱 data/ticker.json|js(헤더 시세 칩)는 GitHub Actions(.github/workflows/korea.yml)가 2시간마다 갱신·커밋하는 파일
# → 이 스크립트는 절대 올리지 않는다. 로컬 사본(오래됐을 수 있음)은 버리고 원격 것을 받는다(pull 때 충돌·덮어쓰기 방지).
KOREA_FILES="data/korea.json data/korea.js data/ticker.json data/ticker.js"
# (2026-10-30 공통화) 곁 데이터 파일 목록은 site/<lang>.json side.files(side-data.yml 이 갱신). 없으면 옛 기본값
SIDE_FILES="$(python3 -c 'import sys;sys.path.insert(0,"tools");import siteconf;print(" ".join((siteconf.load().get("side") or {}).get("files") or []))' 2>/dev/null || true)"
[ -z "$SIDE_FILES" ] || KOREA_FILES="$SIDE_FILES"
# 그 파일을 따로 갱신하는 워크플로(side-data.yml, 옛 korea.yml·china.yml)가 있는 채널만 제외. 판 실행 안(pre_cmd)에서만 갱신하는 채널은 같이 커밋
if [ -f .github/workflows/side-data.yml ] || [ -f .github/workflows/korea.yml ] || [ -f .github/workflows/china.yml ]; then
  for f in $KOREA_FILES; do
    if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then git checkout -q -- "$f"; else rm -f "$f"; fi
  done
else
  KOREA_FILES=""
fi
# 검색 노출(2026-10-18 R-seo-2): sitemap.xml 을 data/index.json·e/ 에 맞춰 다시 만듦(share_kit 도 만들지만 한 번 더 — 실패해도 배포는 계속)
python3 tools/seo.py sitemap || echo "경고: sitemap.xml 갱신 실패(배포는 계속)" >&2
# IndexNow 키 파일만 보장(제출은 push 뒤)
python3 -c "import sys; sys.path.insert(0,'tools'); import seo; print('indexnow', seo.indexnow_key())" || true
# 홈 뉴스판 링크를 갱신한 뒤 앱 셸 버전을 계산해야 캐시에도 새 링크가 반영됨.
python3 tools/stamp_assets.py
# 측정 한 줄(2026-10-23): ops/metrics.jsonl — 실패해도 배포 계속
python3 tools/metrics.py "$LATEST" || true
# YouTube Tower 입력(2026-10-28): md 판이면 ops/video/<date>.json 생성(실패해도 배포 계속). 2026-10-29 공통화: site/<lang>.json edition.video_feed 가 true 인 채널만
VIDEO_FEED="$(python3 -c 'import sys;sys.path.insert(0,"tools");import siteconf;print("1" if (siteconf.load().get("edition") or {}).get("video_feed") else "")' 2>/dev/null || true)"
if [ -n "$VIDEO_FEED" ] && [[ "$LATEST" == *-md ]]; then
  python3 tools/video_picks.py --date "${LATEST%-md}" || echo "경고: video_picks 실패(배포는 계속)" >&2
fi
# 사이트 파일만 스테이징 (.gitignore 가 제외 대상 차단) · ops/base = base_add 기본 목록 기록(2026-10-30)
# og/(링크 미리보기 이미지)·e/(판별 미리보기 페이지)는 tools/share_kit.py 가 만듦 — 있는 경로만 추가
PATHS=""
for p in index.html robots.txt sitemap.xml feed.xml .nojekyll .gitignore README.md manifest.json sw.js firestore.rules assets data tools og e .github ops/metrics.jsonl ops/last-run.json ops/published.json ops/source-verify.json ops/picks ops/base ops/gemini-usage.jsonl ops/edition-fail.json; do   # edition-fail.json: 성공하면 지운 것도 커밋돼야 옛 실패가 안 남음(2026-10-29)
  [ -e "$p" ] && PATHS="$PATHS $p"
done
# IndexNow 공개 키 파일(ops/indexnow-key 내용 = 파일명)도 스테이징
INDEXNOW_KEY_FILE=""
if [ -f ops/indexnow-key ]; then
  INDEXNOW_KEY_FILE="$(tr -d '[:space:]' < ops/indexnow-key).txt"
  [ -f "$INDEXNOW_KEY_FILE" ] && PATHS="$PATHS $INDEXNOW_KEY_FILE ops/indexnow-key"
fi
# YouTube Tower ops/video (md 판에서 생성). 디렉터리가 있을 때만 스테이징
[ -d ops/video ] && PATHS="$PATHS ops/video"
git add -A -- $PATHS
# 성공한 판은 ops/edition-fail.json 을 지운다(gemini_edition). 지워진 파일은 위 루프(-e)에 안 잡히므로 삭제를 따로 스테이징(2026-10-29)
if [ ! -e ops/edition-fail.json ] && git ls-files --error-unmatch ops/edition-fail.json >/dev/null 2>&1; then git rm -q --cached ops/edition-fail.json; fi
[ -n "$KOREA_FILES" ] && { git reset -q -- $KOREA_FILES 2>/dev/null || true; }   # 혹시 스테이징됐어도 빼기
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 생략"
else
  git commit -q -m "edition $LATEST"
  echo "커밋: $(git log -1 --oneline)"
fi

# push (force 금지). 먼저 원격(Actions 의 korea.json 커밋 등)을 rebase 로 받은 뒤 일반 push, 거부되면 최대 4번 재시도.
# spend 원장(ops/gemini-spend.json)이 실행 중 main에 갱신되면 rebase 충돌이 난다.
# 원장은 main이 권위이므로, 그 파일만 충돌이면 rebase 중 ours(=onto/main)를 채택하고 계속한다.
_pull_rebase() {
  if git pull --rebase --autostash -q origin main; then
    return 0
  fi
  if git ls-files -u | grep -qE '(^|[[:space:]])ops/gemini-spend\.json$'; then
    echo "rebase 충돌: ops/gemini-spend.json → main(ours) 채택" >&2
    git checkout --ours -- ops/gemini-spend.json
    git add -- ops/gemini-spend.json
    if git diff --name-only --diff-filter=U | grep -q .; then
      echo "git pull --rebase 실패(다른 파일 충돌) — 수동 확인 필요" >&2
      git rebase --abort 2>/dev/null || true
      return 1
    fi
    if ! GIT_EDITOR=true git rebase --continue; then
      echo "git pull --rebase 실패(continue) — 수동 확인 필요" >&2
      git rebase --abort 2>/dev/null || true
      return 1
    fi
    return 0
  fi
  echo "git pull --rebase 실패(충돌?) — 수동 확인 필요" >&2
  git rebase --abort 2>/dev/null || true
  return 1
}
ok=""
for i in 1 2 3 4; do
  _pull_rebase || { exit 3; }
  if git push -q origin main; then ok=1; break; fi
  echo "push 거부($i) → 잠시 뒤 pull --rebase 후 재시도"; sleep $((i * 5))
done
[ -n "$ok" ] || { echo "push 실패" >&2; exit 3; }
echo "push 완료: $(git rev-parse --short HEAD)"
# IndexNow 제출(빙·네이버·얀덱스, 계정 불필요). 실패해도 배포 계속
python3 -c "import sys; sys.path.insert(0,'tools'); import seo; c,u=seo.indexnow_submit(); print('IndexNow',c,len(u))" || echo "경고: IndexNow 제출 실패" >&2

# (2026-10-29 공통화) TNK_LIVE_CHECK=none: 저장(push)까지만. Cloudflare 배포 채널은 tools/run_edition.py 가 이어서 배포·라이브 대조
if [ "${TNK_LIVE_CHECK:-curl}" = "none" ]; then echo "저장 완료(배포·검증은 호출자가): $(git rev-parse --short HEAD) (판 $LATEST)"; exit 0; fi
# 라이브 검증: index.js 에 최신 id 가 반영될 때까지 대기 후 헤드리스 브라우저로 렌더 확인
deadline=$(( $(date +%s) + TIMEOUT ))
# (2026-10-23) TNK_LIVE_CHECK=pages: 사이트에 직접 못 붙는 곳(Claude 클라우드 비상 발행)에서는 GitHub Pages 빌드 결과로 확인
if [ "${TNK_LIVE_CHECK:-curl}" = "pages" ]; then
  REPO="$(git config --get remote.origin.url | sed -E 's#.*github.com[/:]##; s#\.git$##')"; HEAD_SHA="$(git rev-parse HEAD)"
  while :; do
    # pages build and deployment 실행 중 이 커밋(또는 그 뒤 커밋)이 success 면 통과. 뒤 커밋이 덮으면 앞 실행은 cancelled 가 정상.
    st="$(gh api "repos/$REPO/actions/runs?event=dynamic&per_page=10" --jq '.workflow_runs[]|select(.name=="pages build and deployment")|.head_sha+" "+.status+" "+(.conclusion//"")' 2>/dev/null || true)"
    # (2026-10-26 Claude) push 직후엔 Pages 실행이 목록에 아직 없어 grep 결과가 빔 → set -e·pipefail 로 exit 1 되던 것(10-26 pm 판 Actions 40310376950). 빈 결과면 기다렸다 다시 봄
    mine="$(echo "$st" | grep "^$HEAD_SHA " | head -1 || true)"
    if echo "$mine" | grep -q " completed success"; then echo "Pages 빌드 완료: ${HEAD_SHA:0:7} (사이트 직접 확인은 생략)"; echo "배포 완료: $LIVE_URL (판 $LATEST)"; exit 0; fi
    if echo "$mine" | grep -q " completed cancelled" && git merge-base --is-ancestor "$HEAD_SHA" "$(echo "$st" | grep ' completed success' | head -1 | cut -c1-40)" 2>/dev/null; then
      echo "Pages: 뒤 커밋 빌드가 성공(이 커밋 포함)"; echo "배포 완료: $LIVE_URL (판 $LATEST)"; exit 0; fi
    echo "$mine" | grep -q " completed failure" && { echo "실패: Pages 빌드 실패 ($mine)" >&2; exit 2; }
    [ "$(date +%s)" -ge "$deadline" ] && { echo "실패: ${TIMEOUT}s 안에 Pages 빌드 확인 안 됨 ($st)" >&2; exit 2; }
    sleep 20
  done
fi
while :; do
  ts=$(date +%s)
  # 최신 판 id 뿐 아니라 내용(같은 판을 고쳐 다시 올린 경우)과 앱 코드까지 로컬과 같아야 통과
  if curl -fsS "${LIVE_URL}data/index.js?_=$ts" 2>/dev/null | grep -F "\"latest\": \"$LATEST\"" >/dev/null \
     && [ "$(curl -fsS "${LIVE_URL}data/$LATEST.js?_=$ts" 2>/dev/null | sha256sum | cut -d' ' -f1)" = "$(sha256sum "data/$LATEST.js" | cut -d' ' -f1)" ] \
     && [ "$(curl -fsS "${LIVE_URL}assets/app.js?_=$ts" 2>/dev/null | sha256sum | cut -d' ' -f1)" = "$(sha256sum assets/app.js | cut -d' ' -f1)" ] \
     && [ "$(curl -fsS "${LIVE_URL}sw.js?_=$ts" 2>/dev/null | sha256sum | cut -d' ' -f1)" = "$(sha256sum sw.js | cut -d' ' -f1)" ]; then
    echo "라이브 데이터·앱 코드에 $LATEST (현재 커밋 내용) 반영됨"; break
  fi
  [ "$ts" -ge "$deadline" ] && { echo "실패: ${TIMEOUT}s 안에 라이브에 $LATEST 가 반영되지 않음 ($LIVE_URL)" >&2; exit 2; }
  sleep 20
done

if python3 -c 'import playwright' 2>/dev/null; then
  if [ "$SITE_LANG" = "ko" ]; then python3 tools/verify_live.py "$LIVE_URL" "$LATEST" "screenshots/live-mobile-390.png"
  else python3 tools/dev/lang_check.py "$LIVE_URL" "$LATEST" "screenshots/live-$SITE_LANG"; fi   # 언어판(2026-10-18): verify_live 는 한국판 문구 기준
else
  echo "playwright 없음 — 브라우저 렌더 검증 생략(데이터 검증은 통과)"
fi
echo "배포 완료: $LIVE_URL (판 $LATEST)"
