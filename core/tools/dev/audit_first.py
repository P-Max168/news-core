# -*- coding: utf-8 -*-
"""첫 화면·광고 표시 점검(Max 디자인 지시 6번):
  ① 첫 화면(처음 방문 / 다시 방문 / 아이폰 다시 방문)에 화면을 덮는 창·떠 있는 요소·로그인 요구가 있는지 — position:fixed 로 보이는 것 목록(머리 줄 masthead 빼고)
  ② 보이는 광고 칸마다 '광고' 글자가 보이는지 — 첫 화면 전체(맨 아래까지)·☰ 서랍·한국 뉴스 펼침·📍 내 주변 5곳·#jobs
  python3 tools/dev/audit_first.py [URL]"""
import asyncio, sys, time, json
from playwright.async_api import async_playwright
URL = next((a for a in sys.argv[1:] if a.startswith("http")), "https://tnews.pmaxone.com/")
SEED = """(()=>{ if(!localStorage.getItem('tnk.profile.v1')) localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life'],taste:{w:{},votes:{},vf:{}},ui:{},updatedAt:1,settingsAt:1})); })()"""
IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
FIXED = """()=>[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);if(!/fixed|sticky/.test(s.position)||s.display==='none'||s.visibility==='hidden'||+s.opacity===0)return false;const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&!e.closest('.masthead')&&!e.closest('.masthead *')}).map(e=>{const r=e.getBoundingClientRect();return (e.id?'#'+e.id:'.'+String(e.className).split(' ')[0])+' '+Math.round(r.width)+'x'+Math.round(r.height)+' '+(e.innerText||'').trim().replace(/\\s+/g,' ').slice(0,30)})"""
LOGIN = """()=>{const t=document.body.innerText;const vis=[...document.querySelectorAll('[role=dialog],.sheet,.modal')].filter(e=>{if(e.hidden)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&r.right>0&&r.left<innerWidth&&r.bottom>0&&r.top<innerHeight&&s.visibility!=='hidden'&&s.display!=='none'});return {dialogs:vis.map(e=>(e.id||e.className)+':'+(e.innerText||'').slice(0,30)),loginWords:/로그인하세요|로그인이 필요|로그인해 주세요/.test(t)}}"""
ADS = """()=>{const boxes=[...document.querySelectorAll('.dm-ad, .ad')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')});
 return boxes.map(b=>{const lab=[...b.querySelectorAll('*')].find(x=>x.children.length===0&&/^\\s*(광고|AD 광고|광고 ·.*)\\s*$/.test(x.textContent)&&x.getBoundingClientRect().width>0&&getComputedStyle(x).visibility!=='hidden'&&+getComputedStyle(x).opacity>0);
  const slot=b.closest('[data-ad-slot]');return {slot:slot?slot.getAttribute('data-ad-slot'):(b.closest('.ad-slot--feed')?'infeed':b.closest('.k-ad')?'korea':b.closest('.nb-page,.tn-page')?'page':'?'),label:!!lab,txt:lab?lab.textContent.trim():''}})}"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        # ① 첫 화면
        for name, seed, ua in (("처음 방문", False, None), ("다시 방문(안드로이드·PC)", True, None), ("다시 방문(아이폰 Safari)", True, IOS)):
            kw = dict(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
            if ua: kw["user_agent"] = ua
            ctx = await b.new_context(**kw)
            if seed: await ctx.add_init_script(SEED)
            pg = await ctx.new_page(); await pg.goto(URL + "?_=%d" % time.time(), wait_until="load"); await pg.wait_for_timeout(3500)
            fx = await pg.evaluate(FIXED); lg = await pg.evaluate(LOGIN)
            await pg.evaluate("scrollTo(0, 1500)"); await pg.wait_for_timeout(600); fx2 = await pg.evaluate(FIXED)
            print(("통과" if not fx and not lg["dialogs"] and not lg["loginWords"] else "문제") + " · 첫 화면 %s — 떠 있는 것 %s · 창 %s · 로그인 요구 글 %s · (스크롤 뒤 떠 있는 것 %s)" % (name, fx, lg["dialogs"], lg["loginWords"], fx2), flush=True)
            await ctx.close()
        # ② 광고 '광고' 표시
        ctx = await b.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
        await ctx.add_init_script(SEED.replace("ui:{}", "ui:{installHintUntil:Date.now()+864e5}"))
        pg = await ctx.new_page(); allads = []
        async def grab(where):
            a = await pg.evaluate(ADS); allads.extend([dict(x, where=where) for x in a])
        await pg.goto(URL + "?_=%d" % time.time(), wait_until="load"); await pg.wait_for_timeout(3000)
        h = await pg.evaluate("document.documentElement.scrollHeight")
        for y in range(0, h, 600): await pg.evaluate("scrollTo(0,%d)" % y); await pg.wait_for_timeout(120)
        await grab("첫 화면 전체")
        if await pg.locator("[data-korea-more]").count(): await pg.locator("[data-korea-more]").first.click(); await pg.wait_for_timeout(300); await grab("한국 뉴스 펼침")
        await pg.evaluate("scrollTo(0,0)"); await pg.click("#menuBtn"); await pg.wait_for_timeout(500); await grab("☰ 서랍"); await pg.keyboard.press("Escape")
        for h2 in ("#nearby/food", "#nearby/massage", "#nearby/pet", "#nearby/beauty", "#nearby/moto", "#jobs", "#places"):
            await pg.goto("about:blank"); await pg.goto(URL + "?_=%d%s" % (time.time() * 1000, h2), wait_until="load"); await pg.wait_for_timeout(2500); await grab(h2)
        seen = {}
        for x in allads: seen.setdefault((x["where"], x["slot"]), []).append(x["label"])
        miss = [k for k, v in seen.items() if not all(v)]
        print(("통과" if not miss else "문제") + " · 광고 칸 %d개(%d곳) — '광고' 글자 없는 칸: %s" % (len(allads), len(seen), miss or "없음"))
        print("   " + json.dumps({"%s/%s" % k: len(v) for k, v in seen.items()}, ensure_ascii=False))
        await b.close()
asyncio.run(main())
