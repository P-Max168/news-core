# -*- coding: utf-8 -*-
"""검색 노출(SEO) 공용 도구 — 2026-10-18 Grok(민구님 승인: 한국어판 검색 노출, Claude 요청 R-seo-1~4 대행).

    python3 tools/seo.py sitemap        # sitemap.xml 다시 만들기(data/index.json + e/<판>/ 있는 것)
    python3 tools/seo.py rss            # feed.xml RSS 갱신(네이버 등)
    python3 tools/seo.py indexnow       # IndexNow 키 보장 + 현재 URL 제출
    python3 tools/seo.py regen-e        # 기존 e/<판>/index.html 전부를 '판 기사 전체 정적 HTML'로 다시 만들기
                                        #   (제목·설명·OG 태그는 기존 파일 것을 그대로 유지 → og 이미지·카톡 미리보기 안 바뀜)
    python3 tools/seo.py all            # 둘 다

- e/<판>/index.html = 판의 모든 기사(제목·요약·출처 링크, 기사별 앵커 #<기사id>)를 정적 HTML 로 → 네이버·다음 수집기도 읽음.
  사람(브라우저)은 지금처럼 바로 앱 화면 ../../?ed=<판> 으로 이동. 검색 수집기(UA 에 bot/crawl/spider/Yeti/Daum 등)는 이동하지 않음.
  canonical = 자기 자신(https://tnews.pmaxone.com/e/<판>/). 앱의 ?ed=<판> 주소는 app.js 가 canonical 을 이 쪽으로 바꿈.
- 판 빌드 때: tools/share_kit.py 가 e 쪽을 이 모듈로 만들고, 직후 sitemap 갱신. tools/deploy.sh 도 커밋 전에 sitemap 을 한 번 더 만듦.
- ฿·태국 글자는 넣지 않음(title_th 는 쓰지 않음, 본문에 있으면 생성 거부 — 화면 규칙과 같음).
- 언어판(zh 등)은 site/<lang>.json 의 site_url·brand 를 넘기면 같은 코드로 만듦(시스템 공유·편집 기준 분리).
"""
import html, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://tnews.pmaxone.com/"
BRAND = "태국 뉴스 한눈에"
INFO_PAGES = ["about.html", "contact.html", "privacy.html", "terms.html"]
BOT_RX = r"bot|crawl|spider|slurp|yeti|daum|bingpreview|mediapartners|facebookexternalhit|kakaotalk-scrap|lighthouse"
e = html.escape
_THAI = re.compile(r"[\u0E00-\u0E7F]")


def _site():
    """site/<lang>.json 이 있으면 그 값(언어판), 없으면 한국판 기본값."""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import siteconf
        c = siteconf.load()
        b = c.get("brand", BRAND)
        return c.get("site_url", SITE), (b.get("name", BRAND) if isinstance(b, dict) else b), c.get("htmlLang", "ko")
    except Exception:
        return SITE, BRAND, "ko"


def canonical_tag(url):
    return '<link rel="canonical" href="%s">' % e(url)


def _paras(summary):
    if isinstance(summary, str):
        summary = [summary]
    return "".join("<p>%s</p>" % e(p) for p in (summary or []) if p)


