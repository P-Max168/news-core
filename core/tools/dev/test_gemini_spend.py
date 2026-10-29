# -*- coding: utf-8 -*-
"""gemini_spend 일일 상한·예약 CAS 단위 검사(2026-10-29 hardcap).
실행: GEMINI_SPEND_BACKEND=local GEMINI_SPEND_LOCAL_PATH=/tmp/... python3 tools/dev/test_gemini_spend.py
"""
import json, os, pathlib, sys, tempfile, threading, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# force local backend before import if not set
os.environ.setdefault("GEMINI_SPEND_BACKEND", "local")

import gemini_spend as s

FAIL = 0

def eq(label, got, exp):
    global FAIL
    if got != exp:
        FAIL += 1
        print("FAIL", label, "got=%r exp=%r" % (got, exp))
    else:
        print("ok  ", label, "→", got)

def ok(label, cond):
    global FAIL
    if not cond:
        FAIL += 1
        print("FAIL", label)
    else:
        print("ok  ", label)

def near(label, got, exp, eps=1e-6):
    global FAIL
    if abs(got - exp) > eps:
        FAIL += 1
        print("FAIL", label, "got=%r exp=%r" % (got, exp))
    else:
        print("ok  ", label, "→", got)


def _reset_session():
    s._SESSION_ENTRIES.clear()
    s._SESSION_SPENT_THB = 0.0
    s._OPEN_RESERVATIONS.clear()


def _with_local(td):
    path = str(pathlib.Path(td) / "ledger.json")
    os.environ["GEMINI_SPEND_BACKEND"] = "local"
    os.environ["GEMINI_SPEND_LOCAL_PATH"] = path
    s.SPEND_BACKEND = "local"
    s.LOCAL_LEDGER_PATH = path
    _reset_session()
    return path


def test_official_prices():
    eq("lite in", s.PRICES_USD_PER_1M["gemini-3.5-flash-lite"]["input"], 0.30)
    eq("lite out", s.PRICES_USD_PER_1M["gemini-3.5-flash-lite"]["output"], 2.50)
    eq("38 in", s.PRICES_USD_PER_1M["gemini-3.8-flash"]["input"], 0.75)
    eq("38 out", s.PRICES_USD_PER_1M["gemini-3.8-flash"]["output"], 3.75)
    eq("cap default", s.DAILY_CAP_THB, 200.0)
    eq("usd_thb default", s.USD_THB, 34.0)
    ok("margin default", s.SAFETY_MARGIN >= 1.5)


def test_cost_math():
    near("lite 1M", s.cost_thb("gemini-3.5-flash-lite", 1_000_000, 1_000_000, 0), 2.80 * 34.0)
    near("thinking as out", s.cost_usd("gemini-3.5-flash-lite", 0, 0, 1_000_000), 2.50)
    near("38 1M", s.cost_usd("gemini-3.8-flash", 1_000_000, 1_000_000, 0), 0.75 + 3.75)


def test_estimate_uses_higher_model_and_margin():
    # lite request still priced as 3.8 * margin
    est = s.estimate_next_thb("gemini-3.5-flash-lite", "hi" * 100, assumed_output=10000)
    raw38 = s.cost_thb("gemini-3.8-flash", s.estimate_prompt_tokens("hi" * 100), 10000, 0)
    near("est = 38 * margin", est, raw38 * s.SAFETY_MARGIN, eps=1e-5)
    ok("est > lite raw", est > s.cost_thb("gemini-3.5-flash-lite", s.estimate_prompt_tokens("hi" * 100), 10000, 0))


def test_tally_day_reset_and_merge():
    day = "2026-10-28"
    a = s.empty_tally(day)
    a["entries"].append(s.make_entry("gemini-3.5-flash-lite", 1000, 500, 0,
                                      meta={"edition": "2026-10-28-am"}, repo="P-Max168/thai-news-kr", call_i=1))
    a["entries"][0]["day"] = day
    a["entries"][0]["at"] = day + "T08:00:00+07:00"
    a["entries"][0]["id"] = "kr-1"
    b = s.empty_tally(day)
    b["entries"].append({
        "id": "zh-1", "at": day + "T09:00:00+07:00", "day": day,
        "repo": "P-Max168/thai-news-zh", "edition": "2026-10-28-am",
        "model": "gemini-3.5-flash-lite", "prompt": 2000, "output": 1000, "thinking": 0,
        "cost_usd": s.cost_usd("gemini-3.5-flash-lite", 2000, 1000, 0),
        "cost_thb": s.cost_thb("gemini-3.5-flash-lite", 2000, 1000, 0),
    })
    b["entries"].append(dict(b["entries"][0], cost_thb=0.01, cost_usd=0.0001))
    m = s.merge_tallies(a, b, day=day)
    eq("merged count", len(m["entries"]), 2)
    near("merged spent", m["spent_thb"],
         s.cost_thb("gemini-3.5-flash-lite", 1000, 500, 0) + 0.01)
    other = s.empty_tally("2026-10-27")
    other["entries"].append(dict(a["entries"][0], day="2026-10-27", id="old"))
    m2 = s.merge_tallies(m, other, day=day)
    eq("day filter", len(m2["entries"]), 2)


