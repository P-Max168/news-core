# -*- coding: utf-8 -*-
"""헤더 '빠른 정보' 4칸 최악 경우 점검(2026-10-05) — 가장 긴 값·글을 억지로 넣고 넘침을 잼.
  python3 tools/dev/header_worst.py [URL] [--shots DIR]     (기본 라이브, 320·360·412 × 모던·클래식)
억지로 넣는 값(모두 '가짜 시험값' — 서버에 안 씀, 화면만):
  PM2.5 188 '매우 나쁨'(가장 긴 단계) · 기온 38° · 강수확률 100% · 뇌우 아이콘 · 1바트 48.8원 · 1달러 38.8฿ · 1USDT 38.8฿ · 금 108,888฿(6자리) · 휘발유 48.88฿
  조회 시각 '12/28 23:58'(두 자리 월·일) — 브라우저 시계를 2026-12-28 23:58(방콕)로 고정
결과: 폭마다 {'over': 헤더 줄 넘친 px, 'tiles': 칸 안에서 넘친 칸 수, 'minpx': 칸 안 가장 작은 글자 px, 'vbad': '매우 나쁨' 보임}
regress.py 가 같은 함수(worst)를 씀."""
import asyncio, json, re, sys, time, pathlib
from playwright.async_api import async_playwright

NOW = "2026-12-28T23:58:00+07:00"
# --yesterday: 자정 직후(00:30) — 환율·금·휘발유는 어제 23:55 값이라 '12/27 23:55'(날짜가 그대로 남는 경우)
YDAY = "--yesterday" in sys.argv
if YDAY: NOW = "2026-12-28T00:30:00+07:00"
def fake_ticker(real):
    d = json.loads(json.dumps(real)) if real else {"v": 1}
    t = "2026-12-27T23:55:00+07:00" if YDAY else "2026-12-28T23:50:00+07:00"
    d["updated_at"] = t
    d["fx"] = dict(d.get("fx") or {}, THB_KRW=48.8, USD_THB=38.8, USD_KRW=1888, rate_time=t, fetched_at=t)
    d["usdt"] = dict(d.get("usdt") or {}, USDT_THB=38.8, price_time=t, fetched_at=t)
    d["gold"] = dict(d.get("gold") or {}, bar_sell=108888, bar_buy=108788, announced_at=t, fetched_at=t)
    d["fuel"] = dict(d.get("fuel") or {}, gasohol95=48.88, feed_date=t[:10], fetched_at=t)
    return d
WX = {"current": {"temperature_2m": 38.4, "weather_code": 95, "is_day": 1, "time": NOW[:16].replace("23:58", "23:45").replace("00:30", "00:15")}, "hourly": {"precipitation_probability": [100, 100, 90]}}
AQ = {"current": {"pm2_5": 188.4, "time": WX["current"]["time"]}}
SEED = "localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life']}));localStorage.setItem('tnk.rxon','0');localStorage.setItem('tnk.repon','0');localStorage.setItem('tnk.adclick','0')"
MEASURE = """()=>{const b=document.getElementById('ticker'); if(!b) return null; const tiles=[...b.querySelectorAll('.tk-tile')];
 let minpx=99, bad=0; const det=[];
 tiles.forEach(t=>{ const tr=t.getBoundingClientRect(); let o=0;
   t.querySelectorAll('*').forEach(e=>{ if(!e.childNodes.length) return; const has=[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()); const r=e.getBoundingClientRect();
     if(has){ minpx=Math.min(minpx, parseFloat(getComputedStyle(e).fontSize)); } if(r.width&&(r.right>tr.right+.5||r.left<tr.left-.5)) o++; });
   if(t.scrollWidth>t.clientWidth+1) o++; if(o) bad++; det.push({k:t.getAttribute('data-tk'), w:Math.round(tr.width), sw:t.scrollWidth, cw:t.clientWidth, txt:t.innerText.replace(/\\n/g,' | ')}); });
 return {over: Math.max(0,b.scrollWidth-b.clientWidth), tiles: bad, n: tiles.length, minpx: Math.round(minpx*100)/100, vbad: /매우 나쁨/.test(b.innerText), fit: b.getAttribute('data-fit'), doc: document.documentElement.scrollWidth>innerWidth+1, h: Math.round(b.getBoundingClientRect().height), det};}"""

async def worst(browser, url, width, theme="", shot=None):
    ctx = await browser.new_context(viewport={"width": width, "height": 700}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ko-KR", timezone_id="Asia/Bangkok")
    await ctx.clock.install(time=NOW)
    await ctx.add_init_script(SEED)
    real = {}
    async def tk(route):
        try:
            r = await route.fetch(); real.update(json.loads(await r.text()))
        except Exception: pass
        await route.fulfill(status=200, content_type="application/json", body=json.dumps(fake_ticker(real)))
    await ctx.route(re.compile(r".*/data/ticker\.json.*"), tk)
    await ctx.route(re.compile(r"https://api\.open-meteo\.com/.*"), lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(WX)))
    await ctx.route(re.compile(r"https://air-quality-api\.open-meteo\.com/.*"), lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(AQ)))
    await ctx.route(re.compile(r"https://firestore\.googleapis\.com/.*"), lambda r: r.abort())
    pg = await ctx.new_page()
    q = ("&" if "?" in url else "?") + "_=%d" % time.time() + ("&theme=" + theme if theme else "")
    await pg.goto(url + q, wait_until="load")
    m = None
    for _ in range(60):   # 칸 4개 + '매우 나쁨' 이 다 그려질 때까지(최대 약 30초)
        await ctx.clock.run_for(500); await pg.wait_for_timeout(250)
        m = await pg.evaluate(MEASURE)
        if m and m["n"] == 4 and m["vbad"]: break
    await pg.evaluate("document.fonts && document.fonts.ready")
    m = await pg.evaluate(MEASURE)
    if shot:
        el = pg.locator("header").first
        await el.screenshot(path=shot)
    await ctx.close()
    return m

async def main():
    url = next((a for a in sys.argv[1:] if a.startswith("http")), "https://tnews.pmaxone.com/")
    shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
    pre = sys.argv[sys.argv.index("--pre") + 1] if "--pre" in sys.argv else "worst"
    async with async_playwright() as p:
        kw = dict(args=["--no-sandbox"])
        if pathlib.Path("/usr/bin/google-chrome").exists(): kw["executable_path"] = "/usr/bin/google-chrome"
        b = await p.chromium.launch(**kw); out = {}
        for th in ["", "classic"]:
            for w in (320, 360, 412):
                m = await worst(b, url, w, th, shot=(shots and "%s/%s-%s-%d.png" % (shots, pre, th or "modern", w)))
                out["%s-%d" % (th or "modern", w)] = m
                print(th or "modern", w, {k: m[k] for k in ("over", "tiles", "n", "minpx", "vbad", "fit", "doc", "h")} if m else None, flush=True)
                if "-v" in sys.argv and m: print("   ", m["det"])
        await b.close()
    if shots: pathlib.Path(shots, pre + "-measure.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if all(m and m["over"] == 0 and m["tiles"] == 0 and m["vbad"] for m in out.values()) else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
