# -*- coding: utf-8 -*-
"""공용 도우미: 판(edition) 데이터 검증·저장 + data/index 재생성.

파일 이름 규칙 (data/ 폴더)
  <YYYY-MM-DD>-am   아침판 (매일 06:40 정기 실행, 07:00 게시 — 2026-10-23 변경)
  <YYYY-MM-DD>-pm   저녁판 (매일 17:40 정기 실행, 18:00 게시)
  <YYYY-MM-DD>-early 새벽판 (정기 외 임시판. 2026-09-29-early 한 건만 존재)
날짜만 있는 파일(<YYYY-MM-DD>.json)은 더 이상 만들지 않는다.

기사 형식(2026-10-03 아침판부터 = 새 형식, README '기사 스키마')
  topic      : 주 주제 1개 (TOPICS 의 id: east bangkok north south poleco society visa life travel ent weather)
               2026-10-03 저녁판부터 pattaya·sriracha 는 east('동부(촌부리·라용)')로 통합 — 옛 id 는 검증에서 막힘
  secondary  : 보조 주제 0~3개 (예: 파타야 침수 기사 = topic "east", secondary ["weather"])
  tags       : 키워드 태그 2~6개(👍👎 취향 학습에 씀) — 반드시 넣는다
  briefing   : [{topic, text("**굵게**" 표시 1곳 이상), story_id}] 5~6줄
옛 형식(category 6종 + 문단 briefing)도 검증을 통과한다(화면은 assets/topics.js 매핑으로 렌더).
"""
import json, re, pathlib, sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EDITION_LABEL = {"am": "아침판", "md": "점심판", "pm": "저녁판", "early": "새벽판"}
# md = 점심판(중국어판 시험 13:00, 2026-10-18 R-zh-2). 순서 값만 늘림(early<am<md<pm) — 한국판 판 정렬·비교 결과는 그대로
EDITION_ORDER = {"early": 0, "am": 1, "md": 2, "pm": 3}
ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(am|md|pm|early)$")
# ── 언어판 설정(R-zh-2, 2026-10-18): 시스템 공유·편집 기준 분리. 한국판(site/LANG=ko 또는 없음)은 아래 값이 지금과 똑같음 ──
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import siteconf  # noqa: E402
SITE = siteconf.load()
LANG = SITE["lang"]
if LANG != "ko":
    EDITION_LABEL = dict(SITE["edition_label"])
CATS = {"politics", "economy", "society", "local", "visa", "sns"}          # 옛 형식(10월 2일 저녁판까지)
CAT_ORDER = ["politics", "economy", "society", "local", "visa", "sns"]
# 새 형식 주제 11개 (assets/topics.js 와 같은 id·순서) — 2026-10-03 운영자 결정: 파타야·시라차 → 동부(촌부리·라용), 북부·남부 추가
TOPICS = {
    "east": "동부(촌부리·라용)", "bangkok": "방콕", "north": "북부", "south": "남부",
    "poleco": "정치·경제", "society": "사회·사건사고", "visa": "외국인·비자",
    "life": "생활·물가·부동산", "travel": "여행·맛집", "ent": "연예·스포츠·SNS", "weather": "날씨·교통",
}
if LANG != "ko" and siteconf.topic_ids(SITE):   # 언어판 주제(예: zh 에는 cn 涉华 추가) — site/topics.<lang>.json
    TOPICS = {x["id"]: x["label"] for x in SITE["topics"]["TOPICS"]}
TOPIC_ORDER = list(TOPICS)
# 옛 주제 id(2026-10-03 아침판까지 쓰임) → 새 id. 그 판까지는 별칭으로 받아 주고, 저녁판부터는 막는다.
TOPIC_ALIAS = {"pattaya": "east", "sriracha": "east"}
ALIAS_UNTIL = "2026-10-03-am"
# 판마다 맞추려는 구성(경고만 — 실제 뉴스가 없으면 적게 싣는다. 절대 지어내지 않는다)
TARGETS = dict(stories=(20, 25), visa=(2, 4), places=("east", "bangkok"), want=("travel", "life"))
B = lambda topic, text, story_id: dict(topic=topic, text=text, story_id=story_id)   # 브리핑 한 줄
BLOCKLIST = ROOT / "tools" / "trend_blocklist.txt"
_BL = None
# ── 판마다 채울 필드(2026-10-03 추가, README '판마다 채울 필드') ──
#   impact[]      : 한인 영향도 태그(아래 5개 중 0~3개)       for_me        : '그래서 나는?' 한 문장(없으면 "")
#   also[]        : 같은 사건을 보도한 다른 매체 [{source, url}] (확인한 실제 기사 주소만)
#   issue         : {id, title} — 이어지는 이슈(tools/issues.json 등록부의 id 만)   quick_replies[] : 추천 댓글 3~4개
IMPACTS = ["비자·체류", "환율·물가", "교통·사고", "치안", "날씨·재해"]
if LANG != "ko":
    IMPACTS = list(SITE["impacts"]) if SITE.get("impacts") is not None else IMPACTS   # 빈 목록 = 영향 태그 안 씀(태국어판 kstar)
ISSUES_FILE = ROOT / "tools" / "issues.json"
ISSUE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
# 한국어 글에 섞이면 안 되는 한자·일본 가나(번역 잔재 — 例 '追いつ었으나', '해양沿岸자원국'). 한국어 본문 필드에만 적용
CJK_RE = re.compile(r"[\u3040-\u30FF\u31F0-\u31FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF66-\uFF9F]")
KO_FIELDS = ("headline", "summary", "context", "update", "region", "for_me", "quick_replies")


def cjk_check(data):
    """한국어 본문 필드(기사 제목·요약·배경·후속·지역·그래서 나는?·추천 댓글·이슈 이름·오늘의 질문·브리핑)에 한자·가나가 있으면 예외."""
    def chk(where, v):
        for t in (v if isinstance(v, list) else [v]):
            m = CJK_RE.search(t) if isinstance(t, str) else None
            assert not m, (where, "한국어 글에 한자·가나 금지(번역 잔재) — 한국어로 고칠 것", t[max(0, m.start() - 12):m.end() + 8])
    for s in data.get("stories", []):
        for k in KO_FIELDS:
            if k in s: chk((s["id"], k), s[k])
        if isinstance(s.get("issue"), dict): chk((s["id"], "issue.title"), s["issue"].get("title"))
        d = s.get("discussion")
        if isinstance(d, dict): chk((s["id"], "discussion"), [d.get("question") or "", d.get("operator_comment") or ""])
    br = data.get("briefing")
    chk("briefing", [b.get("text") or "" for b in br] if isinstance(br, list) else (br or ""))
# 화면에 보이는 글에 태국 문자 금지. title_th·원문 URL 처럼 화면에 안 나오는 필드는 검사 안 함.
#   ฿(U+0E3F)도 판 글에서는 금지(2026-10-04 21:41 Max 승인) — ฿ 는 헤더 숫자 칸(assets/ticker.js .tk-u)에만, 글에서는 '350바트(약 1.41만 원)'.
#   2026-10-04 저녁판 요약에 '이민국(สตม.)'·'재난방지국(ปภ.)'·키워드 'ปภ.' 가 들어가 라이브 화면에 태국 글자가 보였던 일 → 판 저장 때 막음
THAI_SHOWN_RE = re.compile(r"[\u0E00-\u0E3E\u0E40-\u0E7F]+")


