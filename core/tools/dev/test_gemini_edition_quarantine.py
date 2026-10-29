# -*- coding: utf-8 -*-
"""gemini_edition 격리·재번역·503/5분 예산 단위 검사(2026-10-28).
실행: python3 tools/dev/test_gemini_edition_quarantine.py
"""
import os, pathlib, sys, tempfile, types, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
# 예약 원장: 시험은 로컬 파일 CAS (허브 토큰 불필요)
_td = tempfile.mkdtemp(prefix="spend-test-")
os.environ["GEMINI_SPEND_BACKEND"] = "local"
os.environ["GEMINI_SPEND_LOCAL_PATH"] = str(pathlib.Path(_td) / "ledger.json")
import gemini_spend as _gs
_gs.SPEND_BACKEND = "local"
_gs.LOCAL_LEDGER_PATH = os.environ["GEMINI_SPEND_LOCAL_PATH"]
import gemini_edition as g

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


def test_story_id_from_assert():
    ids = ["ea1", "ea2", "ea3", "bk1"]
    a = (("ea3", "headline"), "화면에 태국 문자 금지", "촌부리 방ละ뭉에")
    eq("nested where", g.story_id_from_assert(a, ids), "ea3")
    eq("plain sid", g.story_id_from_assert(("ea1", "필수 필드 없음"), ids), "ea1")
    eq("sid only str", g.story_id_from_assert("bk1", ids), "bk1")
    eq("unknown", g.story_id_from_assert((("briefing",), "태국"), ids), None)
    eq("briefing str", g.story_id_from_assert(("briefing", "태국"), ids), None)
    eq("empty", g.story_id_from_assert((), ids), None)


def _stub_story(sid, headline="제목"):
    return dict(id=sid, topic="east", secondary=[], region="촌부리",
                headline=headline, summary=["요약1", "요약2"], source="테스트",
                url="https://example.com/%s" % sid, title_th="th",
                published="2026-10-28T06:00:00+07:00", related=[], tags=["촌부리", "동부"],
                impact=[], for_me="", also=[], issue=None, quick_replies=[])


def _base_data(stories):
    return dict(id="2026-10-28-am", date="2026-10-28", edition="am",
                edition_label="아침판", weekday="수", timezone="Asia/Bangkok (UTC+7)",
                coverage="test", previous="", briefing=[
                    dict(topic="east", text="**촌부리** %s" % s["id"], story_id=s["id"])
                    for s in stories[:4]
                ], highlights=[s["id"] for s in stories[:3]], stories=stories, fx={"THB_KRW": 40.0})


def _thai_write_factory():
    def fake_write(d):
        bad = [s for s in d["stories"] if any("\u0e00" <= c <= "\u0e7f" for c in (s.get("headline") or ""))]
        if bad:
            raise AssertionError(((bad[0]["id"], "headline"),
                                  "화면에 태국 문자 금지 — 한국어/로마자로 고칠 것(TRANSLATION_RULES)",
                                  bad[0]["headline"][:20]))
        return None
    return fake_write


def test_save_with_drop_quarantine():
    stories = [_stub_story("ea%d" % i) for i in range(1, 6)]
    stories[2]["headline"] = "촌부리 방ละ뭉 신도시"
    data = _base_data(stories)
    real_write = g.newslib.write_edition
    g.newslib.write_edition = _thai_write_factory()
    try:
        ok_pub = g.save_with_drop(data, min_stories=4)  # no retranslate
    finally:
        g.newslib.write_edition = real_write
    ok("published after quarantine", ok_pub is True)
    eq("dropped ea3", "ea3" in [s["id"] for s in data["stories"]], False)
    eq("kept 4+", len(data["stories"]) >= 4, True)


def test_retranslate_then_keep():
    """재번역 성공 → 기사 유지."""
    stories = [_stub_story("ea%d" % i) for i in range(1, 6)]
    stories[2]["headline"] = "촌부리 방ละ뭉 신도시"
    data = _base_data(stories)
    calls = {"re": 0}

    def re_fn(d, sid, defect_note=""):
        calls["re"] += 1
        for s in d["stories"]:
            if s["id"] == sid:
                s["headline"] = "촌부리 방라뭉 신도시"  # Thai removed
                return True
        return False

    real_write = g.newslib.write_edition
    g.newslib.write_edition = _thai_write_factory()
    try:
        ok_pub = g.save_with_drop(data, min_stories=4, retranslate_fn=re_fn)
    finally:
        g.newslib.write_edition = real_write
    ok("published after retranslate", ok_pub is True)
    eq("retranslate once", calls["re"], 1)
    eq("ea3 kept", "ea3" in [s["id"] for s in data["stories"]], True)
    eq("headline fixed", next(s["headline"] for s in data["stories"] if s["id"] == "ea3"),
       "촌부리 방라뭉 신도시")


