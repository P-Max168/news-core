# -*- coding: utf-8 -*-
"""언어판 화면 적용(R-zh-1·2·9, 2026-10-18 Grok — 민구님 08:00 승인으로 Claude 대신).

원칙: 시스템(index.html·assets/*·tools/*)은 한국판 저장소 것을 그대로 공유하고, 언어판 저장소에서는 이 스크립트가
**언어별 편집 기준 파일만 읽어서** 화면 껍데기에 입힌다. 한국판(site/LANG=ko)에서는 아무것도 하지 않는다.

    python3 tools/site_build.py            # 이 저장소 언어(site/LANG) — ko 면 '건너뜀'
    TNK_LANG=zh python3 tools/site_build.py --root /path/to/zh-repo

읽는 것(언어판 저장소): site/<lang>.json · site/topics.<lang>.json · i18n/<lang>.json
만드는 것/고치는 것(언어판 저장소 안에서만):
  data/site.js   window.TN_SITE = {lang, brand, i18n, topics, currency, home_section, hidden_sections, firestore_prefix, admins_doc, impacts_ui, login(LINE 로그인 경로)}
  index.html     <html lang>, <title>·description·og·canonical·앱 이름, data/site.js 넣기, data-i18n 글자, 홈 나라 국기, 숨길 코너 CSS
  manifest.json  name·short_name·lang·description
같은 파일에 여러 번 돌려도 결과가 같음(멱등). sync_core.sh 가 한국판 index.html 을 덮어쓴 뒤 → 이 스크립트 → deploy.
"""
import argparse, html, json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import siteconf  # noqa: E402

IMPACT_UI = [("🛂", "#6741d9"), ("💱", "#0c8f6a"), ("🚗", "#d9480f"), ("🚨", "#c92a2a"), ("🌧️", "#1971c2")]   # app.js IMPACT 와 같은 아이콘·색·순서
FLAGS = {  # 홈 나라 국기(index.html 의 data-site-flag 자리) — 한국판 태극기 대신
    "cn": '<svg class="flag flag--cn" data-site-flag viewBox="0 0 30 20" width="30" height="20" role="img" aria-label="中国国旗"><rect width="30" height="20" fill="#DE2910"/>'
          '<g fill="#FFDE00"><polygon points="5,2 5.9,4.8 8.8,4.8 6.4,6.5 7.3,9.3 5,7.6 2.7,9.3 3.6,6.5 1.2,4.8 4.1,4.8"/>'
          '<circle cx="10" cy="2" r=".9"/><circle cx="12" cy="4" r=".9"/><circle cx="12" cy="7" r=".9"/><circle cx="10" cy="9" r=".9"/></g></svg>',
}

LOCAL_FLAGS = {  # 현지 나라 국기(index.html 맨 앞 태국 국기 자리)
    "vn": '<svg class="flag" viewBox="0 0 30 20" width="30" height="20" role="img" aria-label="베트남 국기" data-i18n-aria="a11y.flag_th">'
          '<rect width="30" height="20" fill="#DA251D"/><polygon fill="#FFFF00" points="15,4 16.18,7.64 20,7.64 16.91,9.88 18.09,13.52 15,11.27 11.91,13.52 13.09,9.88 10,7.64 13.82,7.64"/></svg>',
}


