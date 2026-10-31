# Codex 인수인계 — 뉴스 채널 통합 코드 새로 짜기 전 읽을 것 · 2026-10-31 19:40 BKK · Claude(code 방) → Codex

맥스 지시(2026-10-31 19:10): 열린 PR 4건을 "맥스 결정과 맞는 부분만" 남겨 **참고용으로 열어 둠**. Codex 가 통합 코드를 새로 짤 때 이 PR 들을 읽고, 새 통합 코드가 올라가면 "흡수 완료"로 닫는다. **이 PR 들은 main 에 병합하지 않는다.**

## 1. 진행 상황 (확인됨)
| 저장소 | 참고용 PR | 브랜치 | 정리 커밋 | 남은 내용 |
|---|---|---|---|---|
| news-core | [#2](https://github.com/P-Max168/news-core/pull/2) | `claude/edition-quality-p1` | `1aa298e` | factcheck.py+시험, grok_add.py+시험(최대 4·X/Google News 거부·24h·같은 사건·big_event), run_edition picker `base_add`(코드가 select 건 확정, 그록 추가, ops/base 기록, 묵은 후보 다시 수집, last-run selection·factcheck_drops), gemini_edition(factcheck 연결, 위안 이중 환산 제거, 최소 기사 수 없음), edition.yml feedparser, deploy.sh ops/base |
| thai-news-kr | [#11](https://github.com/P-Max168/thai-news-kr/pull/11) | `claude/edition-quality-p1` | `dd8d89e` | `site/ko.json` edition(base_add·select 25·grok_add) + `.core-version` 만 |
| thai-news-zh | [#5](https://github.com/P-Max168/thai-news-zh/pull/5) | `claude/edition-quality-p1` | `effdcf2` | `site/zh.json` edition + `.core-version` 만. 수집처는 `tools/sources.zh.json`(저장소 안) |
| vn-news-kr | [#3](https://github.com/P-Max168/vn-news-kr/pull/3) | `claude/edition-quality-p1` | `a4c7a9c` | `site/vn.json` edition(base_cmd vn_picks·select 25·grok_add) + `.core-version` 만 |

의존: 채널 PR 3개 → news-core `1aa298e`(→ news-core#1 `bea8cc5`) → 각 채널의 공통화 PR(KR#10·ZH#4·VN#2, 2026-10-30, 역시 미병합).
PR 본문 첫 줄에 "참고용 · 병합 금지" 표시, 전부 초안(draft) 상태.

### 맥스 결정(2026-10-31)과 코드의 관계
- **선정은 코드가 전부, 그록은 판마다 X 보탬 기사 최대 4건만, 제미나이는 번역만** → PR 에서 제미나이 25건 고르기를 뺌(`grok_add.merge` select 0, `code_picks --pool select --select 0`).
- **최소 기사 수 없음** → `save_with_drop` min 1, `articles_lt_1`.
- **새 판 시각표(방콕)**: 아침 KR 06:30·VN 06:35·ZH 06:40 / 점심 11:30·11:35·11:40 / 저녁 17:30·17:35·17:40. **아직 코드·설정(watch_slots·floor_minutes·cron·grok_add.cutoff)에 들어가지 않았다.** 옛 마감 설정만 뺐음.
- **X 화제는 언론사 기사 URL 로만** → `grok_add.BAD_HOSTS`(x.com·t.co·twitter 등)로 코드가 거부(시험 있음).
- **수집처는 나라별 목록 1개, 각 채널은 설정으로 참조. ZH 가 KR 목록을 원격으로 받지 않음** → 원격(raw.githubusercontent) 경로 전부 뺌. 공통 목록 파일(예: news-core `core/sources/th.json` → 채널 `tools/sources.th.json` 복사, `edition.grok_add.sources`·`edition.cand_sources` 로 참조)은 **아직 없음 — Codex 몫**.
- **설정만으로 카테고리 추가 가능한 구조는 넣어도 됨. X 전용 카테고리 실제 도입은 통합 뒤.** PR 에는 카테고리 구조 변경 없음.

## 2. 실패한 방법과 이유 (반복 금지)
| 시도 | 결과 | 대신 |
|---|---|---|
| 제미나이에게 후보 40건 중 25건을 고르게(select 25) | 맥스 결정과 어긋남(선정은 코드) | 코드가 select 건 확정, select 0 |
| 최소 기사 수 4 미만이면 판 실패 | 맥스: 번역된 만큼 발행 | min 1 |
| 그록 추가 마감을 옛 판 시각(07:05 등)으로 설정 | 판 시각 30분 앞당겨짐 | 값 뺌, 새 시각표 확정 뒤 `grok_add.cutoff` |
| ZH 가 KR `tools/sources.json` 을 raw URL 로 받음 | 채널 간 원격 의존 금지 | 저장소 안 파일만, 나라별 공통 목록은 통합에서 |
| 채널 PR 에 공통 tools 를 통째로 복사 | 코어+설정 구조와 겹침 | 채널 PR 은 설정 + `.core-version` 만 |
| (10-30) 단위 없는 작은 숫자까지 10^k 비교 / 본문 없을 때 요약 금액 대조 / 영어 "37-million-baht" | 오탐 | factcheck.py 머리말 참고 |
| (10-30) grok-add push 로 판 깨우기 | 판을 일찍 만들어 그록 추가가 빠질 위험 | 깨우지 않음 — 판 시각이 마감 |
| (10-30) Claude 세션에서 태그 push·브랜치 삭제·운영 PR 병합·Actions 시크릿 조회 | 403/승인 거부 | 맥스·그록 |
| (10-30) Claude 세션에서 vn.pmaxone.com curl | 프록시 403 | WebFetch |

## 3. 다음 할 일 (Codex 통합 코드)
1. 새 판 시각표를 설정 한 곳에: 채널 `site/<lang>.json` `watch_slots`·`edition.floor_minutes`·`edition.grok_add.cutoff` + 워크플로 cron(CORE-PULL-KEEP 블록). 발행 예약 변경은 맥스 승인 뒤.
2. 나라별 수집처 목록 1개(태국: KR·ZH 공용 / 베트남: VN)와 설정 참조 방식(`edition.grok_add.sources`, `edition.cand_sources`). 원격 참조 금지.
3. 통합 실행기: news-core#1·#2 의 `run_edition.py`(base_add)·`grok_add.py`·`factcheck.py` 를 흡수. 유지할 동작: 코드 선정(select 건) + 그록 추가 4건(코드 강제) + 제미나이 번역만 + factcheck(재번역 1회 → 격리) + 최소 기사 수 없음 + ops/base 기록(본문 없음) + last-run selection·factcheck_drops + 묵은 후보 다시 수집.
4. 통합 코드가 올라가면 참고용 PR 4개를 "흡수 완료"로 닫기(병합 아님). 2026-10-30 공통화 PR(news-core#1, KR#10, ZH#4, VN#2)의 처리도 맥스 결정.
5. Codex push 허용 범위는 **맥스 결정 대기(미확인)** — 결정 전까지 기존 동결 유지.

## 4. 손대지 말 것
- 그록 작업 영역: VN 운영, 오역 대조, 번역 규칙 파일(`tools/TRANSLATION_RULES*.md`), 영상 원고 / `kstar-th` 저장소 전체.
- 채널 저장소 `ops/picks/*.json`·`ops/grok-add/*.json`(그록 데이터; VN edition.yml 의 push 트리거가 브랜치 제한 없음 → 발행이 돌 수 있음).
- CNAME·DNS·firestore.rules·robots.txt·광고·비밀키. 강제 푸시·`git config --global` 금지. 유료 API 호출 테스트 금지.
- push 금지 시간(방콕): 06:40~08:10, 11:40~12:40, 17:40~18:40.
- 그록은 코드 push 금지(picks·grok-add·댓글·맥스 승인 데이터 수정은 계속 허용).

## 5. 검증 방법(이번 정리에서 쓴 것, 유료 호출 없음)
```bash
python3 /path/news-core/sync.py --pull --clone <채널 클론 복제> --site kr|zh|vn   # py_compile·site_build --check·test_pwa·HTML diff
cd <채널 클론 복제> && python3 tools/dev/test_grok_add.py && python3 tools/dev/test_factcheck.py && python3 tools/dev/test_gemini_edition_quarantine.py && python3 tools/dev/test_money_round.py
```
2026-10-31 결과: 3채널 sync 검사 전부 통과(HTML diff 0), 시험 4종 통과(KR 복제). 미확인: 실제 제미나이 호출 판, Actions 에서의 다시 수집 시간, VN 실제 수집(이 환경은 베트남 RSS 차단).