def test_retranslate_fail_then_drop():
    """재번역 실패 → 격리."""
    stories = [_stub_story("ea%d" % i) for i in range(1, 6)]
    stories[2]["headline"] = "촌부리 방ละ뭉 신도시"
    data = _base_data(stories)
    calls = {"re": 0}

    def re_fn(d, sid, defect_note=""):
        calls["re"] += 1
        return False  # still bad / API fail

    real_write = g.newslib.write_edition
    g.newslib.write_edition = _thai_write_factory()
    try:
        ok_pub = g.save_with_drop(data, min_stories=4, retranslate_fn=re_fn)
    finally:
        g.newslib.write_edition = real_write
    ok("published after drop", ok_pub is True)
    eq("retranslate once then drop", calls["re"], 1)
    eq("ea3 dropped", "ea3" in [s["id"] for s in data["stories"]], False)


def test_retranslate_once_only():
    """같은 기사 재번역은 1회만."""
    stories = [_stub_story("ea%d" % i) for i in range(1, 6)]
    stories[2]["headline"] = "촌부리 방ละ뭉 신도시"
    data = _base_data(stories)
    calls = {"re": 0}

    def re_fn(d, sid, defect_note=""):
        calls["re"] += 1
        # "fix" but leave Thai → second validation fails → drop without 2nd retranslate
        return True

    real_write = g.newslib.write_edition
    g.newslib.write_edition = _thai_write_factory()
    try:
        ok_pub = g.save_with_drop(data, min_stories=4, retranslate_fn=re_fn)
    finally:
        g.newslib.write_edition = real_write
    ok("still published", ok_pub is True)
    eq("retranslate only once", calls["re"], 1)
    eq("eventually dropped", "ea3" in [s["id"] for s in data["stories"]], False)


def test_save_with_drop_below_min():
    stories = [_stub_story("ea%d" % i, "방ละ뭉 %d" % i) for i in range(1, 5)]
    data = _base_data(stories)
    real_write = g.newslib.write_edition
    g.newslib.write_edition = _thai_write_factory()
    try:
        ok_pub = g.save_with_drop(data, min_stories=4)
    finally:
        g.newslib.write_edition = real_write
    ok("below min → False", ok_pub is False)
    ok("stories drained below 4", len(data["stories"]) < 4)


def test_primary_backoff_constants():
    eq("primary backoff", g.PRIMARY_BACKOFF_S, [20, 60, 120])
    eq("budget 5min", g.PRIMARY_BUDGET_S, 300)
    eq("retranslate timeout", g.RETRANSLATE_TIMEOUT_S, 75)
    eq("fallback one-shot", g.FALLBACK_BACKOFF_S, [])
    ok("fallback backoff shorter than old 16min", sum(g.FALLBACK_BACKOFF_S) < 980)
    ok("primary wait sum < 5min", sum(g.PRIMARY_BACKOFF_S) <= 300)
    eq("default primary lite", g.MODEL, "gemini-3.5-flash-lite")
    eq("default fallback 3.8", g.FALLBACK_MODEL, "gemini-3.8-flash")


def test_call_gemini_retries_then_fallback():
    # 단위 검사: 3.8이 주·lite가 폴백인 경로를 시뮬레이션(운영 기본과 역할이 반대여도 폴백 로직은 동일)
    g.FALLBACK_MODEL = "gemini-3.5-flash-lite"
    sleeps = []
    real_sleep = g.time.sleep
    g.time.sleep = lambda s: sleeps.append(s)

    class FakeResp:
        def __init__(self, code, body=None, text=""):
            self.status_code = code
            self._body = body or {}
            self.text = text
        def json(self):
            return self._body

    posts = {"models": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        model = url.split("/models/")[1].split(":")[0]
        posts["models"].append(model)
        if "lite" in model:
            return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                                  "usageMetadata": {}})
        return FakeResp(503, text="unavailable")

    fake_req = types.ModuleType("requests")
    fake_req.post = fake_post
    sys.modules["requests"] = fake_req
    g.PRIMARY_EXHAUSTED = False
    g.PRIMARY_PHASE_T0 = time.time()
    g.USAGE = dict(calls=0, prompt=0, output=0, thinking=0, total=0)
    g._log_usage = lambda rec: None
    g._write_edition_fail = lambda *a, **k: None
    try:
        out = g.call_gemini("hi", "KEY", "gemini-3.8-flash", meta=dict(edition="test"), allow_fallback=True)
    finally:
        g.time.sleep = real_sleep
    eq("json ok", out, {"ok": True})
    eq("sleeps primary", sleeps, [20, 60, 120])
    ok("tried primary then lite", posts["models"][0] == "gemini-3.8-flash" and any("lite" in m for m in posts["models"]))
    ok("PRIMARY_EXHAUSTED set", g.PRIMARY_EXHAUSTED is True)

    sleeps.clear(); posts["models"].clear()
    g.time.sleep = lambda s: sleeps.append(s)
    try:
        out2 = g.call_gemini("hi2", "KEY", "gemini-3.8-flash", allow_fallback=True)
    finally:
        g.time.sleep = real_sleep
    eq("second ok", out2, {"ok": True})
    eq("second no primary sleeps", sleeps, [])
    ok("second only lite", all("lite" in m for m in posts["models"]))