def flat(d, pre=""):
    out = {}
    for k, v in (d or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            out.update(flat(v, pre + k + "."))
        elif isinstance(v, str):
            out[pre + k] = v
    return out


def site_js(c, i18n):
    keep = {k: c.get(k) for k in ("lang", "htmlLang", "brand", "brand_sub", "site_url", "currency", "home_section", "hidden_sections",
                                  "firestore_prefix", "admins_doc", "slots", "edition_label", "share", "wx_coords", "origin_hide_rx", "login") if k in c}
    keep["i18n"] = i18n
    keep["topics"] = {k: v for k, v in (c.get("topics") or {}).items() if not k.startswith("_") and k != "REGION_PATTERNS"}
    keep["impacts_ui"] = [{"k": k, "e": IMPACT_UI[i % 5][0], "c": IMPACT_UI[i % 5][1]} for i, k in enumerate(c.get("impacts") or [])]
    return ("/* 언어판 설정 — tools/site_build.py 가 site/%s.json·topics·i18n 로 만듦(손으로 고치지 말 것). 한국판에는 이 파일이 없음 */\n"
            "window.TN_SITE = %s;\n" % (c["lang"], json.dumps(keep, ensure_ascii=False)))


def _attr(s):
    return html.escape(s, quote=True)


ROOT_FOR_SKIN = []


def patch_index(t, c, i18n):
    f = flat(i18n)
    seo = c.get("seo") or {}
    title = seo.get("title") or c["brand"]
    desc = seo.get("description") or c.get("brand_sub", "")
    url = c["site_url"]
    t = re.sub(r'<html lang="[^"]*"', '<html lang="%s"' % c.get("htmlLang", c["lang"]), t, count=1)
    t = re.sub(r"<title>.*?</title>", "<title>%s</title>" % html.escape(title), t, count=1, flags=re.S)
    t = re.sub(r'<meta name="description" content="[^"]*">', '<meta name="description" content="%s">' % _attr(desc), t, count=1)
    t = re.sub(r'<link rel="canonical" href="[^"]*">', '<link rel="canonical" href="%s">' % _attr(url), t, count=1)
    t = re.sub(r'<meta name="apple-mobile-web-app-title" content="[^"]*">', '<meta name="apple-mobile-web-app-title" content="%s">' % _attr(c.get("short_name", c["brand"])), t, count=1)
    og = {"og:site_name": c["brand"], "og:locale": seo.get("og_locale", "zh_CN"), "og:title": title, "og:description": seo.get("og_description", desc), "og:url": url,
          "og:image": url + "og/latest.png"}
    for k, v in og.items():
        t = re.sub(r'<meta property="%s" content="[^"]*">' % re.escape(k), '<meta property="%s" content="%s">' % (k, _attr(v)), t)
    t = re.sub(r'<meta name="twitter:image" content="[^"]*">', '<meta name="twitter:image" content="%s">' % _attr(url + "og/latest.png"), t)
    # 검색 인증 메타 자리(한국판 값 주석)는 언어판에서 지움 — 언어판 값은 site/<lang>.json seo.verification 으로
    t = re.sub(r"<!-- 검색 등록 인증.*?-->\n(?:(?:<!-- )?<meta name=\"(?:google|naver)-site-verification\"[^\n]*\n)*", "", t, flags=re.S)  # (10-18) 주석 푼 한국판 값 줄도 지움
    for name, val in (seo.get("verification") or {}).items():
        if val and ('name="%s"' % name) not in t:
            t = t.replace("</title>", '</title>\n<meta name="%s" content="%s">' % (_attr(name), _attr(val)), 1)
    # 검색 구조화 데이터(JSON-LD)·숨은 h1(2026-10-18 한국판 키워드 정리) — 언어판은 한국어 키워드를 물려받지 않게 자기 값으로 바꿈
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "@id": url + "#website", "url": url, "name": c["brand"], "description": desc,
         "inLanguage": c.get("htmlLang", c["lang"]), "publisher": {"@id": url + "#org"}},
        {"@type": "NewsMediaOrganization", "@id": url + "#org", "name": c["brand"], "url": url,
         "logo": {"@type": "ImageObject", "url": url + "assets/icons/icon-512.png", "width": 512, "height": 512},
         "areaServed": c.get("area", "TH"), "knowsLanguage": c.get("htmlLang", c["lang"])}]}
    ldj = json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    t = re.sub(r'<script type="application/ld\+json" id="tn-ld">.*?</script>(<!--.*?-->)?',
               lambda _: '<script type="application/ld+json" id="tn-ld">%s</script>' % ldj, t, count=1, flags=re.S)
    t = re.sub(r'(<h1 class="sr-only" id="tn-h1">).*?(</h1>)', lambda m: m.group(1) + html.escape(seo.get("h1") or title, quote=False) + m.group(2), t, count=1, flags=re.S)
    # 검색 차단 판(site/<lang>.json noindex=true, 2026-10-25 Claude — 베트남판·kstar 공개 승인 전): robots 메타를 noindex 로
    if c.get("noindex"):
        t = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex, nofollow, noarchive">', t)
    # data/site.js — 앱 코드보다 먼저(topics.js 가 TN_SITE 를 읽음). 한 번만
    if 'src="data/site.js"' not in t:
        t = t.replace('<script src="data/index.js"></script>', '<script src="data/site.js"></script>\n<script src="data/index.js"></script>', 1)
    # 숨길 코너 CSS(R-zh-9) — topics.js 가 <html class="tn-hide-places …"> 를 붙임
    hid = c.get("hidden_sections") or []
    css = []
    if "places" in hid:
        css.append(".tn-hide-places .subbar--nearby,.tn-hide-places [data-quick-nearby],.tn-hide-places [data-page=\"nearby\"]{display:none!important}")
    if "rentals" in hid:
        css.append(".tn-hide-rentals [data-page=\"rentals\"],.tn-hide-rentals [href^=\"#rent\"]{display:none!important}")
    if "jobs" in hid:
        css.append(".tn-hide-jobs [data-page=\"jobs\"],.tn-hide-jobs [href^=\"#jobs\"]{display:none!important}")
    t = re.sub(r'<style id="tn-site-hide">.*?</style>\n?', "", t, flags=re.S)
    if css:
        t = t.replace("</head>", '<style id="tn-site-hide">%s</style>\n</head>' % "".join(css), 1)
    # 현지 나라 국기(맨 앞 태국 국기 자리, 2026-10-25 Claude — 베트남판 local_flag=vn)
    lf = LOCAL_FLAGS.get(c.get("local_flag", ""))
    if lf:
        t = re.sub(r'<svg class="flag" viewBox="0 0 30 20"[^>]*data-i18n-aria="a11y.flag_th">.*?</svg>', lambda _: lf, t, count=1, flags=re.S)
    # 홈 나라 국기
    fl = FLAGS.get((c.get("home_section") or {}).get("flag", ""))
    if fl:
        t = re.sub(r'<svg class="flag flag--\w+" data-site-flag.*?</svg>', fl, t, count=1, flags=re.S)
    # data-i18n 글자(속에 다른 태그 없는 칸만) · data-i18n-html(속 태그 허용, 값은 운영자 문구 그대로)
    def rep(m):
        k = m.group(3)
        return m.group(1) + (html.escape(f[k], quote=False) if k in f else m.group(4)) + m.group(5)
    t = re.sub(r'(<(\w+)\b[^>]*\sdata-i18n="([\w.]+)"[^>]*>)([^<]*)(</\2>)', rep, t)
    def reph(m):
        k = m.group(3)
        return m.group(1) + (f[k] if k in f else m.group(4)) + m.group(5)
    t = re.sub(r'(<(\w+)\b[^>]*\sdata-i18n-html="([\w.]+)"[^>]*>)(.*?)(</\2>)', reph, t, flags=re.S)
    # data-i18n-aria="키" → 그 태그의 aria-label 값(2026-10-18, 화면엔 안 보이는 읽기 글자)
    def repa(m):
        k = m.group(2)
        return re.sub(r'aria-label="[^"]*"', lambda _: 'aria-label="%s"' % _attr(f[k]), m.group(0), count=1) if k in f else m.group(0)
    t = re.sub(r'<(\w+)\b[^>]*\sdata-i18n-aria="([\w.]+)"[^>]*>', repa, t)
    # aria-label 의 브랜드
    t = t.replace('aria-label="태국 뉴스 한눈에 홈"', 'aria-label="%s"' % _attr(f.get("brand_home", c["brand"])))
    # 판 전용 겉모습(skin, 2026-10-25 — KSTAR): site/<lang>.json skin_css 가 있으면 배포본 assets/skin.css 를 맨 뒤에 연결(엔진·기능은 그대로, 색·글꼴만)
    sk = c.get("skin_css")
    t = re.sub(r'\n?<link rel="stylesheet" href="assets/skin\.css[^"]*" id="tn-skin">', "", t)
    if sk:
        import hashlib
        sp = ROOT_FOR_SKIN[0] / sk if ROOT_FOR_SKIN else None
        v = hashlib.sha256(sp.read_bytes()).hexdigest()[:8] if sp and sp.exists() else "1"
        t = t.replace("</body>", '<link rel="stylesheet" href="assets/skin.css?v=%s" id="tn-skin">\n</body>' % v, 1)
    # 한국판 '지난 뉴스판' 링크 묶음(tools/seo.py home_edition_links)은 언어판에선 비움 — 한국판 판 목록·한국어 글이 따라오지 않게(2026-10-25)
    t = re.sub(r"(<!-- edition-links:start -->).*?(<!-- edition-links:end -->)", r"\1\2", t, count=1, flags=re.S)
    return t


