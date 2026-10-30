# HANDOFF — 뉴스 채널 공통 구조(news-core) 인수인계 · 2026-10-30 11:50 BKK

이 파일만 읽고 바로 이어서 일할 수 있게 쓴 것이다. 확인한 사실만 적었고, 확인 못 한 것은 **UNVERIFIED** 로 표시했다. 비밀값은 없다.
이전 인수인계(`HANDOFF_2026-10-30.md`)·운영 규칙(`OPERATING_RULES.md`)·설계서(드라이브 00_INBOX `news-core_변경설계서_20261029 (클로드).md`)는 참고용이며, 이 파일이 가장 최신이다.

---

## 1. 프로젝트 개요

| 채널 | 저장소 | 사이트 | 언어 | 배포 | 공개 |
|---|---|---|---|---|---|
| tnews(KR) | `P-Max168/thai-news-kr` | https://tnews.pmaxone.com/ | 태국 뉴스 → 한국어 | GitHub Pages(main 루트) | 공개 |
| zh | `P-Max168/thai-news-zh` | https://zh.pmaxone.com/ | 태국 뉴스 → 중국어(간체) + zh1 한국어 검수 미러 | GitHub Pages | 공개 |
| vn | `P-Max168/vn-news-kr` | https://vn.pmaxone.com/ | 베트남 뉴스 → 한국어 | Cloudflare Worker(`dist/` 서빙) | 비공개 |
| 공통 | `P-Max168/news-core` | — | 공통 코드·워크플로 템플릿 | — | 공개 |
| 모음 | `P-Max168/news-hub`(news.pmaxone.com, Cloudflare D1) | 실행 기록·비용 원장 허브 | — | 배포 안 함(Firebase 승인 도메인 전) | — |

**구조의 목적**
1. 한 번 고치면 세 채널에 다 반영 — 공통 코드는 **news-core 에만** 있고, 채널은 `.core-version` 한 줄로 가리켜 당겨온다(pull). 채널 저장소에서 공통 파일을 직접 고치지 않는다.
2. 새 채널 = 설정 파일 하나 — 채널 고유값(판 시각·고르기·배포·곁 데이터·통화·브랜드)은 전부 `site/<lang>.json` 에. 코드 수정 0.
3. 사람·AI 가 바로 이해 — 채널마다 다른 것은 `site/<lang>.json`, `.core-version`, 워크플로의 cron 줄, 채널 전용 폴더(번역 규칙·수집기)뿐.

**하루 흐름(채널 공통)**: 그록이 `ops/picks/<판id>.json` 을 push(KR·ZH) 또는 예약 → `tools/run_edition.py` 가 판 id 결정 → 후보 → 제미나이(원장 예약·검증·상한·격리) → 저장(commit+push) → 배포 → 라이브 대조 → 담당 해제. 하루 3판(am/md/pm). 실패 = Actions 빨간색 + `ops/edition-fail.json`.

---

## 2. 현재 구조

### news-core (공통 원본)
```
news-core/
├─ core.json            공통 파일 목록(67개: src→dst)·사이트 목록·검사 설정   ← 파일 추가/삭제 시 여기도
├─ sync.py              채널 클론에 공통 파일 복사 + 검사(py_compile·site_build --check·test_pwa·HTML diff).  --pull = 복사까지
├─ core/tools/          공통 tools 44개 + dev 24개 (채널의 tools/ 로 그대로 복사됨)
│   run_edition.py        공통 발행 실행기(설계서 3-3). 채널 차이는 site json "edition" 키
│   gemini_edition.py     후보 → 제미나이 → 검증·상한·격리·저장. fx_now(환율), assemble(기사 조립)
│   newslib.py            검증(thai_check·money_check 등)·금액 표기·source_label(매체명 정리)
│   seo.py                e/<판>/index.html(판 정적 페이지)·sitemap·feed
│   share_kit.py          공유 카드 PNG·카톡 문구·e/ 페이지 저장(--pages-only 로 e/ 만)
│   deploy.sh             담당 확인·커밋·push·Pages 확인(곁 데이터 파일은 side.files 로 제외)
│   side_data.py          곁 데이터(시세·한국뉴스·中国要闻) 2시간 갱신 공통 실행기 — site json "side" 키
│   edition_watch.py      판 공백 감시 + 자가 복구(늦은 판이면 edition.yml dispatch)
│   edition_claim.py      판 담당 표시(원격 브랜치 claim/<판>/<누구>)
│   gemini_spend.py       비용 원장(hub=git 파일 / d1=news-hub / local)
│   fetch_ticker.py       시세(환율·금·날씨). fx_live(pair) 즉시 조회
│   siteconf.py           site/<lang>.json 읽기(site/LANG 또는 TNK_LANG)
├─ core/workflows/      채널 .github/workflows/ 로 복사되는 템플릿 4개 (cron 줄은 "# CORE-PULL-KEEP" 아래 블록만 채널 고유로 보존)
│   edition.yml  edition-watch.yml  side-data.yml  core-pull.yml
├─ rollout/             채널별 설정 템플릿 kr|zh|vn.edition.json ({"edition":…,"side":…}) + 전환 체크리스트 README.md
├─ OPERATING_RULES.md   운영 규칙(어디를 고치나·되돌리기·감시)
└─ HANDOFF*.md          인수인계
```

