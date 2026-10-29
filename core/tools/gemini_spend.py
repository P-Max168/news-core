# -*- coding: utf-8 -*-
"""제미나이 일일 비용 상한(코드 측 하드캡, 예약-후-호출). 2026-10-28 Max: 하루 200바트.
2026-10-29 Max: 절대 오버 금지 → 호출 전 허브에 예상비용을 원자적으로 예약(CAS).

Google Cloud 예산은 알림만 보내고 끊지 않으므로, 호출 전에 이 모듈이 막는다.
집계 허브: P-Max168/thai-news-kr 의 ops/gemini-spend.json (프로젝트 공용 키 기준).
모든 유료 호출은 허브에 예약한 뒤에만 한다. 허브 읽기/쓰기 실패 = 상한 도달로 간주(유료 호출 금지).

가격(확인됨, Standard Paid, USD / 1M 토큰):
  출처: https://ai.google.dev/gemini-api/docs/pricing  (페이지 Last updated 2026-10-27 UTC, 읽은 날 2026-10-28 BKK)
  gemini-3.5-flash-lite: input 0.30, output 2.50 (thinking 포함 output)
  gemini-3.8-flash:      input 0.75, output 3.75  (2026-12-31까지 프로모 가; 이후 1.50/7.50)
환율: USD_THB=34.0 고정(보수적). 근거: Yahoo USDTHB 2026-10-28 ≈33.81, Exa ≈33.83.
  바트가 비싸게(비용을 크게) 잡히면 상한이 더 일찍 걸려 안전하다.

예상비용: 요청 모델과 폴백(3.8) 중 높은 단가 × 안전배수(기본 1.5) × 가정 출력토큰.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import threading
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

BKK = timezone(timedelta(hours=7))

# --- 설정(환경 변수로 덮어쓰기 가능) ---
DAILY_CAP_THB = float(os.environ.get("GEMINI_DAILY_CAP_THB", "200"))
CAP_FROM_ENV = "GEMINI_DAILY_CAP_THB" in os.environ   # 2026-10-29: 환경변수로 준 상한이 원장에 저장된 cap 보다 우선(시험 저장소 30바트)
USD_THB = float(os.environ.get("GEMINI_USD_THB", "34.0"))
HUB_REPO = os.environ.get("GEMINI_SPEND_HUB_REPO", "P-Max168/thai-news-kr")
HUB_PATH = os.environ.get("GEMINI_SPEND_HUB_PATH", "ops/gemini-spend.json")
PEER_REPOS = [
    "P-Max168/thai-news-kr",
    "P-Max168/thai-news-zh",
    "P-Max168/vn-news-kr",
]
PRICING_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
PRICING_READ = "2026-10-28"
PRICES_USD_PER_1M = {
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
}
# 다음 호출 예상 출력(토큰). 실제보다 크게 잡아 상한을 일찍 건다.
ASSUMED_OUTPUT_TOKENS = int(os.environ.get("GEMINI_ASSUMED_OUT_TOKENS", "10000"))
# 예상 단가 안전배수(과다 추정 → 상한 조기 차단)
SAFETY_MARGIN = float(os.environ.get("GEMINI_SPEND_MARGIN", "1.5"))
# 예상 단가에 쓸 폴백(더 비싼 쪽) 모델
ESTIMATE_FLOOR_MODEL = os.environ.get("GEMINI_ESTIMATE_FLOOR_MODEL", "gemini-3.8-flash")
# prompt 문자→토큰 대략치(바이트/4). 공식 countTokens 없이 사전 검사용.
CHARS_PER_TOKEN = 4
# 예약 TTL(초). 만료 시 예상비용을 확정 지출로 올려 과소계상을 막음.
RESERVATION_TTL_S = int(os.environ.get("GEMINI_RESERVATION_TTL_S", "2700"))
# hub = GitHub Contents API(옛 방식, 원장이 git 파일) / d1 = news.pmaxone.com D1 원장(2026-10-29 S1, GitHub OIDC 인증, 토큰 없음) / local = 파일 CAS(시험용)
SPEND_BACKEND = (os.environ.get("GEMINI_SPEND_BACKEND") or "hub").strip().lower()
D1_HUB_URL = os.environ.get("GEMINI_SPEND_D1_URL", "https://news.pmaxone.com").rstrip("/")
LOCAL_LEDGER_PATH = os.environ.get("GEMINI_SPEND_LOCAL_PATH", "")

# 이번 프로세스에서 아직 허브에 안 올라간 추가분(감사용)
_SESSION_ENTRIES = []
_SESSION_SPENT_THB = 0.0
_OPEN_RESERVATIONS = {}  # rsv_id -> meta
_LOCK = threading.Lock()


class SpendCapExceeded(Exception):
    """하루 상한을 넘기면 유료 호출을 하지 않는다."""

    def __init__(self, spent_thb, est_thb, cap_thb, day, reserved_thb=0.0):
        self.spent_thb = spent_thb
        self.est_thb = est_thb
        self.cap_thb = cap_thb
        self.day = day
        self.reserved_thb = reserved_thb
        super().__init__(
            "daily_spend_cap: spent=%.4f reserved=%.4f est_next=%.4f cap=%.2f THB day=%s"
            % (spent_thb, reserved_thb, est_thb, cap_thb, day)
        )


class LedgerUnavailable(Exception):
    """허브 원장을 읽거나 쓰지 못하면 상한 도달로 간주(유료 호출 금지)."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__("ledger_unavailable: %s" % reason)


