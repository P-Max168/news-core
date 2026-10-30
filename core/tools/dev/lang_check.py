# -*- coding: utf-8 -*-
"""언어판 로컬 화면 점검(2026-10-18 Grok) — tools/screenshot.py 는 한국판 문구·페르소나 기준이라 언어판엔 이걸 씀.
    python3 tools/dev/lang_check.py <BASE_URL> <판 id> [출력 폴더]
390px 휴대폰으로 첫 화면·설정·메뉴·기사 펼침을 열어: 콘솔 오류 0, 그 판이 보이는지(카드 수), 화면에 보이는 한글·태국 문자 0
(운영자 화면 제외 — 사용자 화면만), 사진 4장. 문제 있으면 'FAIL:' 줄 + exit 1."""
import asyncio, json, pathlib, re, sys
from playwright.async_api import async_playwright

BASE, EID = sys.argv[1].rstrip("/") + "/", sys.argv[2]
OUT = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "/tmp/lang-check"); OUT.mkdir(parents=True, exist_ok=True)
SEED = "try{localStorage.setItem('tnk.rxon','0');localStorage.setItem('tnk.repon','0');localStorage.setItem('tnk.adclick','0')}catch(e){}"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import siteconf  # noqa: E402
_C = siteconf.load()
# 화면 언어가 아닌 글자: 한국어 화면이 아니면 한글, 태국 글자를 막는 판이면 태국 문자(태국어판 kstar = 한글만)
BAD = "".join((["가-힣"] if _C.get("htmlLang", _C["lang"]) != "ko" else []) + (["\\u0E00-\\u0E3E\\u0E40-\\u0E7F"] if siteconf.forbids("thai", _C) else [])) or "\\uFFFF"
SCAN = r"""()=>{const bad=/[__BAD__]/;const out=new Set();const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
while(n=w.nextNode()){const t=n.nodeValue.trim();if(!bad.test(t))continue;const e=n.parentElement;if(!e)continue;const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 if(!r.width||!r.height||s.visibility==='hidden'||s.display==='none'||e.closest('[hidden],[aria-hidden=true]'))continue;out.add(t.slice(0,60))}
document.querySelectorAll('[aria-label],[placeholder]').forEach(e=>['aria-label','placeholder'].forEach(a=>{const v=e.getAttribute(a);if(v&&bad.test(v)&&e.getClientRects().length&&!e.closest('[aria-hidden=true]'))out.add('@'+a+'='+v.slice(0,60))}));return [...out]}"""
SCAN = SCAN.replace("__BAD__", BAD)
STEPS = [("feed", None), ("settings", "document.querySelector('[data-open-settings]')&&document.querySelector('[data-open-settings]').click()"),
         ("drawer", "var b=document.querySelector('[data-drawer-open],#menuBtn,.mbox button');b&&b.click()"),
         ("expand", "var c=document.querySelector('.card');c&&c.click()")]


async def main():
    fails = []
    async with async_playwright() as p:
        kw = dict(args=["--no-sandbox"])
        if pathlib.Path("/usr/bin/google-chrome").exists(): kw["executable_path"] = "/usr/bin/google-chrome"
        b = await p.chromium.launch(**kw)
        for name, js in STEPS:
            c = await b.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Bangkok")
            await c.add_init_script(SEED)
            await c.route(re.compile(r"https://firestore\.googleapis\.com/.*"), lambda r: r.abort())
            pg = await c.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
            await pg.goto(BASE + "?e=" + EID, wait_until="networkidle"); await pg.wait_for_timeout(1500)
            if js:
                await pg.evaluate(js); await pg.wait_for_timeout(1200)
            info = await pg.evaluate("()=>({cards:document.querySelectorAll('.card').length, sel:(document.getElementById('editionSelect')||{}).value||'', lang:document.documentElement.lang})")
            bad = await pg.evaluate(SCAN)
            await pg.screenshot(path=str(OUT / ("%s.png" % name)))
            print("%-8s 카드 %d · 판 %s · lang %s · 오류 %d · 한글/태국 %d" % (name, info["cards"], info["sel"] or "?", info["lang"], len(errs), len(bad)))
            if errs: fails.append("%s 콘솔 오류: %s" % (name, errs[:2]))
            if bad: fails.append("%s 보이는 한글/태국 문자: %s" % (name, bad[:6]))
            if name == "feed" and not info["cards"]: fails.append("feed 기사 카드 0")
            await c.close()
        await b.close()
    for f in fails: print("FAIL: " + f)
    print("사진: %s/*.png" % OUT)
    print("ALL OK" if not fails else "FAIL 개수: %d" % len(fails))
    return 1 if fails else 0

sys.exit(asyncio.run(main()))