### 채널 저장소 (세 곳 같은 모양)
```
<채널>/
├─ .core-version                  news-core 태그(또는 브랜치) 한 줄  ← 지금은 브랜치 claude/news-core-handoff-review-ob9uw9
├─ site/LANG                      ko | zh | vn
├─ site/<lang>.json               ★ 채널 설정 원본(아래 3절 키 설명). topics.<lang>.json(주제)
├─ .github/workflows/
│   edition.yml                   발행(템플릿 + 채널 cron)
│   edition-watch.yml             감시·자가 복구(템플릿 + 채널 cron)
│   side-data.yml                 곁 데이터(템플릿 + 채널 cron)
│   core-pull.yml                 news-core 당겨오기(.core-version 바뀌면 자동)
│   (채널 전용) KR: collect.yml·claim-prune.yml·gpt-lane.yml / ZH: zh1-mirror.yml·gpt-lane.yml / VN: hub-deploy.yml·gpt-lane.yml
├─ tools/                         공통(core.json 목록) + 채널 전용(TRANSLATION_RULES.*.md, sources*.json, KR gpt_lane_check.py, ZH fetch_china.py, modern/, cloudflare/)
├─ data/<판id>.json|js, index.json 기사 데이터(판) · korea.* ticker.* china.*(곁 데이터)
├─ e/<판id>/index.html            판 정적 페이지(검색용) · og/ 공유 이미지
├─ ops/picks/ edition-fail.json last-run.json metrics.jsonl …  실행 기록
└─ VN 전용: pipeline/(vn_picks.py·build_dist.py·refresh_side.py·tools/publish.py), cloudflare/worker.mjs, wrangler.json, hub/(news-hub 로 이전 예정)
```

### `site/<lang>.json` 의 공통 실행기 키
- `edition`: `picker`(grok_file|code|cmd) `picker_cmd` `pool` `select`(0=그록 picks 그대로) `claim` `publisher` `deploy`(pages|cloudflare|none) `deploy_cmd` `live_check`(pages|curl|none) `video_feed` `candidates_from`(own|kr) `floor_minutes` `stale_slots` `after_deploy_cmd` `metrics_line` `watch_recover_min`
- `side`: `cmds`(차례로 실행, `{force}` 치환) `files`(커밋할 파일 = 판 저장 때 제외할 파일) `label`(커밋 메시지) `pip`
- `currency.fx_update_bkk`: 환율 API 갱신 시각(기본 "07:02") — 시세 파일이 이 시각 전 값이면 판 생성 때 즉시 조회
- 기존 키: `watch_slots`(판 시작 시각 = 하한·감시·곁 데이터 대기 창), `slots`, `validate.forbid_scripts`, `currency.pair/format/check`, `site_url`, `repo` …

---

## 3. 변경 전부 (처음 받은 코드 대비)

기준점: news-core `3c09555`(브랜치 `claude/s0-core-refresh`), KR main `388ec21`, ZH main `22daa8f`, VN main `ae20ac9`.
작업 브랜치(4저장소 공통 이름): `claude/news-core-handoff-review-ob9uw9`. 백업 브랜치(채널 3곳, 병합 전 main 그대로): **`backup/before-unify-20261030`**.