def thai_check(data):
    """화면에 보이는 필드(기사 제목·요약·배경·후속·지역·그래서 나는?·추천 댓글·키워드·매체 이름·이슈 이름·오늘의 질문·브리핑·한국 뉴스 제목)에
    태국 문자나 '฿' 가 있으면 예외. 기관 약칭은 한국어(+로마자)로: 예 สตม. → 태국 이민국, ปภ. → 재난방지청(DDPM).
    태국어판(validate.forbid_scripts 에 'thai' 없음)은 화면 글이 태국어라 건너뜀(2026-10-25)."""
    if not siteconf.forbids("thai", SITE):
        return
    def chk(where, v):
        for t in (v if isinstance(v, list) else [v]):
            m = THAI_SHOWN_RE.search(t) if isinstance(t, str) else None
            assert not m, (where, "화면에 태국 문자 금지 — 한국어/로마자로 고칠 것(TRANSLATION_RULES)", t[max(0, m.start() - 12):m.end() + 8])
            i = t.find("฿") if isinstance(t, str) else -1
            assert i < 0, (where, "'฿' 금지 — 글에서는 '바트'(예 350바트(약 1.41만 원)), ฿ 는 헤더 숫자 칸에만(TRANSLATION_RULES)", t[max(0, i - 12):i + 8])
    for s in data.get("stories", []):
        # source(매체 이름)는 카드 아래·출처 목록에 그대로 보임 → 'MGR Online (매니저 온라인)' 처럼 (2026-10-04 추가)
        for k in KO_FIELDS + ("tags", "source"):
            if k in s: chk((s.get("id"), k), s[k])
        chk((s.get("id"), "related.source"), [r.get("source") or "" for r in s.get("related") or [] if isinstance(r, dict)])
        if isinstance(s.get("issue"), dict): chk((s.get("id"), "issue.title"), s["issue"].get("title"))
        d = s.get("discussion")
        if isinstance(d, dict): chk((s.get("id"), "discussion"), [d.get("question") or "", d.get("operator_comment") or ""])
    br = data.get("briefing")
    chk("briefing", [b.get("text") or "" for b in br] if isinstance(br, list) else (br or ""))
    for i, k in enumerate(data.get((SITE.get("home_section") or {}).get("key") or "korea_top") or []):
        if isinstance(k, dict): chk(("korea_top", i), k.get("headline") or "")


# ---- 바트 → 원 환산(2026-10-05 추가) -------------------------------------------------
# 규칙(Mingoo 확인): 판 글의 바트 금액마다 바로 뒤에 원화 환산 '(약 N원)', 판 하나 = 환율 하나(data fx.THB_KRW).
# 10-05 아침판 '(약 14억6,271만 바트)'·'(약 13억678만 바트)' 가 원화 없이 라이브에 나감 → 원인: 이 검사(baht_ok)가
# for_me·quick_replies 에만 걸려 있었고 제목·요약·배경·후속·브리핑·오늘의 질문은 판 저장 때 안 봤음. 이제 krw_check 가 전부 보고 실패시킴.
#   금액 형식: 350 / 1,200 / 0.75 / 50만 / 1만6,000 / 13억678만 / 14억6,271만 / 3조2,000억 / 범위 300~500 · 1만~2만
KRW_FROM = "2026-10-02-pm"   # fx.THB_KRW 가 판에 들어간 첫 판 — 이 판부터 krw_check 실패 = 판 저장 실패
_NUM = r"\d[\d,]*(?:\.\d+)?"
_AMT = r"(?=\d)(?:%s\s*[조억만]\s*)*(?:%s)?" % (_NUM, _NUM)
BAHT_AMT_RE = re.compile(r"(?<![\d,.])(%s)(?:\s*[~\-–]\s*(%s))?\s*바트" % (_AMT, _AMT))
# 금액 뒤 원화: '바트(약 4.19만 원)' · '바트(약 281억~401억 원)' · 괄호 안 '바트, 약 588억 원)' · 굵게 '**110억 바트(약 …원)**' (2026-10-28: 3유효숫자)
KRW_AFTER_RE = re.compile(r"\**\s*(?:\(\s*|,\s*)약\s*[\d조억만,.\s~\-–]*원")
# 원 → 바트 역환산('1,000만 원(약 25만 바트)')은 이미 원화가 앞에 있으므로 통과
KRW_BEFORE_RE = re.compile(r"원\s*\(\s*약\s*$")


def ko_amount(s):
    """'14억6,271만' → 1462710000, '1만6,000' → 16000, '0.75' → 0.75, '3조2,000억' → 3.2e12. 숫자 없으면 None."""
    s = re.sub(r"[\s,]", "", s or "")
    if not re.search(r"\d", s):
        return None
    total, units = 0.0, {"조": 10 ** 12, "억": 10 ** 8, "만": 10 ** 4}
    for num, u in re.findall(r"(\d+(?:\.\d+)?)([조억만]?)", s):
        total += float(num) * units.get(u, 1)
    return total


def _man(n):
    """0~9999 → '4,190' 처럼 쉼표. (하위 호환·테스트용)"""
    return "{:,}".format(int(n))


def _round_sig(n, sig=3):
    """양수를 유효숫자 sig자리로 반올림한 정수. 0 이하면 0.
    2026-10-28 Max: 환산 금액은 전체 규모에 맞게 뒷자리를 줄인다(약 3유효숫자)."""
    from math import floor, log10
    n = int(round(float(n)))
    if n <= 0:
        return 0
    digits = floor(log10(n)) + 1
    if digits <= sig:
        return n
    factor = 10 ** (digits - sig)
    return int(round(n / factor) * factor)


def _fmt_coef(n):
    """단위 앞 계수: 123 / 12.3 / 1.23 (불필요 소수·Trailing 0 제거)."""
    n = float(n)
    if abs(n - round(n)) < 1e-9:
        return "{:,}".format(int(round(n)))
    s = ("{:.2f}".format(n)).rstrip("0").rstrip(".")
    if "." in s:
        a, b = s.split(".", 1)
        return "{:,}".format(int(a)) + "." + b
    return "{:,}".format(int(s))


def krw_text(won):
    """원 금액 → 약 3유효숫자 + 한국 단위(만·억·조).
    예: 588→590원, 1,234,567→123만 원, 12,345,678,900→123억 원.
    (2026-10-28 Max: 환산 원화는 규모에 맞게 뒷자리 생략, 원문 통화 금액은 그대로)"""
    w = _round_sig(abs(won), 3)
    if w >= 10 ** 12:
        return _fmt_coef(w / 10 ** 12) + "조 원"
    if w >= 10 ** 8:
        return _fmt_coef(w / 10 ** 8) + "억 원"
    if w >= 10 ** 4:
        return _fmt_coef(w / 10 ** 4) + "만 원"
    if w >= 100:
        w = int(round(w / 10.0) * 10)  # 원 단위 표기는 10원 자리로(588→590)
    return "%s원" % "{:,}".format(w)