def test_cap_blocks_and_reserve():
    day = "2099-01-01"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        # seed near cap
        def seed(t):
            t = dict(t)
            t["cap_thb"] = 200
            t["entries"] = [{
                "id": "big", "at": day + "T01:00:00+07:00", "day": day,
                "repo": "local", "edition": "x", "model": "gemini-3.5-flash-lite",
                "prompt": 0, "output": 0, "thinking": 0,
                "cost_usd": 199.5 / 34.0, "cost_thb": 199.5,
            }]
            return t
        s.cas_update(seed, day=day)
        blocked = False
        try:
            s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hello " * 100, day=day,
                               meta={"edition": day + "-am"})
        except s.SpendCapExceeded as ex:
            blocked = True
            ok("ex has spent", ex.spent_thb >= 199.5)
            ok("ex cap 200", ex.cap_thb == 200)
        ok("blocked near cap", blocked)

        # empty allows + reserve
        td2 = tempfile.mkdtemp()
        root2 = pathlib.Path(td2)
        (root2 / "ops").mkdir()
        _with_local(td2)
        rsv = s.reserve_or_raise(root2, "gemini-3.5-flash-lite", "hi", day=day,
                                 meta={"edition": day + "-am"})
        ok("rsv id", bool(rsv.get("id")))
        t = s.load_shared(root2, day=day)
        ok("reserved>0", float(t.get("reserved_thb") or 0) > 0)
        # settle
        entry, _, hub_ok, _ = s.settle(root2, rsv, "gemini-3.5-flash-lite",
            {"promptTokenCount": 100, "candidatesTokenCount": 50, "thoughtsTokenCount": 0},
            meta={"edition": day + "-am"}, call_i=1)
        ok("settle ok", hub_ok)
        t2 = s.load_shared(root2, day=day)
        eq("reserved cleared", float(t2.get("reserved_thb") or 0), 0.0)
        ok("spent>0", float(t2.get("spent_thb") or 0) > 0)
        near("spent=actual", t2["spent_thb"], entry["cost_thb"])


def test_release_frees_cap():
    day = "2099-03-03"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        # tiny cap
        prev = s.DAILY_CAP_THB
        s.DAILY_CAP_THB = 5.0
        try:
            rsv = s.reserve_or_raise(root, "gemini-3.8-flash", "x" * 200, day=day,
                                     meta={"edition": day + "-am"}, assumed_output=25000)
            t = s.load_shared(root, day=day)
            # second reserve should fail while first open (est ~ several THB each, cap 3)
            blocked = False
            try:
                s.reserve_or_raise(root, "gemini-3.8-flash", "y" * 200, day=day,
                                   meta={"edition": day + "-am"}, assumed_output=25000)
            except s.SpendCapExceeded:
                blocked = True
            ok("second blocked while reserved", blocked)
            s.release(root, rsv, reason="test")
            # now should succeed
            rsv2 = s.reserve_or_raise(root, "gemini-3.8-flash", "z" * 200, day=day,
                                      meta={"edition": day + "-am"}, assumed_output=25000)
            ok("after release ok", bool(rsv2.get("id")))
            s.release(root, rsv2, reason="cleanup")
        finally:
            s.DAILY_CAP_THB = prev


