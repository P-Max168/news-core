# -*- coding: utf-8 -*-
"""카카오톡 공유 키트 — 판(edition) 하나로 이미지 카드·링크 미리보기(OG)·메시지 문구를 만든다.

    python3 tools/share_kit.py                # data/index.json 의 latest 판
    python3 tools/share_kit.py 2026-10-02-pm  # 특정 판
    옵션: --pick pt1,vi2,...  카드·메시지 기사 순서를 직접 지정(첫 번째가 큰 카드)
          --n 5               카드에 넣을 기사 수(3~5, 기본 5) / 메시지는 앞 3건
          --no-main-link      메시지에서 포털 메인 링크 줄 빼기
          --no-publish        og/·e/ 는 건드리지 않고 share/ 만 만들기
          --out DIR           share/ 대신 DIR 에 만들기(시험용, --no-publish 포함 — share/·og/·e/ 안 건드림)

만드는 파일
  share/<id>.png        1080x1350 세로 카드(오픈채팅에 사진으로 올리기)
  share/<id>-og.png     1200x630 링크 미리보기 이미지
  share/<id>.txt        카카오톡 메시지 문구(링크 1~2개)
  share/<id>-card.html, share/<id>-og.html  렌더에 쓴 HTML(확인용)
  og/<id>.png, og/latest.png(최신 판일 때만)  ← 사이트에 올릴 OG 이미지
  e/<id>/index.html     판별 OG 태그 + 판 기사 전체 정적 HTML(검색용, tools/seo.py) → 사람은 ../../?ed=<id> 로 이동
share/ 는 .gitignore(올리지 않음). og/ e/ 는 사이트에 올릴 파일(배포 스크립트에 경로 추가 필요).

기사 고르기(기본): 🏖️동부(촌부리·라용) 2건 → 🛂외국인·비자 1건(주 주제 +2, 제목·지역에 촌부리·라용 지명 +1,
주요 뉴스(highlights) +1, 동점이면 편집 순서) → 나머지는 주요 뉴스 순서 → 편집 순서.
주제는 화면과 똑같이 assets/topics.js(옛 판 매핑 포함)를 node 로 돌려서 구한다(node 없으면 topic/category 로 대충).
문장은 데이터의 headline 을 그대로 쓰고, 짧은 형태는 '…' 앞부분만 자른다(지어내지 않음).
"""
import argparse, asyncio, html, json, pathlib, re, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://tnews.pmaxone.com/"
SHORT = "tnews.pmaxone.com"
UPDATE_LINE = "매일 아침 7시·저녁 6시 업데이트"

TOPICS = {  # assets/topics.js 와 같은 값(이모지·색)
    "east": ("동부(촌부리·라용)", "🏖️", "#0b7285"), "bangkok": ("방콕", "🏙️", "#495057"),
    "north": ("북부", "⛰️", "#5c940d"), "south": ("남부", "🏝️", "#1971c2"), "poleco": ("정치·경제", "🏛️", "#3b5bdb"),
    "society": ("사회·사건사고", "🚨", "#d9480f"), "visa": ("외국인·비자", "🛂", "#6741d9"),
    "life": ("생활·물가·부동산", "🛒", "#0c8f6a"), "travel": ("여행·맛집", "🍜", "#e67700"),
    "ent": ("연예·스포츠·SNS", "💬", "#c2255c"), "weather": ("날씨·교통", "🌦️", "#0ca678"),
}
LEGACY = {"politics": "poleco", "economy": "poleco", "society": "society", "visa": "visa", "sns": "ent", "local": "east"}
ALIAS = {"pattaya": "east", "sriracha": "east"}   # 2026-10-03 통합(옛 판 데이터 → 동부)
RX_PLACE = {
    "east": re.compile(r"파타야|좀티엔|쫌티엔|방라뭉|방람웅|싸따힙|사따힙|사타힙|나끌루아|농쁘루|프라탐낙|꼬란|"
                       r"시라차|스리라차|씨라차|램차방|아마타|촌부리|판통|반븡|방센|라용|맙따풋|꼬사멧"),
}
PRIORITY = ["east", "east", "visa"]   # 예전 파타야·시라차 1건씩 → 통합 뒤 동부 2건
ED_NAME = {"am": "아침판", "pm": "저녁판", "early": "새벽판"}
BRIEF_BADGE = {"am": "아침 브리핑", "pm": "저녁 브리핑", "early": "새벽 브리핑"}

e = html.escape