def cny_text(yuan):
    """인민폐 금액 → 약 3유효숫자 + 万/亿. 예: 70 / 1.23万 / 123亿 (뒤에 '元'은 호출측에서)."""
    a = abs(yuan)
    if a < 1:   # 2026-10-29: 1元 미만을 정수로 반올림하면 '约0元' — 소수로 쓴다(0.2 / 0.04)
        t = ("%.1f" % a) if round(a, 1) >= 0.1 else ("%.2f" % max(a, 0.01))
        return t[:-2] if t.endswith(".0") else t
    w = _round_sig(a, 3)
    if w >= 10 ** 8:
        return _fmt_coef(w / 10 ** 8) + "亿"
    if w >= 10 ** 4:
        return _fmt_coef(w / 10 ** 4) + "万"
    if w >= 100:
        w = int(round(w / 10.0) * 10)
    return "{:,}".format(w)


def krw_for(amount_text, rate):
    """'13억678만' + 40.19 → '약 526억 원'(3유효). 범위 '300~500' → '약 1.21만~2.01만 원'."""
    parts = re.split(r"\s*[~\-–]\s*", amount_text.strip())
    vals = [ko_amount(p) for p in parts]
    if len(vals) == 2 and re.search(r"[조억만]\s*$", parts[1]) and not re.search(r"[조억만]", parts[0]):
        u = re.search(r"([조억만])\s*$", parts[1]).group(1)   # '1~2만' → 앞 숫자도 만
        vals[0] = ko_amount(parts[0] + u)
    return "약 " + "~".join(krw_text(v * rate).replace(" 원", "").replace("원", "") for v in vals[:-1]) + \
        ("~" if len(vals) > 1 else "") + krw_text(vals[-1] * rate)


def _shown_texts(data):
    """화면에 보이는 판 글 (where, text) — thai_check 와 같은 범위(한국 뉴스 제목·키워드·매체 이름은 남의 글이라 제외)."""
    for s in data.get("stories", []):
        for k in KO_FIELDS:
            v = s.get(k)
            for i, t in enumerate(v if isinstance(v, list) else [v]):
                if isinstance(t, str): yield (s.get("id"), k, i), t
        if isinstance(s.get("issue"), dict): yield (s.get("id"), "issue.title"), s["issue"].get("title") or ""
        d = s.get("discussion")
        if isinstance(d, dict):
            for k in ("question", "operator_comment"):
                if d.get(k): yield (s.get("id"), "discussion." + k), d[k]
    br = data.get("briefing")
    for i, b in enumerate(br if isinstance(br, list) else [{"text": br or ""}]):
        yield ("briefing", i), (b.get("text") or "") if isinstance(b, dict) else str(b)


def krw_missing(data):
    """원화 환산이 없는 바트 금액 → [(where, '금액 바트', '넣을 글', 앞뒤 글)]. 넣을 글은 판 환율(fx.THB_KRW)로 계산."""
    rate = (data.get("fx") or {}).get("THB_KRW")
    out = []
    for where, t in _shown_texts(data):
        for m in BAHT_AMT_RE.finditer(t):
            k = KRW_AFTER_RE.match(t, m.end())
            # 소수점 '원'은 금지. 단 '1.41만 원'·'5.75억 원'처럼 만·억·조 앞 계수는 허용(2026-10-28 3유효숫자).
            if k and re.search(r"\d\.\d", k.group(0)) and not re.search(r"\d\.\d+\s*[만억조]", k.group(0)):
                out.append((where, m.group(0), "원화는 정수로(소수점 없이): " + krw_for(m.group(0)[:-2].strip(), rate) if rate else "원화는 정수로", k.group(0)))
                continue
            if k or KRW_BEFORE_RE.search(t[:m.start()]):
                continue
            amt = m.group(0)[:-2].strip()
            inside = t[m.end():m.end() + 1] == ")"
            sug = ((", " if inside else "(") + krw_for(amt, rate) + ("" if inside else ")")) if rate else "(환율 fx.THB_KRW 없음)"
            out.append((where, m.group(0), sug, t[max(0, m.start() - 12):m.end() + 8]))
    return out


def krw_check(data):
    """KRW_FROM 판부터: 바트 금액에 원화 환산이 하나라도 없으면 예외(판 저장 실패). 넣을 글을 메시지에 같이 보여 줌."""
    if _ed_key(data.get("id", "")) < _ed_key(KRW_FROM):
        return
    rate = (data.get("fx") or {}).get("THB_KRW")
    miss = krw_missing(data)
    assert not miss, ("바트 금액 %d건에 원화 환산 없음 — 판 환율 %s 로 '바트' 바로 뒤에 넣을 것(TRANSLATION_RULES: 바트마다 (약 N원))" % (len(miss), rate),
                      ["%s: '%s' 뒤에 '%s' ← …%s…" % (w, a, g, c) for w, a, g, c in miss])


# ---- 泰铢 → 元 환산(중국어판, 2026-10-18 R-zh-2) — 한국판 krw_check 와 같은 자리, 표기만 언어별(site/zh.json currency.format) ----
#   규칙(TRANSLATION_RULES.zh.md): 금액마다 '350泰铢（约70元）' · 판 하나 = 환율 하나(data fx.THB_CNY). 반각 괄호 '(约…元)' 도 받아 줌
_ZNUM = r"\d[\d,]*(?:\.\d+)?"
CNY_BAHT_RE = re.compile(r"(?<![\d,.])(%s)\s*(?:[万亿]\s*)?(?:[~\-–至]\s*%s\s*(?:[万亿]\s*)?)?泰铢" % (_ZNUM, _ZNUM))
CNY_AFTER_RE = re.compile(r"\**\s*[（(]\s*约\s*[\d,.万亿~\-–至\s]*元")
CNY_BEFORE_RE = re.compile(r"元\s*[（(]\s*约\s*$")


def cny_missing(data):
    out = []
    for where, t in _shown_texts(data):
        for m in CNY_BAHT_RE.finditer(t):
            if CNY_AFTER_RE.match(t, m.end()) or CNY_BEFORE_RE.search(t[:m.start()]):
                continue
            out.append((where, m.group(0), t[max(0, m.start() - 10):m.end() + 10]))
    return out


def cny_check(data):
    rate = (data.get("fx") or {}).get("THB_CNY")
    miss = cny_missing(data)
    assert not miss, ("泰铢 금액 %d건에 인민币 환산 없음 — 판 환율 %s 로 '泰铢' 바로 뒤에 （约N元）(TRANSLATION_RULES.zh)" % (len(miss), rate),
                      ["%s: '%s' ← …%s…" % (w, a, c) for w, a, c in miss])


