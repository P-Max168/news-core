# status.json 스키마 (news-core/status@1)
모음 페이지(news.pmaxone.com)는 이 파일만 읽으면 됩니다. 시각은 모두 방콕(+07:00).
- schema: "news-core/status@1"
- generated_bkk: 생성 시각
- overall: ok | warn | alert (아래 level 중 가장 나쁜 값)
- sites[]: { site: vn|zh|kr, repo, last_edition: "YYYY-MM-DD-am|md|pm", runs[]: {workflow,status,conclusion,at_bkk} (최근 5개),
  claims[]: "판/담당" (남은 claim 브랜치), gemini_thb_today, gemini_thb_month, problems[]: 한국어 문장, level }
- gemini_cost: { month_thb (세 사이트 합, 추정), alert_thb: 500, limit_thb: 800, basis, level (≥500 warn, ≥800 alert) }
- pat: { status: ok|expiring|expired|invalid_or_expired|not_configured|no_expiry, expires_bkk, days_left, level (14일 이하 warn, 만료 alert) }
샘플: status.sample.json (2026-10-26 실데이터)
