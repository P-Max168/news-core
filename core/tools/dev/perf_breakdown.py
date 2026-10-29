# -*- coding: utf-8 -*-
"""받은 양 쪼개 보기(perf.py 와 같은 조건: 느린 4G·CPU×4·캐시 끔·390px): 요청마다 종류·크기·끝난 시각.
  python3 tools/dev/perf_breakdown.py URL [회수] [json 저장 경로]
  - 'perf창' = perf.py 가 세는 범위(load 뒤 2.5초 안에 끝난 요청) / '전체' = 그 뒤 5초 더 기다린 뒤 전부
  - 2026-10-05(Max 05:23 ③): 클래식 받은 양 197→241KB 원인 찾기용으로 만듦"""
import asyncio, sys, json, time, re, statistics, collections
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "https://tnews.pmaxone.com/"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
OUT = sys.argv[3] if len(sys.argv) > 3 else None
def kind(u):
    if "pretendard" in u.lower() and re.search(r"\.woff2?", u): return "글꼴 조각(" + ("jsdelivr" if "jsdelivr" in u else "자체") + ")"
    if re.search(r"\.css", u): return "css"
    if re.search(r"\.js(\?|$)", u): return "js"
    if re.search(r"/data/|\.json", u): return "데이터"
    if re.search(r"\.(png|jpe?g|svg|webp|gif|ico)", u): return "그림"
    if "open-meteo" in u or "er-api" in u or "googleapis" in u or "gstatic" in u: return "외부 API·라이브러리"
    return "기타"
async def one(b):
    ctx = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, locale="ko-KR")
    pg = await ctx.new_page(); cdp = await ctx.new_cdp_session(pg)
    await cdp.send("Network.enable"); await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    await cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150, "downloadThroughput": 1.6e6 / 8, "uploadThroughput": 750e3 / 8})
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    await ctx.add_init_script("localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',region:'east',interests:['life'],topics:['east','visa','life','weather','society'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1}));localStorage.setItem('tnk.rxon','0');localStorage.setItem('tnk.repon','0');localStorage.setItem('tnk.adclick','0')")
    await pg.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(time.time()), wait_until="load", timeout=90000)
    await pg.wait_for_timeout(2500)
    win = await pg.evaluate("(()=>{const n=performance.getEntriesByType('navigation')[0]; return {t: performance.now(), nav: n.transferSize||0, load: n.loadEventEnd}})()")
    await pg.wait_for_timeout(5000)
    rs = await pg.evaluate("performance.getEntriesByType('resource').map(e=>({u:e.name, b:e.transferSize||0, end:Math.round(e.responseEnd), st:Math.round(e.startTime)}))")
    txt = await pg.evaluate("document.body.innerText")
    await ctx.close()
    inwin = [r for r in rs if r["end"] <= win["t"]]
    return {"window_ms": round(win["t"]), "load_ms": round(win["load"]), "nav": win["nav"], "res": rs, "inwin_bytes": win["nav"] + sum(r["b"] for r in inwin),
            "all_bytes": win["nav"] + sum(r["b"] for r in rs), "chars": len(set(txt))}
def summary(r, key):
    g = collections.defaultdict(lambda: [0, 0])
    for x in r["res"]:
        if key == "win" and x["end"] > r["window_ms"]: continue
        k = kind(x["u"]); g[k][0] += 1; g[k][1] += x["b"]
    return {k: "%d개 %dKB" % (v[0], round(v[1] / 1024)) for k, v in sorted(g.items(), key=lambda kv: -kv[1][1])}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        runs = [await one(b) for _ in range(N)]
        await b.close()
    for i, r in enumerate(runs):
        print("#%d perf창 %dKB (load %.2f초 + 2.5초 = %.2f초까지) · 전체 %dKB · 화면 글자 종류 %d" % (i + 1, r["inwin_bytes"] / 1024, r["load_ms"] / 1000, r["window_ms"] / 1000, r["all_bytes"] / 1024, r["chars"]))
        print("   perf창:", summary(r, "win")); print("   전체 :", summary(r, "all"))
    print("중앙값 perf창 %dKB · 전체 %dKB" % (statistics.median([r["inwin_bytes"] for r in runs]) / 1024, statistics.median([r["all_bytes"] for r in runs]) / 1024))
    if OUT: open(OUT, "w", encoding="utf-8").write(json.dumps(runs, ensure_ascii=False, indent=1))
asyncio.run(main())