# ── 언어판(R-zh-8, 2026-10-18 Grok): 시스템 공유·편집 기준 분리. 한국판은 TX 기본값 = 지금 글자 그대로 ──
sys.path.insert(0, str(ROOT / "tools"))
import siteconf  # noqa: E402
import newslib  # noqa: E402  (매체 이름 표시 source_label, 2026-10-30)
_S = siteconf.load()
LANG = _S["lang"]
TX = {"brand": "태국 뉴스 한눈에", "brand_sub": "파타야에서 읽는 오늘의 태국", "html_lang": "ko", "og_locale": "ko_KR",
      "date_long": "{m}월 {d}일 {wd}요일", "date_short": "{m}월 {d}일({wd})", "time": "{m}월 {d}일 {hh}:{mm}", "wd": "월화수목금토일",
      "tz_line": "방콕 시간 기준", "spot": "이번 판 주목", "brief_title": '이번 판 주요 소식 <span class="bcount">{n}</span>건',
      "og_brief_title": "한국어로 정리한 현지 소식", "brief_badge": "오늘의 브리핑",
      "msg_head": "📰 태국 뉴스 한눈에 {m}월 {d}일({wd}) {edn}이에요. 현지 보도를 한국어로 정리했어요.",
      "msg_edition": "👉 이번 판 보기: ", "msg_home": "🏠 최신 뉴스({upd}): ", "title": "태국 뉴스 한눈에 — {m}월 {d}일({wd}) {edn}",
      "font": '"Pretendard","Pretendard Variable","Noto Sans CJK KR","Noto Sans KR"'}
# 검색용 판 제목·설명(2026-10-18 키워드 정리, 민구님 09:00 승인) — 한국판만. 언어판은 share.text 에 seo_* 를 넣을 때만 씀
# (한국어 검색어 '태국 뉴스'·'태국 현지 뉴스'·지역 이름을 언어판이 물려받지 않게)
SEO_TX = {"seo_title": "{m}월 {d}일({wd}) 태국 뉴스 {edn} — {heads} | {brand}",
          "seo_desc": "{m}월 {d}일({wd}) {edn}, 태국 현지 뉴스 {n}건을 한국어로 정리했어요{regions}. {heads}",
          "seo_regions": " ({r} 소식)", "seo_h1": "{label} 태국 뉴스", "seo_sep_title": "·", "seo_sep_desc": " · "}
if LANG == "ko":
    TX.update(SEO_TX)
if LANG != "ko":
    SITE = _S["site_url"]
    SHORT = _S.get("domain") or SITE.split("//")[-1].strip("/")
    TX.update((_S.get("share") or {}).get("text") or {})
    UPDATE_LINE = TX.get("update_line", UPDATE_LINE)
    ED_NAME = dict(_S.get("edition_label") or ED_NAME)
    BRIEF_BADGE = dict((_S.get("share") or {}).get("brief_badge") or {})
    PRIORITY = list((_S.get("share") or {}).get("priority") or PRIORITY)
    if _S.get("topics"):
        TOPICS = {x["id"]: (x["label"], x["emoji"], x["color"]) for x in _S["topics"]["TOPICS"]}


def _tpl(h):
    """카드·OG 틀의 @@자리@@ 를 TX 로 채움(2026-10-18). 날짜 자리는 %d·%s 로 바뀌어 뒤의 % 채우기에 그대로 들어감"""
    fmt = lambda s: e(s).replace("{m}", "%d").replace("{d}", "%d").replace("{wd}", "%s")
    for k, v in (("@@LANG@@", e(TX["html_lang"])), ("@@BRAND@@", e(TX["brand"])), ("@@SUB@@", e(TX["brand_sub"])),
                 ("@@DLONG@@", fmt(TX["date_long"])), ("@@DSHORT@@", fmt(TX["date_short"])), ("@@TZ@@", e(TX["tz_line"])),
                 ("@@BTITLE@@", TX["brief_title"].replace("%", "%%").replace("{n}", "%d")), ("@@OGBT@@", e(TX["og_brief_title"]))):
        h = h.replace(k, v)
    return h


# ---------------------------------------------------------------- 데이터
def load(ed_id):
    idx = json.loads((ROOT / "data/index.json").read_text(encoding="utf-8"))
    if ed_id in (None, "latest"):
        ed_id = idx["latest"]
    meta = next((x for x in idx["editions"] if x["id"] == ed_id), None)
    if not meta:
        sys.exit("data/index.json 에 없는 판: %s" % ed_id)
    data = json.loads((ROOT / "data" / (ed_id + ".json")).read_text(encoding="utf-8"))
    return idx, meta, data