def patch_manifest(t, c):
    m = json.loads(t)
    m["name"] = c["brand"]
    m["short_name"] = c.get("short_name", c["brand"])
    m["lang"] = c.get("htmlLang", c["lang"])
    if c.get("brand_sub"):
        m["description"] = c["brand_sub"]
    return json.dumps(m, ensure_ascii=False, indent=1) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE.parent))
    ap.add_argument("--check", action="store_true", help="파일을 쓰지 않고 바뀔지만 출력")
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    ROOT_FOR_SKIN[:] = [root]
    lg = siteconf.lang(root)
    if lg == "ko":
        print("site_build: 한국판(ko) — 건너뜀(화면은 index.html 그대로)")
        return 0
    c = siteconf.load(lg, root)
    ip = root / "i18n" / ("%s.json" % lg)
    i18n = {k: v for k, v in json.loads(ip.read_text(encoding="utf-8")).items() if not k.startswith("_") or k == "_locale"} if ip.exists() else {}
    outs = {root / "data" / "site.js": site_js(c, i18n)}
    idx = root / "index.html"
    outs[idx] = patch_index(idx.read_text(encoding="utf-8"), c, i18n)
    mf = root / "manifest.json"
    if mf.exists():
        outs[mf] = patch_manifest(mf.read_text(encoding="utf-8"), c)
    bad = [p.name for p, v in outs.items() if re.search(r"[\u0E00-\u0E3E\u0E40-\u0E7F]", v)] if "thai" in (c.get("validate") or {}).get("forbid_scripts", ["thai", "cjk"]) else []   # 태국어판은 화면 글이 태국어
    if bad:
        sys.exit("site_build: 태국 글자 들어감 — %s" % ", ".join(bad))
    for p, v in outs.items():
        old = p.read_text(encoding="utf-8") if p.exists() else None
        if old != v:
            print("site_build: %s %s" % ("바뀜" if old is not None else "새로", p.relative_to(root)))
            if not a.check:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(v, encoding="utf-8")
    left = len(re.findall(r"[가-힣]+", re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", outs[idx], flags=re.S)))
    print("site_build: %s 완료 · index.html 에 남은 한글 낱말 %d개(화면 코드 문구는 tools/dev/i18n_scan.py)" % (lg, left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
