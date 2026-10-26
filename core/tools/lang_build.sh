#!/usr/bin/env bash
# 언어판(zh 등) 판 빌드 절차 — 기계적인 단계만 묶음(2026-10-18 Grok, 민구님 10-18 08:00 승인 'Grok 이 공유 코드 직접').
# 원칙: 시스템 공유·편집 기준 분리. 이 스크립트는 공유 코드(한국판 저장소 → sync_core 로 언어판에 복사).
#   기사 고르기·번역·브리핑·질문 초안 같은 '편집'은 루틴 에이전트가 언어판 저장소의 ROUTINE_<slot>.md 를 보고 한다.
# 한국판(site/LANG=ko)에서는 돌지 않음(한국판 07:08·18:08 은 README '정기 실행' 절차 그대로).
#
# 사용 — 언어판 정본(/workspace/thai-news-<lang>-portal) 안에서:
#   bash tools/lang_build.sh prep [slot]     # ① 점검(preflight) → 수집(한국판 sources.json + sources.<lang>.json 보강) → 환율 → 편집 파일 준비. 끝에 ID=… 출력
#   bash tools/lang_build.sh build <id>      # ② build_data 검증(한글·태국 문자·위안 환산 검사 포함) → 언어 적용 → 로컬 화면 점검(screenshot.py)
#   bash tools/lang_build.sh publish <id>    # ③ 금지 구간(07:00–08:10·18:00–18:40) 기다림·마감(17:50) 확인 → deploy → share_kit → deploy → 라이브/Pages 확인
#   bash tools/lang_build.sh draft <id>      # ④ 질문·운영자 첫 댓글 초안(drafts/discussion/<id>.json, approved=false — 민구님 승인 전 비공개)
#   bash tools/lang_build.sh end ok|fail "메모"
# 환경 변수: HOURS(수집 창, 기본 26 — 시험 기간 하루 1판), TNK_TEST=1(정본 아닌 폴더 허용·push 안 함 = publish 막힘)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
L="$(cat site/LANG 2>/dev/null | tr -d '[:space:]')"; L="${L:-ko}"
[ "$L" != "ko" ] || { echo "lang_build: 한국판에서는 안 씀(README 정기 실행 절차)" >&2; exit 2; }
CANON="/workspace/thai-news-$L-portal"
if [ "${TNK_TEST:-}" != "1" ] && [ "$(pwd -P)" != "$(readlink -f "$CANON" 2>/dev/null)" ]; then
  echo "lang_build: 정본($CANON) 안에서만 실행(지금 $(pwd)). 시험은 TNK_TEST=1" >&2; exit 2