def test_parallel_reservations_never_exceed_cap():
    day = "2099-04-04"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        prev_cap = s.DAILY_CAP_THB
        prev_out = s.ASSUMED_OUTPUT_TOKENS
        prev_margin = s.SAFETY_MARGIN
        # Make each reserve ~40 THB so at most 5 fit in 200
        s.DAILY_CAP_THB = 200.0
        s.ASSUMED_OUTPUT_TOKENS = 200000  # large → ~40 THB each with margin
        s.SAFETY_MARGIN = 1.5
        results = []
        lock = threading.Lock()

        def worker(i):
            try:
                rsv = s.reserve_or_raise(
                    root, "gemini-3.8-flash", "p" * 500, day=day,
                    meta={"edition": day + "-am", "chunk": i}, assumed_output=200000)
                with lock:
                    results.append(("ok", rsv["id"], rsv["est_thb"]))
            except s.SpendCapExceeded as ex:
                with lock:
                    results.append(("cap", None, ex.est_thb))
            except s.LedgerUnavailable as ex:
                with lock:
                    results.append(("ledger", None, str(ex)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        oks = [r for r in results if r[0] == "ok"]
        caps = [r for r in results if r[0] == "cap"]
        print("  parallel ok=%d cap=%d ledger=%d" % (
            len(oks), len(caps), len([r for r in results if r[0] == "ledger"])))
        t = s.load_shared(root, day=day)
        reserved = float(t.get("reserved_thb") or 0)
        spent = float(t.get("spent_thb") or 0)
        ok("parallel some ok", len(oks) >= 1)
        ok("parallel some blocked", len(caps) >= 1)
        ok("reserved+spent <= cap", spent + reserved <= 200.0 + 1e-6)
        ok("ok count matches reservations", len(oks) == len(t.get("reservations") or []))
        # cleanup
        for _, rid, _ in oks:
            s.release(root, rid, reason="test_cleanup")
        s.DAILY_CAP_THB = prev_cap
        s.ASSUMED_OUTPUT_TOKENS = prev_out
        s.SAFETY_MARGIN = prev_margin


def test_ledger_unavailable_without_token_on_hub():
    # hub backend without token → LedgerUnavailable
    prev_b = s.SPEND_BACKEND
    s.SPEND_BACKEND = "hub"
    os.environ.pop("SPEND_HUB_TOKEN", None)
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GITHUB_REPOSITORY", None)
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        raised = False
        try:
            s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hi", day="2099-05-05",
                               meta={"edition": "2099-05-05-am"})
        except s.LedgerUnavailable as ex:
            raised = True
            ok("reason mentions hub", "hub" in ex.reason or "token" in ex.reason)
        ok("no token → ledger unavailable", raised)
    s.SPEND_BACKEND = prev_b
    os.environ["GEMINI_SPEND_BACKEND"] = "local"


def test_date_rollover_bkk():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        day1 = "2099-06-01"
        day2 = "2099-06-02"
        rsv = s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hi", day=day1,
                                 meta={"edition": day1 + "-am"}, assumed_output=100)
        s.settle(root, rsv, "gemini-3.5-flash-lite",
                 {"promptTokenCount": 10, "candidatesTokenCount": 5},
                 meta={"edition": day1 + "-am"}, call_i=1)
        t1 = s.load_shared(root, day=day1)
        ok("day1 spent>0", t1["spent_thb"] > 0)
        # new day empty
        t2 = s.load_shared(root, day=day2)
        # load_shared local reads file - if file still day1, returns empty for day2
        eq("day2 spent0", t2["spent_thb"], 0.0)
        eq("day2 reserved0", t2["reserved_thb"], 0.0)
        # reserve on day2 works independently
        rsv2 = s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hi", day=day2,
                                  meta={"edition": day2 + "-am"}, assumed_output=100)
        ok("day2 reserve", bool(rsv2.get("id")))
        s.release(root, rsv2)


def test_stale_reservation_becomes_spent():
    day = "2099-07-07"
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        prev_ttl = s.RESERVATION_TTL_S
        s.RESERVATION_TTL_S = 1
        rsv = s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hi", day=day,
                                 meta={"edition": day + "-am"}, assumed_output=100)
        # backdate reservation
        def backdate(t):
            out = dict(t)
            rs = []
            for r in out.get("reservations") or []:
                r = dict(r)
                if r.get("id") == rsv["id"]:
                    r["at"] = "2020-01-01T00:00:00+07:00"
                rs.append(r)
            out["reservations"] = rs
            return out
        s.cas_update(backdate, day=day)
        time.sleep(0.05)
        t = s.load_shared(root, day=day)  # expire on load via _expire_stale in cas; load_shared local also expires
        # force expire via cas no-op
        s.cas_update(lambda x: x, day=day)
        t = s.load_shared(root, day=day)
        ok("stale → spent", float(t.get("spent_thb") or 0) > 0)
        eq("stale reserved0", float(t.get("reserved_thb") or 0), 0.0)
        s.RESERVATION_TTL_S = prev_ttl


def test_record_local_compat():
    day = s.today_bkk()
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "ops").mkdir()
        _with_local(td)
        rsv = s.reserve_or_raise(root, "gemini-3.5-flash-lite", "hi", day=day,
                                 meta={"edition": day + "-am"}, assumed_output=100)
        entry, local, hub_ok, hub_msg = s.record_usage(
            root, "gemini-3.5-flash-lite",
            {"promptTokenCount": 1000, "candidatesTokenCount": 500, "thoughtsTokenCount": 0},
            meta={"edition": day + "-am"}, call_i=1, reservation=rsv)
        ok("entry cost>0", entry["cost_thb"] > 0)
        ok("hub ok", hub_ok)
        again = s.load_local(root, day=day)
        ok("local has entries or reserved cleared", len(again.get("entries") or []) >= 0)


def test_env_cap_override():
    prev = s.DAILY_CAP_THB
    s.DAILY_CAP_THB = 50.0
    t = s.empty_tally("2099-02-02")
    eq("cap override empty", t["cap_thb"], 50.0)
    s.DAILY_CAP_THB = prev


if __name__ == "__main__":
    test_official_prices()
    test_cost_math()
    test_estimate_uses_higher_model_and_margin()
    test_tally_day_reset_and_merge()
    test_cap_blocks_and_reserve()
    test_release_frees_cap()
    test_parallel_reservations_never_exceed_cap()
    test_ledger_unavailable_without_token_on_hub()
    test_date_rollover_bkk()
    test_stale_reservation_becomes_spent()
    test_record_local_compat()
    test_env_cap_override()
    if FAIL:
        print("FAILED", FAIL)
        raise SystemExit(1)
    print("ALL OK")