# ---- 원 → 바트 환산(태국어판 kstar, 2026-10-25 Claude) — 한국 연예 기사 금액(วอน)마다 '(ประมาณ N บาท)' · 판 환율 fx.KRW_THB ----
_TNUM = r"\d[\d,]*(?:\.\d+)?"
_TMUL = r"(?:ล้านล้าน|แสนล้าน|หมื่นล้าน|พันล้าน|ร้อยล้าน|สิบล้าน|ล้าน|แสน|หมื่น|พัน)"
THB_WON_RE = re.compile(r"(?<![\d,.])%s\s*%s?(?:\s*[~\-–]\s*%s\s*%s?)?\s*วอน" % (_TNUM, _TMUL, _TNUM, _TMUL))
THB_AFTER_RE = re.compile(r"\**\s*[（(]\s*(?:ประมาณ|ราว|~)\s*[\d,.~\-–\s]*(?:ล้านล้าน|แสนล้าน|หมื่นล้าน|พันล้าน|ล้าน|แสน|หมื่น|พัน)?\s*บาท")
TH_MUL = {"ล้านล้าน": 1e12, "แสนล้าน": 1e11, "หมื่นล้าน": 1e10, "พันล้าน": 1e9, "ร้อยล้าน": 1e8, "สิบล้าน": 1e7, "ล้าน": 1e6, "แสน": 1e5, "หมื่น": 1e4, "พัน": 1e3}


def th_amount(s):
    """'1,500 ล้าน' → 1.5e9 (숫자 + 태국어 단위)."""
    m = re.match(r"\s*(%s)\s*(%s)?" % (_TNUM, _TMUL), s)
    return float(m.group(1).replace(",", "")) * TH_MUL.get(m.group(2) or "", 1) if m else 0.0


def thb_text(v):
    """바트 금액을 태국어 표기로: 1,234 / 12.5 ล้าน / 1,200 ล้าน."""
    if v >= 1e6:
        x = v / 1e6
        return ("{:,.1f}".format(x).rstrip("0").rstrip(".") if x < 100 else "{:,}".format(int(round(x)))) + " ล้าน"
    return "{:,}".format(int(round(v)))


def thb_for(amount_text, rate):
    """'5 ล้าน' 원 → 'ประมาณ 0.1 ล้าน บาท' 식 글(괄호 없이)."""
    parts = re.split(r"\s*[~\-–]\s*", amount_text.strip())
    vals = [th_amount(p) for p in parts if re.search(r"\d", p)]
    if len(vals) == 2 and re.search(_TMUL + r"\s*$", parts[1]) and not re.search(_TMUL, parts[0]):
        vals[0] *= TH_MUL[re.search("(" + _TMUL + r")\s*$", parts[1]).group(1)]
    x = "~".join(thb_text(v * rate) for v in vals)
    return "ประมาณ " + x + ("บาท" if x.endswith("ล้าน") else " บาท")   # '12.7 ล้านบาท' · '191 บาท'


def thb_missing(data):
    rate = (data.get("fx") or {}).get("KRW_THB")
    out = []
    for where, t in _shown_texts(data):
        for m in THB_WON_RE.finditer(t):
            if THB_AFTER_RE.match(t, m.end()):
                continue
            out.append((where, m.group(0), ("(" + thb_for(m.group(0)[:-3], rate) + ")") if rate else "(환율 fx.KRW_THB 없음)", t[max(0, m.start() - 10):m.end() + 10]))
    return out


def thb_check(data):
    miss = thb_missing(data)
    assert not miss, ("วอน 금액 %d건에 바트 환산 없음 — 판 환율 fx.KRW_THB 로 'วอน' 바로 뒤에 (ประมาณ N บาท)" % len(miss),
                      ["%s: '%s' 뒤에 '%s' ← …%s…" % (w, a, g, c) for w, a, g, c in miss])


def money_check(data):
    """판 글 금액 환산 검사 — 언어판 설정 currency.check(ko=krw_check, zh=cny_check, th=thb_check)."""
    ck = SITE.get("currency", {}).get("check")
    return cny_check(data) if ck == "cny_check" else thb_check(data) if ck == "thb_check" else krw_check(data)


def money_ok(text):
    """한 문장 검사(for_me·quick_replies): ko=바트(약 N원), zh=泰铢（约N元）, th=วอน (ประมาณ N บาท)."""
    ck = SITE.get("currency", {}).get("check")
    if ck == "cny_check":
        return not cny_missing({"briefing": [{"text": text}]})
    if ck == "thb_check":
        return not thb_missing({"briefing": [{"text": text}]})
    return baht_ok(text)


HANGUL_RE = re.compile(r"[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]")


def source_label(name, fallback=""):
    """매체 이름 표시용(2026-10-30). 화면에 태국 글자가 금지된 언어판이면 태국어 부분(괄호 안 원어 이름 등)을 뺀다.
    'Bangkok Biz News(กรุงเทพธุรกิจ)' → 'Bangkok Biz News', 전부 태국어면 fallback.
    (also[].source 에 태국 글자가 남아 판 미리보기(e/<판>/)를 못 만들고 404 가 나던 것 — thai_check 는 source·related.source 만 봤음)"""
    s = str(name or "").strip()
    if not thai_bad(s):
        return s
    s = re.sub(r"[(\[（［][^)\]）］]*[\u0E00-\u0E7F][^)\]）］]*[)\]）］]", "", s)   # 괄호 안에 태국 글자 → 괄호째
    s = THAI_RE.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–·/|,:")
    return s or fallback


def thai_bad(text):
    """한 문장에 태국 글자가 있고, 이 언어판이 태국 글자를 막는지(태국어판은 항상 False)."""
    return bool(siteconf.forbids("thai", SITE) and THAI_RE.search(text or ""))


def script_check(data):
    """언어판 금지 문자(site/<lang>.json validate.forbid_scripts): ko = cjk(한자·가나, 번역 잔재), zh = hangul(한글). thai 는 thai_check 가 따로."""
    fs = SITE.get("validate", {}).get("forbid_scripts", ["thai", "cjk"])
    if "cjk" in fs:
        cjk_check(data)
    if "hangul" in fs:
        def chk(where, v):
            for t in (v if isinstance(v, list) else [v]):
                m = HANGUL_RE.search(t) if isinstance(t, str) else None
                assert not m, (where, "이 언어판 글에 한글 금지(번역 잔재) — 화면 언어로 고칠 것", t[max(0, m.start() - 12):m.end() + 8])
        for where, t in _shown_texts(data):
            chk(where, t)
        for s in data.get("stories", []):   # 키워드·매체 이름도 화면에 보임
            for k in ("tags", "source"):
                if k in s: chk((s.get("id"), k), s[k])


# 추천 댓글은 독자 본인이 올리는 문장 — 겪지 않은 경험을 지어내게 만드는 표현 금지
FAKE_EXP_RE = re.compile(r"저도\s*(거기|그\s*동네|근처|여기)\s*(살|사는|살아)|제가\s*(직접|가\s*봤|가봤|겪|봤)|저도\s*(겪|당했|가\s*봤|가봤|다녀왔|봤어)|우리\s*(집|동네)도|저희\s*(집|동네|가게)")
LINK_RE = re.compile(r"https?://|www\.|\.(com|net|org|co|th|me|ly)\b", re.I)
_REG = None


