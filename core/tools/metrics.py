# -*- coding: utf-8 -*-
"""판마다 측정 한 줄(2026-10-23, ops/SYSTEM_PLAN.md 6절 1단계 5번) → ops/metrics.jsonl
그록 토큰 수는 볼 수 없어서, 대신 '그록에게 준 자료 양·만든 결과·시각'을 남겨 방식 변경 전후를 비교한다.
  python3 tools/metrics.py <판 id>      (deploy.sh 가 배포 커밋 전에 부름. 실패해도 배포는 계속)
남기는 것: 판 id, 담당(TNK_PUBLISHER), 후보 수·후보 글자 수(drafts/candidates/latest.*), 기사 수, 판 generated, 기록 시각,
          담당 표시(claim) 목록, 검사 재작업은 판 파일 편집 횟수 대신 같은 판 id 의 기록 줄 수로 본다(배포 반복 = 재작업).
"""
import json, os, pathlib, subprocess, sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
BKK = timezone(timedelta(hours=7))


def main(ed):
    d = json.loads((ROOT / "data" / (ed + ".json")).read_text(encoding="utf-8"))
    cand_json = ROOT / "drafts" / "candidates" / "latest.json"
    cand_md = ROOT / "drafts" / "candidates" / "latest.md"
    cand = None
    if cand_json.exists():
        try:
            cand = json.loads(cand_json.read_text(encoding="utf-8")).get("candidates")
        except ValueError:
            pass
    claims = ""
    try:
        claims = subprocess.run([sys.executable, str(ROOT / "tools" / "edition_claim.py"), "status", ed],
                                capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        pass
    row = dict(edition=ed, publisher=os.environ.get("TNK_PUBLISHER", "grok"),
               candidates=cand, candidate_chars=cand_md.stat().st_size if cand_md.exists() else None,
               stories=len(d.get("stories", [])), generated=d.get("generated"),
               recorded=datetime.now(BKK).isoformat(timespec="seconds"), claims=claims)
    out = ROOT / "ops" / "metrics.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("metrics:", row)


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except Exception as e:
        print("metrics 기록 실패(배포는 계속):", e, file=sys.stderr)
