# -*- coding: utf-8 -*-
"""첫 화면 속도 측정(Playwright + 크롬 CDP 느린 4G·CPU 4배 느리게): FCP·LCP·DCL·load·CLS, 5회 중앙값.
  python3 tools/dev/perf.py [URL] [회수]"""
import asyncio, sys, statistics, time
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "https://tnews.pmaxone.com/"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
JS = """()=>new Promise(res=>{let lcp=0,cls=0;new PerformanceObserver(l=>{for(const e of l.getEntries())lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)cls+=e.value}).observe({type:'layout-shift',buffered:true});
setTimeout(()=>{const n=performance.getEntriesByType('navigation')[0];const p=performance.getEntriesByType('paint').find(x=>x.name==='first-contentful-paint');
const feed=document.querySelector('#feed .card, #sheet:not([hidden]) button');res({fcp:p?p.startTime:0,lcp,cls,dcl:n.domContentLoadedEventEnd,load:n.loadEventEnd,bytes:performance.getEntriesByType('resource').reduce((a,r)=>a+(r.transferSize||0),n.transferSize||0),fontb:performance.getEntriesByType('resource').filter(r=>/pretendard/i.test(r.name)&&/[.]woff2?/.test(r.name)).reduce((a,r)=>a+(r.transferSize||0),0),fontn:performance.getEntriesByType('resource').filter(r=>/pretendard/i.test(r.name)&&/[.]woff2?/.test(r.name)&&r.transferSize>0).length})},2500)})"""
async def one(b, cold=True):
    ctx = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="ko-KR")
    pg = await ctx.new_page(); cdp = await ctx.new_cdp_session(pg)
    await cdp.send("Network.enable"); await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    await cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8})
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    # 첫 방문 시작 화면(온보딩)은 건너뛴 상태로 측정(재방문자 기준)
    await ctx.add_init_script("localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',region:'east',interests:['life'],topics:['east','visa','life','weather','society'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1}))")
    # 피드 첫 카드가 생긴 시각(페이지 시작 기준) — MutationObserver 로 기록
    await ctx.add_init_script("new MutationObserver(function(m,o){if(document.querySelector('#feed .card')){window.__feedT=performance.now();o.disconnect()}}).observe(document,{childList:true,subtree:true})")
    await pg.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(time.time()), wait_until="load", timeout=90000)
    await pg.wait_for_function("window.__feedT", timeout=30000)
    feed = await pg.evaluate("window.__feedT")
    m = await pg.evaluate(JS); m["feed"] = feed
    await ctx.close(); return m
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        rs = [await one(b) for _ in range(N)]
        await b.close()
    med = {k: statistics.median([r[k] for r in rs]) for k in rs[0]}
    print("느린 4G(150ms·1.6Mbps)+CPU×4, %d회 중앙값: 첫 화면(FCP) %.2f초 · 가장 큰 요소(LCP) %.2f초 · 첫 기사 카드 %.2f초 · DOM 준비 %.2f초 · load %.2f초 · CLS %.3f · 받은 양 %dKB"
          % (N, med["fcp"]/1000, med["lcp"]/1000, med["feed"]/1000, med["dcl"]/1000, med["load"]/1000, med["cls"], med["bytes"]/1024))
    # 2026-10-05(Max 05:23 ③): '받은 양'은 load 뒤 2.5초 안에 끝난 요청만 셈 → 글꼴 조각(Pretendard, 화면 글자에 따라 받는 unicode-range 조각)이
    #  그 창 끝에 걸리면 회마다 0~수십 KB 씩 오락가락(클래식 04:23 197KB → 05:19 241KB 가 이것). 비교는 '글꼴 제외'로
    print("   받은 양 쪼개기: 글꼴 제외 중앙값 %dKB(회마다 %s) · 창 안에 들어온 글꼴 조각 %s개 %sKB — 글꼴 조각은 화면 글자·도착 시각에 따라 달라짐(비교는 글꼴 제외로)"
          % (statistics.median([(r["bytes"] - r["fontb"]) / 1024 for r in rs]), "/".join("%d" % ((r["bytes"] - r["fontb"]) / 1024) for r in rs),
             "/".join(str(r["fontn"]) for r in rs), "/".join("%d" % (r["fontb"] / 1024) for r in rs)))
asyncio.run(main())