def today_bkk(now=None):
    return (now or datetime.now(BKK)).strftime("%Y-%m-%d")


def _norm_model(model):
    m = (model or "").strip()
    if m in PRICES_USD_PER_1M:
        return m
    for k in PRICES_USD_PER_1M:
        if k in m or m in k:
            return k
    return m


def cost_usd(model, prompt_tokens, output_tokens, thinking_tokens=0):
    """thinking 은 공식상 output 에 포함 과금 → output+thinking 합산."""
    p = PRICES_USD_PER_1M.get(_norm_model(model))
    if not p:
        p = PRICES_USD_PER_1M["gemini-3.8-flash"]
    inp = max(0, int(prompt_tokens or 0))
    out = max(0, int(output_tokens or 0)) + max(0, int(thinking_tokens or 0))
    return (inp / 1_000_000.0) * p["input"] + (out / 1_000_000.0) * p["output"]


def cost_thb(model, prompt_tokens, output_tokens, thinking_tokens=0, usd_thb=None):
    rate = USD_THB if usd_thb is None else float(usd_thb)
    return cost_usd(model, prompt_tokens, output_tokens, thinking_tokens) * rate


def estimate_prompt_tokens(prompt_text):
    if not prompt_text:
        return 0
    return max(1, len(prompt_text.encode("utf-8")) // CHARS_PER_TOKEN)


def _estimate_price_model(model):
    """요청 모델과 폴백 중 더 비싼 단가의 모델 키를 고른다(입력+출력 합산 기준)."""
    a = _norm_model(model)
    b = _norm_model(ESTIMATE_FLOOR_MODEL)
    pa = PRICES_USD_PER_1M.get(a) or PRICES_USD_PER_1M["gemini-3.8-flash"]
    pb = PRICES_USD_PER_1M.get(b) or PRICES_USD_PER_1M["gemini-3.8-flash"]
    if (pb["input"] + pb["output"]) >= (pa["input"] + pa["output"]):
        return b if b in PRICES_USD_PER_1M else "gemini-3.8-flash"
    return a if a in PRICES_USD_PER_1M else "gemini-3.8-flash"


def estimate_next_thb(model, prompt_text, assumed_output=None, margin=None):
    """보수적 예상: 비싼 단가 × 가정 출력 × 안전배수."""
    pt = estimate_prompt_tokens(prompt_text)
    ot = ASSUMED_OUTPUT_TOKENS if assumed_output is None else int(assumed_output)
    m = SAFETY_MARGIN if margin is None else float(margin)
    priced = _estimate_price_model(model)
    return cost_thb(priced, pt, ot, 0) * m


def empty_tally(day=None):
    return {
        "day": day or today_bkk(),
        "tz": "Asia/Bangkok",
        "cap_thb": DAILY_CAP_THB,
        "usd_thb": USD_THB,
        "pricing_source": PRICING_SOURCE,
        "pricing_read": PRICING_READ,
        "prices_usd_per_1m": dict(PRICES_USD_PER_1M),
        "spent_thb": 0.0,
        "spent_usd": 0.0,
        "reserved_thb": 0.0,
        "entries": [],
        "reservations": [],
    }


def _parse_at(at):
    if not at:
        return None
    try:
        s = str(at).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _expire_stale(tally, now=None):
    """TTL 지난 예약을 확정 지출로 올려 과소계상을 막는다."""
    now = now or datetime.now(BKK)
    day = tally.get("day") or today_bkk(now)
    entries = list(tally.get("entries") or [])
    kept = []
    for r in tally.get("reservations") or []:
        if (r.get("day") or day) != day:
            continue
        if (r.get("status") or "open") != "open":
            continue
        at = _parse_at(r.get("at"))
        age = (now - at).total_seconds() if at else RESERVATION_TTL_S + 1
        if age > RESERVATION_TTL_S:
            est = float(r.get("est_thb") or 0)
            entries.append({
                "id": "stale:%s" % (r.get("id") or uuid.uuid4().hex[:12]),
                "at": now.isoformat(timespec="seconds"),
                "day": day,
                "repo": r.get("repo") or "unknown",
                "edition": r.get("edition"),
                "model": r.get("model") or ESTIMATE_FLOOR_MODEL,
                "prompt": 0,
                "output": 0,
                "thinking": 0,
                "cost_usd": round(est / USD_THB, 8) if USD_THB else 0.0,
                "cost_thb": round(est, 6),
                "source": "stale_reservation",
                "reservation_id": r.get("id"),
            })
        else:
            kept.append(r)
    out = dict(tally)
    out["entries"] = entries
    out["reservations"] = kept
    return _recompute(out)


def _recompute(tally):
    day = tally.get("day") or today_bkk()
    entries = [e for e in (tally.get("entries") or []) if (e.get("day") or day) == day]
    by_id = {}
    for e in entries:
        eid = e.get("id") or "%s|%s|%s|%s" % (e.get("repo"), e.get("edition"), e.get("at"), e.get("call_i"))
        e = dict(e, id=eid, day=day)
        by_id[eid] = e
    merged = sorted(by_id.values(), key=lambda x: x.get("at") or "")
    spent_thb = round(sum(float(e.get("cost_thb") or 0) for e in merged), 6)
    spent_usd = round(sum(float(e.get("cost_usd") or 0) for e in merged), 8)
    reservations = [
        r for r in (tally.get("reservations") or [])
        if (r.get("day") or day) == day and (r.get("status") or "open") == "open"
    ]
    reserved_thb = round(sum(float(r.get("est_thb") or 0) for r in reservations), 6)
    out = dict(tally)
    out.update(
        day=day,
        tz="Asia/Bangkok",
        cap_thb=(DAILY_CAP_THB if CAP_FROM_ENV else float(tally.get("cap_thb") or DAILY_CAP_THB)),
        usd_thb=float(tally.get("usd_thb") or USD_THB),
        pricing_source=tally.get("pricing_source") or PRICING_SOURCE,
        pricing_read=tally.get("pricing_read") or PRICING_READ,
        prices_usd_per_1m=tally.get("prices_usd_per_1m") or dict(PRICES_USD_PER_1M),
        spent_thb=spent_thb,
        spent_usd=spent_usd,
        reserved_thb=reserved_thb,
        entries=merged,
        reservations=reservations,
    )
    return out


def merge_tallies(*tallies, day=None):
    day = day or today_bkk()
    base = empty_tally(day)
    entries = []
    reservations = []
    for t in tallies:
        if not t:
            continue
        if (t.get("day") or day) != day:
            continue
        entries.extend(t.get("entries") or [])
        reservations.extend(t.get("reservations") or [])
    base["entries"] = entries
    base["reservations"] = reservations
    return _recompute(base)


def local_path(root):
    # Actions: hub CAS is authoritative. Never write ops/gemini-spend.json into the
    # git worktree (that mirror caused rebase conflicts on deploy/fail push).
    if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("GEMINI_SPEND_LOCAL_TMP") == "1":
        base = pathlib.Path(os.environ.get("TMPDIR") or "/tmp")
        repo = (this_repo() or "local").replace("/", "_")
        return base / ("gemini-spend-%s.json" % repo)
    return pathlib.Path(root) / "ops" / "gemini-spend.json"


def load_local(root, day=None):
    day = day or today_bkk()
    p = local_path(root)
    if not p.exists():
        return empty_tally(day)
    try:
        t = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return empty_tally(day)
    if (t.get("day") or "") != day:
        return empty_tally(day)
    return _recompute(t)


def save_local(root, tally):
    p = local_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _recompute(tally)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return data


def _github_headers(token=None):
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gemini-spend-cap/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = "Bearer %s" % token
    return h


def _http_json(url, method="GET", data=None, token=None, timeout=30):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=_github_headers(token))
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            j = json.loads(raw) if raw else {}
        except Exception:
            j = {"message": raw[:300]}
        return e.code, j
    except Exception as ex:
        return 0, {"message": "%s:%s" % (type(ex).__name__, ex)}


