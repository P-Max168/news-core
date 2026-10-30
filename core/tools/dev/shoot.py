# -*- coding: utf-8 -*-
"""휴대폰(390px) 스크린샷 → 작은 JPG(품질 70). 백업 폴더(backups/<태그>/)에 전·후 사진을 남길 때 씀.
  python3 tools/dev/shoot.py <저장 폴더> <접두어(before|after)> <화면…> [--url URL] [--w 360] [--font 150]
  --w = 화면 폭(기본 390, 파일 이름에 -<폭> 붙음) · --font = 글자 크게(html 글자 %, 예 120·150 — 파일 이름에 -f<값>)
화면 이름: home(첫 화면) feed(피드 중간) drawer(☰ 서랍) article(기사 펼침) nearby(📍 맛집) onboarding(첫 방문 시작 화면)
          onboarding2(시작 화면 2단계) hearts(하트 목록) admin(관리자 화면, 로그인 없이 보이는 상태) page:<경로>(예: page:privacy.html)
          footer(맨 아래) full(전체 페이지, 길이 제한)"""
import asyncio, sys, time, pathlib
from playwright.async_api import async_playwright

args = [a for a in sys.argv[1:]]
URL = "https://tnews.pmaxone.com/"
if "--url" in args:
    i = args.index("--url"); URL = args[i + 1]; del args[i:i + 2]
W, FONT = 390, None
if "--w" in args:
    i = args.index("--w"); W = int(args[i + 1]); del args[i:i + 2]
if "--font" in args:
    i = args.index("--font"); FONT = int(args[i + 1]); del args[i:i + 2]
SUF = ("-%d" % W if W != 390 else "") + ("-f%d" % FONT if FONT else "")
OUT, PFX, SHOTS = pathlib.Path(args[0]), args[1], args[2:]
SEED = """(()=>{ if(!localStorage.getItem('tnk.profile.v1')) localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life','biz'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1})); })()"""

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for name in SHOTS:
            ctx = await b.new_context(viewport={"width": W, "height": 844}, device_scale_factor=1.5, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
            if not name.startswith("onboarding"): await ctx.add_init_script(SEED)
            pg = await ctx.new_page()
            u = URL + (name[5:] if name.startswith("page:") else "")
            await pg.goto(u + ("&" if "?" in u else "?") + "_=" + str(int(time.time())), wait_until="networkidle")
            await pg.evaluate("document.fonts.ready"); await pg.wait_for_timeout(900)
            full = False
            await pg.add_style_tag(content="html{scroll-behavior:auto!important}" + ("html{font-size:%d%%!important}" % FONT if FONT else ""))
            if FONT: await pg.wait_for_timeout(300)
            if name == "myfeed": await pg.evaluate("(()=>{const c=document.querySelector('#feed .mine')||document.querySelector('#feed');scrollTo(0,c.getBoundingClientRect().top+scrollY-150)})()"); await pg.wait_for_timeout(300)
            if name == "regionad": await pg.evaluate("(()=>{const c=document.querySelector('#feed .ad-slot--region')||document.querySelector('#feed');scrollTo(0,c.getBoundingClientRect().top+scrollY-300)})()"); await pg.wait_for_timeout(300)
            if name == "feed": await pg.evaluate("(()=>{const c=document.querySelector('#feed .card:not(.pin .card)')||document.querySelector('#feed .card');scrollTo(0,c.getBoundingClientRect().top+scrollY-200)})()"); await pg.wait_for_timeout(300)
            elif name == "drawer": await pg.click("#menuBtn"); await pg.wait_for_timeout(500)
            elif name == "article":
                await pg.locator("#feed .card .card__head").first.click(); await pg.wait_for_timeout(500)
                await pg.evaluate("document.querySelector('#feed .card.is-open').scrollIntoView()"); await pg.evaluate("scrollBy(0,-120)")
            elif name == "nearby": await pg.evaluate("location.hash='#nearby/food'"); await pg.wait_for_timeout(700)
            elif name == "onboarding2":
                await pg.locator("[data-region]").first.click(); await pg.wait_for_timeout(200)
                await pg.locator("[data-ob-next]").click(); await pg.wait_for_timeout(400)
            elif name.startswith("hash:"): await pg.evaluate("location.hash=%r" % ("#" + name[5:])); await pg.wait_for_timeout(1200)
            elif name == "hearts": await pg.evaluate("location.hash='#hearts'"); await pg.wait_for_timeout(700)
            elif name == "admin": await pg.evaluate("location.hash='#admin'"); await pg.wait_for_timeout(900)
            elif name == "footer": await pg.evaluate("scrollTo(0, document.body.scrollHeight)"); await pg.wait_for_timeout(400)
            elif name == "full": full = True
            fn = OUT / ("%s-%s%s.jpg" % (PFX, name.replace("page:", "").replace("hash:", "").replace("/", "_").replace(".html", ""), SUF))
            await pg.screenshot(path=str(fn), type="jpeg", quality=70, full_page=full, clip=None if not full else {"x": 0, "y": 0, "width": W, "height": min(4000, await pg.evaluate("document.documentElement.scrollHeight"))})
            print(fn, fn.stat().st_size // 1024, "KB")
            await ctx.close()
        await b.close()
asyncio.run(main())
