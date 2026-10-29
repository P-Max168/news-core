# -*- coding: utf-8 -*-
"""큰 글자 점검: 휴대폰 폭(기본 360px)에서 html 글자 크기를 100·120·150% 로 바꿔 화면마다 가로 넘침·잘린 글자를 셈 (+ 원하면 전체 사진).
  python3 tools/dev/bigtext.py [URL] [--w 360] [--shots 폴더]
화면: 첫 화면, ☰ 서랍, 기사 펼침, #places, #nearby/food, #hearts, #jobs, #rent, #approve
잘림 = 글자가 있는 칸 중 scrollWidth > clientWidth+1 이고 overflow 가 숨김/말줄임인 것(의도한 말줄임 .dq-line__q 등은 빼고 셈)."""
import asyncio, sys, time, pathlib, json
from playwright.async_api import async_playwright
args = sys.argv[1:]
URL = next((a for a in args if a.startswith("http")), "https://tnews.pmaxone.com/")
W = int(args[args.index("--w") + 1]) if "--w" in args else 360
SHOTS = pathlib.Path(args[args.index("--shots") + 1]) if "--shots" in args else None
SEED = """(()=>{ if(!localStorage.getItem('tnk.profile.v1')) localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1})); })()"""
MEASURE = """()=>{const vw=innerWidth, out=[], clip=[];
 const ok=e=>e.closest('.ticker,.tk-in,.dq-line,.k-t,.brief-line,[class*="ellip"],.sr,.sr-only,.drawer:not(.is-open)')||e.closest('[hidden]');
 for(const e of document.querySelectorAll('body *')){ if(!e.offsetParent&&getComputedStyle(e).position!=='fixed') continue; const r=e.getBoundingClientRect(); if(!r.width||!r.height) continue;
  const cs=getComputedStyle(e); if(cs.visibility==='hidden') continue;
  if(r.right>vw+1){ let R=r.right, a=e.parentElement; while(a&&a!==document.body){ const s=getComputedStyle(a); if(/hidden|clip|auto|scroll/.test(s.overflowX)) R=Math.min(R,a.getBoundingClientRect().right); a=a.parentElement; }
    if(R>vw+1) out.push(((e.className||e.tagName)+'').slice(0,40)+':'+(e.textContent||'').trim().slice(0,16)); }
  // 잘림: 버튼·링크가 잘라 내는 부모(overflow 숨김) 밖으로 3px 넘게 나감(옆으로 미는 줄 .ticker·.nb-cats·스크롤 칸은 뺌)
  if(/^(BUTTON|A)$/.test(e.tagName) && !e.closest('.ticker,.nb-cats')){ let a=e.parentElement; while(a&&a!==document.body){ const s=getComputedStyle(a); if(/hidden|clip/.test(s.overflowX)){ const pr=a.getBoundingClientRect(); if(r.right>pr.right+3||r.left<pr.left-3){ clip.push('잘림 '+((e.className||e.tagName)+'').slice(0,30)+':'+(e.textContent||'').trim().slice(0,16)); } break; } if(/auto|scroll/.test(s.overflowX)) break; a=a.parentElement; } }
  if(e.children.length===0 && e.textContent.trim() && e.scrollWidth>e.clientWidth+1 && /hidden|clip/.test(cs.overflowX+cs.overflow) && !ok(e)) clip.push(((e.className||e.tagName)+'').slice(0,40)+':'+e.textContent.trim().slice(0,20));
 }
 return {page: document.documentElement.scrollWidth>vw+1, out:[...new Set(out)].slice(0,8), clip:[...new Set(clip)].slice(0,8)}}"""
SCREENS = [("home", None), ("drawer", "drawer"), ("article", "article"), ("places", "#places"), ("nearby", "#nearby/food"), ("hearts", "#hearts"), ("jobs", "#jobs"), ("rent", "#rent"), ("approve", "#approve")]
async def main():
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for F in (100, 120, 150):
            for name, act in SCREENS:
                ctx = await b.new_context(viewport={"width": W, "height": 800}, device_scale_factor=1.5, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
                await ctx.add_init_script(SEED)
                pg = await ctx.new_page()
                await pg.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(int(time.time())), wait_until="load"); await pg.wait_for_timeout(2500)
                await pg.add_style_tag(content="html{scroll-behavior:auto!important;font-size:%d%%!important}" % F); await pg.wait_for_timeout(300)
                if act == "drawer": await pg.click("#menuBtn"); await pg.wait_for_timeout(500)
                elif act == "article": await pg.locator("#feed .card .card__head").first.click(); await pg.wait_for_timeout(500)
                elif act: await pg.evaluate("location.hash=%r" % act); await pg.wait_for_timeout(1500)
                m = await pg.evaluate(MEASURE); res["%s@%d" % (name, F)] = m
                bad = m["page"] or m["out"] or m["clip"]
                print(("문제" if bad else "통과"), "· %s %d%%" % (name, F), json.dumps(m, ensure_ascii=False) if bad else "", flush=True)
                if SHOTS and F != 100:
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    h = min(3000, await pg.evaluate("document.documentElement.scrollHeight"))
                    await pg.screenshot(path=str(SHOTS / ("big-%s-%d-f%d.jpg" % (name, W, F))), type="jpeg", quality=60, full_page=act not in ("drawer",), clip=None if act == "drawer" else {"x": 0, "y": 0, "width": W, "height": h})
                await ctx.close()
        await b.close()
    n = sum(1 for v in res.values() if v["page"] or v["out"] or v["clip"])
    print("== 큰 글자 점검(%dpx): 화면 %d개 중 문제 %d" % (W, len(res), n))
asyncio.run(main())
