# 뉴스 채널 공통 구조 — 운영 규칙 (전환 뒤, 그록·GPT·Claude 공통)

작성: Claude 2026-10-29. 맥스 승인 뒤 효력. 설계서: 드라이브 00_INBOX `news-core_변경설계서_20261029 (클로드).md`.

## 1. 어디를 고치나
| 바꾸고 싶은 것 | 어디서 | 누가 |
|---|---|---|
| 공통 기능(고르기·번역 연결·검증·저장·배포·감시 코드, 화면 껍데기, 워크플로 템플릿) | **news-core 만** (`core/tools`, `core/workflows`) → 버전 올림 → 각 채널이 당겨옴 | 맥스가 맡긴 AI |
| 채널 고유값(언어·출처·기사 수·시각·브랜드·도메인·배포 방식) | 그 채널 `site/<lang>.json` | 채널 담당 |
| 기사·발행 데이터(`data/`, `ops/picks/`, 공유 카드) | 그 채널 저장소 — 지금 방식 그대로 | 발행 루틴(그록 picks·Actions) |
| 번역 규칙·페르소나·수집처 목록 | 그 채널 `tools/TRANSLATION_RULES*.md`, `sources*.json`, VN `pipeline/` | 채널 담당 |

**금지**: 채널 저장소에서 공통 파일(`core.json` 목록, `.github/workflows/edition*.yml`·`core-pull.yml`)을 직접 고치는 것. 고치면 다음 당겨오기 때 덮이고, 세 채널이 다시 갈라진다. 급하면 news-core 에 고치고 그 채널만 먼저 당겨오면 된다(채널마다 버전이 달라도 됨).
**금지**: KR 코드를 ZH·VN 에 복사하는 것(`tools/dev/sync_core.py` 퇴역).

## 2. 공통 수정 → 반영 순서
1. news-core 브랜치에 수정 → `python3 sync.py --site <lang> --clone <채널 클론>` 으로 dry-run(HTML diff 0·검사 통과 확인)
2. news-core `main` 병합 → **버전 태그** `vYYYY.MM.DD[-n]` (태그는 맥스가 GitHub Releases 에서, 또는 그록이. Claude 클라우드 세션은 태그를 못 만듦)
3. 채널 저장소에서 `core-pull` 실행(Run workflow → version) 또는 `.core-version` 파일을 그 태그로 바꿔 push → 자동 PR
4. PR 확인(변경 파일이 의도한 것뿐인지) → 병합. **처음 2주는 사람이 병합**, 그 뒤 검사 통과 시 자동 병합 검토
5. 채널 순서: VN → ZH → KR (설계서 5장). 한 채널에서 판 하나 정상 발행 확인 뒤 다음 채널

## 3. 되돌리기
- 채널: `.core-version` 을 이전 태그로 → core-pull → PR 병합. 또는 PR revert.
- 긴급 전체 중지: 채널 저장소 변수 `CORE_SYNC=off`(당겨오기만 멈춤, 발행은 계속)
- 원장: 저장소 변수 `GEMINI_SPEND_BACKEND` 삭제 → 옛 git 원장 방식

## 4. 발행 흐름(공통 실행기 `tools/run_edition.py`)
설정 → 판 id(하한·이미 있음·담당 표시) → 후보 → 원장 예약 → 제미나이 → 검증·상한·격리 → **저장(commit+push) → 그 커밋으로 배포 → 라이브 대조** → 담당 해제·기록.
- 실패 = Actions 빨간색 + `ops/edition-fail.json` 커밋(exit 3 생성 / 4 저장 / 5 배포·대조). 초록인데 판이 없는 경우는 "하한 전"·"이미 있음"·"담당 표시 있음" skip 뿐이며 로그 첫 줄에 이유가 찍힌다.
- 같은 판은 두 번 안 만든다(picks 재push·예약 재실행 모두 skip). 일부러 다시 만들 때만 Run workflow 에 판 id 지정.
- 그록 picks 루틴은 그대로: `ops/picks/<판id>.json` push 가 발행을 깨운다. 하한(06:40 등)보다 2~3분 일찍 올려도 그 판으로 만든다.
- picks push 로 깬 실행이 대기열에서 밀려 취소돼도, 다음 실행(예약·감시 자가 복구·수동)이 "판 없는 오늘 picks"(하한 15분 전부터)를 찾아 그 판으로 만든다(2026-10-30).
- 실패 기록 push 는 origin/main 위에 기록 파일만 올린다 — 저장 단계에서 못 올린 판 커밋은 절대 같이 나가지 않는다.
- 배포 직전 담당 확인에서 다른 담당(Claude 비상 take)이 가져갔으면 실패가 아니라 넘겨줌(초록, 실패 기록 없음).
- `GEMINI_API_KEY` 가 없으면 빨간색 + `edition-fail.json`(예전엔 초록 skip 이라 아무도 몰랐음).

