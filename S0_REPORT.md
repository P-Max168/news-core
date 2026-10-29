# S0 코어 갱신 보고 (2026-10-29 · Claude)

설계서: 드라이브 00_INBOX `news-core_변경설계서_20261029 (클로드).md` 5장 S0.
브랜치 `claude/s0-core-refresh`. **main 병합·사이트 반영 없음**(맥스 승인 전).

## 한 것
- 그록 로컬 패치 `1b636f1` 적용(edition_watch gap marker·legal_pages 개인정보 문구) → 라이브와 md5 동일 확인.
- 뒤처진 파일 갱신: `edition_claim.py`(KR, release 추가) · `pending.py`(ZH 가드판, 주석 일반화).
- 코어에 없던 공통 파일 추가: code_picks · comment_replies · gemini_edition · gemini_spend(KR) · newslib(ZH, <1元 소수) · preflight.sh · seo · share_kit · site_build · siteconf · video_picks(KR=VN) · `tools/dev/` 23개.
- `edition_stale.py`는 코어에서 **제거**(10/26 판이 세 사이트보다 뒤처졌고, 사이트별 값이 코드에 박혀 있어 S2 설정화 뒤 다시 추가). `deploy.sh`·`gpt_lane_check.py`도 같은 이유로 S2.

## 검증 (sync.py dry-run, 2026-10-29 16:40 BKK, 기준 KR aff53a0 / ZH ae4f73c / VN aa6e4f5)
| 사이트 | 바뀔 파일 | HTML diff | py_compile / site_build / test_pwa |
|---|---|---|---|
| vn | edition_claim, gemini_spend, newslib, pending | 0 | ok / ok / ok |
| zh | pending(주석만), video_picks(새 파일, 설정으로 꺼짐) | 0 | ok / ok / ok |
| kr | newslib(CNY 함수만), pending | 0 | ok / ok / ok |

바뀔 파일 목록이 설계서 4장 ④ 표와 정확히 일치. `checks_pass=false`는 2단계 게이트가 "파일 diff 0"을 요구해서이며, S0은 코어를 사이트보다 앞서게 두는 단계라 의도된 결과.

## 다음
S1 원장(D1) · S2 실행기(run_edition.py)+설정화 — 설계서 5장.