### 3-1. news-core — PR [#1](https://github.com/P-Max168/news-core/pull/1) (초안, main 병합 안 됨)

| 커밋 | 파일 | 무엇 | 왜 |
|---|---|---|---|
| [d72178d](https://github.com/P-Max168/news-core/commit/d72178d) | `core/tools/run_edition.py` | `write_fail`: 이번 실행 전에 있던 `edition-fail.json` 은 덮어씀 · `push_fail_record`: 임시 worktree(origin/main)에 기록 파일만 커밋·push · `pushed_picks_id`: push 이벤트 페이로드(`GITHUB_EVENT_PATH`)의 모든 커밋에서 picks 파일 찾기, 없으면 `GITHUB_SHA~1` · `waiting_picks_id`: 판 없는 오늘 그록 picks(하한 15분 전부터)를 어느 실행이든 집음 · `live_check`·`redeploy_if_stale`: 기사 수 + `generated` 대조 · `GEMINI_API_KEY` 없음 = exit 3 + 실패 기록(예전 초록 skip) · deploy.sh exit 4(다른 담당이 가져감) = 넘겨줌(초록, 기록 없음) | 지난 판 실패 기록이 남아 비상 발행이 엉뚱한 판을 읽음 / 저장 실패 뒤 실패 기록 push 가 못 올린 판 커밋까지 올려 Pages 에 실패 판이 뜸 / checkout 이 최신 main 이라 picks 뒤 다른 커밋이 끼면 판을 놓침 / picks 실행이 대기열에서 취소되면 판 놓침 / 같은 id·건수의 다른 실행을 일치로 봄 / 운영 규칙(초록 skip 3가지) 위반 |
| 〃 | `core/tools/gemini_edition.py` | `select` 있으면 `cap_kept` 항상(한 번 호출 포함) · 지난 실패 기록 덮어씀(`_T0`) | 25건 상한이 한 번 호출일 때 안 걸림(설계서 2-1 ②) |
| 〃 | `core/tools/edition_watch.py` | `recover()`: 오늘 판이 예정+30분(`RECOVER_MIN`, `edition.watch_recover_min`) 늦고, edition 실행이 대기·진행 중·25분 안 시작이 아니고, 그 판 실패 기록이 없으면 `edition.yml` workflow_dispatch(ref main). `WATCH_DISPATCH=0` 이면 끔. `--now`·`--latest` 흉내 때는 안 함 | GitHub 예약이 빠지면 발행·감시가 같이 멈추고 비상도 막힘 → 판 없음(10-30 KR·VN 아침) |
| 〃 | `core/workflows/edition-watch.yml` | `GH_TOKEN`→`GITHUB_TOKEN`, `permissions.actions: write`, `WATCH_DISPATCH` 변수 전달, sparse-checkout 에 `tools/siteconf.py` `site` `ops/edition-fail.json` | 스크립트는 `GITHUB_TOKEN` 을 읽음 → 무인증 → 비공개 VN 에서 이슈 못 엶 / KR 에서 `No module named siteconf` |
| 〃 | `core/workflows/edition.yml` | `TNK_LIVE_CHECK: pages` 고정값 삭제 | 실행기가 site json 으로 정함(설정 원본 하나) |
| 〃 | `OPERATING_RULES.md` `HANDOFF_2026-10-30.md` | 규칙 4·6절 보강, 7절 추가 | 문서 |
| [c2c9568](https://github.com/P-Max168/news-core/commit/c2c9568) | `core/tools/newslib.py` | `source_label(name, fallback)` 추가: 화면에 태국 글자가 금지된 언어판이면 매체명의 태국어 부분(괄호 안 원어 등) 제거 | 알려진 문제 (a) |
| 〃 | `core/tools/seo.py` | `edition_page` 가 source·also.source 를 `source_label` 로 표시 | 이미 발행된 판의 e/ 페이지도 다시 만들 수 있게 |
| [d49d26c](https://github.com/P-Max168/news-core/commit/d49d26c) | `core/tools/gemini_edition.py` | `assemble`: source·also[].source 를 `source_label`(전부 태국어면 도메인) · `_fx_stale`·`fx_now`: 시세 파일 환율이 오늘 `currency.fx_update_bkk`(기본 07:02)+3분 뒤에도 그 전 값이면 `fetch_ticker.fx_live` 로 즉시 조회(실패하면 파일 값) | (a) 데이터 단계에서 차단 / (c) 어제 환율 |
| 〃 | `core/tools/share_kit.py` | `import newslib`; 카드 매체명도 `source_label`; 카드 PNG 렌더(playwright) 실패해도 e/·sitemap·feed 생성(og 복사는 렌더 성공 때만); `--pages-only` 옵션 | 브라우저 설치 실패 = e/ 404 였음 / 빠진 판 미리보기만 다시 만들기 |
| [0be25a8](https://github.com/P-Max168/news-core/commit/0be25a8) | `core/tools/side_data.py`(새) | 곁 데이터 공통 실행기: `watch_slots` 시작~+61분 대기 → `side.cmds` 실행 → `side.files` 중 바뀐 것 커밋(라벨) → pull --rebase -X theirs → push. 명령 실패 exit 1, push 실패 2 | KR `korea.yml`·ZH `china.yml` 100줄 복사본 2개 → 하나로. VN 은 곁 데이터 갱신이 판 때만이었음 |
| 〃 | `core/workflows/side-data.yml`(새) | 템플릿: cron 기본 `9 */2 * * *`(UTC = 07:09 BKK 부터 2시간), `side.pip` 설치, `side_data.py` 실행 | (c) 환율 API 07:02 갱신 뒤 첫 실행 |
| 〃 | `core/tools/fetch_ticker.py` | `fx_live(pair)` 추가(open.er-api `latest/<base>` 의 quote) | fx_now 가 씀 |
| 〃 | `core/tools/deploy.sh` | 제외할 곁 데이터 파일을 `side.files` 로(없으면 옛 기본값); `side-data.yml` 도 "따로 갱신하는 워크플로" 로 인정 | 설정 원본 하나 |
| [22ad9dc](https://github.com/P-Max168/news-core/commit/22ad9dc) | `core/tools/run_edition.py` `core/workflows/edition.yml` | `AFTER_DEPLOY_OFF=1`(저장소 변수) 이면 `after_deploy_cmd` 건너뜀(옛 `ZH1_MIRROR=off` 대체) | 템플릿에 채널 이름 변수를 두지 않기 위해 |
| 〃 | `core.json` | `tools/side_data.py` 추가(67개), source_of_truth 설명 | |
| 〃 | `rollout/kr|zh|vn.edition.json` | 형식 `{"edition":…, "side":…}` 로; VN `pre_cmd`(refresh_side) 제거 | side-data.yml 이 대신 갱신, deploy.sh 가 그 파일을 원격 것으로 받음 |
| [52c80e3](https://github.com/P-Max168/news-core/commit/52c80e3) | `core/tools/run_edition.py` | `make_picks`: picker grok_file/code 면 picks 파일이 있어도 `fetch_candidates()`(실패 무시) | 옛 KR·ZH yml 은 후보 목록을 항상 받아 picks 의 빠진 제목·매체를 채웠음 |

### 3-2. thai-news-kr — PR [#10](https://github.com/P-Max168/thai-news-kr/pull/10)
| 커밋 | 무엇 |
|---|---|
| [eb48d24](https://github.com/P-Max168/thai-news-kr/commit/eb48d24) | `site/ko.json`: `edition`(grok_file·pool 30·select 0·claim·pages·video_feed·own) · `side`(fetch_korea --standalone {force}, fetch_ticker / korea.*·ticker.* / "korea: 한국 주요 뉴스·시세" / googlenewsdecoder) · `currency.fx_update_bkk` |
| [59dc681](https://github.com/P-Max168/thai-news-kr/commit/59dc681) | news-core 당겨오기: tools 12개(deploy.sh edition_stale edition_watch fetch_ticker gemini_edition gemini_spend newslib pending run_edition seo share_kit side_data) + 워크플로 4개(core-pull edition-watch edition side-data) + `.core-version` |
| [5e01ded](https://github.com/P-Max168/thai-news-kr/commit/5e01ded) | `gemini-edition.yml`·`korea.yml` 삭제. cron: edition `5 0`,`5 5`,`5 11`(옛 값 그대로) · edition-watch `50 *`,`41 1,12`(옛 값) · side-data `9 */2`,`17 1-23/6`(옛 korea.yml `47 */2` → `9 */2`, 예비 4회 유지) |
| [617cfb1](https://github.com/P-Max168/thai-news-kr/commit/617cfb1) | e/ 빠진 판 9개 생성(10-01 am·pm, 10-02 am, 10-24 pm, 10-25 pm, 10-26 am, 10-27 pm, 10-28 am, 10-29 am) + sitemap.xml·feed.xml·index.html(홈 '지난 뉴스판' 링크 목록만) |

### 3-3. thai-news-zh — PR [#4](https://github.com/P-Max168/thai-news-zh/pull/4)
| 커밋 | 무엇 |
|---|---|
| [d3c88a8](https://github.com/P-Max168/thai-news-zh/commit/d3c88a8) | `site/zh.json`: `edition`(grok_file·candidates_from kr·after_deploy_cmd = zh1 미러 + 커밋·push) · `side`(fetch_china --standalone {force}, fetch_ticker / china.*·ticker.*) · `fx_update_bkk` |
| [cca88ba](https://github.com/P-Max168/thai-news-zh/commit/cca88ba) | news-core 당겨오기(KR 과 같은 파일 + video_picks.py) |
| [6fc2680](https://github.com/P-Max168/thai-news-zh/commit/6fc2680) | `gemini-edition.yml`·`china.yml` 삭제. cron: edition `45 0`,`45 5`,`45 11`(옛 값) · watch `50 *`,`41 1,5,12`(옛 값) · side-data `9 */2`(옛 china.yml `17 */2`) |
| [9c6df68](https://github.com/P-Max168/thai-news-zh/commit/9c6df68) | e/2026-10-29-am 생성 + sitemap·feed |

### 3-4. vn-news-kr — PR [#2](https://github.com/P-Max168/vn-news-kr/pull/2)
| 커밋 | 무엇 |
|---|---|
| [8cd94c6](https://github.com/P-Max168/vn-news-kr/commit/8cd94c6) | `site/vn.json`: `side`(refresh_side.py / korea.*·ticker.*) 추가, `edition.pre_cmd` 삭제, `fx_update_bkk` |
| [e7996b0](https://github.com/P-Max168/vn-news-kr/commit/e7996b0) | news-core 당겨오기(tools + 워크플로; `side-data.yml` 새로, cron 기본 `9 */2`). edition·edition-watch cron 은 옛 값 보존 |

### 3-5. 하지 않은 것(확인)
CNAME·robots.txt·firestore.rules·광고·비밀값·기사 데이터(`data/`)·디자인(assets·index 본문)·발행 cron 시각 — 전부 손대지 않음. force push 없음. 채널 `main` 직접 push 없음(브랜치·PR 만).

---

## 4. 고친 문제 — 원인과 수정

| 문제 | 원인(확인됨) | 수정 |
|---|---|---|
| **(a) 매체명에 태국 글자 → /e/<날짜>-am/ 404** | 공동 출처 `also[].source`(예 `Bangkok Biz News(กรุงเทพธุรกิจ)`)는 `newslib.thai_check` 가 안 보는 필드(source·related.source 만 봄) → 판은 통과. `share_kit` 이 e/ 페이지(`seo.edition_page` 가 also 매체명 출력)를 만들며 태국 글자 검사에 걸려 `sys.exit` → e/·sitemap 생성 전 중단. 워크플로는 이 단계가 `continue-on-error` 라 초록. KR 9판·ZH 1판이 404 | `newslib.source_label` 로 매체명 정리 — 판 생성(`assemble`)·e/ 페이지(`seo`)·카드(`share_kit`) 공통. share_kit 은 PNG 렌더 실패에도 e/ 생성. 빠진 e/ 10개 재생성해 PR 에 포함 |
| **(b) 10-30 아침 예약 미실행** | GitHub Actions schedule 누락. KR `gemini-edition.yml` 07:05(UTC 00:05) 예약 오늘 0회(어제 18:05 예약도 00:23 에 6시간 늦게 돎). VN 은 `publish.yml` 이 10-29 `edition.yml` 로 교체·07:04 병합된 뒤 `edition`·`edition-watch` 예약 0회(같은 저장소 `gpt-lane` 은 돎 → 새 cron 재등록 안 된 것으로 봄). 11:35 점심판 예약도 안 돎. Claude 비상 예약 9개는 예약 작업에 저장소가 안 붙어 0단계에서 종료(22초) | 코드로 예약 자체는 못 고침. **감시 자가 복구**(edition_watch → edition.yml dispatch) 추가. 워크플로 파일이 바뀐 PR 병합 = cron 재등록 효과. 11:43 VN 점심판은 손으로 dispatch(아래 6절) |
| **(c) 어제 환율** | open.er-api 갱신 07:02 BKK. 시세 수집이 KR 06:47(`47 */2`)·ZH 06:17(`17 */2`)·VN 판 때(06:35)로 전부 갱신 전 → `data/ticker.json` 이 어제 값 → `fx_now` 가 그대로 씀 | ① 곁 데이터 cron `9 */2`(07:09 BKK 부터) ② `fx_now` 가 stale 이면 즉시 조회(ZH dry 실행에서 작동 확인). **단 KR 06:40·VN 06:35 아침판은 갱신 전에 만들어져 어제 환율이 불가피**(6절) |
| 실패 기록이 지난 판 것 | `edition-fail.json` 이 있으면 안 썼음(KR main 에 10-28-am 기록이 아직 남아 있음) | 이번 실행 전 파일은 덮어씀 |
| 실패 기록 push 가 판 커밋 동반 | 작업 폴더 HEAD 를 push | origin/main worktree 에 기록 파일만 |
| picks 판 놓침 | `HEAD~1..HEAD` 만 봄 / 대기열 취소 | 이벤트 페이로드 + 판 없는 오늘 picks 집기 |
| 25건 상한 | 묶음(청크)일 때만 재적용 | 항상 |
| 감시 경보 끊김(비공개 VN) | 템플릿이 `GH_TOKEN` 만 넘김 | `GITHUB_TOKEN` |
| KR 감시 `No module named siteconf` | sparse-checkout 이 edition_watch.py 만 | siteconf·site 포함 |
| 곁 데이터 워크플로 복사본 2개 + VN 은 하루 3회 | 채널마다 yml | `side_data.py` + 템플릿, VN 도 2시간 |

---

## 5. 검증 결과 (2026-10-30 11:00~11:30 BKK, 이 세션의 리눅스 컨테이너)

| 검사 | KR | ZH | VN |
|---|---|---|---|
| `sync.py --pull`: py_compile·preflight 문법·`site_build.py --check`·test_pwa·HTML diff | 전부 ok, HTML diff 0줄 | 전부 ok, 0줄 | 전부 ok, 0줄 |
| 기존 e/ 페이지를 새 코드로 재생성 → 커밋본과 바이트 동일? | 10-29-md **동일** | 10-30-am **동일** | 10-29-pm **동일** |
| 빠진 e/ 생성 — 태국 글자 0, `<article id>` = 기사 id(#so1 등) | 9판 생성·확인 | 10-29-am 생성·확인 | 빠진 판 없음 |
| `run_edition.py --dry --now "… 12:xx"`(판 결정→후보→제미나이 dry, 유료 호출 없음) | ok(code_picks 30건, 청크 2) | ok(+ stale 환율 즉시 조회 작동) | 후보 0건 — 이 환경에서 베트남 RSS 차단. **UNVERIFIED**(Actions 에서는 10-29 24건 정상) |
| 단위시험 `tools/dev/test_gemini_edition_quarantine.py` `test_gemini_spend.py` `test_money_round.py` | ALL OK | — | — |
| `side_data.py` 대기 창 계산·설정 읽기 | ok | ok | ok |
| `edition_watch.py --dry-run` | 실행(복구 판단은 edition.yml 이 main 에 없어 404 → 안 함, 정상) | 정상(열린 공백 이슈 닫을 예정 출력) | 실행 |
| VN `pipeline/build_dist.py` | — | — | 231개 파일 ok |
| 카드 PNG(playwright) | **UNVERIFIED** — 이 환경에 python playwright 없음. 새 폴백(렌더 실패 → e/ 는 생성) 작동 확인 | | |
| 실제 GitHub Actions 실행 | **UNVERIFIED** — PR 병합 전. 병합 뒤 `edition` Run workflow dry=true 1회로 확인 필요 | | |

---

## 6. 남은 문제 · 사람이 정할 것

1. **PR 병합(맥스)** — 순서 news-core#1 → VN#2 → ZH#4 → KR#10. 각각 판 사이 창(13:30~17:30 또는 19:00~)에서 병합 → Actions `edition` Run workflow **dry=true** 1회 → 다음 판 관찰. 되돌리기 = PR revert 또는 `backup/before-unify-20261030`.
2. **news-core 태그** — main 병합 뒤 `v2026.10.30`(Releases 또는 그록; Claude 클라우드 세션은 태그 못 만듦) → 채널 `.core-version` 을 태그로.
3. **Claude 비상 예약 9개 저장소 연결** — 앱에서만 가능. VN 3개(08:20·13:50·19:20): vn-news-kr + thai-news-kr / ZH 3개(08:10·13:10·19:10): thai-news-zh + thai-news-kr / tnews 3개: thai-news-kr. 쓰기 권한.
4. **아침판 환율** — KR 06:40·VN 06:35 판은 07:02 갱신 전. (가) 지금처럼(판에 환율 시각 표기됨) (나) 아침판 하한을 07:05 이후로(발행 시각 변경).
5. **GitHub 예약 누락 근본 해결** — 설계서 2-5 B(미니PC self-hosted runner) 또는 C(Cloudflare cron → dispatch, Actions 쓰기 토큰 1개). 그전까지 감시 자가 복구 + 비상 예약.
6. **10-30 미발행 판** — KR·VN 아침판은 되살리지 않음(지난 판 규칙). VN 점심판은 11:43 에 `edition.yml` 을 workflow_dispatch(edition=2026-10-30-md) 로 손으로 실행 → [run 41004422835](https://github.com/P-Max168/vn-news-kr/actions/runs/41004422835) **성공**: main 커밋 `eab36e1 edition 2026-10-30-md`, 22건(≤25), generated 11:47:52, 환율 VND_KRW 오늘 07:02 값, `edition-fail.json` 없음, 라이브 https://vn.pmaxone.com/data/2026-10-30-md.json = generated 11:47:52·22건·id 일치(저장소 = 라이브 확인). KR 점심판은 12:05 예약 또는 그록 picks 대기.
7. VN `hub/` 폴더·`hub-deploy.yml` 은 news-hub 저장소로 이전 뒤 삭제 예정(아직). 원장 D1 전환(`GEMINI_SPEND_BACKEND=d1`)은 news-hub 배포 뒤.
8. KR `tools/gpt_lane_check.py` 는 KR 전용 경로가 박혀 있어 아직 코어에 없음(core.json pending_s2).
9. 공통 파일을 채널에서 직접 고친 것을 잡는 md5 검사(core-check)는 아직 없음.
10. 알려진 데이터 오류(KR 10-28 wt1 "8개 주", VN 10-28 pe1 "1억 원대", tỷ 환산)는 번역 검사 범위 — 미수정.

---

## 7. 이어서 고치는 법

### 새 채널 추가 — 예시 `site/ph.json`(필리핀 가정)
```json
{
 "lang": "ph", "brand": "필리핀 뉴스 한눈에", "domain": "ph.pmaxone.com", "site_url": "https://ph.pmaxone.com/",
 "repo": "P-Max168/ph-news-kr", "slots": ["am","md","pm"],
 "watch_slots": [["am",7,0],["md",12,0],["pm",18,0]],
 "currency": {"pair": "PHP_KRW", "format": "{php}페소(약 {krw}원)", "check": "krw_check", "fx_update_bkk": "07:02"},
 "validate": {"forbid_scripts": ["thai","cjk"]},
 "edition": {"picker": "code", "pool": 30, "select": 20, "claim": true, "publisher": "grok", "deploy": "pages", "live_check": "pages",
             "video_feed": false, "candidates_from": "own", "floor_minutes": {"am":[6,40],"md":[11,40],"pm":[17,40]}},
 "side": {"cmds": ["python3 tools/fetch_ticker.py"], "files": ["data/ticker.json","data/ticker.js"], "label": "ticker: 시세", "pip": []}
}
```
순서: 저장소 생성 → `site/LANG`=`ph`, 위 json, `topics.ph.json`(KR 것 복사) → `.core-version`=태그 → `core-pull.yml` 한 장 복사해 Run workflow → 공통 파일·워크플로 들어옴 → cron 줄만 채널 시각으로 → 시크릿 `GEMINI_API_KEY`(Cloudflare 면 `CLOUDFLARE_*`) → `*-staging` 에서 판 1개 시험(`GEMINI_DAILY_CAP_THB=30`) → 운영. `fetch_ticker.py` 의 `fx_er_api` 는 THB 기준이라 다른 통화 채널은 `side.cmds` 에 채널 수집기(VN `refresh_side.py` 식)를 쓴다.

### 자주 고칠 곳
| 바꾸고 싶은 것 | 어디 |
|---|---|
| 공통 동작(고르기·번역 연결·검증·저장·배포·감시·곁 데이터) | news-core `core/tools/*` → `sync.py` 검사 → PR → 태그 → 채널 `core-pull` |
| 워크플로 단계 | news-core `core/workflows/*.yml`(cron 줄은 `# CORE-PULL-KEEP` 아래만 채널 고유) |
| 채널 고유값 | 그 채널 `site/<lang>.json` |
| 판 시각 | `site/<lang>.json` `watch_slots`·`edition.floor_minutes` + 그 채널 `.github/workflows/*.yml` cron 줄 |
| 매체명 표시 규칙 | `newslib.source_label` |
| 환율 갱신 시각 | `currency.fx_update_bkk` |
| 공통 파일 추가/삭제 | `core.json` `files` |

### 빌드·검증 명령
```bash
# 1) 공통 코드 고친 뒤 채널 클론에 적용·검사(dry: 복사 안 함)
python3 /path/news-core/sync.py --site kr --clone /path/thai-news-kr        # kr|zh|vn
python3 /path/news-core/sync.py --site kr --clone /path/thai-news-kr --pull # 검사 통과 시 복사(커밋은 직접)
# 2) 채널 클론 안에서
python3 tools/site_build.py --root . --check
TZ=Asia/Bangkok python3 tools/run_edition.py --dry --now "2026-11-01 12:00"   # 제미나이 안 부름·push 안 함
python3 tools/share_kit.py <판id> --pages-only          # e/<판>/index.html·sitemap·feed 만(브라우저 불필요)
python3 tools/share_kit.py <판id> --out /tmp/sk         # 카드·OG 까지 임시 폴더로(og/·e/ 안 건드림, playwright 필요)
python3 tools/edition_watch.py --dry-run                # 감시 판단만
python3 tools/side_data.py --dry --no-wait              # 곁 데이터 명령 실행, 커밋 안 함
python3 tools/dev/test_gemini_edition_quarantine.py; python3 tools/dev/test_gemini_spend.py; python3 tools/dev/test_money_round.py
# 3) VN 만
python3 pipeline/build_dist.py && ls dist | wc -l
# 4) e/ 페이지 확인
python3 -c "import re;s=open('e/<판id>/index.html',encoding='utf-8').read();print(len(re.findall(r'[฀-๿]',s)), re.findall(r'id=\"[a-z]{2}\d+\"',s))"
```
이 컨테이너에서 안 되는 것: `vn.pmaxone.com` 직접 curl(프록시 403 → WebFetch), 베트남 RSS, python playwright(pip 설치 필요), 태그 push·브랜치 삭제·운영 PR 병합(403 — 맥스·그록).

---

## 8. 절대 규칙
- **손대지 않는 것**: `CNAME`, DNS, `firestore.rules`, `robots.txt`, 광고 코드(`ads.txt`·광고 스크립트), 시크릿·토큰(값을 파일·로그·커밋·메시지에 쓰지 않음).
- **force push 금지, 히스토리 재작성 금지, `git config --global` 금지.**
- **push 금지 시간(방콕)**: 06:40–08:10, 17:40–18:40 (판 발행 창). 판 발행 push 자체는 예외.
- 기사 내용·디자인·발행 예약 시각은 바꾸지 않는다. 채널 저장소에서 공통 파일을 직접 고치지 않는다(news-core 에서).
- 이미 있는 판은 잘못된 판이라도 덮어쓰지 않는다. 지난 판은 자동으로 다시 만들지 않는다.
- 유료 호출(제미나이)은 시험 저장소(`*-staging`, 상한 30바트)에서만.
- 밖으로 나가는 것(push·배포·공유)은 맥스 승인 목록 안에서만.