fi
KO_CANON=/workspace/thai-news-portal
conf() { python3 tools/siteconf.py | python3 -c "import json,sys;d=json.load(sys.stdin);print(eval(sys.argv[1]))" "$1"; }
SITE_URL="$(conf 'd["site_url"]')"
REPO="$(python3 -c "import json;print(json.load(open('site/$L.json')).get('repo',''))" 2>/dev/null)"
hm() { local x; x=$(TZ=Asia/Bangkok date +%H%M); echo $((10#$x)); }
CMD="${1:-}"; shift || true

case "$CMD" in
prep)
  SLOT="${1:-$(python3 -c "import json;d=json.load(open('site/$L.json'));print(d['schedule']['test'][0]['slot'])")}"
  ID="$(TZ=Asia/Bangkok date +%F)-$SLOT"
  if [ "${TNK_TEST:-}" = "1" ]; then echo "TNK_TEST=1 — preflight 건너뜀(시험)"
  else bash tools/preflight.sh "$L-$SLOT-build" || { echo "PREFLIGHT FAIL — 판 만들지 말고 알림"; exit 1; }; fi
  # 수집: 본문 핵심 = 한국판 정본의 태국 매체 목록(공유 수집) + 언어판 보강 매체(sources.<lang>.json thai_news_<lang>.sources)
  SRC=/tmp/tnk-$L-sources.json
  python3 - "$KO_CANON/tools/sources.json" "tools/sources.$L.json" "$L" "$SRC" <<'PY' || exit 1
import json, sys
ko, extra, lang, out = sys.argv[1:5]
cfg = json.load(open(ko, encoding="utf-8"))
ex = json.load(open(extra, encoding="utf-8")).get("thai_news_%s" % lang, {}).get("sources", [])
add = [dict(s, language=s.get("language", lang), topics=s.get("topics", []), group="lang-%s" % lang) for s in ex if s.get("type") in ("rss", "gnews", "sitemap")]
cfg["sources"] = cfg["sources"] + add
json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("수집 소스: 한국판 공유 %d + %s 보강 %d" % (len(cfg["sources"]) - len(add), lang, len(add)))
PY
  python3 tools/collect.py --sources "$SRC" --hours "${HOURS:-26}" | tail -3 || echo "경고: collect 일부 실패(후보 파일 확인)"
  # 환율(판 하나 = 환율 하나): 언어판 currency.pair
  PAIR="$(conf 'd["currency"]["pair"]')"; mkdir -p drafts
  python3 - "$PAIR" "drafts/fx-$ID.json" <<'PY' || echo "경고: 환율 못 받음 — 편집 파일 fx 를 손으로(출처·시각 적기)"
import json, sys, urllib.request, datetime
pair, out = sys.argv[1:3]; base, quote = pair.split("_")
d = json.load(urllib.request.urlopen("https://open.er-api.com/v6/latest/%s" % base, timeout=20))
rate = d["rates"][quote]; t = datetime.datetime.fromtimestamp(d["time_last_update_unix"], datetime.timezone(datetime.timedelta(hours=7)))
fx = {pair: round(rate, 4), "source": "open.er-api.com", "note": "%s %s BKK" % (pair, t.strftime("%Y-%m-%d %H:%M"))}
json.dump(fx, open(out, "w"), ensure_ascii=False); print("FX", json.dumps(fx, ensure_ascii=False))
PY
  mkdir -p tools/editions
  if [ ! -f "tools/editions/$ID.py" ]; then cp tools/editions/_template.py "tools/editions/$ID.py" && echo "편집 파일 만듦: tools/editions/$ID.py(※ 부분을 실제 내용으로)"; else echo "편집 파일 있음: tools/editions/$ID.py"; fi
  echo "후보: drafts/candidates/latest.md · 편집 기준: tools/TRANSLATION_RULES.$L.md · site/topics.$L.json"
  echo "ID=$ID"
  ;;
build)
  ID="${1:?id}"
  python3 tools/build_data.py "tools/editions/$ID.py" || { echo "BUILD FAIL(검증) — 위 이유를 고친 뒤 다시"; exit 1; }
  python3 tools/site_build.py
  PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
  python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 & SRV=$!
  sleep 1; OUT=/tmp/tnk-$L-shots-$ID
  python3 tools/dev/lang_check.py "http://127.0.0.1:$PORT/" "$ID" "$OUT"; RC=$?
  kill $SRV 2>/dev/null
  [ $RC -eq 0 ] && echo "BUILD OK $ID — 사진 $OUT/*.png 직접 볼 것" || { echo "BUILD CHECK FAIL $ID — 위 FAIL 줄 고친 뒤 다시(사진 $OUT)"; exit 1; }
  ;;
publish)
  ID="${1:?id}"
  [ "${TNK_TEST:-}" = "1" ] && { echo "TNK_TEST=1 — publish(배포) 안 함"; exit 0; }
  while :; do
    t=$(hm)
    if [ "$t" -ge 1750 ] && [ "${ALLOW_LATE:-}" != "1" ]; then   # 시험 기간 마감 17:50(site/<lang>.json schedule.test hard_stop)
      echo "마감(17:50) 지남 — 배포 멈춤(PAUSED). 다음 날 또는 민구님 확인 뒤 ALLOW_LATE=1"; exit 4; fi
    if { [ "$t" -ge 700 ] && [ "$t" -le 810 ]; } || { [ "$t" -ge 1800 ] && [ "$t" -le 1840 ]; }; then
      echo "$(TZ=Asia/Bangkok date +%H:%M) push 금지 구간 — 1분 뒤 다시"; sleep 60; continue; fi
    break
  done
  # 주소(DNS)가 아직 없으면 deploy.sh 의 라이브 대기(기본 900초)를 짧게 — push 는 되고 라이브 확인만 못 함(exit 2 = 그 경우로 봄)
  HOST="$(echo "$SITE_URL" | sed -E 's#^https?://##; s#/.*##')"; NODNS=""
  # (상자 DNS 는 없는 이름에도 가짜 IP(198.18.x)를 줄 수 있어 getent 대신 실제 접속으로 판단)
  curl -fsS -m 20 -o /dev/null "$SITE_URL" 2>/dev/null || { NODNS=1; export DEPLOY_TIMEOUT=60; echo "주소 $HOST DNS 없음 — 배포는 하고 라이브 확인은 Pages 빌드 상태로"; }
  dep() { bash tools/deploy.sh; local c=$?; [ $c -eq 0 ] && return 0; [ -n "$NODNS" ] && [ $c -eq 2 ] && { echo "(DNS 없음: push 완료·라이브 확인 생략)"; return 0; }; return $c; }
  dep || { echo "DEPLOY FAIL"; exit 1; }
  python3 tools/share_kit.py "$ID" || echo "경고: share_kit 실패(카드·e/·og/ 없음)"
  dep || { echo "DEPLOY(2) FAIL"; exit 1; }
  # 라이브 확인: 주소(DNS)가 살아 있으면 data/index.js latest, 아니면 GitHub Pages 빌드 상태로 대신
  if curl -fsS -m 20 "${SITE_URL}data/index.js?_=$RANDOM" -o /tmp/tnk-$L-live-index.js 2>/dev/null; then
    grep -q "\"latest\": *\"$ID\"" /tmp/tnk-$L-live-index.js && echo "LIVE OK $SITE_URL $ID" || echo "LIVE 아직 옛 판(몇 분 뒤 다시 확인)"
  else
    echo "라이브 주소($SITE_URL) 접속 안 됨(DNS 없음?) — GitHub Pages 빌드 상태로 대신:"
    [ -n "$REPO" ] && gh api "repos/$REPO/pages/builds/latest" --jq '"PAGES " + .status + " " + .commit[0:7] + " " + .updated_at' 2>/dev/null || echo "Pages 상태 못 읽음"
  fi
  ;;
draft)
  ID="${1:?id}"
  python3 tools/discussion.py draft "$ID" && echo "초안: drafts/discussion/$ID.json — tools/DISCUSSION_PERSONA.$L.md 말투로 채우고 approved=false 그대로(승인 전 비공개)"
  ;;
end)
  bash tools/preflight.sh end "$L-build" "${1:-ok}" "${2:-}"
  ;;
*) sed -n 2,16p "$0"; exit 2 ;;
esac