def issue_registry():
    """tools/issues.json → {id: {...}} (없으면 빈 dict)."""
    global _REG
    if _REG is None:
        _REG = {}
        if ISSUES_FILE.exists():
            for it in json.loads(ISSUES_FILE.read_text(encoding="utf-8")).get("issues", []):
                _REG[it["id"]] = it
    return _REG


def baht_ok(text):
    """바트 금액마다 바로 뒤에 '(약 N원)' 원화 환산이 있는지(TRANSLATION_RULES)."""
    for m in re.finditer(r"\d[\d,.]*\s*(?:만|억|조)?\s*바트", text or ""):
        if not re.match(r"\s*\(약\s*[\d,.]+\s*(?:만|억|조)?\s*(?:\d[\d,.]*\s*(?:만|억)?\s*)?원", text[m.end():]):
            return False
    return True


EXTRAS_FROM = "2026-10-03-am"   # 이 판 id 보다 뒤 판은 다섯 필드 필수


def validate_extras(s):
    """impact / for_me / also / issue / quick_replies 형식 점검(있을 때만). 문제 있으면 예외."""
    sid = s["id"]
    if "impact" in s:
        im = s["impact"]
        assert isinstance(im, list) and len(im) <= 3 and len(set(im)) == len(im) and all(x in IMPACTS for x in im), \
            (sid, "impact 는 %s 중 0~3개 목록" % "/".join(IMPACTS), im)
    if "for_me" in s:
        fm = s["for_me"]
        assert isinstance(fm, str) and len(fm) <= 160, (sid, "for_me 는 한 문장(160자 이하) 문자열, 의미 없으면 \"\"")
        assert not thai_bad(fm), (sid, "for_me 에 태국 글자 금지")
        assert not blocked(fm) and money_ok(fm), (sid, "for_me 차단 키워드 또는 바트 금액에 (약 N원) 없음")
    if "also" in s:
        al = s["also"]
        assert isinstance(al, list) and len(al) <= 8, (sid, "also 는 최대 8개 목록")
        urls = set()
        for a in al:
            assert isinstance(a, dict) and a.get("source") and str(a.get("url", "")).startswith("http"), (sid, "also = [{source, url}]", a)
            assert "news.google.com" not in a["url"], (sid, "also 에 Google News 중계 링크 금지 — 실제 기사 URL", a["url"])
            assert a["url"] != s.get("url") and a["url"] not in urls, (sid, "also 에 원문·중복 URL", a["url"])
            urls.add(a["url"])
    if s.get("issue") is not None:
        iss = s["issue"]
        assert isinstance(iss, dict) and ISSUE_ID_RE.match(str(iss.get("id", ""))) and iss.get("title"), (sid, "issue = {id(영문 소문자·숫자·-), title}", iss)
        assert not thai_bad(iss["title"]) and len(iss["title"]) <= 40, (sid, "issue.title 은 한국어 40자 이하")
        reg = issue_registry()
        assert iss["id"] in reg, (sid, "issue id '%s' 가 tools/issues.json 에 없음 — 새 이슈면 등록부에 먼저 추가" % iss["id"])
    if "quick_replies" in s:
        qr = s["quick_replies"]
        assert isinstance(qr, list) and (len(qr) == 0 or 3 <= len(qr) <= 4), (sid, "quick_replies 는 3~4개(없으면 빈 목록)")
        for q in qr:
            assert isinstance(q, str) and 2 <= len(q.strip()) <= 40, (sid, "quick_replies 한 줄 2~40자", q)
            assert not thai_bad(q) and not LINK_RE.search(q) and not blocked(q), (sid, "quick_replies 태국 글자·링크·차단 키워드 금지", q)
            assert not FAKE_EXP_RE.search(q), (sid, "quick_replies 에 겪지 않은 경험을 꾸미는 표현 금지('저도 거기 살아요' 등)", q)
            assert money_ok(q), (sid, "quick_replies 바트 금액엔 (약 N원)", q)


def _blocklist():
    """tools/trend_blocklist.txt → [(원문 줄, 컴파일된 정규식)]."""
    global _BL
    if _BL is None:
        _BL = []
        for line in BLOCKLIST.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pat = line[3:] if line.startswith("re:") else re.escape(line)
            _BL.append((line, re.compile(pat, re.I)))
    return _BL


def blocked(text):
    """성인·선정적 키워드가 있으면 걸린 항목(문자열), 없으면 None."""
    for raw, rx in _blocklist():
        if rx.search(text or ""):
            return raw
    return None


def KR(headline, source, url, published=None, badge=None):
    """korea_top 한 줄: KR("제목", "연합뉴스", "https://…", "2026-10-03T06:10:00+07:00")"""
    d = dict(headline=headline, source=source, url=url)
    if published: d["published"] = published
    if badge: d["badge"] = badge
    return d


def label_for(date, edition):
    m, d = int(date[5:7]), int(date[8:10])
    if LANG != "ko":
        return SITE.get("label_format", "{m}/{d} {slot}").format(m=m, d=d, slot=EDITION_LABEL[edition])
    return "%d월 %d일 %s" % (m, d, EDITION_LABEL[edition])


