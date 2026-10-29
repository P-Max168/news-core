# -*- coding: utf-8 -*-
"""쪽 화면(#places·#rent·#jobs 등, 화면 위에 덮이는 #tnPage) 안에서 원하는 칸까지 내려서 휴대폰 사진 1장.
  python3 tools/dev/pageshot.py <저장 파일.jpg> <#주소> [CSS 선택자] [--w 360] [--font 150] [--url URL] [--first]
  --first = 첫 방문(저장값 없음)"""
import asyncio, sys, time
from playwright.async_api import async_playwright
a = sys.argv[1:]
def opt(k, d):
    if k in a: i = a.index(k); v = a[i + 1]; del a[i:i + 2]; return v
    return d
W = int(opt("--w", "360")); F = opt("--font", None); URL = opt("--url", "https://tnews.pmaxone.com/")
FIRST = "--first" in a; a = [x for x in a if x != "--first"]
OUT, HASH, SEL = a[0], a[1], (a[2] if len(a) > 2 else None)
SEED = """(()=>{ if(!localStorage.getItem('tnk.profile.v1')) localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1})); })()"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width": W, "height": 844}, device_scale_factor=1.5, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
        if not FIRST: await ctx.add_init_script(SEED)
        pg = await ctx.new_page()
        await pg.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(int(time.time())) + (HASH if HASH.startswith("#") else ""), wait_until="load"); await pg.wait_for_timeout(2500)
        await pg.add_style_tag(content="html{scroll-behavior:auto!important}" + ("html{font-size:%s%%!important}" % F if F else "")); await pg.wait_for_timeout(400)
        if SEL:
            await pg.evaluate("""(s)=>{const e=document.querySelector(s); if(!e) return; let a=e.parentElement; while(a&&a!==document.documentElement){const o=getComputedStyle(a).overflowY; if(/auto|scroll/.test(o)&&a.scrollHeight>a.clientHeight){a.scrollTop+=e.getBoundingClientRect().top-a.getBoundingClientRect().top-70; return;} a=a.parentElement;} scrollTo(0,e.getBoundingClientRect().top+scrollY-170);}""", SEL)
            await pg.wait_for_timeout(400)
        await pg.screenshot(path=OUT, type="jpeg", quality=70); print(OUT)
        await ctx.close(); await b.close()
asyncio.run(main())
