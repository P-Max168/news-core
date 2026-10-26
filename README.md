# news-core — 뉴스 3사이트 공통 코드 원본
대상: vn(vn-news-kr) → zh(thai-news-zh) → kr(thai-news-kr) 순서로 반영.
- `core/tools/`: 세 사이트에서 글자까지 같은 공통 파일(2026-10-26 기준 29개, md5 확인). **수정은 Claude만**(GPT는 인수인계 후).
- `core.json`: 파일 목록·복사 위치·사이트·순서·보호 영역(비용·권한/토큰·robots/sitemap·개인정보 → 자동 합치기 안 함).
- `sync.py`: 사이트 하나에 복사 → py_compile·preflight 문법·site_build 건조 실행·test_pwa(전후 비교)·HTML 전후 diff. 기본 DRY-RUN.
  `--apply`는 `CORE_STAGE_LOCK=unlocked`일 때만 PR 생성(3단계 이후).
- `status_check.py` → `status.json`(스키마: STATUS_SCHEMA.md). 모음 페이지용 데이터. 읽기 전용.
- 사이트별 끄기: 사이트 저장소에 `.core-skip` 파일 또는 Actions 변수 `CORE_SYNC=off`.
- 비상: news-core를 지워도 각 사이트는 그대로 동작(파일이 복사돼 있으므로).
현재: 2단계(시험) 완료. 사이트 저장소에는 아무것도 반영하지 않음. 동기화·감시 담당: Grok.