def validate(data):
    """사람이 실수하기 쉬운 부분만 점검. 문제 있으면 예외."""
    eid = data["id"]
    m = ID_RE.match(eid)
    assert m, "id 형식 오류: %s (YYYY-MM-DD-am|pm|early|md)" % eid
    assert m.group(2) in SITE.get("slots", ["early", "am", "pm"]), "이 언어판(%s)에 없는 판 슬롯: %s" % (LANG, m.group(2))
    assert data["date"] == m.group(1) and data["edition"] == m.group(2), "id/date/edition 불일치"
    ids = [s["id"] for s in data["stories"]]
    assert len(ids) == len(set(ids)), "기사 id 중복"
    new = is_new_format(data)
    ok_ids = topic_ids_for(eid)
    for s in data["stories"]:
        if new:
            if s.get("topic") in TOPIC_ALIAS and s["topic"] not in ok_ids:
                raise AssertionError((s["id"], "topic '%s' 는 2026-10-03 저녁판부터 'east'(동부(촌부리·라용))로 통합됨 — east 를 쓸 것" % s["topic"]))
            assert s.get("topic") in ok_ids, (s["id"], "topic 은 %s 중 하나" % "/".join(TOPICS), s.get("topic"))
            sec = s.get("secondary", [])
            assert isinstance(sec, list) and len(sec) <= 3, (s["id"], "secondary 는 0~3개 목록")
            for t in sec:
                assert t not in TOPIC_ALIAS or t in ok_ids, (s["id"], "secondary '%s' → 'east'(동부(촌부리·라용))로 통합됨" % t)
                assert t in ok_ids and t != s["topic"], (s["id"], "secondary 오류", t)
            canon = [TOPIC_ALIAS.get(t, t) for t in [s["topic"]] + sec]
            assert len(canon) == len(set(canon)), (s["id"], "주제 중복(통합 뒤 같은 주제) — secondary 에서 빼기", canon)
            tags = s.get("tags") or []
            assert isinstance(tags, list) and 2 <= len(tags) <= 8 and all(isinstance(t, str) and t.strip() and not t.startswith("#") for t in tags), \
                (s["id"], "tags(키워드) 2~8개 필수, '#' 없이")
            if "category" in s:
                assert s["category"] in CATS, (s["id"], s["category"])
        else:
            assert s["category"] in CATS, (s["id"], s["category"])
        for k in ("headline", "summary", "source", "url", "title_th", "published"):
            assert s.get(k), (s["id"], "필수 필드 없음: " + k)
        assert s["url"].startswith("http"), (s["id"], s["url"])
        assert s["published"].endswith("+07:00"), (s["id"], "published 는 +07:00(방콕) ISO")
        datetime.fromisoformat(s["published"])
        for r in s.get("related", []):
            assert r["url"].startswith("http"), (s["id"], r)
    for s in data["stories"]:
        # 성인·선정적 기사 금지(공통 차단 목록). 이미지·영상은 아예 싣지 않는다.
        txt = " ".join([s["headline"], s["title_th"], " ".join(s.get("tags", [])), " ".join(s["summary"])])
        hit = blocked(txt)
        assert not hit, (s["id"], "성인·선정적 키워드(%s) — 기사를 빼거나 표현 확인 (tools/trend_blocklist.txt)" % hit)
        for k in ("image", "images", "img", "media", "video", "embed"):
            assert k not in s, (s["id"], "이미지·미디어 필드 금지: " + k)
        dsc = s.get("discussion")
        if dsc is not None:  # 💬 오늘의 질문(정적, tools/discussion.py apply 로만 넣음)
            assert isinstance(dsc, dict) and dsc.get("question") and dsc.get("operator_comment") and isinstance(dsc.get("approved"), bool), \
                (s["id"], "discussion = {question, operator_comment, approved: bool}")
            assert len(dsc["question"]) <= 200 and len(dsc["operator_comment"]) <= 500, (s["id"], "discussion 이 너무 김")
            assert not blocked(dsc["question"] + " " + dsc["operator_comment"]), (s["id"], "discussion 차단 목록 키워드")
        validate_extras(s)
        if new and eid > EXTRAS_FROM:   # 2026-10-03 저녁판부터: 다섯 필드를 판마다 반드시 채움(값은 비어도 됨, quick_replies 는 3~4개)
            miss = [k for k in ("impact", "for_me", "also", "issue", "quick_replies") if k not in s]
            assert not miss, (s["id"], "판마다 채울 필드 없음: %s (README '판마다 채울 필드(2026-10-03 추가)')" % ", ".join(miss))
            assert 3 <= len(s["quick_replies"]) <= 4, (s["id"], "quick_replies 3~4개 필수")
        if s.get("category") == "visa" or s.get("topic") == "visa" or "visa" in s.get("secondary", []):
            # 외국인·비자: 저볼륨이라 최대 7일 전 기사 허용(그 이상은 금지)
            age = datetime.fromisoformat(data["generated"]) - datetime.fromisoformat(s["published"])
            assert age.days < 8, (s["id"], "외국인·비자 기사는 7일 이내만")
    # trends is a legacy field. It is intentionally optional and ignored: old editions
    # may retain it for history, while new editions do not collect or render it.
    # discussion(오늘의 질문) 건수 제한 없음 — 2026-10-03 운영자 결정: 판의 모든 기사에(승인된 것만 화면에)
    kt = data.get((SITE.get("home_section") or {}).get("key") or "korea_top")   # 홈 나라 칸: ko=korea_top, zh=china_top (R-zh-3)
    if kt is not None:   # 🇰🇷 오늘의 한국 주요 뉴스(tools/fetch_korea.py) — 최대 10건, 링크 필수
        assert isinstance(kt, list) and len(kt) <= 10, "korea_top 은 최대 10건 목록"
        for i, k in enumerate(kt):
            assert isinstance(k, dict) and k.get("headline") and k.get("source"), ("korea_top", i, "headline·source 필수")
            assert str(k.get("url", "")).startswith("http"), ("korea_top", i, "url(원문 링크) 필수")
            assert "news.google.com" not in k["url"], ("korea_top", i, "Google News 중계 링크 말고 실제 기사 URL(fetch_korea.py --decode-only)")
            assert len(k["headline"]) <= 80, ("korea_top", i, "제목은 짧게(80자 이하)")
            if k.get("published"):
                assert k["published"].endswith("+07:00"), ("korea_top", i, "published 는 +07:00")
                datetime.fromisoformat(k["published"])
            assert not blocked(k["headline"]), ("korea_top", i, "차단 목록 키워드")
    for h in data["highlights"]:
        assert h in ids, "highlights 에 없는 id: " + h
    assert len(data["highlights"]) == 3, "highlights 는 3개"
    script_check(data)   # ko = cjk_check(한자·가나), zh = 한글 금지 — site/<lang>.json validate (R-zh-2)
    thai_check(data)
    money_check(data)   # 2026-10-05: 바트 금액마다 원화 환산(없으면 판 저장 실패). zh = 泰铢（约N元）
    br = data.get("briefing")
    if new:
        assert isinstance(br, list), "새 형식 briefing 은 [{topic, text, story_id}] 목록 (newslib.B 사용)"
    if isinstance(br, list):
        assert 4 <= len(br) <= 7, "briefing 은 5~6줄(4~7 허용)"
        for i, b in enumerate(br):
            assert isinstance(b, dict) and b.get("topic") in ok_ids, ("briefing", i, "topic 오류(파타야·시라차 = east)", b.get("topic") if isinstance(b, dict) else b)
            assert b.get("text") and re.search(r"\*\*[^*]+\*\*", b["text"]), ("briefing", i, "text 에 **굵게** 핵심어/숫자 1곳 이상")
            assert len(b["text"]) <= 120, ("briefing", i, "한 줄은 짧게(120자 이하)")
            assert b.get("story_id") in ids, ("briefing", i, "story_id 가 기사 id 가 아님", b.get("story_id"))
            assert not blocked(b["text"]), ("briefing", i, "차단 목록 키워드")
    else:
        assert isinstance(br, str) and br.strip(), "briefing 없음"


def _ed_key(eid):
    m = ID_RE.match(eid)
    return (m.group(1), EDITION_ORDER[m.group(2)]) if m else (eid, 9)


def topic_ids_for(eid):
    """그 판에서 허용하는 주제 id: 새 11개 + (2026-10-03 아침판까지만) 옛 pattaya·sriracha 별칭."""
    ids = set(TOPICS)
    if _ed_key(eid) <= _ed_key(ALIAS_UNTIL):
        ids |= set(TOPIC_ALIAS)
    return ids


def is_new_format(data):
    """기사에 topic 이 하나라도 있거나 briefing 이 목록이면 새 형식으로 검증."""
    return isinstance(data.get("briefing"), list) or any("topic" in s for s in data["stories"])


