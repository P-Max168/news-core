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

## 5. 비용 원장
- 운영 원장은 news.pmaxone.com(D1) — 운영 4저장소 `main` 실행만 `prod`, 브랜치·시험 저장소·로컬은 `test`. 상한은 prod 만 센다.
- git 에 원장 파일을 두지 않는다. `SPEND_HUB_TOKEN` 은 전환 뒤 삭제.
- 시험은 반드시 `*-staging` 저장소에서(상한 30바트, 원장 분리).

## 6. 감시·비상
- `edition-watch`(각 채널, 시각은 `site/<lang>.json watch_slots`) + 그록 상자 판+40분 점검 + Claude 비상 예약 9개 — 기존 그대로.
- Claude 비상 발행은 `ops/edition-fail.json` 과 판 파일 유무로 판단. 성공한 판은 그 파일을 지우므로(deploy.sh), 남아 있으면 진짜 실패.

## 7. 새 채널(예: 필리핀) 추가 규약
1. 채널 저장소 생성 → KR 저장소의 "채널 전용이 아닌" 파일을 news-core 에서 당겨옴(core-pull)
2. `site/LANG`, `site/<lang>.json`(brand·site_url·domain·currency·slots·watch_slots·validate·edition 키) 작성 — 템플릿 `rollout/*.edition.json` 참고
3. 채널 전용: 번역 규칙, 수집처, 필요하면 수집기(`picker: cmd`)
4. 시크릿: `GEMINI_API_KEY` (배포가 Cloudflare 면 `CLOUDFLARE_*`). 원장은 D1 이므로 토큰 불필요
5. news-hub `config.json` channels 에 추가(OIDC 허용·모음 페이지)
6. `*-staging` 에서 판 1개 시험 → 운영
