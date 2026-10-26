# -*- coding: utf-8 -*-
"""Google News RSS 검색 도우미 (수집용 — 결과는 raw/ 에만 저장, 사이트엔 안 올라감).

  python3 tools/gnews.py raw/<id>/visa "สตม." "วีซ่า DTV" "en:Thailand immigration visa"
    - 'en:' 로 시작하면 영어판(hl=en-US), 아니면 태국어판. 기본 기간 'when:8d'(외국인·비자용, 최대 7일)
    - 각 검색 RSS 를 <outdir>/gn_<검색어>.xml 로 저장하고 '방콕시각 | 매체 | 제목' 출력
  python3 tools/gnews.py --decode raw/<id>/visa "제목 일부" ...
    - 저장된 RSS 에서 제목에 해당 문자열이 들어간 항목의 실제 기사 URL 을 풀어 <outdir>/decoded.json 에 추가
※ Google News 날짜는 참고용. 실제 게재 시각은 원문 페이지에서 확인할 것(README).
"""
import sys, re, json, glob, pathlib, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import timezone, timedelta
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
BKK = timezone(timedelta(hours=7))


def search(out, queries, window="when:8d"):
    for q in queries:
        en = q.startswith("en:")
        qq = q[3:] if en else q
        hl = "en-US&gl=TH&ceid=TH:en" if en else "th&gl=TH&ceid=TH:th"
        u = "https://news.google.com/rss/search?q=" + urllib.parse.quote(qq + " " + window) + "&hl=" + hl
        data = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
        (out / ("gn_" + re.sub(r"\W+", "_", q)[:40] + ".xml")).write_bytes(data)
        items = ET.fromstring(data).findall(".//item")
        print("=== %s (%d)" % (q, len(items)))
        for it in items[:25]:
            d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(BKK)
            print(d.strftime("%m-%d %H:%M"), "|", it.findtext("source"), "|", it.findtext("title"))


def decode(out, pats):
    from googlenewsdecoder import gnewsdecoder
    fn = out / "decoded.json"
    res = json.loads(fn.read_text(encoding="utf-8")) if fn.exists() else {}
    for f in glob.glob(str(out / "gn_*.xml")):
        for it in ET.parse(f).getroot().iter("item"):
            t = it.findtext("title")
            if t in res or not any(p in t for p in pats):
                continue
            res[t] = gnewsdecoder(it.findtext("link"), interval=1).get("decoded_url")
            print(t[:90], "->", res[t])
    fn.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    dec = args and args[0] == "--decode"
    if dec:
        args = args[1:]
    out = pathlib.Path(args[0]); out.mkdir(parents=True, exist_ok=True)
    (decode if dec else search)(out, args[1:])