def topics_of(s):
    """기사의 주제 목록(새 형식: topic+secondary / 옛 형식: category 를 대략 매핑 — 집계용)."""
    if s.get("topic"):
        out = []
        for t in [s["topic"]] + list(s.get("secondary", [])):
            t = TOPIC_ALIAS.get(t, t)
            if t not in out:
                out.append(t)
        return out
    return [{"politics": "poleco", "economy": "poleco", "society": "society", "local": "east",
             "visa": "visa", "sns": "ent"}.get(s.get("category"), "society")]


def coverage_report(data):
    """구성 점검(경고만). 반환: 경고 문자열 목록."""
    st, warn = data["stories"], []
    if not is_new_format(data):
        warn.append("옛 형식(category·문단 브리핑) — README '기사 스키마'의 새 형식(topic/secondary/tags, 브리핑 목록)을 쓰세요")
    lo, hi = TARGETS["stories"]
    if not lo <= len(st) <= hi:
        warn.append("기사 %d건 (목표 %d~%d건, 실제 뉴스가 없으면 적어도 됨)" % (len(st), lo, hi))
    any_ = lambda t: sum(1 for s in st if t in topics_of(s))
    v = any_("visa"); lo, hi = TARGETS["visa"]
    if "visa" in TOPICS and (v < lo or v > 8):
        warn.append("외국인·비자 %d건 (목표 %d~%d, 최대 8)" % (v, lo, hi))
    for t in TARGETS["places"] + TARGETS["want"]:
        if t in TOPICS and not any_(t):   # 이 언어판에 없는 주제는 건너뜀(태국어판 kstar = 연예 주제만)
            warn.append("%s 기사 0건 — 실제 뉴스가 있으면 1건 이상" % TOPICS[t])
    return warn

# 정기 실행 안전장치(2026-10-03): 판 스크립트가 옛 주제(pattaya·sriracha 또는 한국어 '파타야'·'시라차')를 써도
# write_edition 이 검증 전에 east 로 바꾸고 경고만 출력(실패 아님). validate() 자체는 그대로 엄격.
TOPIC_AUTOFIX = {"pattaya": "east", "sriracha": "east", "파타야": "east", "시라차": "east"}


def _fix_tid(t):
    return TOPIC_AUTOFIX.get(t.strip() if isinstance(t, str) else t, t)


def normalize_topics(data):
    """기사 topic·secondary·브리핑 topic 의 옛 주제 값을 east 로 바꿈(중복 제거). 바꾼 내역 목록 반환."""
    fixed = []
    for s in data.get("stories", []):
        t = s.get("topic")
        if t is not None and _fix_tid(t) != t:
            s["topic"] = _fix_tid(t); fixed.append("%s topic %r→east" % (s.get("id"), t))
        sec = s.get("secondary")
        if isinstance(sec, list):
            out = []
            for x in sec:
                y = _fix_tid(x)
                if y != x:
                    fixed.append("%s secondary %r→east" % (s.get("id"), x))
                if y != s.get("topic") and y not in out:
                    out.append(y)
            if out != sec:
                s["secondary"] = out
    for b in data.get("briefing") or []:
        if isinstance(b, dict) and b.get("topic") is not None and _fix_tid(b["topic"]) != b["topic"]:
            fixed.append("briefing topic %r→east" % b["topic"]); b["topic"] = _fix_tid(b["topic"])
    for f in fixed:
        print("경고(자동 수정): 옛 주제 → 'east'(동부(촌부리·라용)):", f)
    return fixed


def build_stamp():
    """판을 실제로 만든 시각(방콕, 초 단위) — 'generated' 는 이것만 씀(손으로 쓰지 않음)."""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")


