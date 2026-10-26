# 3단계 준비 — PAT(CORE_SYNC_TOKEN) 설정 체크리스트 (값은 어디에도 적지 않음)
github.com → Settings → Developer settings → Fine-grained tokens → Generate new token
- Token name: news-core-sync
- Resource owner: P-Max168
- Expiration: 90 days (만료 14일 전부터 status 경고)
- Repository access: Only select → news-core, thai-news-kr, thai-news-zh, vn-news-kr (kstar-th 제외: 별도 관리)
- Permissions (Repository):
  - Contents: Read and write
  - Pull requests: Read and write
  - Workflows: Read and write
  - Actions: Read-only
  - Variables: Read-only
  - Metadata: Read-only (자동)
- 생성 후: news-core → Settings → Secrets and variables → Actions → New repository secret
  - Name: CORE_SYNC_TOKEN / Value: 방금 토큰 (채팅·파일에 붙여넣지 말 것)
## 3단계 전 확인됨 (2026-10-26)
- vn dry-run: files_changed 0, html_diff 0, checks_pass true (test_pwa 기존 실패 1건 known_fail)
- 미반영: .github/sync.yml, status.yml (gh에 workflow 권한 없음 → 푸시 거부)