def edition_page(data, meta, title, desc, og_block, emoji=None, label=None):
    """판 전체 정적 HTML. emoji = {기사id: '🏖️'} (없으면 생략)."""
    site, brand, lang = _site()
    eid = data["id"]
    url = site + "e/%s/" % eid
    target = "../../?ed=" + eid
    emoji = emoji or {}
    arts = []
    for s in data.get("stories", []):
        src = '<a href="%s" rel="nofollow noopener" target="_blank">%s</a>' % (e(s["url"]), e(s.get("source", "원문"))) if s.get("url") else e(s.get("source", ""))
        also = "".join(' · <a href="%s" rel="nofollow noopener" target="_blank">%s</a>' % (e(a["url"]), e(a.get("source", "")))
                       for a in (s.get("also") or []) if a.get("url"))
        ctx = '<p class="ctx">%s</p>' % e(s["context"]) if s.get("context") else ""
        region = '<span class="rg">%s</span> ' % e(s["region"]) if s.get("region") else ""
        arts.append('<article id="%s"><h2>%s%s</h2>%s%s%s<p class="src">출처: %s%s · <a href="%s#%s">앱에서 보기</a></p></article>'
                    % (e(s["id"]), (emoji.get(s["id"], "") + " ") if emoji.get(s["id"]) else "", e(s["headline"]),
                       ('<p class="meta">%s</p>' % region) if region else "", _paras(s.get("summary")), ctx, src, also,
                       e(target), e(s["id"])))
    brief = data.get("briefing")
    if isinstance(brief, dict):
        brief = brief.get("lines") or brief.get("items") or []
    brief_html = ""
    if isinstance(brief, list) and brief:
        brief_html = '<section class="brief"><h2>브리핑</h2><ul>%s</ul></section>' % "".join(
            "<li>%s</li>" % e((b if isinstance(b, str) else (b.get("text") or b.get("line") or "")).replace("**", "")) for b in brief)
    # 검색 구조화 데이터(2026-10-18 키워드 정리): 판 = CollectionPage + 기사 목록(ItemList). 언어판도 자기 brand·site_url 로
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "@id": url, "url": url, "name": title, "description": desc,
          "inLanguage": lang, "isPartOf": {"@type": "WebSite", "@id": site + "#website", "name": brand, "url": site},
          "publisher": {"@type": "NewsMediaOrganization", "@id": site + "#org", "name": brand, "url": site},
          "mainEntity": {"@type": "ItemList", "numberOfItems": len(data.get("stories", [])), "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "url": url + "#" + s["id"], "name": s["headline"]}
              for i, s in enumerate(data.get("stories", []))]}}
    if data.get("generated"):
        ld["datePublished"] = data["generated"]
    ld_html = '<script type="application/ld+json">%s</script>' % json.dumps(ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow, max-image-preview:large">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
%(canon)s
%(og)s
%(ld)s
<meta name="theme-color" content="#ffffff">
<link rel="icon" type="image/png" sizes="32x32" href="../../assets/icons/favicon-32.png">
<!-- 판 전체 정적 페이지(tools/seo.py 가 생성, tools/share_kit.py 가 판마다 부름). 검색 수집기는 이 글을 읽고,
     사람(브라우저)은 바로 앱 화면으로 이동. meta refresh 는 미리보기 수집기가 따라가 메인 태그를 읽을 수 있어 쓰지 않음(JS 이동 + 링크). -->
<script>if(!/%(botrx)s/i.test(navigator.userAgent||""))location.replace(%(target_js)s + location.hash);</script>
<style>body{margin:0;font-family:Pretendard,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:#F2F4F6;color:#191F28;line-height:1.65;word-break:keep-all;overflow-wrap:anywhere}
header{background:#fff;color:#191F28;padding:18px 20px;font-weight:800;font-size:20px;box-shadow:0 1px 0 rgba(0,0,0,.05)}header a{color:inherit;text-decoration:none}
main{padding:20px;max-width:720px;margin:auto}h1{font-size:22px;margin:0 0 6px}article,.brief{background:#fff;border-radius:16px;padding:16px 18px;margin:12px 0}
article h2,.brief h2{font-size:18px;margin:0 0 8px;line-height:1.4}.meta,.src{color:#5F6B7A;font-size:14px}.ctx{color:#4E5968;font-size:15px}
a{color:#1B64DA}a.btn{display:inline-block;margin:10px 0;background:#1B64DA;color:#fff;font-weight:700;padding:12px 18px;border-radius:12px;text-decoration:none}
li{margin:6px 0;color:#333D4B}footer{color:#5F6B7A;font-size:14px;padding:10px 20px 30px;max-width:720px;margin:auto}</style>
<link rel="stylesheet" href="/assets/g-pages.css?v=1">
<!-- 방문 통계: Cloudflare Web Analytics(쿠키 없음, 2026-10-23 맥스님 승인). 주소별 토큰 -->
<script>(function(){var t={"tnews.pmaxone.com":"bea5ff7413d34c85b4f9f0df04a87e4e","zh.pmaxone.com":"bb059d024cbc42a99df391388dcae578"}[location.hostname];if(!t)return;var s=document.createElement("script");s.defer=true;s.src="https://static.cloudflareinsights.com/beacon.min.js";s.setAttribute("data-cf-beacon",JSON.stringify({token:t}));document.head.appendChild(s);})();</script>
<!-- Google Analytics 4 (2026-10-28 맥스님 승인). 주소별 측정 ID. Google Signals·맞춤 광고 끔 -->
<script>(function(){var id={"tnews.pmaxone.com":"G-5DLEKHRS3V","zh.pmaxone.com":"G-PPLDYZ0827","vn.pmaxone.com":"G-484XFW9761"}[location.hostname];if(!id)return;window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag("js",new Date());gtag("config",id,{"allow_google_signals":false,"allow_ad_personalization_signals":false});var s=document.createElement("script");s.async=true;s.src="https://www.googletagmanager.com/gtag/js?id="+id;document.head.appendChild(s);})();</script>
</head>
<body>
<header><a href="../../">%(brand)s</a></header>
<main><h1>%(label)s</h1><a class="btn" href="%(target)s">이번 판 앱에서 열기 →</a>
%(brief)s
%(arts)s
<a class="btn" href="%(target)s">이번 판 앱에서 열기 →</a></main>
<footer><a href="../../">최신 뉴스</a> · <a href="../../about.html">소개</a> · <a href="../../contact.html">연락하기</a> · <a href="../../privacy.html">개인정보 처리방침</a> · <a href="../../terms.html">이용약관</a></footer>
</body>
</html>
""" % {"lang": lang, "title": e(title), "desc": e(desc), "canon": canonical_tag(url), "og": og_block, "botrx": BOT_RX,
       "target_js": json.dumps(target), "target": e(target), "brand": e(brand), "label": e(label or meta.get("label", eid)),
       "brief": brief_html, "arts": "\n".join(arts), "ld": ld_html}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import siteconf as _sc
    if (_sc.forbids_symbol("฿") and "฿" in page) or (_sc.forbids("thai") and _THAI.search(page)):   # 태국어판(kstar)은 둘 다 허용
        raise SystemExit("e/%s: '฿' 또는 태국 글자가 들어감 — 데이터 문구 확인(TRANSLATION_RULES)" % eid)
    return page


def sitemap(root=ROOT):
    site, _, _ = _site()
    idx = json.loads((root / "data/index.json").read_text(encoding="utf-8"))
    eds = idx.get("editions", [])
    latest = next((x for x in eds if x["id"] == idx.get("latest")), eds[0] if eds else {})
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lm = lambda g: ("<lastmod>%s</lastmod>" % e(g)) if g else ""
    out.append("  <url><loc>%s</loc>%s<changefreq>hourly</changefreq><priority>1.0</priority></url>" % (site, lm(latest.get("generated"))))
    for p in INFO_PAGES:
        if (root / p).exists():
            out.append("  <url><loc>%s%s</loc><changefreq>monthly</changefreq><priority>0.3</priority></url>" % (site, p))
    for x in sorted(eds, key=lambda x: x["id"], reverse=True):
        if (root / "e" / x["id"] / "index.html").exists():
            out.append("  <url><loc>%se/%s/</loc>%s<changefreq>never</changefreq><priority>0.6</priority></url>" % (site, x["id"], lm(x.get("generated"))))
    out.append("</urlset>")
    txt = "\n".join(out) + "\n"
    (root / "sitemap.xml").write_text(txt, encoding="utf-8")
    home_edition_links(root, eds)
    return len(out) - 3


def home_edition_links(root, editions, limit=14):
    """Keep real edition links in the home HTML, without requiring JS or a select change."""
    path = root / "index.html"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- edition-links:start -->", "<!-- edition-links:end -->"
    pattern = re.escape(start) + r".*?" + re.escape(end)
    _, _, lang = _site()
    block = ""
    # Other language builds must not inherit Korean navigation from the shared shell.
    if lang == "ko":
        links = []
        for item in sorted(editions, key=lambda x: x["id"], reverse=True):
            eid = item["id"]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-(am|md|pm|early)", eid):
                continue
            if not (root / "e" / eid / "index.html").is_file():
                continue
            links.append('<a href="e/%s/">%s</a>' % (e(eid), e(item.get("label") or eid)))
            if len(links) >= limit:
                break
        if links:
            block = start + '\n    <details><summary>지난 뉴스판</summary><nav aria-label="지난 뉴스판"><p class="footer__links">' + "".join(links) + '</p></nav></details>\n    ' + end
    if start in text and end in text:
        text = re.sub(pattern, lambda _: block, text, count=1, flags=re.S)
    elif block:
        anchor = '    <p class="footer__small" id="generated"></p>'
        if anchor not in text:
            raise ValueError("Home edition links: footer anchor missing")
        text = text.replace(anchor, "    " + block + "\n" + anchor, 1)
    path.write_text(text, encoding="utf-8")


def _old_head(path):
    """기존 e 쪽에서 제목·설명·OG 묶음을 그대로 꺼냄(og 이미지·카톡 미리보기 유지)."""
    t = path.read_text(encoding="utf-8")
    title = html.unescape(re.search(r"<title>(.*?)</title>", t, re.S).group(1))
    desc = html.unescape(re.search(r'<meta name="description" content="(.*?)">', t, re.S).group(1))
    og = "\n".join(l for l in t.splitlines() if l.startswith('<meta property="og:') or l.startswith('<meta name="twitter:'))
    return title, desc, og


def regen_e(root=ROOT):
    sys.path.insert(0, str(root / "tools"))
    import share_kit
    site, _, _ = _site()
    idx = json.loads((root / "data/index.json").read_text(encoding="utf-8"))
    n = 0
    for meta in idx.get("editions", []):
        p = root / "e" / meta["id"] / "index.html"
        dp = root / "data" / (meta["id"] + ".json")
        if not p.exists() or not dp.exists():
            continue
        data = json.loads(dp.read_text(encoding="utf-8"))
        title, desc, og = _old_head(p)
        tp = share_kit.story_topics(data)
        emo = {k: share_kit.TOPICS.get(v["topic"], ("", ""))[1] for k, v in tp.items()}
        # (2026-10-18) 검색 제목·설명 다시 만들기 — 카드에 골랐던 기사는 기존 설명에 든 제목으로 되찾음(og 이미지는 그대로)
        heads = [(s, share_kit.split_head(s["headline"])[0]) for s in data.get("stories", [])]
        chosen = sorted([s for s, h in heads if h and h in desc], key=lambda s: desc.find(share_kit.split_head(s["headline"])[0]))
        h1 = None
        if chosen:
            title, desc, h1 = share_kit.seo_meta(data, meta, chosen, tp)
            img = re.search(r'<meta property="og:image" content="([^"]*)"', og)
            if img:
                og = share_kit.og_tags(title, desc, site + "e/%s/" % meta["id"], html.unescape(img.group(1)))
        p.write_text(edition_page(data, meta, title, desc, og, emo, label=h1), encoding="utf-8")
        n += 1
    return n



def rss(root=ROOT, limit=30):
    """RSS 2.0 feed.xml — 네이버 서치어드바이저·구독기용. 판마다 sitemap과 같이 갱신."""
    site, brand, lang = _site()
    idx = json.loads((root / "data/index.json").read_text(encoding="utf-8"))
    eds = sorted(idx.get("editions", []), key=lambda x: x["id"], reverse=True)
    items = []
    for meta in eds:
        eid = meta["id"]
        if not (root / "e" / eid / "index.html").exists():
            continue
        link = "%se/%s/" % (site, eid)
        title = e(meta.get("label") or eid)
        desc = e("%s · %s" % (brand, meta.get("label") or eid))
        # pubDate: RFC 822 from generated ISO if present
        gen = meta.get("generated") or ""
        pub = ""
        if gen:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(gen)
                pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0700")
            except Exception:
                pub = ""
        items.append(
            "  <item>\n"
            "    <title>%s</title>\n"
            "    <link>%s</link>\n"
            "    <guid isPermaLink=\"true\">%s</guid>\n"
            "%s"
            "    <description>%s</description>\n"
            "  </item>" % (title, link, link, ("    <pubDate>%s</pubDate>\n" % pub) if pub else "", desc)
        )
        if len(items) >= limit:
            break
    channel = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        "  <title>%s</title>" % e(brand),
        "  <link>%s</link>" % e(site),
        "  <description>%s</description>" % e(brand),
        "  <language>%s</language>" % e(lang),
        '  <atom:link href="%sfeed.xml" rel="self" type="application/rss+xml"/>' % e(site),
    ] + items + ["</channel>", "</rss>", ""]
    (root / "feed.xml").write_text("\n".join(channel), encoding="utf-8")
    _ensure_rss_link(root, site)
    return len(items)


def _ensure_rss_link(root, site):
    """홈 index.html <head>에 RSS alternate 링크가 없으면 넣음(멱등)."""
    path = root / "index.html"
    if not path.exists():
        return
    t = path.read_text(encoding="utf-8")
    if 'type="application/rss+xml"' in t or "type='application/rss+xml'" in t:
        return
    tag = '<link rel="alternate" type="application/rss+xml" title="RSS" href="%sfeed.xml">' % e(site)
    if "</title>" in t:
        t = t.replace("</title>", "</title>\n" + tag, 1)
        path.write_text(t, encoding="utf-8")


def indexnow_key(root=ROOT):
    """사이트 루트 IndexNow 키 파일 보장. 반환: (key, key_file_name). 공개 값(비밀 아님)."""
    import secrets
    marker = root / "ops" / "indexnow-key"
    marker.parent.mkdir(parents=True, exist_ok=True)
    key = None
    if marker.exists():
        key = marker.read_text(encoding="utf-8").strip()
        if not (8 <= len(key) <= 128) or any(c not in "0123456789abcdefABCDEF-" for c in key):
            key = None
    if not key:
        key = secrets.token_hex(16)
        marker.write_text(key + "\n", encoding="utf-8")
    key_file = root / ("%s.txt" % key)
    if not key_file.exists() or key_file.read_text(encoding="utf-8").strip() != key:
        key_file.write_text(key + "\n", encoding="utf-8")
    # 예전 키 파일 정리(같은 마커 기준이 아닌 *.txt 는 건드리지 않음 — 마커에 적힌 키만 유지)
    return key, key_file.name


def indexnow_submit(root=ROOT, urls=None, limit=40):
    """현재 사이트 URL을 IndexNow API에 제출. urls 없으면 sitemap 최근 항목. 반환: HTTP 상태 코드(또는 -1)."""
    import urllib.request, urllib.error
    site, _, _ = _site()
    host = site.split("//", 1)[-1].rstrip("/").split("/")[0]
    key, key_name = indexnow_key(root)
    if urls is None:
        sm = root / "sitemap.xml"
        if not sm.exists():
            return -1, []
        locs = re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
        urls = locs[:limit]
    if not urls:
        return -1, []
    body = json.dumps({
        "host": host,
        "key": key,
        "keyLocation": "%s%s" % (site if site.endswith("/") else site + "/", key_name),
        "urlList": urls,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            code = resp.getcode()
            return code, urls
    except urllib.error.HTTPError as ex:
        return ex.code, urls
    except Exception as ex:
        print("indexnow submit error:", ex, file=sys.stderr)
        return -1, urls

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("regen-e", "all"):
        print("e 쪽 다시 만듦:", regen_e())
    if cmd in ("sitemap", "all"):
        n = sitemap()
        print("sitemap.xml: 판 쪽 %d개 포함" % n)
        print("feed.xml: 항목 %d개" % rss())
    if cmd == "rss":
        print("feed.xml: 항목 %d개" % rss())
    if cmd == "indexnow":
        key, name = indexnow_key()
        print("indexnow key file:", name)
        code, urls = indexnow_submit()
        print("indexnow HTTP", code, "urls", len(urls))
