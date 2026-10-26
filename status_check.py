#!/usr/bin/env python3
"""세 사이트 통합 상태 → status.json (읽기 전용, gh api 조회만). news.pmaxone.com 모음 페이지가 읽을 데이터.
사용: python3 status_check.py [-o status.json]
PAT 만료: 환경변수 CORE_SYNC_TOKEN 이 있으면 GitHub 응답 헤더(github-authentication-token-expiration)로 읽음. 값은 출력하지 않음.
비용: ops/gemini-usage.jsonl 토큰 × core.json 단가(추정). 단가는 맥스님/Claude가 실제 청구서로 맞출 것.
"""
import base64, datetime as dt, json, os, re, subprocess, sys, urllib.request
BKK = dt.timezone(dt.timedelta(hours=7)); NOW = dt.datetime.now(BKK)
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "core.json")))
P = M.get("pricing", {"usd_per_1m_input": 0.30, "usd_per_1m_output": 2.50, "thb_per_usd": 33.0, "basis": "추정"})
def gh(path):
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(p.stdout) if p.returncode == 0 else None
def content(repo, path):
    j = gh(f"repos/{repo}/contents/{path}"); return base64.b64decode(j["content"]).decode() if j and "content" in j else None
def thb(u): return (u.get("prompt", 0) * P["usd_per_1m_input"] + (u.get("output", 0) + u.get("thinking", 0)) * P["usd_per_1m_output"]) / 1e6 * P["thb_per_usd"]

def site(key, repo):
    s = {"site": key, "repo": repo, "problems": []}
    files = gh(f"repos/{repo}/contents/data") or []
    eds = sorted(f["name"][:-5] for f in files if re.match(r"\d{4}-\d\d-\d\d-[a-z]+\.json$", f["name"]))
    s["last_edition"] = eds[-1] if eds else None
    runs = (gh(f"repos/{repo}/actions/runs?per_page=10") or {}).get("workflow_runs", [])
    s["runs"] = [{"workflow": r["name"], "status": r["status"], "conclusion": r["conclusion"],
                  "at_bkk": dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone(BKK).isoformat(timespec="minutes")} for r in runs[:5]]
    if any(r["conclusion"] == "failure" for r in s["runs"][:3]): s["problems"].append("최근 실행 실패")
    refs = gh(f"repos/{repo}/git/matching-refs/heads/claim/") or []
    s["claims"] = [r["ref"].replace("refs/heads/claim/", "") for r in refs]
    if s["claims"]: s["problems"].append(f"남은 claim {len(s['claims'])}개")
    u = content(repo, "ops/gemini-usage.jsonl") or ""
    rows = [json.loads(l) for l in u.splitlines() if l.strip().startswith("{")]
    mon = NOW.strftime("%Y-%m"); today = NOW.strftime("%Y-%m-%d")
    s["gemini_thb_month"] = round(sum(thb(r) for r in rows if str(r.get("at", "")).startswith(mon)), 2)
    s["gemini_thb_today"] = round(sum(thb(r) for r in rows if str(r.get("at", "")).startswith(today)), 2)
    # 판 누락: 아침 09:00·저녁 20:00 이후 그날 판 없으면 경고
    exp = []
    if NOW.hour >= 9: exp.append(today + "-am")
    if NOW.hour >= 20: exp.append(today + "-pm")
    miss = [e for e in exp if e not in eds and not (e.endswith("-am") and today + "-md" in eds)]
    if miss: s["problems"].append(f"판 없음 {miss}")
    s["level"] = "ok" if not s["problems"] else "warn"
    return s

def pat():
    tok = os.environ.get("CORE_SYNC_TOKEN")
    if not tok: return {"status": "not_configured", "expires_bkk": None, "days_left": None, "level": "warn", "note": "CORE_SYNC_TOKEN 없음 — 동기화 불가"}
    req = urllib.request.Request("https://api.github.com/rate_limit", headers={"Authorization": "Bearer " + tok})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: h = r.headers.get("github-authentication-token-expiration")
    except Exception as e: return {"status": "invalid_or_expired", "level": "alert", "note": type(e).__name__}
    if not h: return {"status": "no_expiry", "level": "ok"}
    exp = dt.datetime.strptime(h.replace(" UTC", " +0000"), "%Y-%m-%d %H:%M:%S %z").astimezone(BKK); d = (exp - NOW).days
    return {"status": "ok" if d > 14 else ("expiring" if d >= 0 else "expired"), "expires_bkk": exp.isoformat(timespec="minutes"), "days_left": d,
            "level": "ok" if d > 14 else ("warn" if d >= 0 else "alert")}

def main():
    out = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else "status.json"
    sites = [site(k, M["sites"][k]["repo"]) for k in M["rollout_order"]]
    tm = round(sum(s["gemini_thb_month"] for s in sites), 2)
    cost = {"month_thb": tm, "alert_thb": 500, "limit_thb": 800, "basis": P["basis"],
            "level": "alert" if tm >= 800 else ("warn" if tm >= 500 else "ok")}
    p = pat(); lv = [s["level"] for s in sites] + [cost["level"], p["level"]]
    st = {"schema": "news-core/status@1", "generated_bkk": NOW.isoformat(timespec="minutes"),
          "overall": "alert" if "alert" in lv else ("warn" if "warn" in lv else "ok"), "sites": sites, "gemini_cost": cost, "pat": p}
    json.dump(st, open(out, "w"), ensure_ascii=False, indent=1); print(out, st["overall"])
if __name__ == "__main__": main()