def hub_token():
    """허브 쓰기용. SPEND_HUB_TOKEN(교차 저장소 PAT) 우선, 없으면 같은 저장소 GITHUB_TOKEN."""
    return (os.environ.get("SPEND_HUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()


def this_repo():
    return os.environ.get("GITHUB_REPOSITORY") or ""


def can_write_hub():
    """허브에 CAS 쓸 수 있는지. 교차 저장소는 SPEND_HUB_TOKEN 필수. d1 은 Actions OIDC 만 있으면 됨(토큰 없음)."""
    if SPEND_BACKEND == "local":
        return True
    if SPEND_BACKEND == "d1":
        return bool(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"))
    if os.environ.get("SPEND_HUB_TOKEN", "").strip():
        return True
    if this_repo() == HUB_REPO and os.environ.get("GITHUB_TOKEN", "").strip():
        return True
    return False


def fetch_repo_spend(repo, path=HUB_PATH, token=None, day=None, required=False):
    """GitHub Contents API로 ops/gemini-spend.json 읽기.
    required=True 이고 실패하면 LedgerUnavailable.
    파일이 없으면(404) 빈 원장. 그 외 실패는 None(또는 raise)."""
    day = day or today_bkk()
    url = "https://api.github.com/repos/%s/contents/%s" % (repo, path)
    code, j = _http_json(url + "?ref=main", token=token)
    if code == 404:
        t = empty_tally(day)
        t["_sha"] = None
        return t
    if code != 200 or not j.get("content"):
        if required:
            raise LedgerUnavailable("hub_get_http_%s:%s" % (code, (j.get("message") or "")[:120]))
        return None
    try:
        text = base64.b64decode(j["content"]).decode("utf-8")
        t = json.loads(text)
    except Exception as ex:
        if required:
            raise LedgerUnavailable("hub_decode:%s" % type(ex).__name__)
        return None
    if (t.get("day") or "") != day:
        t = empty_tally(day)
    else:
        t = _recompute(t)
    t["_sha"] = j.get("sha")
    return t


def spent_from_usage_jsonl(path, day=None, repo="local", usd_thb=None):
    """구형 ops/gemini-usage.jsonl 에서 오늘분 비용을 재구성(허브 없을 때 바닥값)."""
    day = day or today_bkk()
    p = pathlib.Path(path)
    if not p.exists():
        return empty_tally(day)
    entries = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return empty_tally(day)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        at = str(rec.get("at") or "")
        if not at.startswith(day):
            continue
        prompt = int(rec.get("prompt") or 0)
        output = int(rec.get("output") or 0)
        thinking = int(rec.get("thinking") or 0)
        if not rec.get("edition"):
            continue
        if not str(rec.get("edition")).startswith(day):
            continue
        if "published" not in rec and "after_check" not in rec:
            continue
        model = rec.get("model") or "gemini-3.5-flash-lite"
        cu = cost_usd(model, prompt, output, thinking)
        ct = cu * (USD_THB if usd_thb is None else float(usd_thb))
        entries.append({
            "id": "usage:%s:%s" % (repo, rec.get("edition")),
            "at": at,
            "day": day,
            "repo": repo,
            "edition": rec.get("edition"),
            "model": model,
            "prompt": prompt,
            "output": output,
            "thinking": thinking,
            "cost_usd": round(cu, 8),
            "cost_thb": round(ct, 6),
            "source": "usage_jsonl",
            "_total": prompt + output + thinking,
        })
    best = {}
    for e in entries:
        k = e["id"]
        prev = best.get(k)
        if prev is None or e.get("_total", 0) >= prev.get("_total", 0):
            best[k] = e
    entries = []
    for e in best.values():
        e = dict(e)
        e.pop("_total", None)
        entries.append(e)
    return _recompute(dict(empty_tally(day), entries=entries))


def _local_ledger_file():
    if LOCAL_LEDGER_PATH:
        return pathlib.Path(LOCAL_LEDGER_PATH)
    return pathlib.Path(os.environ.get("TMPDIR") or "/tmp") / "gemini-spend-local.json"


def _local_cas(mutator, day=None, max_tries=20):
    """파일 잠금 CAS(시험·로컬). mutator(tally)->tally 또는 SpendCapExceeded."""
    import fcntl
    path = _local_ledger_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    day = day or today_bkk()
    for attempt in range(max_tries):
        with path.open("a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read()
            if raw.strip():
                try:
                    cur = json.loads(raw)
                except Exception:
                    cur = empty_tally(day)
            else:
                cur = empty_tally(day)
            if (cur.get("day") or "") != day:
                cur = empty_tally(day)
            cur = _expire_stale(_recompute(cur))
            new = mutator(cur)
            new = _recompute(new)
            f.seek(0)
            f.truncate()
            f.write(json.dumps(new, ensure_ascii=False, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
            return new
    raise LedgerUnavailable("local_cas_exhausted")


def push_hub(tally, token=None, max_tries=8, sha=None):
    """Contents API로 허브 파일 갱신. 충돌 시 호출자가 다시 읽어 합쳐야 함.
    성공 시 (True, sha), 실패 시 (False, reason)."""
    token = (token if token is not None else hub_token()).strip()
    if not token:
        return False, "no_token"
    day = tally.get("day") or today_bkk()
    url = "https://api.github.com/repos/%s/contents/%s" % (HUB_REPO, HUB_PATH)
    data = _recompute(tally)
    payload = {
        "message": "ops: gemini-spend %s spent=%.4f reserved=%.4f THB" % (
            day, data["spent_thb"], data.get("reserved_thb") or 0),
        "content": base64.b64encode(
            (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        ).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    pcode, pres = _http_json(url, method="PUT", data=payload, token=token)
    if pcode in (200, 201):
        return True, (pres.get("content") or {}).get("sha") or "ok"
    return False, "put_http_%s:%s" % (pcode, (pres.get("message") or "")[:160])


def _hub_cas(mutator, token=None, day=None, max_tries=10):
    """허브 CAS: 읽고 → 만료 처리 → mutator → sha로 쓰기. 충돌 시 재시도.
    mutator 가 SpendCapExceeded 를 올리면 그대로 전달.
    실패 시 LedgerUnavailable."""
    token = (token if token is not None else hub_token()).strip()
    if not token:
        raise LedgerUnavailable("no_token")
    day = day or today_bkk()
    url = "https://api.github.com/repos/%s/contents/%s" % (HUB_REPO, HUB_PATH)
    last_reason = ""
    for attempt in range(max_tries):
        code, cur = _http_json(url + "?ref=main", token=token)
        sha = None
        remote = empty_tally(day)
        if code == 200 and cur.get("sha"):
            sha = cur["sha"]
            try:
                remote = json.loads(base64.b64decode(cur["content"]).decode("utf-8"))
                if (remote.get("day") or "") != day:
                    remote = empty_tally(day)
                else:
                    remote = _recompute(remote)
            except Exception as ex:
                last_reason = "decode:%s" % type(ex).__name__
                time.sleep(0.3 + 0.2 * attempt)
                continue
        elif code == 404:
            sha = None
            remote = empty_tally(day)
        else:
            last_reason = "get_http_%s:%s" % (code, (cur.get("message") or "")[:120])
            time.sleep(0.5 + 0.3 * attempt)
            continue
        remote = _expire_stale(remote)
        try:
            new = mutator(remote)
        except SpendCapExceeded:
            raise
        new = _recompute(new)
        ok, msg = push_hub(new, token=token, sha=sha)
        if ok:
            return new
        last_reason = msg
        if "409" in str(msg) or "422" in str(msg):
            time.sleep(0.2 + 0.15 * attempt)
            continue
        time.sleep(0.5 + 0.3 * attempt)
    raise LedgerUnavailable("hub_cas_exhausted:%s" % last_reason)


# ---------- d1 백엔드(S1): news.pmaxone.com /api/spend/tally — 같은 tally JSON 을 (day, env) 마다 하나, ver 로 CAS ----------
_OIDC_CACHE = {}


def oidc_token(audience="news-hub"):
    """GitHub Actions OIDC 토큰(id-token: write). 비밀값 아님·저장 안 함. Actions 밖이면 빈 문자열."""
    url, req = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not (url and req):
        return ""
    if _OIDC_CACHE.get("t") and time.time() - _OIDC_CACHE.get("at", 0) < 240:
        return _OIDC_CACHE["t"]
    try:
        r = urllib.request.Request(url + "&audience=" + audience, headers={"Authorization": "bearer " + req})
        with urllib.request.urlopen(r, timeout=20) as f:
            tok = json.load(f).get("value") or ""
        _OIDC_CACHE.update(t=tok, at=time.time())
        return tok
    except Exception:
        return ""


def _d1_http(path, method="GET", data=None, tok=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(D1_HUB_URL + path, data=body, method=method,
                                 headers={"Authorization": "Bearer " + (tok or ""), "Content-Type": "application/json", "User-Agent": "gemini_spend/d1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            return f.getcode(), json.load(f)
    except urllib.error.HTTPError as ex:
        try:
            return ex.code, json.load(ex)
        except Exception:
            return ex.code, {"error": str(ex)[:120]}
    except Exception as ex:
        return 0, {"error": "%s:%s" % (type(ex).__name__, str(ex)[:120])}


def _d1_cas(mutator, day=None, max_tries=10):
    tok = oidc_token()
    if not tok:
        raise LedgerUnavailable("no_oidc_token(d1 원장은 Actions 안에서만 씀)")
    day = day or today_bkk()
    last = ""
    for attempt in range(max_tries):
        code, cur = _d1_http("/api/spend/tally?day=" + day, tok=tok)
        if code != 200:
            last = "get_%s:%s" % (code, str(cur.get("error") or "")[:120]); time.sleep(0.5 + 0.3 * attempt); continue
        ver = int(cur.get("ver") or 0)
        remote = cur.get("body") or empty_tally(day)
        if (remote.get("day") or "") != day:
            remote = empty_tally(day)
        remote = _expire_stale(_recompute(remote))
        try:
            new = mutator(remote)
        except SpendCapExceeded:
            raise
        new = _recompute(new)
        code, res = _d1_http("/api/spend/tally", method="PUT", data={"day": day, "ver": ver, "body": new}, tok=tok)
        if code == 200 and res.get("ok"):
            return new
        last = "put_%s:%s" % (code, str(res.get("error") or "")[:120])
        if code == 409:
            time.sleep(0.2 + 0.15 * attempt); continue
        time.sleep(0.5 + 0.3 * attempt)
    raise LedgerUnavailable("d1_cas_exhausted:%s" % last)


def _d1_fetch(day):
    tok = oidc_token()
    if not tok:
        raise LedgerUnavailable("no_oidc_token")
    code, cur = _d1_http("/api/spend/tally?day=" + day, tok=tok)
    if code != 200:
        raise LedgerUnavailable("d1_get_%s" % code)
    t = cur.get("body") or empty_tally(day)
    return _expire_stale(_recompute(t if (t.get("day") or "") == day else empty_tally(day)))


def cas_update(mutator, day=None, token=None):
    """백엔드에 따라 local / d1 / hub CAS."""
    if SPEND_BACKEND == "local":
        return _local_cas(mutator, day=day)
    if SPEND_BACKEND == "d1":
        return _d1_cas(mutator, day=day)
    if not can_write_hub():
        raise LedgerUnavailable("cannot_write_hub:need_SPEND_HUB_TOKEN_or_hub_repo_GITHUB_TOKEN")
    return _hub_cas(mutator, token=token, day=day)


def load_shared(root, day=None, token=None, require_hub=True):
    """허브(+로컬 보조) 집계. require_hub 이면 허브 실패 시 LedgerUnavailable.
    예약 기반이므로 동료 저장소 실패는 더 이상 무시해도 안전하지 않음 →
    허브가 단일 진실. 로컬은 보조 표시용."""
    day = day or today_bkk()
    token = token if token is not None else hub_token()
    if SPEND_BACKEND == "d1":
        try:
            return _d1_fetch(day)
        except LedgerUnavailable:
            if require_hub:
                raise
            return empty_tally(day)
    if SPEND_BACKEND == "local":
        path = _local_ledger_file()
        if path.exists():
            try:
                t = json.loads(path.read_text(encoding="utf-8"))
                if (t.get("day") or "") != day:
                    return empty_tally(day)
                return _expire_stale(_recompute(t))
            except Exception as ex:
                if require_hub:
                    raise LedgerUnavailable("local_read:%s" % type(ex).__name__)
        return empty_tally(day)
    if require_hub:
        if not token and not can_write_hub():
            raise LedgerUnavailable("no_token_for_hub")
        hub = fetch_repo_spend(HUB_REPO, HUB_PATH, token=token or None, day=day, required=True)
        return _expire_stale(hub)
    # 비강제(구형 호환): 실패해도 로컬만
    parts = [load_local(root, day)]
    hub = fetch_repo_spend(HUB_REPO, HUB_PATH, token=token or None, day=day, required=False)
    if hub:
        parts.append(hub)
    return merge_tallies(*parts, day=day)


def current_spent_thb(root, day=None, token=None):
    t = load_shared(root, day=day, token=token, require_hub=(SPEND_BACKEND != "local" and bool(hub_token())))
    return float(t.get("spent_thb") or 0), t


def check_can_call(root, model, prompt_text, assumed_output=None, day=None, token=None):
    """상한 내면 (True, spent, est, cap, tally). 넘으면 SpendCapExceeded.
    예약 없이 읽는 검사라 레이스에 취약 → 실제 호출 전엔 reserve_or_raise 를 쓸 것.
    허브 실패 시 LedgerUnavailable(유료 호출 금지)."""
    day = day or today_bkk()
    try:
        tally = load_shared(root, day=day, token=token, require_hub=True)
    except LedgerUnavailable:
        raise
    spent = float(tally.get("spent_thb") or 0)
    reserved = float(tally.get("reserved_thb") or 0)
    est = estimate_next_thb(model, prompt_text, assumed_output=assumed_output)
    cap = (DAILY_CAP_THB if CAP_FROM_ENV else float(tally.get("cap_thb") or DAILY_CAP_THB))
    if spent + reserved + est > cap + 1e-9:
        raise SpendCapExceeded(spent, est, cap, day, reserved_thb=reserved)
    return True, spent, est, cap, tally


def make_entry(model, prompt_tokens, output_tokens, thinking_tokens=0, meta=None, repo=None, call_i=None, reservation_id=None, day=None):
    meta = meta or {}
    day = day or today_bkk()
    at = datetime.now(BKK).isoformat(timespec="seconds")
    if not str(at).startswith(day):
        at = day + "T12:00:00+07:00"
    cu = cost_usd(model, prompt_tokens, output_tokens, thinking_tokens)
    ct = cu * USD_THB
    repo = repo or this_repo() or "local"
    eid = "%s|%s|%s|%s" % (repo, meta.get("edition") or "", at, call_i if call_i is not None else prompt_tokens)
    out = {
        "id": eid,
        "at": at,
        "day": day,
        "repo": repo,
        "edition": meta.get("edition"),
        "chunk": meta.get("chunk"),
        "model": model,
        "prompt": int(prompt_tokens or 0),
        "output": int(output_tokens or 0),
        "thinking": int(thinking_tokens or 0),
        "cost_usd": round(cu, 8),
        "cost_thb": round(ct, 6),
        "source": "live",
    }
    if reservation_id:
        out["reservation_id"] = reservation_id
    return out


def reserve_or_raise(root, model, prompt_text, meta=None, assumed_output=None, write_fail=None, day=None, token=None):
    """호출 전 원자적 예약. 성공 시 reservation dict(id, est_thb, ...).
    상한 초과 → SpendCapExceeded. 원장 실패 → LedgerUnavailable(상한과 동일 취급)."""
    day = day or today_bkk()
    meta = meta or {}
    est = estimate_next_thb(model, prompt_text, assumed_output=assumed_output)
    rsv_id = "rsv:%s:%s:%s" % (
        this_repo() or "local",
        meta.get("edition") or "na",
        uuid.uuid4().hex[:12],
    )
    rsv = {
        "id": rsv_id,
        "at": datetime.now(BKK).isoformat(timespec="seconds"),
        "day": day,
        "repo": this_repo() or "local",
        "edition": meta.get("edition"),
        "model": model,
        "est_thb": round(est, 6),
        "status": "open",
        "priced_as": _estimate_price_model(model),
        "margin": SAFETY_MARGIN,
    }

    def mutator(tally):
        spent = float(tally.get("spent_thb") or 0)
        reserved = float(tally.get("reserved_thb") or 0)
        cap = (DAILY_CAP_THB if CAP_FROM_ENV else float(tally.get("cap_thb") or DAILY_CAP_THB))
        if spent + reserved + est > cap + 1e-9:
            raise SpendCapExceeded(spent, est, cap, day, reserved_thb=reserved)
        reservations = list(tally.get("reservations") or [])
        reservations.append(rsv)
        out = dict(tally)
        out["reservations"] = reservations
        return out

    try:
        new = cas_update(mutator, day=day, token=token)
    except SpendCapExceeded as ex:
        print(
            "일일 비용 상한 — 유료 호출 중단: spent=%.4f + reserved=%.4f + est=%.4f > cap=%.2f THB (day=%s)"
            % (ex.spent_thb, ex.reserved_thb, ex.est_thb, ex.cap_thb, ex.day),
            flush=True,
        )
        if write_fail:
            try:
                write_fail(
                    meta.get("edition"),
                    "daily_spend_cap",
                    spent_thb=round(ex.spent_thb, 4),
                    reserved_thb=round(ex.reserved_thb, 4),
                    est_next_thb=round(ex.est_thb, 4),
                    cap_thb=ex.cap_thb,
                    day=ex.day,
                )
            except Exception:
                pass
        raise
    except LedgerUnavailable as ex:
        print("비용 원장 사용 불가 — 유료 호출 중단(상한 도달로 간주): %s" % ex.reason, flush=True)
        if write_fail:
            try:
                write_fail(meta.get("edition"), "ledger_unavailable", reason=ex.reason, day=day)
            except Exception:
                pass
        raise
    with _LOCK:
        _OPEN_RESERVATIONS[rsv_id] = dict(rsv)
    # 로컬 미러에도 반영(배포 커밋용, 권한 판단에는 안 씀)
    try:
        local = load_local(root, day=day)
        local = merge_tallies(local, new, day=day)
        save_local(root, local)
    except Exception:
        pass
    print(
        "spend reserve ok id=%s est=%.4f spent=%.4f reserved=%.4f cap=%.2f"
        % (rsv_id, est, new.get("spent_thb") or 0, new.get("reserved_thb") or 0, new.get("cap_thb") or DAILY_CAP_THB),
        flush=True,
    )
    return rsv


def settle(root, reservation, model, usage_meta, meta=None, call_i=None, token=None):
    """예약 → 실제 비용으로 확정. reservation 은 reserve_or_raise 반환값 또는 id 문자열."""
    global _SESSION_SPENT_THB
    rsv_id = reservation.get("id") if isinstance(reservation, dict) else str(reservation)
    day = today_bkk()
    if isinstance(reservation, dict) and reservation.get("day"):
        day = reservation["day"]
    u = usage_meta or {}
    prompt = int(u.get("promptTokenCount") or u.get("prompt") or 0)
    output = int(u.get("candidatesTokenCount") or u.get("output") or 0)
    thinking = int(u.get("thoughtsTokenCount") or u.get("thinking") or 0)
    entry = make_entry(model, prompt, output, thinking, meta=meta, call_i=call_i, reservation_id=rsv_id, day=day)

    def mutator(tally):
        reservations = [r for r in (tally.get("reservations") or []) if r.get("id") != rsv_id]
        entries = list(tally.get("entries") or [])
        entries.append(entry)
        out = dict(tally)
        out["reservations"] = reservations
        out["entries"] = entries
        return out

    try:
        new = cas_update(mutator, day=day, token=token)
    except LedgerUnavailable as ex:
        # 정산 실패해도 예약은 남아 TTL 후 예상비용으로 확정됨 → 과소계상 없음
        print("spend settle 실패(예약 유지→TTL 확정): %s" % ex.reason, flush=True)
        with _LOCK:
            _SESSION_ENTRIES.append(entry)
            _SESSION_SPENT_THB += float(entry["cost_thb"])
            _OPEN_RESERVATIONS.pop(rsv_id, None)
        try:
            local = load_local(root, day=day)
            local = merge_tallies(local, {"day": day, "entries": [entry]}, day=day)
            save_local(root, local)
        except Exception:
            pass
        return entry, None, False, ex.reason

    with _LOCK:
        _SESSION_ENTRIES.append(entry)
        _SESSION_SPENT_THB += float(entry["cost_thb"])
        _OPEN_RESERVATIONS.pop(rsv_id, None)
    try:
        local = load_local(root, day=day)
        local = merge_tallies(local, new, day=day)
        save_local(root, local)
    except Exception:
        pass
    print(
        "spend settle ok id=%s actual=%.4f spent=%.4f reserved=%.4f"
        % (rsv_id, entry["cost_thb"], new.get("spent_thb") or 0, new.get("reserved_thb") or 0),
        flush=True,
    )
    return entry, new, True, "ok"


def release(root, reservation, token=None, reason="call_failed"):
    """호출 실패 시 예약 해제(실제 과금 없었을 때). HTTP 200 후라면 settle 을 쓸 것."""
    rsv_id = reservation.get("id") if isinstance(reservation, dict) else str(reservation)
    day = today_bkk()
    if isinstance(reservation, dict) and reservation.get("day"):
        day = reservation["day"]

    def mutator(tally):
        reservations = [r for r in (tally.get("reservations") or []) if r.get("id") != rsv_id]
        out = dict(tally)
        out["reservations"] = reservations
        return out

    try:
        new = cas_update(mutator, day=day, token=token)
        with _LOCK:
            _OPEN_RESERVATIONS.pop(rsv_id, None)
        print("spend release ok id=%s reason=%s" % (rsv_id, reason), flush=True)
        return True, new
    except Exception as ex:
        print("spend release 실패(예약 TTL 대기): %s" % type(ex).__name__, flush=True)
        with _LOCK:
            _OPEN_RESERVATIONS.pop(rsv_id, None)
        return False, None


def record_usage(root, model, usage_meta, meta=None, call_i=None, token=None, push=True, reservation=None):
    """호출 후 토큰으로 비용 기록.
    reservation 이 있으면 settle. 없으면(구형) 허브에 바로 entry 추가(예약 없이 — 비권장).
    push 인자는 호환용(항상 CAS)."""
    if reservation is not None:
        entry, local, hub_ok, hub_msg = settle(root, reservation, model, usage_meta, meta=meta, call_i=call_i, token=token)
        return entry, local or load_local(root), hub_ok, hub_msg
    # 구형 경로: 예약 없이 기록 — 상한 보장은 안 됨. 가능하면 쓰지 말 것.
    global _SESSION_SPENT_THB
    u = usage_meta or {}
    prompt = int(u.get("promptTokenCount") or u.get("prompt") or 0)
    output = int(u.get("candidatesTokenCount") or u.get("output") or 0)
    thinking = int(u.get("thoughtsTokenCount") or u.get("thinking") or 0)
    entry = make_entry(model, prompt, output, thinking, meta=meta, call_i=call_i)
    day = entry["day"]

    def mutator(tally):
        entries = list(tally.get("entries") or [])
        entries.append(entry)
        out = dict(tally)
        out["entries"] = entries
        return out

    hub_ok, hub_msg = False, "skipped"
    new = None
    if push:
        try:
            new = cas_update(mutator, day=day, token=token)
            hub_ok, hub_msg = True, "ok"
        except LedgerUnavailable as ex:
            hub_ok, hub_msg = False, ex.reason
    with _LOCK:
        _SESSION_ENTRIES.append(entry)
        _SESSION_SPENT_THB += float(entry["cost_thb"])
    local = load_local(root, day=day)
    local = merge_tallies(local, {"day": day, "entries": [entry]}, day=day)
    local = save_local(root, local)
    return entry, local, hub_ok, hub_msg


def guard_or_raise(root, model, prompt_text, meta=None, write_fail=None):
    """call_gemini 앞에서 호출. 예약 성공 시 reservation dict 반환.
    상한/원장 실패 시 SpendCapExceeded 또는 LedgerUnavailable."""
    return reserve_or_raise(root, model, prompt_text, meta=meta, write_fail=write_fail)