def test_primary_phase_budget_5min():
    """주 모델 단계 시작 후 5분 지나면 바로 폴백(요청 0회)."""
    g.FALLBACK_MODEL = "gemini-3.5-flash-lite"
    class FakeResp:
        def __init__(self, code, body=None, text=""):
            self.status_code = code
            self._body = body or {}
            self.text = text
        def json(self):
            return self._body

    posts = {"n": 0, "models": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        posts["n"] += 1
        model = url.split("/models/")[1].split(":")[0]
        posts["models"].append(model)
        if "lite" in model:
            return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": '{"ok":1}'}]}}],
                                  "usageMetadata": {}})
        return FakeResp(503, text="no")

    fake_req = types.ModuleType("requests")
    fake_req.post = fake_post
    sys.modules["requests"] = fake_req
    g.PRIMARY_EXHAUSTED = False
    g.PRIMARY_PHASE_T0 = time.time() - (g.PRIMARY_BUDGET_S + 1)  # already over budget
    g.USAGE = dict(calls=0, prompt=0, output=0, thinking=0, total=0)
    g._log_usage = lambda rec: None
    g._write_edition_fail = lambda *a, **k: None
    real_sleep = g.time.sleep
    sleeps = []
    g.time.sleep = lambda s: sleeps.append(s)
    try:
        out = g.call_gemini("x", "KEY", "gemini-3.8-flash", allow_fallback=True)
    finally:
        g.time.sleep = real_sleep
    eq("budget fallback ok", out, {"ok": 1})
    eq("no primary posts", [m for m in posts["models"] if "lite" not in m], [])
    ok("only lite", all("lite" in m for m in posts["models"]))
    eq("no sleeps", sleeps, [])


def test_call_gemini_once_timeout():
    """재번역 once: timeout 인자 전달, 실패 시 None."""
    seen = {}

    class FakeResp:
        status_code = 503
        text = "no"
        def json(self):
            return {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["timeout"] = timeout
        return FakeResp()

    fake_req = types.ModuleType("requests")
    fake_req.post = fake_post
    sys.modules["requests"] = fake_req
    g.USAGE = dict(calls=0, prompt=0, output=0, thinking=0, total=0)
    out = g.call_gemini_once("p", "KEY", "gemini-3.8-flash", timeout=75)
    eq("once None on 503", out, None)
    eq("timeout 75", seen.get("timeout"), 75)

    class OkResp:
        status_code = 200
        text = "ok"
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"headline":"ok"}'}]}}],
                    "usageMetadata": {}}

    def fake_ok(url, headers=None, json=None, timeout=None):
        seen["timeout"] = timeout
        return OkResp()

    fake_req.post = fake_ok
    g._log_usage = lambda rec: None
    out = g.call_gemini_once("p", "KEY", "gemini-3.8-flash", timeout=90)
    eq("once ok", out, {"headline": "ok"})
    eq("timeout 90", seen.get("timeout"), 90)


def test_apply_retranslate_to_story():
    s = _stub_story("ea3", "방ละ뭉")
    out = dict(keep=True, topic="east", secondary=[], region="촌부리",
               headline="촌부리 방라뭉 신도시", summary=["하나", "둘"], context="",
               tags=["EEC", "촌부리"], impact=[], for_me="", quick_replies=[])
    ok("apply", g.apply_retranslate_to_story(s, out) is True)
    eq("headline", s["headline"], "촌부리 방라뭉 신도시")
    ok("keep false", g.apply_retranslate_to_story(s, dict(keep=False)) is False)


def main():
    test_story_id_from_assert()
    test_save_with_drop_quarantine()
    test_retranslate_then_keep()
    test_retranslate_fail_then_drop()
    test_retranslate_once_only()
    test_save_with_drop_below_min()
    test_primary_backoff_constants()
    test_call_gemini_retries_then_fallback()
    test_primary_phase_budget_5min()
    test_call_gemini_once_timeout()
    test_apply_retranslate_to_story()
    if FAIL:
        print("\n%d FAILED" % FAIL)
        return 1
    print("\nALL OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
