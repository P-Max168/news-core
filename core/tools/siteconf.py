# -*- coding: utf-8 -*-
"""언어판 설정 로더(R-zh-2, 2026-10-18 Grok — 민구님 08:00 승인으로 Claude 대신).

원칙(Mingoo 10-17 18:33): **시스템은 공유, 편집 기준은 언어별 분리.**
  - 저장소마다 site/LANG 한 줄(ko | zh | …) = 그 저장소의 언어. 시험용으로 환경 변수 TNK_LANG 이 있으면 그것.
  - site/<lang>.json = 그 언어판 설정(브랜드·판 이름·통화·검사 값·홈 나라 칸·Firestore 접두사·숨길 코너·편집 기준 파일 경로).
  - 없으면 한국판 기본값(지금 동작 그대로) — 한국판은 이 파일이 없어도 똑같이 돈다.
    import siteconf; C = siteconf.load(); C["lang"], C["edition_label"]["am"], siteconf.is_ko()
"""
import json, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT = {
    "lang": "ko", "htmlLang": "ko", "brand": "태국 뉴스 한눈에", "site_url": "https://tnews.pmaxone.com/",
    "slots": ["early", "am", "pm"], "edition_label": {"early": "새벽판", "am": "아침판", "pm": "저녁판"},
    "label_format": "{m}월 {d}일 {slot}",
    "home_section": {"id": "korea", "key": "korea_top", "data": "data/korea.json", "script": "data/korea.js", "global": "KOREA_NEWS"},
    "currency": {"pair": "THB_KRW", "check": "krw_check", "header_symbol": "฿"},
    "validate": {"forbid_scripts": ["thai", "cjk"], "forbid_body_symbols": ["฿"]},
    "impacts": ["비자·체류", "환율·물가", "교통·사고", "치안", "날씨·재해"],
    "firestore_prefix": "", "hidden_sections": [],
}
_CACHE = {}


def lang(root=ROOT):
    v = os.environ.get("TNK_LANG")
    if v:
        return v.strip()
    p = pathlib.Path(root) / "site" / "LANG"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "ko"


def load(lang_=None, root=ROOT):
    lg = lang_ or lang(root)
    key = (str(root), lg)
    if key in _CACHE:
        return _CACHE[key]
    c = json.loads(json.dumps(DEFAULT))
    p = pathlib.Path(root) / "site" / ("%s.json" % lg)
    if p.exists():
        c.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if not k.startswith("_")})
    elif lg != "ko":
        raise SystemExit("site/%s.json 없음 — 언어판 설정 파일부터(형식: site/ko.json)" % lg)
    c["lang"] = lg
    tp = pathlib.Path(root) / "site" / ("topics.%s.json" % lg)
    if tp.exists():
        c["topics"] = json.loads(tp.read_text(encoding="utf-8"))
    _CACHE[key] = c
    return c


def is_ko(c=None):
    return (c or load())["lang"] == "ko"


def forbids(script, c=None):
    """이 언어판 화면 글에 금지된 문자인지(site/<lang>.json validate.forbid_scripts — thai·cjk·hangul).
    한국판·중국어판·베트남판은 'thai' 를 넣어 두어 지금 동작 그대로, 태국어판(kstar)은 'thai' 를 빼고 'hangul' 을 넣음(2026-10-25 Claude)."""
    return script in (c or load()).get("validate", {}).get("forbid_scripts", ["thai", "cjk"])


def forbids_symbol(sym, c=None):
    """판 글에 금지된 기호인지(validate.forbid_body_symbols — 한국판·중국어판·베트남판 '฿')."""
    return sym in (c or load()).get("validate", {}).get("forbid_body_symbols", ["฿"])


def topic_ids(c=None):
    """언어판 topics 파일이 있으면 그 id 목록, 없으면 None(= 한국판 기본 TOPICS)."""
    c = c or load()
    t = c.get("topics")
    return [x["id"] for x in t["TOPICS"]] if t else None


if __name__ == "__main__":
    c = load()
    print(json.dumps({k: c[k] for k in ("lang", "brand", "site_url", "slots", "currency", "firestore_prefix", "hidden_sections")}, ensure_ascii=False))
