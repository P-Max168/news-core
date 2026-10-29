# 채널 전환(S4~S6) 적용물 — 설계서 5장

각 채널 전환 PR 에 들어갈 것:
1. `.core-version` = news-core 태그
2. `site/<lang>.json` 에 `"edition": {...}` 키 추가 — 이 폴더의 `<lang>.edition.json` 내용 그대로(운영: deploy=pages|cloudflare)
3. `.github/workflows/`: 옛 `gemini-edition.yml`(KR·ZH) / `publish.yml`·`hub-deploy.yml`(VN) 삭제 → 템플릿 `edition.yml`·`edition-watch.yml`·`core-pull.yml`(cron 은 옛 값 그대로)
4. 공통 파일(core.json 목록) 복사 = `sync.py --pull`
5. VN 만: `pipeline/vn_picks.py`·`pipeline/build_dist.py` 추가(사이트 전용), `pipeline/run_vn.py` 는 삭제(기능은 run_edition + 위 둘로 이동), `vn/hub/` 삭제(news-hub 저장소로 이전)
6. 원장: 저장소 변수 `GEMINI_SPEND_BACKEND=d1` 는 **news-hub 배포 뒤** 켬. 그 전까지는 옛 hub(git 원장) 그대로 동작
7. 전환 창(판 사이 2~3시간): PR 병합 → `Run workflow`(dry) 1회 → 다음 판은 예약대로

되돌리기: `.core-version` 이전 값 + core-pull, 또는 PR revert 1회. 원장은 변수 삭제로 즉시 옛 방식.
