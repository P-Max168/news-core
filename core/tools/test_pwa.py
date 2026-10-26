# -*- coding: utf-8 -*-
"""PWA 점검: 설치 가능 여부(Chrome CDP Page.getInstallabilityErrors), manifest, 서비스 워커, 오프라인 읽기.
  python3 tools/test_pwa.py [BASE_URL]   (http://127.0.0.1:8765/ 또는 라이브 주소. file:// 불가)
실패하면 exit 1."""
import asyncio, sys, json, pathlib, tempfile
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
OUT = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
fails = []


def check(c, m):
    print(("ok   " if c else "FAIL: ") + m)
    if not c:
        fails.append(m)


async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        kw = dict(args=["--no-sandbox"])
        if pathlib.Path("/usr/bin/google-chrome").exists():
            kw["executable_path"] = "/usr/bin/google-chrome"
        # 시크릿 모드에서는 설치 불가 판정('in-incognito') → 일반 프로필(임시 폴더)로 실행
        ctx = await p.chromium.launch_persistent_context(tempfile.mkdtemp(prefix="tnk-pwa-"), viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                                         timezone_id="Asia/Bangkok", locale="ko-KR", **kw)
        await ctx.add_init_script("localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],taste:{w:{},votes:{}},ui:{},updatedAt:1}))")
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE, wait_until="networkidle")
        ready = await pg.evaluate("Promise.race([navigator.serviceWorker.ready.then(r=>r.active&&r.active.state), new Promise(r=>setTimeout(()=>r(null),10000))])")
        check(ready in ("activated", "activating"), "서비스 워커 활성화 (%s)" % ready)
        cdp = await ctx.new_cdp_session(pg)
        man = await cdp.send("Page.getAppManifest")
        check(not man.get("errors"), "manifest 오류 없음 %s" % man.get("errors"))
        mj = json.loads(man.get("data") or "{}")
        print("  manifest:", {k: mj.get(k) for k in ("name", "short_name", "display", "theme_color", "start_url")}, "icons:", [(i["sizes"], i.get("purpose")) for i in mj.get("icons", [])])
        check(mj.get("name") == "태국 뉴스 한눈에" and mj.get("theme_color") == "#ffffff", "manifest 이름·테마색(모던 흰 헤더, 2026-10-05)")
        await pg.reload(wait_until="networkidle")   # SW 가 페이지를 제어하도록
        ctrl = await pg.evaluate("!!navigator.serviceWorker.controller")
        check(ctrl, "페이지가 서비스 워커 제어 중")
        inst = await cdp.send("Page.getInstallabilityErrors")
        check(not inst.get("installabilityErrors"), "설치 가능(Chrome installability) %s" % inst.get("installabilityErrors"))
        caches = await pg.evaluate("(async()=>{const o={};for(const k of await caches.keys()){o[k]=(await (await caches.open(k)).keys()).map(r=>r.url.replace(location.origin,''))}return o})()")
        print("  caches:", {k: len(v) for k, v in caches.items()})
        latest = await pg.evaluate("window.NEWS_INDEX.latest")
        check(any(("data/%s.js" % latest) in u for v in caches.values() for u in v), "최신 판 데이터 캐시됨(%s)" % latest)
        # 오프라인 읽기
        await ctx.set_offline(True)
        await pg.reload(wait_until="load")
        await pg.wait_for_timeout(1200)
        off = await pg.evaluate("({cards:document.querySelectorAll('#feed .card').length, top:document.querySelectorAll('#topGrid .top-card').length, brief:document.querySelectorAll('#briefing .brief-line').length, title:document.title})")
        check(off["cards"] > 0 and off["top"] == 3, "오프라인 새로고침 → 최신 판 표시 %s" % off)
        await pg.screenshot(path=str(OUT / "mobile-390-offline.png"))
        await ctx.set_offline(False)
        # 온라인: 데이터는 네트워크 우선(새로 받음)
        reqs = []
        pg.on("requestfinished", lambda r: reqs.append(r.url))
        await pg.reload(wait_until="networkidle")
        check(not errs, "페이지 오류 없음 %s" % errs)
        await ctx.close()
    if fails:
        print("FAIL 개수:", len(fails)); return 1
    print("PWA ALL OK"); return 0

sys.exit(asyncio.run(main()))