def story_topics(data):
    """화면과 같은 주제(assets/topics.js storyTopics). {id: {topic, secondary[]}}"""
    # 언어판: data/site.js(window.TN_SITE — 그 판 주제 목록)를 먼저 읽음. 한국판엔 이 파일이 없어 그대로(2026-10-18)
    js = ("const fs=require('fs');global.window=global;if(process.argv[3]&&fs.existsSync(process.argv[3]))eval(fs.readFileSync(process.argv[3],'utf8'));"
          "eval(fs.readFileSync(process.argv[1],'utf8'));"
          "const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const o={};"
          "d.stories.forEach(s=>{const r=window.TNTopics.storyTopics(s);o[s.id]={topic:r.topic,secondary:r.secondary}});"
          "process.stdout.write(JSON.stringify(o));")
    node = shutil.which("node")
    if node:
        try:
            out = subprocess.run([node, "-e", js, str(ROOT / "assets/topics.js"), str(ROOT / "data" / (data["id"] + ".json")), str(ROOT / "data/site.js") if LANG != "ko" else ""],
                                 capture_output=True, text=True, timeout=30, check=True).stdout
            return json.loads(out)
        except Exception as ex:  # noqa
            print("경고: topics.js 실행 실패 → 간단 매핑 사용:", ex, file=sys.stderr)
    return {s["id"]: {"topic": ALIAS.get(s.get("topic"), s.get("topic")) or LEGACY.get(s.get("category"), "society"),
                      "secondary": [ALIAS.get(x, x) for x in s.get("secondary", [])]} for s in data["stories"]}


def pick(data, tp, n, manual=None):
    stories = data["stories"]
    by = {s["id"]: s for s in stories}
    hl = data.get("highlights") or []
    if manual:
        bad = [x for x in manual if x not in by]
        if bad:
            sys.exit("없는 기사 id: " + ", ".join(bad))
        return [by[x] for x in manual][:max(n, 3)]
    order = {s["id"]: i for i, s in enumerate(stories)}
    chosen = []

    def place_hit(s):
        txt = " ".join([s["headline"], s.get("region") or ""])
        return any(r.search(txt) for r in RX_PLACE.values())

    for slot in PRIORITY:
        cands = [s for s in stories if s not in chosen and slot in [tp[s["id"]]["topic"]] + tp[s["id"]]["secondary"]]
        if not cands:
            continue
        def score(s):
            return ((2 if tp[s["id"]]["topic"] == slot else 0) + (1 if place_hit(s) else 0)
                    + (1 if s["id"] in hl else 0), -order[s["id"]])
        chosen.append(max(cands, key=score))
    for x in hl:
        if x in by and by[x] not in chosen:
            chosen.append(by[x])
    for s in stories:
        if s not in chosen:
            chosen.append(s)
    return chosen[:n]


def split_head(h):
    """'핵심…부가' → (핵심, 부가). 앞부분이 너무 짧으면 자르지 않음."""
    if "…" in h:
        a, b = h.split("…", 1)
        if len(a.strip()) >= 8:
            return a.strip(), b.strip()
    return h.strip(), ""


def date_label(data, meta):
    m, d = int(data["date"][5:7]), int(data["date"][8:10])
    wd = (data.get("weekday") or "")[:1]
    if LANG != "ko":
        import datetime as _dt
        wd = TX["wd"][_dt.date(int(data["date"][:4]), m, d).weekday()]
    edn = ED_NAME.get(data.get("edition"), meta.get("label", "").split(" ")[-1])
    return m, d, wd, edn


# ---------------------------------------------------------------- HTML
# 모던 모양(2026-10-05, DESIGN_THEME.md 와 같은 값): 옅은 회색 바탕 #F2F4F6 · 흰 카드(모서리 = 휴대폰 16px × --u) ·
# 강조색 하나 #1B64DA · 글자 회색 단계 #191F28 / #4E5968 / #5F6B7A · 아이콘만 #8B95A1 ·
# 그라데이션·물결 장식·남색 헤더·테두리·주제별 여러 색 없음 · 주제 칩은 글자만, 📍 등은 선 아이콘(assets/modern-icons.svg)
ACCENT = "#1B64DA"
_ICONS = None


def icon(name):
    """assets/modern-icons.svg 의 Lucide 아이콘을 글 속 SVG 로(크기 = 1em, 색 = currentColor)."""
    global _ICONS
    if _ICONS is None:
        src = (ROOT / "assets/modern-icons.svg").read_text(encoding="utf-8")
        _ICONS = {m[1]: m[2] for m in re.finditer(r'<symbol id="i-([\w-]+)"[^>]*>(.*?)</symbol>', src, re.S)}
    return ('<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>' % _ICONS[name])


BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:%(W)dpx;height:%(H)dpx;overflow:hidden}
body{font-family:%(FONT)s,sans-serif;
  background:#F2F4F6;color:#191F28;word-break:keep-all;overflow-wrap:anywhere;-webkit-font-smoothing:antialiased}
.page{width:%(W)dpx;height:%(H)dpx;display:flex;flex-direction:column}
.ic{width:1em;height:1em;flex:0 0 auto;vertical-align:-.12em}
.mast{background:#fff;color:#191F28;display:flex;align-items:center;gap:calc(var(--u)*10px)}
.mark{flex:0 0 auto;border-radius:calc(var(--u)*8px);
  background:linear-gradient(180deg,#ef3340 0 16.6%%,#fff 16.6%% 33.3%%,#2d2a6e 33.3%% 66.6%%,#fff 66.6%% 83.3%%,#ef3340 83.3%%);
  box-shadow:inset 0 0 0 calc(var(--u)*1px) rgba(0,0,0,.08)}
.btext{display:flex;flex-direction:column;line-height:1.2}
.btext strong{font-weight:800;letter-spacing:-.02em;color:#191F28}
.btext small{color:#5F6B7A;font-weight:500}
.dl{margin-left:auto;text-align:right;line-height:1.25}
.dl .d{font-weight:700;color:#191F28;white-space:nowrap}
.dl .t{display:block;color:#5F6B7A;font-weight:500}
.edtag{font-weight:800;color:#1B64DA}
.card{background:#fff;border-radius:calc(var(--u)*16px);box-shadow:0 1px 2px rgba(0,0,0,.04)}
.top-card{position:relative;overflow:hidden;display:flex;flex-direction:column;justify-content:center}
.badges{display:flex;flex-wrap:wrap;gap:.45em;align-items:center}
.rank{font-weight:700;background:#1B64DA;color:#fff;border-radius:999px;line-height:1.4}
.chip{display:inline-flex;align-items:center;gap:.25em;font-weight:600;border-radius:999px;line-height:1.4;white-space:nowrap;
  background:#F2F4F6;color:#4E5968}
.chip .ic{color:#8B95A1}
.top-card h3{font-weight:800;letter-spacing:-.025em;color:#191F28}
.top-card p{color:#4E5968;display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
.top-card .meta{color:#5F6B7A} .top-card .meta b{color:#4E5968;font-weight:600}
.briefing{display:flex;flex-direction:column;overflow:hidden}
.bhead{display:flex;align-items:center;gap:.6em}
.bbadge{background:#E8F0FD;color:#1B64DA;font-weight:700;border-radius:999px;white-space:nowrap}
.btitle{font-weight:600;color:#5F6B7A}
.btitle .bcount{color:#1B64DA;font-weight:700}
ul{list-style:none}
li{display:flex;align-items:flex-start;gap:.5em}
.btx{flex:1;line-height:1.5;color:#4E5968}
.btx b{color:#191F28;font-weight:700}
.bchip{display:inline-block;font-weight:600;color:#4E5968;background:#F2F4F6;border-radius:999px;padding:0 .6em;margin-right:.45em;
  white-space:nowrap;line-height:1.6;vertical-align:.08em}
.go{color:#8B95A1;line-height:1.5;display:flex;align-items:center}
.foot{display:flex;align-items:center;justify-content:space-between;background:#fff;color:#191F28}
.foot .url{font-weight:700;letter-spacing:-.01em;display:flex;align-items:center;gap:.4em}
.foot .url .ic{color:#1B64DA}
.foot .upd{color:#5F6B7A;font-weight:500}
"""


def fmt_time(iso):
    m = re.match(r"\d{4}-(\d\d)-(\d\d)T(\d\d):(\d\d)", iso or "")
    return TX["time"].format(m=int(m[1]), d=int(m[2]), hh=m[3], mm=m[4]) if m else ""


def badge_html(s, i, hl, tp):
    t = TOPICS[tp[s["id"]]["topic"]]
    rank = ("TOP %d" % (hl.index(s["id"]) + 1)) if s["id"] in hl else TX["spot"]
    out = '<span class="rank">%s</span><span class="chip">%s</span>' % (e(rank), e(t[0]))
    if s.get("region") and s["region"].strip() != t[0]:
        out += '<span class="chip">%s%s</span>' % (icon("map-pin"), e(s["region"]))
    return out


def brief_li(s, tp, show_go=True):
    t = TOPICS[tp[s["id"]]["topic"]]
    a, b = split_head(s["headline"])
    rest = (" " + e(b)) if b else ""
    return ('<li><span class="btx"><span class="bchip">%s</span><b>%s</b><span class="rest">%s</span></span>%s</li>'
            % (e(t[0]), e(a), rest, ('<span class="go">%s</span>' % icon("chevron-right")) if show_go else ""))


if TX.get("mark_bg"):   # 머리 국기 그림(언어판 share.text.mark_bg — 예: 베트남판 국기). 한국판·중국어판은 없음 = 태국 국기 그대로(2026-10-25 Claude)
    BASE_CSS = re.sub(r"(\.mark\{flex:0 0 auto;border-radius:calc\(var\(--u\)\*8px\);\s*)background:[^;]*;",
                      lambda m: m.group(1) + "background:" + TX["mark_bg"].replace("%", "%%") + ";", BASE_CSS, count=1)
FIT_JS = """
async () => {
  await document.fonts.ready;
  const root = document.documentElement;
  // 넘침 = 내용이 상자보다 큼(scrollHeight) 또는 자식이 상자 밖으로 나감(가운데 정렬로 위·아래로 넘치는 경우까지)
  const over = () => [...document.querySelectorAll('[data-fit]')].some(el => {
    if (el.scrollHeight > el.clientHeight + 1) return true;
    const r = el.getBoundingClientRect();
    return [...el.children].some(c => { if (getComputedStyle(c).position === 'absolute') return false;  // 장식 글자(.deco) 제외
      const b = c.getBoundingClientRect(); return b.bottom > r.bottom + 1 || b.top < r.top - 1; });
  });
  const shrink = () => { let k = 1; root.style.setProperty('--k', '1');
    while (over() && k > 0.72) { k -= 0.02; root.style.setProperty('--k', k.toFixed(2)); } return k; };
  const rests = () => document.querySelectorAll('.rest');
  const fit = () => {
    rests().forEach(x => x.style.display = '');
    let k = shrink();
    // 글자를 0.9 배 아래로 줄여야 들어가면 목록의 부가 설명(… 뒤)을 빼고 다시 맞춤
    if (k < 0.9 && rests().length) { rests().forEach(x => x.style.display = 'none'); k = shrink(); }
    return k;
  };
  let k = fit(), dropped = 0;
  // 그래도 넘치면(잘림) 브리핑 목록 맨 아래 줄부터 하나씩 빼고 처음부터 다시 맞춤(최소 2줄은 남김) — 절대 잘린 채로 두지 않음
  const items = () => document.querySelectorAll('ul[data-fit] > li');
  while (over() && items().length > 2) {
    items()[items().length - 1].remove(); dropped++;
    const c = document.querySelector('.bcount'); if (c) c.textContent = items().length;
    k = fit();
  }
  // 마지막 수단: 줄 수를 줄여도 넘치면 각 줄을 N줄까지만 보이고 끝을 '…' 로(N = 4→1)
  let clamp = 0;
  for (let n = 4; n >= 1 && over(); n--) {
    clamp = n;
    document.querySelectorAll('ul[data-fit] .btx').forEach(x => Object.assign(x.style,
      {display: '-webkit-box', webkitBoxOrient: 'vertical', webkitLineClamp: String(n), overflow: 'hidden'}));
  }
  return {k, over: over(), dropped, lines: items().length, clamp};
}
"""


def card_html(data, meta, chosen, tp):
    m, d, wd, edn = date_label(data, meta)
    hl = data.get("highlights") or []
    main, rest = chosen[0], chosen[1:]
    a, b = split_head(main["headline"])
    css = BASE_CSS % {"W": 1080, "H": 1350, "FONT": TX["font"]} + """
:root{--u:2.4;--k:1}
.mast{padding:44px 56px 40px}
.mark{width:92px;height:92px}
.btext strong{font-size:54px}.btext small{font-size:29px;margin-top:8px}
.dl .d{font-size:36px}.dl .t{font-size:27px;margin-top:6px}
.body{flex:1;display:flex;flex-direction:column;gap:28px;padding:36px 44px 36px;min-height:0}
.top-card{padding:46px 50px 44px;min-height:400px;flex:0 0 auto;font-size:30px}
.rank{font-size:28px;padding:5px 20px}.chip{font-size:28px;padding:5px 18px}
.top-card h3{font-size:calc(var(--k)*62px);line-height:1.3;margin:24px 0 16px}
.top-card p{font-size:calc(var(--k)*33px);line-height:1.5;-webkit-line-clamp:2;margin-bottom:20px}
.top-card .meta{font-size:26px}
.briefing{flex:1;min-height:0;padding:38px 46px 18px}
.bhead{margin-bottom:8px}
.bbadge{font-size:30px;padding:7px 22px}.btitle{font-size:30px}
ul{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;justify-content:space-around}
li{padding:calc(var(--k)*18px) 0}
.btx{font-size:calc(var(--k)*39px)}
.btx .rest{font-size:.82em;color:#5F6B7A}
.bchip{font-size:calc(var(--k)*28px)}
.go{font-size:calc(var(--k)*40px)}
.foot{padding:30px 56px 34px;gap:24px}.foot .url{font-size:31px}.foot .upd{font-size:26px;white-space:nowrap}
"""
    return _tpl("""<!doctype html><html lang="@@LANG@@"><head><meta charset="utf-8"><style>%s</style></head><body><div class="page">
<header class="mast"><span class="mark"></span><span class="btext"><strong>@@BRAND@@</strong><small>@@SUB@@</small></span>
<span class="dl"><span class="d">@@DLONG@@</span><span class="t"><b class="edtag">%s</b> · @@TZ@@</span></span></header>
<main class="body">
<article class="card top-card" data-fit>
<div class="badges">%s</div><h3>%s</h3>%s<div class="meta"><b>%s</b> · %s</div></article>
<section class="card briefing"><div class="bhead"><span class="bbadge">%s</span><span class="btitle">@@BTITLE@@</span></div>
<ul data-fit>%s</ul></section>
</main>
<footer class="foot"><span class="url">%s%s</span><span class="upd">%s</span></footer>
</div></body></html>""") % (
        css, m, d, e(wd), e(edn), badge_html(main, 0, hl, tp),
        e(a), ("<p>%s</p>" % e(b)) if b else ("<p>%s</p>" % e((main.get("summary") or [""])[0])),
        e(newslib.source_label(main.get("source", ""))), e(fmt_time(main.get("published"))),
        BRIEF_BADGE.get(data.get("edition"), TX["brief_badge"]), len(rest), "".join(brief_li(s, tp) for s in rest),
        icon("link"), SHORT, UPDATE_LINE)


def og_html(data, meta, chosen, tp):
    m, d, wd, edn = date_label(data, meta)
    hl = data.get("highlights") or []
    main, rest = chosen[0], chosen[1:3]
    a, _ = split_head(main["headline"])
    css = BASE_CSS % {"W": 1200, "H": 630, "FONT": TX["font"]} + """
:root{--u:1.9;--k:1}
.mast{padding:24px 44px 22px}
.mark{width:68px;height:68px}
.btext strong{font-size:42px}.btext small{font-size:22px;margin-top:5px}
.edbig{margin-left:auto;background:#1B64DA;color:#fff;font-weight:700;font-size:32px;padding:8px 26px;border-radius:999px;white-space:nowrap}
.body{flex:1;display:grid;grid-template-columns:1.08fr 1fr;gap:22px;padding:24px 40px 24px;min-height:0}
.top-card{padding:30px 32px 28px;font-size:22px;min-height:0}
.rank{font-size:21px;padding:3px 14px}.chip{font-size:21px;padding:3px 13px}
.top-card h3{font-size:calc(var(--k)*44px);line-height:1.3;margin-top:16px}
.briefing{padding:24px 28px 10px;min-height:0}
.bbadge{font-size:22px;padding:4px 16px}.btitle{font-size:22px}
ul{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-around}
li{padding:10px 0}
.btx{font-size:calc(var(--k)*31px);line-height:1.42}
.bchip{font-size:calc(var(--k)*22px)}
.foot{padding:14px 44px 16px}
.foot .url{font-size:25px}.foot .upd{font-size:22px}
"""
    return _tpl("""<!doctype html><html lang="@@LANG@@"><head><meta charset="utf-8"><style>%s</style></head><body><div class="page">
<header class="mast"><span class="mark"></span><span class="btext"><strong>@@BRAND@@</strong><small>@@SUB@@</small></span>
<span class="edbig">@@DSHORT@@ %s</span></header>
<main class="body">
<article class="card top-card" data-fit><div class="badges">%s</div><h3>%s</h3></article>
<section class="card briefing"><div class="bhead"><span class="bbadge">%s</span><span class="btitle">@@OGBT@@</span></div>
<ul data-fit>%s</ul></section></main>
<footer class="foot"><span class="url">%s%s</span><span class="upd">%s</span></footer>
</div></body></html>""") % (
        css, m, d, e(wd), e(edn),
        badge_html(dict(main, region=None), 0, hl, tp), e(a),
        BRIEF_BADGE.get(data.get("edition"), TX["brief_badge"]),
        "".join(brief_li(dict(s, headline=split_head(s["headline"])[0]), tp, False) for s in rest),
        icon("link"), SHORT, UPDATE_LINE)


def _rel(pth):
    try:
        return pth.resolve().relative_to(ROOT)
    except ValueError:
        return pth


async def render(jobs):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        kw = dict(args=["--no-sandbox"])
        if pathlib.Path("/usr/bin/google-chrome").exists():
            kw["executable_path"] = "/usr/bin/google-chrome"
        b = await p.chromium.launch(**kw)
        for html_path, png, w, h in jobs:
            pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            await pg.goto(html_path.as_uri())
            res = await pg.evaluate(FIT_JS)
            await pg.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": w, "height": h})
            drop = (", 브리핑 %d줄 뺌(남은 %d줄)" % (res["dropped"], res["lines"])) if res.get("dropped") else ""
            if res.get("clamp"):
                drop += ", 긴 줄 %d줄까지만(…)" % res["clamp"]
            print("saved %s (%dx%d, 글자 배율 %.2f%s%s)" % (_rel(png), w, h, res["k"], drop, ", 넘침!" if res["over"] else ""))
            await pg.close()
        await b.close()


# ---------------------------------------------------------------- 메시지·정적 페이지
def message(data, meta, chosen, tp, ed_url, main_link=True):
    m, d, wd, edn = date_label(data, meta)
    lines = [TX["msg_head"].format(m=m, d=d, wd=wd, edn=edn)]
    for s in chosen[:3]:
        lines.append("%s %s" % (TOPICS[tp[s["id"]]["topic"]][1], split_head(s["headline"])[0]))
    lines.append("")
    lines.append(TX["msg_edition"] + ed_url)
    if main_link:
        lines.append(TX["msg_home"].format(upd=UPDATE_LINE.replace(" 업데이트", "")) + SITE)
    return "\n".join(lines) + "\n"


def og_tags(title, desc, url, img):
    return "\n".join([
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="%s">' % e(TX["brand"]),
        '<meta property="og:locale" content="%s">' % e(TX["og_locale"]),
        '<meta property="og:title" content="%s">' % e(title),
        '<meta property="og:description" content="%s">' % e(desc),
        '<meta property="og:url" content="%s">' % e(url),
        '<meta property="og:image" content="%s">' % e(img),
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:image:alt" content="%s">' % e(title),
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="twitter:title" content="%s">' % e(title),
        '<meta name="twitter:description" content="%s">' % e(desc),
        '<meta name="twitter:image" content="%s">' % e(img),
    ])


def edition_page(data, meta, chosen, tp, ed_url, img):
    """판 정적 페이지 e/<판>/index.html — 2026-10-18 검색 노출(R-seo-1·3·4): 판 기사 전체(제목·요약·출처) 정적 HTML,
    index/follow, canonical 자기 자신. 본문은 tools/seo.py(공용). 제목·설명·OG 는 여기서(카드 고르기 기준 그대로)."""
    import seo
    title, desc, h1 = seo_meta(data, meta, chosen, tp)
    emo = {k: TOPICS.get(v["topic"], ("", ""))[1] for k, v in tp.items()}
    page = seo.edition_page(data, meta, title, desc, og_tags(title, desc, ed_url, img), emo, label=h1)
    return page, title, desc


def _regions(data, chosen, k=4):
    """판 지역 이름(괄호 앞 큰 이름) — 카드에 고른 기사 먼저, 다음은 판 순서. 같은 이름은 한 번만."""
    out = []
    for s in list(chosen) + [x for x in data.get("stories", []) if x not in chosen]:
        r = re.split(r"[(（]", s.get("region") or "")[0].strip()
        if r and r not in out:
            out.append(r)
    return out[:k]


def seo_meta(data, meta, chosen, tp):
    """(검색 제목, 검색 설명, h1). 한국판 = 날짜 + '태국 뉴스' + 주요 제목·지역. 언어판에 seo_* 문구가 없으면 예전 그대로."""
    m, d, wd, edn = date_label(data, meta)
    if "seo_title" not in TX:
        title = TX["title"].format(m=m, d=d, wd=wd, edn=edn)
        desc = " · ".join("%s %s" % (TOPICS[tp[s["id"]]["topic"]][1], split_head(s["headline"])[0]) for s in chosen[:3])
        if len(desc) > 110:
            desc = desc[:108].rstrip() + "…"
        return title, desc, None
    heads = [split_head(s["headline"])[0] for s in chosen[:3]]
    # 제목: 주요 제목 1~2개, 너무 길면(64자 넘으면) 1개
    title = ""
    for k in (2, 1):
        title = TX["seo_title"].format(m=m, d=d, wd=wd, edn=edn, heads=TX["seo_sep_title"].join(heads[:k]), brand=TX["brand"])
        if len(title) <= 64:
            break
    else:   # 제목 하나로도 길면 그 제목을 줄임
        over = len(title) - 64
        h0 = heads[0][:max(8, len(heads[0]) - over - 1)]
        if h0.count("(") > h0.count(")"):          # 괄호(바트 원화 환산 등) 안에서 자르지 않음
            h0 = h0[:h0.rfind("(")]
        if " " in h0.strip():
            h0 = h0.strip().rsplit(" ", 1)[0]       # 낱말 중간에서 자르지 않음
        h0 = h0.rstrip(" ,·") + "…"
        title = TX["seo_title"].format(m=m, d=d, wd=wd, edn=edn, heads=h0, brand=TX["brand"])
    rg = _regions(data, chosen)
    for k in (3, 2, 1):   # 설명: 150자 안에 들어가는 만큼 주요 제목을 통째로(제목 중간·괄호 안에서 자르지 않음)
        desc = TX["seo_desc"].format(m=m, d=d, wd=wd, edn=edn, n=len(data.get("stories", [])),
                                     regions=TX["seo_regions"].format(r="·".join(rg)) if rg else "", heads=TX["seo_sep_desc"].join(heads[:k]))
        if len(desc) <= 150:
            break
    h1 = TX["seo_h1"].format(label=meta.get("label") or "%d월 %d일 %s" % (m, d, edn))
    return title, desc, h1


def ensure_gitignore():
    gi = ROOT / ".gitignore"
    txt = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if not re.search(r"(?m)^/?share/?\s*$", txt):
        gi.write_text(txt.rstrip("\n") + "\n# 카카오톡 공유 키트 출력(tools/share_kit.py)\nshare/\n", encoding="utf-8")
        print(".gitignore 에 share/ 추가")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", nargs="?", default="latest")
    ap.add_argument("--pick", default="")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--no-main-link", action="store_true")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--pages-only", action="store_true", help="e/<판>/index.html·sitemap·feed 만(카드 PNG·브라우저 없이 — 빠진 판 미리보기 다시 만들기)")
    a = ap.parse_args()
    if a.out:
        a.no_publish = True
    n = min(5, max(3, a.n))
    idx, meta, data = load(a.edition)
    eid = data["id"]
    tp = story_topics(data)
    chosen = pick(data, tp, n, [x.strip() for x in a.pick.split(",") if x.strip()] or None)
    if a.out:
        share = pathlib.Path(a.out).resolve()
    else:
        ensure_gitignore()
        share = ROOT / "share"
    share.mkdir(parents=True, exist_ok=True)
    ed_url = SITE + "e/%s/" % eid
    img_url = SITE + "og/%s.png" % eid

    # ฿ 는 사이트 헤더 숫자 칸에만(2026-10-04) — 카드·OG·카톡 문구·판 미리보기 글에는 '바트'
    _texts = {"카드": card_html(data, meta, chosen, tp), "OG": og_html(data, meta, chosen, tp),
              "카톡 문구": message(data, meta, chosen, tp, ed_url, not a.no_main_link),
              "판 미리보기": edition_page(data, meta, chosen, tp, ed_url, img_url)[0]}
    import siteconf as _sc
    _bad = [k for k, v in _texts.items() if "฿" in v] if _sc.forbids_symbol("฿") else []
    if _bad:
        sys.exit("'฿' 금지(%s) — 글에서는 '바트'로(TRANSLATION_RULES)" % ", ".join(_bad))
    # 태국 글자(฿ 말고 U+0E00–U+0E7F) 도 카드·OG·카톡 문구·판 미리보기에 없어야 함(화면 규칙과 같음)
    _thai = [k for k, v in _texts.items() if re.search(r"[\u0E00-\u0E3E\u0E40-\u0E7F]", v)] if _sc.forbids("thai") else []   # 태국어판은 허용
    if _thai:
        sys.exit("태국 글자 금지(%s) — 한국어·영어 약칭·로마자로(TRANSLATION_RULES)" % ", ".join(_thai))
    ch, oh = share / (eid + "-card.html"), share / (eid + "-og.html")
    ch.write_text(card_html(data, meta, chosen, tp), encoding="utf-8")
    oh.write_text(og_html(data, meta, chosen, tp), encoding="utf-8")
    card_png, og_png = share / (eid + ".png"), share / (eid + "-og.png")
    rendered = False
    if not a.pages_only:
        try:   # (2026-10-30) 브라우저(playwright)가 없거나 실패해도 판 미리보기 e/ 페이지·sitemap 은 만든다 — 그래야 /e/<판>/ 이 404 가 안 남
            asyncio.run(render([(ch, card_png, 1080, 1350), (oh, og_png, 1200, 630)])); rendered = True
        except Exception as ex:
            print("경고: 카드 PNG 렌더 실패(%s) — e/ 페이지·sitemap 은 계속" % str(ex)[:120], file=sys.stderr)

    msg = message(data, meta, chosen, tp, ed_url, not a.no_main_link)
    (share / (eid + ".txt")).write_text(msg, encoding="utf-8")

    page, title, desc = edition_page(data, meta, chosen, tp, ed_url, img_url)
    (share / (eid + "-og-tags.txt")).write_text(og_tags(title, desc, ed_url, img_url) + "\n", encoding="utf-8")
    if not a.no_publish:
        og = ROOT / "og"
        og.mkdir(exist_ok=True)
        if rendered:
            shutil.copyfile(og_png, og / (eid + ".png"))
            print("saved og/%s.png" % eid)
            if eid == idx["latest"]:
                shutil.copyfile(og_png, og / "latest.png")
                print("saved og/latest.png")
        ep = ROOT / "e" / eid
        ep.mkdir(parents=True, exist_ok=True)
        (ep / "index.html").write_text(page, encoding="utf-8")
        print("saved e/%s/index.html" % eid)
        import seo   # 2026-10-18 R-seo-2: 판마다 sitemap.xml 갱신(deploy.sh 도 커밋 전에 한 번 더)
        print("sitemap.xml: 판 쪽 %d개" % seo.sitemap())
        print("feed.xml: 항목 %d개" % seo.rss())

    print("\n기사:", ", ".join("%s(%s)" % (s["id"], tp[s["id"]]["topic"]) for s in chosen))
    print("\n----- %s/%s.txt (%d자) -----\n%s" % (_rel(share), eid, len(msg.rstrip("\n")), msg))


if __name__ == "__main__":
    main()