## 5. 비용 원장
- 운영 원장은 news.pmaxone.com(D1) — 운영 4저장소 `main` 실행만 `prod`, 브랜치·시험 저장소·로컬은 `test`. 상한은 prod 만 센다.
- git 에 원장 파일을 두지 않는다. `SPEND_HUB_TOKEN` 은 전환 뒤 삭제.
- 시험은 반드시 `*-staging` 저장소에서(상한 30바트, 원장 분리).

## 6. 감시·비상
- `edition-watch`(각 채널, 시각은 `site/<lang>.json watch_slots`) + 그록 상자 판+40분 점검 + Claude 비상 예약 9개.
- **감시 자가 복구(2026-10-30)**: 오늘 판이 예정(watch_slots) + 30분 지나도 라이브에 없고, edition 실행이 대기·실행 중이거나 25분 안에 시작된 게 없고, 그 판의 `edition-fail.json` 도 없으면 감시가 `edition.yml` 을 기본 토큰으로 실행한다(판 지정 없음 = 지금 슬롯만, 지난 판은 안 만듦). 끄기: 저장소 변수 `WATCH_DISPATCH=0`. 분 조정: `edition.watch_recover_min`.
- Claude 비상 예약은 **예약 작업 설정에 저장소가 붙어 있어야** 돈다(2026-10-30 확인: 9개 전부 저장소 없음 → 0단계에서 종료). 저장소 연결은 맥스가 Claude 앱 예약 작업 설정에서.
- Claude 비상 발행은 `ops/edition-fail.json` 과 판 파일 유무로 판단. 성공한 판은 그 파일을 지우므로(deploy.sh), 남아 있으면 진짜 실패.

## 7. 새 채널(예: 필리핀) 추가 규약
1. 채널 저장소 생성 → KR 저장소의 "채널 전용이 아닌" 파일을 news-core 에서 당겨옴(core-pull)
2. `site/LANG`, `site/<lang>.json`(brand·site_url·domain·currency·slots·watch_slots·validate·edition 키) 작성 — 템플릿 `rollout/*.edition.json` 참고
3. 채널 전용: 번역 규칙, 수집처, 필요하면 수집기(`picker: cmd`)
4. 시크릿: `GEMINI_API_KEY` (배포가 Cloudflare 면 `CLOUDFLARE_*`). 원장은 D1 이므로 토큰 불필요
5. news-hub `config.json` channels 에 추가(OIDC 허용·모음 페이지)
6. `*-staging` 에서 판 1개 시험 → 운영

## 8. 기사 고르기 통합 — 코드 기본 목록 + 그록 추가 (2026-10-30 밤, 맥스 원칙 "모든 사이트 동일")
- 모든 채널 `edition.picker = "base_add"`. 코드가 기본 목록(후보 40건, `ops/base/<판>.json`)을 만들고, 그록은 `ops/grok-add/<판>.json` 에 최대 4건만 보탠다.
- 그록 추가 마감 = 그 채널 발행 예약 시각(KR 07:05/12:05/18:05 · ZH 07:45/12:45/18:45 · VN 06:35/11:35/17:35). 그 뒤에 올린 파일은 그 판에 안 쓰인다.
- 규칙은 코드(`tools/grok_add.py`)가 강제: 최대 4건, 수집처 매체 주소만(X·Google News·블로그 금지), 24시간 안, 최근 6판 중복·같은 사건 금지, 큰 사건(big_event)은 angle 이 다른 4건까지. 미리 검사: `python3 tools/grok_add.py check <판 id>`.
- 그록은 더 이상 `ops/picks/<판>.json`(25건 고르기)을 올리지 않는다 — 올리면 그 push 가 판을 일찍 깨워 그록 추가가 빠질 수 있다.
- 기록: `ops/last-run.json` 의 `selection.path` = `code`(코드만) / `code+grok` / `code+grok-big`, `dropped`(뺀 그록 추가분과 이유), `factcheck_drops`(사실 대조로 뺀 기사).
- 되돌리기: 채널 `site/<lang>.json` 의 `edition.picker` 를 KR·ZH `grok_file`, VN `cmd` 로(설정 한 줄).

## 9. 발행 전 사실 대조 (factcheck, 2026-10-30)
- 판 저장 직전에 기사마다 원문(제목·본문·메모)과 대조: 금액이 원문 숫자와 정확히 10^k 배 다르면(단위 오류), 태국 채널은 원문에 없는 주 이름이 나오면 → 재번역 1회 → 그래도 틀리면 그 기사만 빼고 발행.
- 원문 본문을 못 가져온 기사는 제목 금액만 보고 지명은 안 본다(근거 없이 빼지 않기). 원문에 없는 '새 금액'은 계산·환산일 수 있어 빼지 않는다.
- 끄기(비상): 채널 `site/<lang>.json` 에 `"factcheck": {"places": false}`(지명만 끔). 금액 대조는 끄는 설정을 두지 않았다.