def write_edition(data, merge_discussions=True, keep_generated=False):
    """data/<id>.json + data/<id>.js 저장 후 index 재생성.
    tools/discussions/<id>.json(운영자가 승인한 💬 오늘의 질문, tools/discussion.py apply)이 있으면 다시 합친다.
    2026-10-05: 'generated'(업데이트 시각·'몇 시간 전' 기준) = 판을 만든 실제 시각(build_stamp)을 여기서 자동으로 넣는다.
      10-05 아침판에서 tools/editions/<id>.py 에 손으로 쓴 예정 시각 07:55 가 그대로 나가 실제(07:23)보다 미래 시각이 보였음 →
      판 파일에 손으로 쓴 generated 는 무시(경고). keep_generated=True = 이미 만든 판을 다시 저장할 때만(discussion.py apply/clear 등) 원래 값 유지."""
    if not keep_generated:
        real = build_stamp()
        hand = data.get("generated")
        if hand and hand != real:
            print("점검(경고): 판 파일에 손으로 쓴 generated(%s)는 무시 → 실제 만든 시각 %s 로 저장" % (hand, real), file=sys.stderr)
        data["generated"] = real
    if merge_discussions:
        f = pathlib.Path(__file__).resolve().parent / "discussions" / (data["id"] + ".json")
        if f.exists():
            by = {s["id"]: s for s in data["stories"]}
            for x in json.loads(f.read_text(encoding="utf-8")):
                if x["id"] in by and x.get("approved") is True:
                    by[x["id"]]["discussion"] = dict(question=x["question"], operator_comment=x["operator_comment"], approved=True)
    if is_new_format(data):
        normalize_topics(data)
    validate(data)
    eid = data["id"]
    (DATA / (eid + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    js = "window.NEWS_DATA = window.NEWS_DATA || {};\nwindow.NEWS_DATA[%s] = %s;\n" % (
        json.dumps(eid), json.dumps(data, ensure_ascii=False))
    (DATA / (eid + ".js")).write_text(js, encoding="utf-8")
    build_index()
    print("saved", eid, "stories:", len(data["stories"]),
          {t: sum(1 for s in data["stories"] if t in topics_of(s)) for t in TOPIC_ORDER})
    for w in coverage_report(data):
        print("점검(경고):", w)


# "지연 발행" 라벨은 코드가 자동 판정(2026-10-23 맥스님 결정 — 판 파일의 delayed_publication 손 표시는 쓰지 않음).
# 예정 게시 시각 + 30분 이 지나서 만들어진(generated) 판만 지연. 10-26 전 판은 옛 예정(07:08·18:08) 기준.
DELAY_GRACE_MIN = 30
def _due_hm(date, edition):
    new = date >= "2026-10-26"
    return {"am": (7, 0) if new else (7, 8), "pm": (18, 0) if new else (18, 8), "md": (13, 0), "early": None}.get(edition)


def is_delayed(date, edition, generated):
    hm = _due_hm(date, edition)
    if not hm or not generated:
        return False
    try:
        g = datetime.fromisoformat(generated)
        due = datetime.fromisoformat("%sT%02d:%02d:00+07:00" % (date, hm[0], hm[1]))
    except ValueError:
        return False
    return (g - due).total_seconds() > DELAY_GRACE_MIN * 60


def build_index():
    """data/*.json 을 훑어 index.json / index.js 재생성 (최신 판이 맨 앞 = 기본 화면)."""
    eds = []
    for p in sorted(DATA.glob("20*.json")):
        m = ID_RE.match(p.stem)
        if not m:
            print("경고: 규칙에 맞지 않는 파일은 index 에서 제외:", p.name, file=sys.stderr)
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        date, ed = m.group(1), m.group(2)
        label = label_for(date, ed)
        if is_delayed(date, ed, d.get("generated", "")):
            label += " · " + (SITE.get("delayed_label", "延迟发布") if LANG != "ko" else "지연 발행")
        eds.append(dict(id=p.stem, date=date, edition=ed, label=label,
                        generated=d.get("generated", ""), stories=len(d.get("stories", []))))
    eds.sort(key=lambda e: (e["date"], EDITION_ORDER[e["edition"]], e["generated"]), reverse=True)
    idx = {"latest": eds[0]["id"] if eds else None, "editions": eds, "dates": [e["id"] for e in eds]}
    (DATA / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "index.js").write_text("window.NEWS_INDEX = %s;\n" % json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    print("index:", [(e["id"], e["label"]) for e in eds])
    build_ads()
    build_issues(eds)
    return idx


def build_issues(eds=None):
    """🗓️ 이슈 타임라인: tools/issues.json(등록부·옛 판 members) + 판 기사 issue 필드 → data/issues.json|js.
    {updated, issues: {id: {title, items:[{edition, label, story, headline, published}]}}} (items 는 시간순)"""
    reg = issue_registry()
    if eds is None:
        eds = json.loads((DATA / "index.json").read_text(encoding="utf-8"))["editions"]
    labels = {e["id"]: e["label"] for e in eds}
    out = {k: dict(title=v["title"], items=[]) for k, v in reg.items()}
    seen = set()
    def add(iid, eid, s):
        if iid not in out or (eid, s["id"]) in seen:
            return
        seen.add((eid, s["id"]))
        out[iid]["items"].append(dict(edition=eid, label=labels.get(eid, eid), story=s["id"], headline=s["headline"], published=s.get("published", "")))
    cache = {}
    def load(eid):
        if eid not in cache:
            p = DATA / (eid + ".json")
            cache[eid] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"stories": []}
        return cache[eid]
    for e in eds:
        for s in load(e["id"]).get("stories", []):
            if isinstance(s.get("issue"), dict) and s["issue"].get("id"):
                add(s["issue"]["id"], e["id"], s)
    for iid, v in reg.items():
        for m in v.get("members", []):
            st = [s for s in load(m["edition"]).get("stories", []) if s["id"] == m["story"]]
            if m["edition"] in labels and st:
                add(iid, m["edition"], st[0])
            else:
                print("경고: issues.json members 에 없는 기사:", iid, m, file=sys.stderr)
    order = {e["id"]: i for i, e in enumerate(reversed(eds))}
    for v in out.values():
        v["items"].sort(key=lambda x: (x["published"] or "", order.get(x["edition"], 0)))
    out = {k: v for k, v in out.items() if v["items"]}
    doc = dict(updated=max([e.get("generated", "") for e in eds] or [""]), issues=out)
    (DATA / "issues.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "issues.js").write_text("window.TN_ISSUES = %s;\n" % json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print("issues:", {k: len(v["items"]) for k, v in out.items()})


def build_ads():
    """data/ads.json(광고 자리 설정) → data/ads.js(window.TN_ADS, file:// 용). 없으면 아무것도 안 함."""
    src = DATA / "ads.json"
    if not src.exists():
        return
    ads = json.loads(src.read_text(encoding="utf-8"))
    for sl in ads.get("slots", []):
        assert sl.get("id") in ("top", "mid", "korea-mid", "home-mid", "china-mid", "infeed", "drawer", "footer", "nearby-food", "nearby-massage", "nearby-pet", "nearby-beauty", "nearby-moto",
                             "nearby-hair", "nearby-mart",
                             "region-east", "region-bangkok", "region-north", "region-south", "region-other"), ("ads", sl.get("id"))  # region-* = 내 피드 지역 광고(2026-10-03 야간)  # hair·mart = 10-03 v1 옛 자리(지금 화면 없음, 남아 있어도 무해)
        for it in sl.get("items", []):
            for k in ("image", "link"):
                assert not it.get(k) or str(it[k]).startswith("https://"), ("ads", sl["id"], k, "https:// 만")
    campaign = ads.get("campaign")
    if campaign and campaign.get("enabled"):
        items = campaign.get("items", [])
        assert len(items) == 6 and len({x["id"] for x in items}) == 6, "campaign: six unique advertisers required"
        assert {x["id"]: x["weight"] for x in items} == {"dragon": 40, "seven": 12, "suwon": 12, "lounge": 12, "dongwon": 12, "kt": 12}, "campaign: 40/12 weights required"
        assert all(x.get("approved") is True for x in items), "campaign: unapproved creative"
        for key in ("creatives_url", "css_url"):
            path = campaign[key].split("?", 1)[0]
            assert path.startswith("assets/ads/partners/") and ".." not in path, "campaign: invalid asset path"
            assert (ROOT / path).is_file(), "campaign: missing " + path
    # 드래곤 스웨디시 배너 데이터(assets/ads/massage/ad.json)를 같이 실어 화면이 바로(동기) 그리게 함 — item.render == "dragon"
    dj = ROOT / "assets/ads/massage/ad.json"
    if dj.exists():
        dg = json.loads(dj.read_text(encoding="utf-8"))
        ads["dragon"] = {k: dg.get(k) for k in ("id", "label", "title", "link", "tel", "kakao_url", "line_url", "display")}
        for k in ("link", "kakao_url", "line_url"):
            assert not ads["dragon"].get(k) or str(ads["dragon"][k]).startswith("https://"), ("ads dragon", k, "https:// 만")
        assert str(ads["dragon"].get("tel") or "tel:").startswith("tel:"), ("ads dragon", "tel")
    # 언어판(R-zh-8, 2026-10-18): data/ads.json 에 dragon_<lang>(그 언어 문구)이 있으면 그것을 배너 데이터로(링크·전화 검사 같음). 한국판은 위 그대로
    ov = ads.pop("dragon_" + LANG, None) if LANG != "ko" else None
    if isinstance(ov, dict):
        ads["dragon"] = {k: ov.get(k) for k in ("id", "label", "title", "link", "tel", "kakao_url", "line_url", "display")}
        ads["dragon"]["label"] = ads["dragon"].get("label") or ads.get("label")
        for k in ("link", "kakao_url", "line_url"):
            assert not ads["dragon"].get(k) or str(ads["dragon"][k]).startswith("https://"), ("ads dragon_" + LANG, k, "https:// 만")
    (DATA / "ads.js").write_text("window.TN_ADS = %s;\n" % json.dumps(ads, ensure_ascii=False), encoding="utf-8")



if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "check":
        # python3 tools/newslib.py check data/<id>.json … : 저장된 판 검증 + 구성 점검
        for f in sys.argv[2:]:
            d = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
            if "id" not in d:   # 2026-09-29-early 같은 초기 형식 — 화면 태국 문자 검사만
                thai_check(d); print("건너뜀(초기 형식, id 없음 — 태국 문자 검사만 통과):", f); continue
            validate(d)
            print("OK", f, "새 형식" if is_new_format(d) else "옛 형식", "| 경고:", coverage_report(d) or "없음")
    else:
        build_index()
