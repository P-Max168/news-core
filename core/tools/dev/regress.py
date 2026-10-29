# -*- coding: utf-8 -*-
"""회귀 점검(REGRESSION_CHECKLIST.md 항목) — 라이브 사이트를 390px 휴대폰 화면으로 열어 핵심 기능을 하나씩 확인.
  python3 tools/dev/regress.py [URL] [--json out.json]
결과: 항목마다 '통과/실패/참고' 한 줄(한국어). 실패가 있으면 exit 1.
뉴스 정기 실행과 무관(개발 점검용). 첫 방문 시작 화면은 저장값을 미리 넣어 건너뜀(온보딩 자체는 따로 점검)."""
import urllib.parse, urllib.request, asyncio, json, re, sys, time, pathlib, subprocess, os
from playwright.async_api import async_playwright

URL = next((a for a in sys.argv[1:] if a.startswith("http")), "https://tnews.pmaxone.com/")
OUT = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
THAI = re.compile(r"[\u0E00-\u0E3E\u0E40-\u0E7F]")   # ฿(U+0E3F)는 허용
SEED = """(()=>{ if(!localStorage.getItem('tnk.profile.v1')) localStorage.setItem('tnk.profile.v1', JSON.stringify({v:1,onboarded:true,persona:'pattaya',topics:['east','visa','life','weather','society'],region:'east',interests:['life'],taste:{w:{},votes:{},vf:{}},ui:{installHintUntil:Date.now()+864e5},updatedAt:1,settingsAt:1})); })()"""
# 2026-10-05: RX_ON·REP_ON 이 켜진 뒤로 자동 점검이 실서버(Firestore)에 반응·신고를 쓰면 안 됨(하트 누르기 점검 = 매번 rx 문서 2개가 생김)
#  → 모든 점검 창에서 ① 이 기기 스위치 끄기(tnk.rxon·tnk.repon = "0") ② Firestore 쓰기 요청(:commit·PATCH·DELETE) 자체를 막고 수를 셈
# 2026-10-05(Max 04:30 ③): 광고 클릭 수(adclicks)도 — 코드 스위치 AD_CLICK_ON=false 지만 이 기기 끄기(tnk.adclick="0")도 같이
NOWRITE = "try{localStorage.setItem('tnk.rxon','0');localStorage.setItem('tnk.repon','0');localStorage.setItem('tnk.adclick','0')}catch(e){}"
FS = {"blocked": 0}
async def guard(c):
    await c.add_init_script(NOWRITE)
    async def h(route):
        r = route.request
        if r.method in ("PATCH", "DELETE") or ":commit" in r.url or ":batchWrite" in r.url:
            FS["blocked"] += 1; await route.abort()
        else: await route.continue_()
    await c.route(re.compile(r"https://firestore\.googleapis\.com/.*"), h)
res = []
def rec(ok, name, detail=""):
    res.append({"ok": ok, "name": name, "detail": detail})
    print(("통과" if ok is True else "실패" if ok is False else "참고") + " · " + name + (" — " + str(detail) if detail != "" else ""), flush=True)

async def main():
    async with async_playwright() as p:
        kw = dict(args=["--no-sandbox"])
        if pathlib.Path("/usr/bin/google-chrome").exists(): kw["executable_path"] = "/usr/bin/google-chrome"
        b = await p.chromium.launch(**kw)
        _nc = b.new_context
        async def _guarded(*a, **k):
            c = await _nc(*a, **k); await guard(c); return c
        b.new_context = _guarded
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                  timezone_id="Asia/Bangkok", locale="ko-KR")
        await ctx.add_init_script(SEED)
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:160]))
        pg.on("console", lambda m: errs.append("console.error: " + m.text[:160]) if m.type == "error" else None)
        t0 = time.time()
        r = await pg.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(int(t0)), wait_until="networkidle")
        await pg.wait_for_timeout(1200)
        rec(r and r.status == 200, "페이지 열림", "HTTP %s, %.1f초" % (r.status if r else None, time.time() - t0))
        # 헤더
        h = await pg.evaluate("""()=>{const t=document.getElementById('ticker'); const tiles=[...t.querySelectorAll('.tk-tile')].filter(e=>e.offsetParent!==null);
          return {menu: !!document.getElementById('menuBtn') && document.getElementById('menuBtn').offsetParent!==null, n: tiles.length, txt: tiles.map(e=>e.innerText.replace(/\\s+/g,' ')),
            over: document.documentElement.scrollWidth > innerWidth + 1, hearts: (document.getElementById('heartBtn')||{}).innerText||null}}""")
        txt = " | ".join(h["txt"])
        need = ["1바트", "원", "1달러", "฿", "USDT", "PM2.5", "금", "휘발유"]
        miss = [k for k in need if k not in txt]
        rec(h["menu"] and h["n"] == 4 and not miss and len(re.findall(r"\d{1,2}/\d{1,2} \d{2}:\d{2}", txt)) >= 4, "헤더 ☰ + 상자 4개(환율·USDT·날씨/PM2.5·금/휘발유, 조회 날짜·시각 M/D HH:MM)", txt[:200] + ((" 빠짐:" + ",".join(miss)) if miss else ""))
        rec(not h["over"], "가로 넘침 없음(390px)")
        vp = await pg.evaluate("(document.querySelector('meta[name=viewport]')||{}).content||''")
        rem = await pg.evaluate("(()=>{let px=0,rm=0;for(const sh of document.styleSheets){let rs;try{rs=sh.cssRules}catch(e){continue}const walk=l=>{for(const r of l){if(r.cssRules)walk(r.cssRules);const f=r.style&&r.style.fontSize;if(!f)continue;if(/\\dpx/.test(f)&&f!=='0px'&&!/rem/.test(f)&&!/dragon|dm-/.test(r.selectorText||''))px++;if(/rem/.test(f))rm++}};walk(rs)}return {px,rm}})()")
        rec(not re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale", vp) and rem["px"] == 0 and rem["rm"] > 100, "확대 허용(viewport 에 user-scalable=no·maximum-scale 없음) + 글자 크기 rem(광고 그림 빼고 px 글자 0)", {"viewport": vp, **rem})
        if h["hearts"] is not None: rec(True, "헤더 ❤️ 개수 표시", h["hearts"])
        # 한국 뉴스
        k = await pg.evaluate("[...document.querySelectorAll('#korea .korea__list > li:not(.k-ad)')].filter(l=>l.offsetParent!==null).length")
        rec(k >= 3, "🇰🇷 한국 주요 뉴스", "보이는 항목 %d" % k)
        # 광고 — 시작 화면(⭐ 내 피드)에서 셈. 브리핑 줄을 누르면 기사 수가 적은 주제 탭으로 바뀔 수 있어(큰 배너·기사 사이 광고 없음)
        #   그 뒤에 세면 판마다 결과가 달라짐 → 브리핑 누르기 전에 셈(2026-10-04)
        ads = await pg.evaluate("""()=>[...document.querySelectorAll('[data-ad-slot]:not([hidden]), .ad-slot--feed')].filter(e=>e.offsetParent!==null||e.closest('#drawer')).map(e=>({id:e.getAttribute('data-ad-slot')||'infeed', dm: !!e.querySelector('.dm-ad'), img: !!e.querySelector('img, picture'), art: [...e.querySelectorAll('.dm-ad__art')].every(i=>i.getAttribute('src')&&/dragon\.svg/.test(i.getAttribute('src'))), gr: /평점|Google \d/.test(e.textContent), tag: !!e.querySelector('.dm-target') && /이 자리 추천 업종/.test(e.querySelector('.dm-target').textContent), tel: !!e.querySelector('a[href="tel:+66807365211"]')}))""")
        bad = [a["id"] for a in ads if not (a["dm"] and a["img"] and a["art"] and a["tag"] and not a["gr"])]
        rec(len(ads) >= 4 and not bad, "광고 자리 = 드래곤 배너 + 같은 그림(dragon.svg) + 📢 추천 업종, 구글 평점 없음", "%d자리, 문제: %s" % (len(ads), bad or "없음"))
        rec(any(a["tel"] for a in ads), "전화 링크 tel:+66807365211")
        # 브리핑 → 기사 열림
        n_brief = await pg.locator("#briefing .brief-line[data-open]").count()
        if n_brief:
            await pg.locator("#briefing .brief-line[data-open]").first.click(); await pg.wait_for_timeout(900)
            opened = await pg.locator(".card.is-open").count()
            rec(opened > 0, "브리핑 줄 누르면 기사 펼침", "브리핑 %d줄" % n_brief)
        else: rec(False, "브리핑 줄 누르면 기사 펼침", "브리핑 줄 없음")
        # 오늘의 질문·댓글
        # 2026-10-05(Max 04:30): 예전엔 '질문 0 = 실패'로 늘 빨간 줄 → 진짜 실패가 묻힘. 오늘의 질문은 운영자 승인(tools/discussion.py apply) 뒤에만 보이는 게 정상.
        #  ① 지금 판: 승인된 질문 수(E, 판 데이터) vs 화면 질문 줄(dq). E>0 인데 dq 0 = 실패 / E=0 이고 승인 대기 초안(정본 drafts/discussion/<판>.json, .gitignore — 이 상자에만) 있으면 '참고' / 초안도 없으면 실패
        #  ② 기능: 가장 최근 '승인된 질문이 있는 판'을 열어 승인된 기사 카드마다 질문 줄이 그려지는지 + 펼치기
        dq = await pg.locator(".dq-line").count(); cm = await pg.locator("[data-cmts]").count()
        info = await pg.evaluate("""async()=>{const ed=(window.TNApp&&TNApp.edId&&TNApp.edId())||(window.NEWS_INDEX||{}).latest; const eds=((window.NEWS_INDEX||{}).editions||[]).map(e=>e.id);
          const appr=async id=>{try{const r=await fetch('data/'+id+'.json?_='+Date.now()); const d=await r.json(); return (d.stories||[]).filter(s=>s.discussion&&s.discussion.approved===true&&s.discussion.question).map(s=>s.id);}catch(e){return null}};
          const cur=await appr(ed); let ok=null, okIds=[]; for(const id of eds){ if(id===ed) continue; const a=await appr(id); if(a&&a.length){ok=id; okIds=a; break;} }
          return {ed, E: cur===null?-1:cur.length, ok, okIds};}""")
        ed = info["ed"]; E = info["E"]
        drafts = [pathlib.Path("/workspace/thai-news-portal/drafts/discussion/%s.json" % ed), pathlib.Path(__file__).resolve().parents[2] / "drafts" / "discussion" / ("%s.json" % ed)]
        nd = 0
        for f in drafts:
            if f.exists():
                try:
                    j = json.loads(f.read_text(encoding="utf-8")); nd = len(j if isinstance(j, list) else (j.get("items") or j.get("stories") or []))
                except Exception: nd = -1
                break
        if cm == 0: rec(False, "💬 댓글 칸", "판 %s 댓글 칸 0" % ed)
        if E > 0: rec(dq > 0, "💬 오늘의 질문 — 지금 판 승인된 질문이 화면에 보임", "판 %s 승인 %d · 화면 질문 줄 %d · 댓글 칸 %d" % (ed, E, dq, cm))
        elif E == 0 and nd > 0: rec(None, "💬 오늘의 질문 0 = 정상(지금 판 질문은 운영자 승인 대기)", "판 %s 승인 0 · 승인 대기 초안 %d건(drafts/discussion/%s.json) · 댓글 칸 %d" % (ed, nd, ed, cm))
        else: rec(False, "💬 오늘의 질문 — 지금 판에 승인된 질문도, 승인 대기 초안도 없음(초안 단계가 안 돌았을 수 있음)", "판 %s 승인 %d · 초안 %s · 댓글 칸 %d" % (ed, E, nd if nd else "없음", cm))
        if info["ok"]:
            pq = await ctx.new_page()
            await pq.goto(URL + ("&" if "?" in URL else "?") + "e=" + info["ok"] + "&_=" + str(int(time.time())), wait_until="load"); await pq.wait_for_timeout(2500)
            shown = await pq.evaluate("ids=>[...document.querySelectorAll('#feed .card')].filter(c=>ids.includes(c.id)).length", info["okIds"])
            dq2 = await pq.locator(".dq-line").count()
            opened = False
            if dq2:
                # 질문 줄은 카드 본문 안 → 그 카드를 먼저 펼친 뒤 질문 줄 누름(안 보이는 줄 클릭으로 30초 멈춤 방지)
                await pq.evaluate("()=>{const b=document.querySelector('.dq-line'); const c=b&&b.closest('.card'); if(c&&!c.classList.contains('is-open')) c.querySelector('.card__head').click();}"); await pq.wait_for_timeout(400)
                try:
                    await pq.locator(".dq-line").first.click(timeout=5000); await pq.wait_for_timeout(500)
                    opened = await pq.evaluate("()=>{const b=document.querySelector('.dq-line'); return !!b && b.getAttribute('aria-expanded')==='true' && b.closest('.talk').classList.contains('is-open');}")
                except Exception as ex: opened = "클릭 실패: %s" % str(ex)[:80]
            rec(shown > 0 and dq2 == shown and opened is True, "💬 승인된 질문 그리기 기능(가장 최근 승인 판) — 승인 기사 카드마다 질문 줄 + 펼치기", "판 %s 승인 %d · 화면 승인 카드 %d · 질문 줄 %d · 펼침 %s" % (info["ok"], len(info["okIds"]), shown, dq2, opened))
            # 2026-10-05(Max 05:23 ②): 승인된 질문 기사는 모두 '허용된 자리'에 있어야 함 — ① 피드 카드 ② 주요 뉴스 TOP 카드(highlights, 피드에서 일부러 뺌 '주요 뉴스 제외') ③ 내 주제 밖 기사 = 그 주제 탭.
            #  ②③ 은 눌렀을 때(TOP 카드 data-open → openStory = 주 주제 탭으로 옮겨 카드 펼침) 질문 줄이 보여야 함. 어디에도 없으면 실패
            pl = await pq.evaluate("""ids=>{const feed=[...document.querySelectorAll('#feed .card')].map(c=>c.id), top=[...document.querySelectorAll('#topGrid [data-open]')].map(c=>c.getAttribute('data-open'));
                return {feed: ids.filter(i=>feed.includes(i)), top: ids.filter(i=>!feed.includes(i)&&top.includes(i)), other: ids.filter(i=>!feed.includes(i)&&!top.includes(i))}}""", info["okIds"])
            reach = {}
            for sid in pl["top"] + pl["other"]:
                await pq.goto(URL + ("&" if "?" in URL else "?") + "e=" + info["ok"] + "&_=" + str(int(time.time())), wait_until="load"); await pq.wait_for_timeout(1500)
                if sid in pl["top"]: await pq.click('#topGrid [data-open="%s"]' % sid)
                else: await pq.evaluate("id=>TNApp.openStory(id)", sid)
                await pq.wait_for_timeout(900)
                reach[sid] = await pq.evaluate("id=>{const c=document.getElementById(id), b=c&&c.querySelector('.dq-line'); return !!(c&&c.classList.contains('is-open')&&b&&b.offsetParent!==null)}", sid)
            okpl = len(pl["feed"]) + len(reach) == len(info["okIds"]) and all(reach.values())
            rec(okpl, "💬 승인된 질문 기사는 모두 허용된 자리에 있음(피드 카드 · 주요 뉴스 TOP 카드 · 내 주제 밖 = 주제 탭) — TOP·주제 탭 기사는 누르면 카드 펼침 + 질문 줄 보임",
                "판 %s 승인 %d = 피드 %d + TOP %s + 주제 탭 %s · 눌러서 질문 보임 %s" % (info["ok"], len(info["okIds"]), len(pl["feed"]), pl["top"], pl["other"], reach))
            await pq.close()
        else:
            rec(False, "💬 승인된 질문 그리기 기능 — 승인된 질문이 있는 판을 못 찾음", info)
        # 🙌/🙅
        up = pg.locator("#feed .card [data-vote='1']").first
        if await up.count():
            await up.click(); await pg.wait_for_timeout(400)
            toast = await pg.locator("#toast").inner_text()
            st = await pg.locator("#feed .card [data-vote='1'][aria-pressed='true']").count()
            rec(st > 0 and bool(toast.strip()), "🙌 더 보여줘 / 🙅 덜 보여줘", toast.strip()[:40])
            await pg.locator("#feed .card [data-vote='1'][aria-pressed='true']").first.click(); await pg.wait_for_timeout(300)   # 취소(원상복구)
        else: rec(False, "🙌 더 보여줘 / 🙅 덜 보여줘", "버튼 없음")
        # 태국 문자·원화
        await pg.goto(URL + ("&" if "?" in URL else "?") + "tab=all&_=" + str(int(time.time())), wait_until="networkidle"); await pg.wait_for_timeout(600)
        await pg.evaluate("document.querySelectorAll('#feed .card:not(.is-open) .card__head').forEach(b=>b.click())"); await pg.wait_for_timeout(400)
        th = await pg.evaluate("document.body.innerText")   # 모든 기사를 펼친 상태
        found = THAI.findall(th)
        where = ""
        if found:   # 어디에 있는지(기사 id·요소·앞뒤 글) — 고칠 곳을 바로 찾게
            locs = await pg.evaluate(r"""()=>{const re=/[\u0E00-\u0E3E\u0E40-\u0E7F]+/, out=[]; const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
              while(w.nextNode()){const n=w.currentNode, m=n.textContent.match(re); if(!m) continue; const el=n.parentElement; if(!el.getClientRects().length) continue;
                const c=el.closest('[data-id],[id]'); const t=n.textContent, i=t.indexOf(m[0]);
                out.push((c?(c.getAttribute('data-id')||'#'+c.id):'?')+' '+el.tagName.toLowerCase()+(el.className?'.'+String(el.className).split(' ')[0]:'')+' “…'+t.slice(Math.max(0,i-12),i+m[0].length+6)+'…”');}
              return out.slice(0,6);}""")
            where = " @ " + " / ".join(locs)
        rec(not found, "화면에 태국 문자 없음(메인, 기사 전부 펼침)", "".join(found[:20]) + where)
        meta = await pg.evaluate("[...document.querySelectorAll('time, .meta, .km, .k-card__m, .tk-ft, .cm, [class*=\"time\"], [class*=\"date\"]')].map(e=>e.innerText).join(' | ')")
        rel = re.findall(r"\d+\s*(?:분|시간|일)\s*전|방금", meta)
        rec(not rel, "상대 시간('N시간 전') 없음 — 실제 날짜만(메인, 기사 전부 펼침)", rel[:5])
        krw = await pg.evaluate(r"""()=>{const d=(window.NEWS_DATA||{})[(window.NEWS_INDEX||{}).latest]; if(!d) return null; let miss=[], n=0;
          // 2026-10-05: 섞인 단위(13억678만)·범위(300~500)를 한 금액으로, 원화는 '바트' 바로 뒤 '(약 …원)' 또는 괄호 안 ', 약 …원' 만 인정(newslib.krw_check 와 같은 규칙)
          const txt=d.stories.map(s=>[s.headline].concat(s.summary||[], s.for_me||'', s.context||'', s.update||'', s.quick_replies||[], (s.discussion&&s.discussion.question)||'', (s.discussion&&s.discussion.operator_comment)||'').join(' \n ')).concat(Array.isArray(d.briefing)?d.briefing.map(b=>(b&&b.text)||''):[String(d.briefing||'')]).join(' \n ');
          const A='(?:\\d[\\d,]*(?:\\.\\d+)?\\s*[조억만]\\s*)*(?:\\d[\\d,]*(?:\\.\\d+)?)?';
          const re=new RegExp('(?<![\\d,.])(?=\\d)'+A+'(?:\\s*[~\\-–]\\s*(?=\\d)'+A+')?\\s*(?:바트|฿)','g'); let m;
          while((m=re.exec(txt))){ n++; const after=txt.slice(m.index+m[0].length), before=txt.slice(0,m.index);
            if(!/^\**\s*(?:\(\s*|,\s*)약\s*[\d조억만,.\s~\-–]*원/.test(after) && !/원\s*\(\s*약\s*$/.test(before)) miss.push(txt.slice(Math.max(0,m.index-12), m.index+m[0].length+12)); }
          return {n, miss: miss.slice(0,5), nmiss: miss.length}}""")
        if krw: rec(krw["nmiss"] == 0 if krw["n"] else None, "바트 금액 옆 원화 병기(최신 판 기사·브리핑·질문, 섞인 단위 13억678만 포함)", "%d건 중 원화 없음 %d %s" % (krw["n"], krw["nmiss"], krw["miss"]))
        # 서랍 + 주제 11개
        await pg.click("#menuBtn"); await pg.wait_for_timeout(500)
        dr = await pg.evaluate("""()=>({open: document.getElementById('drawer').classList.contains('is-open'), items: [...document.querySelectorAll('#drawer button, #drawer a')].filter(e=>e.offsetParent!==null).length, txt: document.getElementById('drawer').innerText,
            topics: [...document.querySelectorAll('#drawer [data-tab]')].map(e=>e.dataset.tab)})""")
        rec(dr["open"] and dr["items"] >= 8, "☰ 서랍 열림·메뉴", "보이는 버튼 %d" % dr["items"])
        rec(not THAI.findall(dr["txt"]), "서랍에 태국 문자 없음")
        T = ["east", "bangkok", "north", "south", "poleco", "society", "visa", "life", "travel", "ent", "weather"]
        miss = [t for t in T if t not in dr["topics"]]
        rec(not miss, "주제 11개 서랍에 있음", "빠짐: %s" % miss if miss else "11개")
        fails = []
        for t in T:
            if not await pg.evaluate("document.getElementById('drawer').classList.contains('is-open')"):
                await pg.click("#menuBtn"); await pg.wait_for_timeout(350)
            await pg.locator('#drawer [data-tab="%s"]' % t).first.click(); await pg.wait_for_timeout(350)
            ok = await pg.evaluate("""(t)=>{const title=document.getElementById('feedTitleText').innerText; const cards=[...document.querySelectorAll('#feed .card')];
                return {title, n: cards.length, okc: cards.every(c=>{const s=(window.TNApp&&window.TNApp.state.data.stories||[]).find(x=>x.id===c.id); return !s || TNTopics.storyTopics(s).all.includes(t);})}}""", t)
            if not ok["okc"]: fails.append(t)
        rec(not fails, "주제 필터 11개 동작", "잘못 걸러진 주제: %s" % fails if fails else "11개 모두 해당 주제 기사만")
        await pg.goto(URL + "?tab=feed&_=" + str(int(time.time())), wait_until="networkidle"); await pg.wait_for_timeout(800)
        # 내 주변
        for cid in ["food", "massage", "pet", "beauty", "moto"]:
            await pg.evaluate("location.hash='#nearby/%s'" % cid); await pg.wait_for_timeout(700)
            nb = await pg.evaluate("""()=>{const p=document.querySelector('.nb-page:not([hidden]), #nbPage:not([hidden])')||document.querySelector('[class*=nb-page]'); if(!p) return null;
                return {subs: p.querySelectorAll('.nb-sub').length, go: !!p.querySelector('.nb-go'), dm: !!p.querySelector('.dm-ad'), img: !!p.querySelector('.dm-ad img'), tag: !!p.querySelector('.dm-target'), th: (p.innerText.match(/[\\u0E00-\\u0E3E\\u0E40-\\u0E7F]/g)||[]).length}}""")
            rec(bool(nb) and nb["subs"] >= 2 and nb["go"] and nb["dm"] and nb["img"] and nb["tag"] and nb["th"] == 0, "📍 내 주변 %s 화면(빠른 찾기·지도·광고)" % cid, nb)
            await pg.evaluate("history.back()"); await pg.wait_for_timeout(400)
        # PWA·공유
        pw = await pg.evaluate("""async()=>{let sw=false; try{sw=await Promise.race([navigator.serviceWorker.ready.then(r=>!!r.active), new Promise(r=>setTimeout(()=>r(false),8000))]);}catch(e){}
            let man=null; try{const r=await fetch(document.querySelector('link[rel=manifest]').href); const j=await r.json(); man={icons:j.icons.map(i=>i.sizes+'/'+(i.purpose||'any')), display:j.display, start:j.start_url};}catch(e){man=String(e)}
            const og=(document.querySelector('meta[property="og:image"]')||{}).content; let ogok=null; try{const r=await fetch(og,{method:'GET',cache:'no-store'}); ogok=r.ok+' '+r.headers.get('content-type');}catch(e){ogok='cors/err'}
            return {sw, man, og, ogok, install: !!(window.TNApp)}}""")
        rec(pw["sw"] is True, "서비스 워커(오프라인·앱)")
        rec(isinstance(pw["man"], dict) and any("512" in i for i in pw["man"]["icons"]) and pw["man"]["display"] == "standalone", "manifest(아이콘 192/512·standalone)", pw["man"])
        rec(None, "홈 화면 추가 안내(설치 프롬프트)", "헤드리스에서는 설치 이벤트가 안 와서 manifest·SW 조건으로 대신 확인")
        rec(bool(pw["og"]) and ("true" in str(pw["ogok"]) or pw["ogok"] == "cors/err"), "카톡 미리보기 이미지(og:image)", "%s %s" % (pw["og"], pw["ogok"]))
        known = [e for e in errs if "429" in e]   # Open-Meteo 날씨 API 요청 제한(같은 IP 에서 점검을 자주 돌릴 때) → 화면은 ticker.json 대체값
        real = [e for e in errs if "favicon" not in e and e not in known]
        rec(not real, "콘솔 오류 없음", real[:5])
        if known: rec(None, "날씨 API 429(요청 제한) — 대체값으로 표시", len(known))
        # 내 피드 구조 — 2단계 시작 화면 스위치(topics.js ONBOARDING_2STEP)가 켜졌을 때만: 칩 → 📌 → 내 지역 → 지역 광고 → 전국
        ob2 = await pg.evaluate("!!(window.TNTopics && TNTopics.ONBOARDING_2STEP)")
        if ob2:
            fs = await pg.evaluate("""()=>({chip:(document.querySelector('#feed .mine__chip')||{}).innerText||'', nat:!!document.querySelector('#feed .fsec--nat'),
              ad:!!document.querySelector('#feed .ad-slot--region .ad, #feed .ad-slot--region a, #feed .ad-slot--region img')})""")
            rec(fs["nat"] and fs["ad"], "내 피드: 칩·내 지역·지역 광고·전국 묶음(2단계 켜짐)", fs)
        else:
            fs = await pg.evaluate("({fsec:document.querySelectorAll('#feed .fsec').length, edit:document.querySelectorAll('[data-ob-edit]').length, cards:document.querySelectorAll('#feed .card').length})")
            rec(fs["fsec"] == 0 and fs["edit"] == 0 and fs["cards"] > 0, "내 피드 = 예전 방식(2단계 시작 화면 보류 중, 묶음·'내 피드 바꾸기' 없음)", fs)
        # ❤️ 하트: 카드 ♡ → ❤️ + 토스트, 헤더 '❤️ N' → 내가 하트한 기사 페이지
        hz = {}
        try:
            cid = await pg.eval_on_selector("#feed .card", "c=>c.id")
            n0 = int(re.sub(r"\D", "", await pg.inner_text("#heartBtn")) or 0)
            await pg.click("#%s [data-heart]" % cid); await pg.wait_for_timeout(300)
            hz["toast"] = "더 보여드릴게요" in await pg.inner_text("#toast")
            hz["n"] = int(re.sub(r"\D", "", await pg.inner_text("#heartBtn")) or 0) - n0
            await pg.click("#heartBtn"); await pg.wait_for_timeout(500)
            hz["rows"] = await pg.locator("#tnPage .hp-row").count()
            await pg.go_back(); await pg.wait_for_timeout(300)
            hz["closed"] = await pg.evaluate("!document.getElementById('tnPage') || document.getElementById('tnPage').hidden")
            await pg.click("#%s [data-heart]" % cid)   # 되돌려 놓기
        except Exception as e:
            hz["err"] = str(e)[:120]
        rec(hz.get("toast") and hz.get("n") == 1 and hz.get("rows", 0) >= 1 and hz.get("closed"), "❤️ 하트 → 헤더 개수·내가 하트한 기사 페이지·뒤로 가기", hz)
        # 📊 반응 통계: 운영자가 아니면 잠금 안내
        try:
            await pg.evaluate("TNPages.open('admin')"); await pg.wait_for_timeout(400)
            lock = "운영자만" in await pg.inner_text("#tnPageBody")
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(300)
        except Exception as e:
            lock = False
        rec(lock, "📊 반응 통계 페이지 — 운영자 아니면 잠금 안내")
        try:
            await pg.evaluate("TNPages.open('approve')"); await pg.wait_for_timeout(400)
            lock2 = "운영자만" in await pg.inner_text("#tnPageBody")
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(300)
            pj = await pg.evaluate("fetch('data/pending.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>d?d.items.length:-1)")
        except Exception as e:
            lock2, pj = False, str(e)[:80]
        rec(lock2 and isinstance(pj, int) and pj >= 0, "✅ 승인함 — 운영자 아니면 잠금 안내, 목록 파일(data/pending.json) 읽힘", "항목 %s건" % pj)
        # 🛡️ 민감 기사 기준(assets/adsafe.js): 메인 큰 배너도 TOP 1 기사로 판단, 승인함에 기준표·숨긴 목록(운영자 흉내로 확인)
        try:
            ms = await pg.evaluate("""async()=>{const st=TNApp.state, d=st.data, A=window.TNAdSafe; if(!A) return {err:'no TNAdSafe'};
              const mid=()=>{const e=document.querySelector('[data-ad-slot="mid"]'); return {hidden:e.hidden, flag:e.hasAttribute('data-ad-hidden')}};
              const risky=d.stories.filter(s=>A.score(s).hide), hl0=d.highlights[0], r={risky:risky.length, now:mid(), hl0risk:A.score(d.stories.find(s=>s.id===hl0)).hide};
              if(risky.length){ d.highlights[0]=risky[0].id; TNApp.rerender(); r.swapped=mid(); d.highlights[0]=hl0; TNApp.rerender(); r.back=mid(); }
              const S=window.TNSocial, o=S&&S.isAdmin; if(S) S.isAdmin=()=>true;
              TNPages.open('approve'); await new Promise(z=>setTimeout(z,1500));
              const sec=document.querySelector('#tnPageBody #adsafe'); r.sec=!!sec; r.rules=sec?sec.querySelectorAll('.as-rules tbody tr').length:0;
              r.listed=sec?sec.querySelectorAll(':scope > .as-list > .as-item').length:-1; r.why=sec?/점 → 광고 숨김/.test(sec.innerText)||!risky.length:false;
              TNPages.close(); if(S) S.isAdmin=o; return r}""")
            await pg.wait_for_timeout(300)
        except Exception as e:
            ms = {"err": str(e)[:120]}
        okm = ms.get("sec") and ms.get("rules", 0) >= 10 and ms.get("listed") == ms.get("risky") and ms.get("why") and ms.get("now", {}).get("flag") == ms.get("hl0risk")
        if ms.get("risky"): okm = okm and ms.get("swapped") == {"hidden": True, "flag": True} and ms.get("back", {}).get("flag") == ms.get("hl0risk")   # 10-11: 되돌린 뒤 = 원래 TOP 1 의 위험 여부(민감 TOP 1 이면 숨김 그대로가 정답)
        rec(okm, "🛡️ 민감 기사 점수 기준 — 메인 큰 배너도 TOP 1 기사가 걸리면 숨김(기사는 그대로), 승인함에 기준표·숨긴 목록·이유", ms)
        # 애드센스 준비: 광고 칸 표준 단위·민감 기사 옆 광고 없음·안내 4쪽·ads.txt
        try:
            au = await pg.evaluate("""()=>{const f=[...document.querySelectorAll('#feed .ad-slot--feed')];
              const bad=f.filter(a=>[a.previousElementSibling,a.nextElementSibling].some(x=>x&&x.dataset&&x.dataset.adsafe==='0')).length;
              const shown=[...document.querySelectorAll('.ad-slot[data-ad-slot]:not([hidden])')];
              return {units:shown.filter(e=>e.dataset.unit).length, shown:shown.length, feedAds:f.length, nextToRisky:bad,
                      popups:document.querySelectorAll('ins.adsbygoogle,script[src*="adsbygoogle"]').length}}""")
        except Exception as e:
            au = {"err": str(e)[:80]}
        rec(au.get("shown", 0) > 0 and au.get("units") == au.get("shown") and au.get("nextToRisky") == 0 and au.get("popups") == 0,
            "광고 칸 — 모두 표준 단위(data-unit), 민감 기사 바로 옆 광고 없음, 애드센스 코드·자동 광고 없음", au)
        lg = {}
        for f in ["privacy.html", "terms.html", "about.html", "contact.html", "ads.txt"]:
            lg[f] = await pg.evaluate("f=>fetch(f,{cache:'no-store'}).then(r=>r.ok?r.text():'').then(t=>t.length).catch(()=>-1)", f)
        links = await pg.locator(".footer__links a").count()
        rec(all(v > 100 for v in lg.values()) and links == 4, "안내 4쪽(개인정보·약관·소개·연락) + ads.txt 열림, 푸터 링크 4개", dict(lg, footerLinks=links))
        # ③d 내 주변: 화면 안 종류 바꾸기 5칸(같은 크기) + '이렇게 찾아요' 기준, 뒤로 = 피드
        try:
            await pg.evaluate("window.scrollTo(0,0)")
            await pg.click('#nearbyRow [data-nb-cat="food"]'); await pg.wait_for_timeout(600)
            await pg.click('[data-nb-sw="moto"]'); await pg.wait_for_timeout(500)
            sw = await pg.evaluate("({t:document.getElementById('nbTitle').textContent,h:location.hash,ws:[...new Set([...document.querySelectorAll('.nb-sw')].map(e=>Math.round(e.getBoundingClientRect().width)))].length,n:document.querySelectorAll('.nb-sw').length,how:!!document.querySelector('.nb-how summary')})")
            await pg.go_back(wait_until="commit"); await pg.wait_for_timeout(500)
            sw["back"] = await pg.evaluate("!document.querySelector('#nearbyPage:not([hidden])') && history.state === null")
        except Exception as e:
            sw = {"err": str(e)[:100]}
        rec(sw.get("h") == "#nearby/moto" and sw.get("n") == 5 and sw.get("ws") == 1 and sw.get("how") and sw.get("back"), "📍 내 주변 — 화면 안에서 종류 바꾸기(같은 크기 5칸)·'이렇게 찾아요'·뒤로 = 피드", sw)
        # 360px 폭: 내 주변 헤더 줄·종류 바꾸기 칸 = 같은 너비, 글자가 칸 안에 들어감(안 잘림)
        try:
            vs = pg.viewport_size; await pg.set_viewport_size({"width": 360, "height": 740}); await pg.wait_for_timeout(400)
            fit = await pg.evaluate("""()=>{const m=(sel,ts)=>{const c=[...document.querySelectorAll(sel)];return {n:c.length,ws:[...new Set(c.map(e=>Math.round(e.getBoundingClientRect().width)))].length,
              over:c.filter(e=>{const t=e.querySelector(ts),r=document.createRange();r.selectNodeContents(t);const cs=getComputedStyle(e);return r.getBoundingClientRect().width>e.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight)+0.5}).map(e=>e.innerText.trim())}};
              return m('#nearbyRow .nb-cat','.nb-cat__t')}""")
            await pg.set_viewport_size(vs); await pg.wait_for_timeout(300)
        except Exception as e:
            fit = {"err": str(e)[:100]}
        rec(fit.get("n") == 5 and fit.get("ws") == 1 and fit.get("over") == [], "360px 폭 — 내 주변 줄 5칸 같은 너비·글자 안 잘림", fit)
        # ⑦ 가게 카드 시험(#places): 실제 OSM 30곳 + Google 지도 한식·한인 20곳, 필터, 칸별 출처, 오래된 정보 뒤로, 태국 문자 없음
        try:
            await pg.evaluate("TNPages.open('places')"); await pg.wait_for_timeout(1200)
            pc = {"n": await pg.locator("#tnPage .pc").count()}
            await pg.click('[data-pc-cat="pet"]'); await pg.wait_for_timeout(300); pc["pet"] = await pg.locator("#tnPage .pc").count()
            await pg.click('[data-pc-cat="korean"]'); await pg.wait_for_timeout(300); pc["kr"] = await pg.locator("#tnPage .pc").count()
            pc["krsrc"] = await pg.evaluate("[...document.querySelectorAll('#tnPage .pc')].every(c=>c.querySelectorAll('.pc__fs').length>=5 && /한식·한인/.test(c.textContent))")
            pc["gm"] = await pg.evaluate("(()=>{const g=[...document.querySelectorAll('#tnPage .pc')].filter(c=>/구글 지도에서 보기/.test(c.textContent));return {n:g.length,bad:g.filter(c=>c.querySelector('a[href^=\"tel:\"]')||/\\+66|★|평점/.test(c.textContent)).length}})()")
            await pg.click('[data-pc-cat="all"]'); await pg.wait_for_timeout(300); pc["all"] = await pg.locator("#tnPage .pc").count()
            # 2026-10-05 06:55: 오래된 정보 중 영업 확인 안 된 곳 = 본 목록 뒤 접힌 칸(영업 확인된 곳은 배지 달고 본 목록, 폐업 의심은 그 아래 칸 — ⑦-2 (나)가 자리 자세히 검사)
            pc["oldlast"] = await pg.evaluate("(()=>{const f=document.querySelector('#tnPage .pc-fold--old');if(!f)return false;const m=[...document.querySelectorAll('#tnPage .pc-list > .pc')].filter(c=>!c.closest('.pc-fold,.pc-sus'));return m.length>0&&[...f.querySelectorAll('.pc')].every(c=>c.querySelector('.pc__old:not(.pc__rc)'))&&m.every(c=>c.compareDocumentPosition(f)&4)})()")
            pc["price"] = await pg.evaluate("(()=>{const c=[...document.querySelectorAll('#tnPage .pc')];return c.length>0&&c.every(e=>{const p=e.querySelector('.pc__top + .pc__price');return p&&(/가격 확인 안 됨/.test(p.textContent)||/[\\d,]+바트 약 [\\d,]+원/.test(p.textContent))})})()")
            pc["vat"] = await pg.evaluate("(()=>{const c=[...document.querySelectorAll('#tnPage .pc')];return c.length>0&&c.every(e=>/가격 VAT 별도/.test(e.textContent))})()")
            pc["excl"] = await pg.evaluate("/cannabis|대마|casino|카지노|도박|erotic|성인용/i.test(document.getElementById('tnPage').textContent)")
            pc["thai"] = await pg.evaluate("/[\\u0E00-\\u0E7F]/.test(document.getElementById('tnPage').textContent)")
            pc["src"] = await pg.evaluate("document.getElementById('tnPage').innerText.indexOf('OpenStreetMap contributors')>=0")
            # 파타야 동네 5칸(같은 크기·한 줄) → 누르면 줄고, 다시 누르면 전체
            pc["sub"] = await pg.evaluate("(()=>{const b=[...document.querySelectorAll('[data-pc-sub]')];const r=b.map(x=>x.getBoundingClientRect());return {n:b.length,same:r.every(q=>Math.abs(q.width-r[0].width)<1.5&&Math.abs(q.top-r[0].top)<1)}})()")
            await pg.click('[data-pc-sub="east"]'); await pg.wait_for_timeout(300); pc["sub"]["east"] = await pg.locator("#tnPage .pc").count()
            await pg.click('[data-pc-sub="east"]'); await pg.wait_for_timeout(300); pc["sub"]["back"] = await pg.locator("#tnPage .pc").count()
            # 지역: 시라차·방콕(OSM 한식·한인만)
            await pg.click('[data-pc-region="bangkok"]'); await pg.wait_for_timeout(1500)
            pc["bkk"] = await pg.evaluate("(()=>{const c=[...document.querySelectorAll('#tnPage .pc')];return {n:c.length,kr:c.filter(x=>/한식·한인 업소/.test(x.textContent)).length,osm:c.every(x=>/출처: OpenStreetMap/.test(x.textContent)),thai:/[\\u0E00-\\u0E7F]/.test(document.getElementById('tnPage').textContent)}})()")
            await pg.click('[data-pc-region="sriracha"]'); await pg.wait_for_timeout(1500)
            pc["sri"] = await pg.locator("#tnPage .pc").count()
            await pg.click('[data-pc-region="pattaya"]'); await pg.wait_for_timeout(800)
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(400)
        except Exception as e:
            pc = {"err": str(e)[:100]}
        rec((lambda q: q.get("n") == 5 and q.get("same") and 0 < q.get("east", 0) < pc.get("all", 0) == q.get("back"))(pc.get("sub", {})) and pc.get("vat") is True and pc.get("price") is True and pc.get("excl") is False and pc.get("all", 0) >= 40 and 0 < pc.get("pet", 0) < 30 and pc.get("kr", 0) >= 10 and pc.get("bkk", {}).get("n", 0) >= 20 and pc["bkk"].get("kr") == pc["bkk"].get("n") and pc["bkk"].get("osm") and pc["bkk"].get("thai") is False and pc.get("sri", 0) >= 1 and pc.get("gm", {}).get("n", 0) >= 20 and pc.get("gm", {}).get("bad") == 0 and pc.get("krsrc") and pc.get("oldlast") and pc.get("thai") is False and pc.get("src"),
            "📇 가게 카드 — 지역 3곳(파타야·시라차·방콕 OSM 한식·한인) · 한식·한인 10곳+(칸마다 출처·확인일, 구글 지도 가게는 이름·동네·링크만 — 전화·시간·평점 없음)·오래된 정보(영업 확인 안 된 곳) 본 목록 뒤 접힌 칸·종류 필터·태국 문자 없음", pc)
        # ⑦-2 가게 카드 믿음 규칙(2026-10-05 Max 06:33·06:55 — 사장님 '폐업한 곳이 너무 많다, 확인했다고 적어 놓고'): 지역 3곳 모두, 기대값은 여기서 데이터(JSON)로 따로 계산
        #   (가) 조사 기록(verified_status='영업 확인' + verified_by + verified_at + verified_source_url)이 없는 가게 카드·안내 글에 '실제로 확인'·'최종 확인'·'확인함' 이 있으면 실패
        #   (나) 지도 기준 날(현장 확인 날, 없으면 지도 정보 고친 날 — 구글 지도 가게는 없음) < 오늘(방콕) − 730일 인 가게: 🕰️ 배지 + 자리(영업 확인 = 본 목록 / 폐업 의심 = 맨 아래 칸 / 보관함 / 나머지 = 오래된 정보 접힌 칸)
        #   (다) 초록불('🟢 지금 영업 중·곧 닫아요·지금 닫힘' + data-pc-ok)은 '영업 확인' 90일 안(폐업 의심·보관함·폐업 신고됨 아님)만 + 화면 함수 openOK 가 89일 전 확인 = 켬, 91일 전 = 끔
        #   (라) 폐업 보관함 가게(data/places-flags.json st=closed)는 기본 화면에서 닫힌 보관함 칸 안에만, '지금 영업 중만 보기'에서는 아예 없음 / 폐업 의심은 맨 아래 칸(.pc-sus)
        import datetime as _dt
        _td = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=7))).date()
        ob = (_td - _dt.timedelta(days=730)).isoformat(); fb = (_td - _dt.timedelta(days=90)).isoformat()
        tr = {}
        try:
            with urllib.request.urlopen(URL.split("?")[0].rstrip("/") + "/data/places-flags.json?_=%d" % int(time.time()), timeout=20) as rr:
                FL = json.loads(rr.read().decode("utf-8")).get("flags") or {}
            await pg.evaluate("TNPages.open('places')"); await pg.wait_for_timeout(1200)
            for rg in ("pattaya", "sriracha", "bangkok"):
                await pg.click('[data-pc-region="%s"]' % rg); await pg.wait_for_timeout(1500)
                if await pg.locator('[data-pc-cat="all"][aria-pressed="false"]').count(): await pg.click('[data-pc-cat="all"]'); await pg.wait_for_timeout(300)
                if await pg.locator('[data-pc-open][aria-pressed="true"]').count(): await pg.click('[data-pc-open]'); await pg.wait_for_timeout(300)
                if await pg.locator('[data-pc-sub][aria-pressed="true"]').count(): await pg.click('[data-pc-sub][aria-pressed="true"]'); await pg.wait_for_timeout(300)
                JS = """()=>{const p=document.getElementById('tnPage');return {intro:(p.querySelector('.pc-intro')||{}).textContent||'',
                  archOpen:!!p.querySelector('.pc-fold--arch[open]'), last:[...p.querySelectorAll('.pc-list > .pc')].slice(-1).map(c=>c.dataset.pc)[0]||'',
                  cards:[...p.querySelectorAll('.pc[data-pc]')].map(c=>({id:c.dataset.pc,txt:c.textContent,old:!!c.querySelector('.pc__old:not(.pc__rc)'),
                    at:c.closest('.pc-fold--old')?'old':c.closest('.pc-fold--arch')?'arch':c.closest('.pc-sus')?'sus':'main', ok:c.hasAttribute('data-pc-ok'),
                    st:(c.querySelector('.pc__top .pc__open')||{}).textContent||''}))}}"""
                dom = await pg.evaluate(JS)
                with urllib.request.urlopen(URL.split("?")[0].rstrip("/") + "/data/places-%s.json?_=%d" % (rg, int(time.time())), timeout=20) as rr:
                    data = json.loads(rr.read().decode("utf-8"))
                P = data["places"]; byid = {c["id"]: c for c in dom["cards"]}
                rec_ = lambda q: bool(q.get("verified_status") and q.get("verified_by") and q.get("verified_at") and q.get("verified_source_url"))
                ver = lambda q: rec_(q) and q["verified_status"] == "영업 확인"
                sus = lambda q: rec_(q) and q["verified_status"] == "폐업 의심"
                arc = lambda q: (FL.get(q["id"]) or {}).get("st") == "closed"
                rep = lambda q: (FL.get(q["id"]) or {}).get("n", 0) >= 2
                base = lambda q: None if q.get("gmaps_only") else (q.get("osm_check") or q.get("osm_edit") or None)
                BAD = re.compile(r"실제로 확인|최종 확인|확인함")
                badw = [q["id"] for q in P if not ver(q) and q["id"] in byid and BAD.search(byid[q["id"]]["txt"])] + (["(안내 글)"] if BAD.search(dom["intro"]) else [])
                olds = [q for q in P if base(q) and base(q) < ob]
                where = lambda q: "arch" if arc(q) else "sus" if sus(q) else "main" if ver(q) else "old"
                miss = [q["id"] for q in olds if q["id"] not in byid or not byid[q["id"]]["old"] or byid[q["id"]]["at"] != where(q)]
                okopen = {q["id"] for q in P if ver(q) and str(q["verified_at"])[:10] >= fb and not sus(q) and not arc(q) and not rep(q)}
                badopen = [c["id"] for c in dom["cards"] if (c["ok"] or re.search(r"지금 영업 중|곧 닫아요|지금 닫힘", c["st"])) and c["id"] not in okopen]
                nok = sum(1 for c in dom["cards"] if c["ok"])
                vq = next((q for q in P if ver(q) and not sus(q) and not arc(q) and not rep(q)), None)
                unit = None
                if vq:
                    d89 = (_td - _dt.timedelta(days=89)).isoformat() + " 12:00"; d91 = (_td - _dt.timedelta(days=91)).isoformat() + " 12:00"
                    unit = await pg.evaluate("([p,a,b])=>[TNPlaces.openOK(Object.assign({},p,{verified_at:a})),TNPlaces.openOK(Object.assign({},p,{verified_at:b})),TNPlaces.openOK(Object.assign({},p,{verified_status:'확인 불가'}))]", [vq, d89, d91])
                arch_ids = {q["id"] for q in P if arc(q)}
                archbad = [i for i in arch_ids if i not in byid or byid[i]["at"] != "arch"] + [c["id"] for c in dom["cards"] if c["at"] == "arch" and c["id"] not in arch_ids] + (["(보관함 열림)"] if dom["archOpen"] else [])
                susbad = [q["id"] for q in P if sus(q) and not arc(q) and (q["id"] not in byid or byid[q["id"]]["at"] != "sus")]
                await pg.click('[data-pc-open]'); await pg.wait_for_timeout(400)
                dom2 = await pg.evaluate(JS)
                await pg.click('[data-pc-open]'); await pg.wait_for_timeout(300)
                archbad += ["영업중만:" + c["id"] for c in dom2["cards"] if c["id"] in arch_ids or c["at"] == "arch"]
                badopen += ["영업중만:" + c["id"] for c in dom2["cards"] if c["id"] not in okopen]
                tr[rg] = {"n": len(P), "cards": len(dom["cards"]), "old": len(olds), "badge": sum(1 for c in dom["cards"] if c["old"]), "miss": miss[:5], "nmiss": len(miss),
                          "badw": badw[:5], "nbadw": len(badw), "badopen": badopen[:5], "nbadopen": len(badopen), "openok": len(okopen), "green": nok, "unit": unit,
                          "arch": len(arch_ids), "archbad": archbad[:5], "sus": len([q for q in P if sus(q) and not arc(q)]), "susbad": susbad[:5], "openonly": len(dom2["cards"])}
            await pg.click('[data-pc-region="pattaya"]'); await pg.wait_for_timeout(800)
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(400)
        except Exception as e:
            tr = {"err": str(e)[:120]}
        okr = "err" not in tr and len(tr) == 3
        rec(okr and all(v["nbadw"] == 0 and v["cards"] == v["n"] for v in tr.values()),
            "📇 가게 카드 — 조사 기록(영업 확인+누가+언제+근거 링크) 없는 가게에 '실제로 확인'·'최종 확인'·'확인함' 문구 없음(파타야·시라차·방콕)",
            {k: {"카드": v["cards"], "문구 걸림": v["nbadw"], "예": v["badw"]} for k, v in tr.items()} if okr else tr)
        rec(okr and all(v["nmiss"] == 0 for v in tr.values()),
            "📇 가게 카드 — 지도 정보 2년 넘음(기준 날 < 오늘−730일 = %s)은 전부 🕰️ 배지 + 제자리(영업 확인 = 본 목록 · 폐업 의심 = 맨 아래 · 보관함 · 나머지 = 접힌 칸)(파타야·시라차·방콕)" % ob,
            {k: {"2년 넘음": v["old"], "배지": v["badge"], "빠짐": v["nmiss"], "예": v["miss"]} for k, v in tr.items()} if okr else tr)
        rec(okr and all(v["nbadopen"] == 0 and (v["unit"] is None or v["unit"] == [True, False, False]) for v in tr.values()) and any(v["unit"] for v in tr.values()),
            "📇 가게 카드 — 초록불(🟢 지금 영업 중·닫힘 표시)은 '영업 확인' %s일 안 가게만(이후 = 꺼짐·재확인 필요, 89일 전 켬 · 91일 전 끔 · 확인 불가 끔)(기준 %s)" % (90, fb),
            {k: {"켜도 되는 곳": v["openok"], "켜진 곳": v["green"], "어긴 곳": v["nbadopen"], "예": v["badopen"], "89/91일·확인불가": v["unit"]} for k, v in tr.items()} if okr else tr)
        rec(okr and all(not v["archbad"] and not v["susbad"] for v in tr.values()),
            "📇 가게 카드 — 폐업 보관함 가게는 기본 목록·'지금 영업 중만 보기'에 없음(닫힌 보관함 칸 안에만) · ⚠️ 폐업 의심은 맨 아래 칸",
            {k: {"보관함": v["arch"], "어긴 곳": v["archbad"], "폐업 의심": v["sus"], "자리 틀림": v["susbad"], "영업중만 카드": v["openonly"]} for k, v in tr.items()} if okr else tr)
        # 🧑‍💼 구인판 시안(#jobs): 주소로만 열림, 예시 6개(모두 '예시' 표시), 광고 1칸, 입력·올리기 없음, 메뉴 링크 없음
        try:
            await pg.evaluate("location.hash='#jobs'"); await pg.wait_for_timeout(2500)
            jb = await pg.evaluate("""()=>{const p=document.getElementById('tnPage');return {open:TNPages.current()==='jobs', n:p.querySelectorAll('.jb').length, ex:p.querySelectorAll('.jb .jb-ex').length, warn:/모두 예시/.test(p.textContent), ad:p.querySelectorAll('.jb-ad .dm-ad').length,
              forms:p.querySelectorAll('form,input,textarea').length, thai:/[\\u0E00-\\u0E7F]/.test(p.textContent), linked:!!document.querySelector('a[href="#jobs"],[data-page="jobs"]')}}""")
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(400)
        except Exception as e:
            jb = {"err": str(e)[:100]}
        rec(jb.get("open") and jb.get("n") == 6 and jb.get("ex") == 6 and jb.get("warn") and jb.get("ad") == 1 and jb.get("forms") == 0 and jb.get("thai") is False and jb.get("linked") is False,
            "🧑‍💼 구인판 시안(#jobs) — 주소로만, 예시 6개 모두 '예시', 광고 1칸, 입력·올리기 없음, 메뉴 링크 없음", jb)
        # 🏠 임대 카드 시험(#rent): 공개 매물 10개, 월세 바트+원, ㎡+평, 칸마다 출처, 메뉴 링크 없음
        try:
            await pg.evaluate("TNPages.open('rent')"); await pg.wait_for_timeout(1500)
            rc = await pg.evaluate("""()=>{const c=[...document.querySelectorAll('#tnPage .rc')];return {n:c.length,
              krw:c.filter(e=>/바트 \(약 [\d,]+원\)/.test(e.textContent)).length, py:c.filter(e=>/㎡ \(약 [\d.]+평\)/.test(e.textContent)).length,
              wd:/임대 카드 시험은 내렸어요/.test(document.getElementById('tnPage').textContent) && !!document.querySelector('#tnPage a[href="https://www.lifullconnect.com/legal-notice-fazwaz/"]'),
              src:c.every(e=>e.querySelectorAll('.pc__fs a[href^="https://www.fazwaz.com/"]').length>=4), img:document.querySelectorAll('#tnPage .rc img').length,
              thai:/[\u0E00-\u0E7F]/.test(document.getElementById('tnPage').textContent), linked:!!document.querySelector('a[href="#rent"],[data-page="rent"]')}}""")
            await pg.evaluate("TNPages.close()"); await pg.wait_for_timeout(300)
        except Exception as e:
            rc = {"err": str(e)[:100]}
        rec(rc.get("n") == 0 and rc.get("wd") and rc.get("img") == 0 and rc.get("thai") is False and rc.get("linked") is False,
            "🏠 임대 카드 시험 — 내림(출처 약관: 복사·모으기 금지) 안내 + 약관 링크만, 매물 0개, 메뉴 링크 없음", rc)
        # 다듬기: 글자 대비(WCAG AA) — 첫 화면(주요 뉴스 사진 카드는 계산 불가라 뺌)
        try:
            await pg.evaluate("window.scrollTo(0,0)")
            low = await pg.evaluate(pathlib.Path(__file__).with_name("contrast.js").read_text(encoding="utf-8"))
        except Exception as e:
            low = [{"err": str(e)[:80]}]
        rec(not low, "글자 대비 4.5:1(큰 글자 3:1) 미달 없음 — 첫 화면", ("%d곳: " % len(low) + ", ".join("%s %s(%s)" % (x.get("cls"), x.get("t"), x.get("cr")) for x in low[:4])) if low else "")
        # 앱 포장 준비: 휴대폰 뒤로 버튼 = 서랍·설정 창·페이지·내 주변 닫기, 기록 칸 안 남음
        bk = {}
        try:
            async def stt():
                return await pg.evaluate("({dr:document.getElementById('drawer').classList.contains('is-open'),sh:!document.getElementById('sheet').hidden,pg:!!(window.TNPages&&TNPages.current()),nb:!!document.querySelector('#nearbyPage:not([hidden])'),hs:history.state})")
            async def gb():
                await pg.go_back(wait_until="commit"); await pg.wait_for_timeout(400)
            await pg.evaluate("window.scrollTo(0,0)")
            await pg.click("#menuBtn"); await pg.wait_for_timeout(400); await gb(); x = await stt(); bk["서랍"] = not x["dr"] and x["hs"] is None
            await pg.click("#menuBtn"); await pg.wait_for_timeout(400); await pg.click("#drawerQuick [data-page=hearts]"); await pg.wait_for_timeout(500); await gb(); x = await stt(); bk["서랍→하트"] = not x["pg"] and not x["dr"] and x["hs"] is None
            await pg.click("#menuBtn"); await pg.wait_for_timeout(400); await pg.click("#drawerQuick [data-quick-nearby]"); await pg.wait_for_timeout(600); await gb(); x = await stt(); bk["서랍→내 주변"] = not x["nb"] and x["hs"] is None
            await pg.click("#menuBtn"); await pg.wait_for_timeout(400); await pg.click("#drawer [data-open-settings]"); await pg.wait_for_timeout(500); await gb(); x = await stt(); bk["서랍→설정 창"] = not x["sh"] and x["hs"] is None
            await pg.click("#menuBtn"); await pg.wait_for_timeout(400); await pg.click("[data-drawer-close]"); await pg.wait_for_timeout(400); x = await stt(); bk["✕ 닫기 뒤 기록 칸"] = x["hs"] is None
        except Exception as e:
            bk["err"] = str(e)[:100]
        rec(bool(bk) and all(v is True for v in bk.values()), "휴대폰 뒤로 버튼 = 서랍·하트·내 주변·설정 창 닫기(피드에 남음, 기록 칸 안 남음)", bk)
        try:
            mf = await pg.evaluate("fetch('manifest.json',{cache:'no-store'}).then(r=>r.json()).then(d=>({icons:d.icons.map(i=>i.sizes+'/'+(i.purpose||'any')).join(' '),shortcuts:(d.shortcuts||[]).length}))")
            off = await pg.evaluate("fetch('offline.html',{cache:'no-store'}).then(r=>r.ok?r.text():'').then(t=>t.indexOf('연결되어 있지 않아요')>0)")
        except Exception as e:
            mf, off = {"err": str(e)[:80]}, False
        rec(isinstance(mf, dict) and "512x512/maskable" in mf.get("icons", "") and "192x192/any" in mf.get("icons", "") and mf.get("shortcuts") == 2 and off,
            "앱 포장 준비 — manifest 아이콘(192·512·maskable)·바로가기 2개, 오프라인 안내 쪽", dict(mf, offline=off) if isinstance(mf, dict) else mf)
        # 다듬기: 없는 주소 = 한국어 404(라이브 GitHub Pages 만), 첫 화면 뼈대 자리
        if "github.io" in URL:
            try:
                r404 = await pg.evaluate("u=>fetch(u,{cache:'no-store'}).then(async r=>({st:r.status,ko:(await r.text()).indexOf('찾을 수 없어요')>0}))", urllib.parse.urljoin(urllib.parse.urlsplit(URL)._replace(query="", fragment="").geturl(), "no-such-page-" + str(int(time.time()))))   # ?theme= 같은 쿼리가 붙은 URL 에서도 사이트 경로 + 없는 쪽
            except Exception as e:
                r404 = {"err": str(e)[:80]}
            rec(r404.get("st") == 404 and r404.get("ko"), "없는 주소 = 한국어 404 쪽('페이지를 찾을 수 없어요' + 오늘의 뉴스 버튼)", r404)
        # 화면 디자인 고르기(2026-10-05): 새 방문자 = 기본값(TN_THEME), ☰ 서랍 📰 클래식/✨ 모던 → 이 기기에 저장(tnk.theme.pick)·다시 열어도 유지
        try:
            base = urllib.parse.urlsplit(URL)._replace(query="", fragment="").geturl()
            c3 = await b.new_context(viewport={"width": 360, "height": 780}, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
            await c3.add_init_script(SEED); p3 = await c3.new_page()
            TJS = "()=>({m:document.documentElement.classList.contains('th-g')?'g':document.documentElement.classList.contains('th-modern')?'modern':'',d:window.TN_THEME,k:localStorage.getItem('tnk.theme.pick'),n:document.querySelectorAll('#themePick .thm').length,on:(document.querySelector('#themePick .thm[aria-checked=\"true\"]')||{}).dataset})"
            await p3.goto(base + "?_=%d" % time.time(), wait_until="load"); await p3.wait_for_timeout(900)
            t1 = await p3.evaluate(TJS)
            await p3.click("#menuBtn"); await p3.wait_for_timeout(400)
            async with p3.expect_navigation(): await p3.click('#themePick .thm[data-theme="classic"]')
            await p3.wait_for_timeout(700)
            await p3.goto(base + "?_=%d" % time.time(), wait_until="load"); await p3.wait_for_timeout(700)
            t2 = await p3.evaluate(TJS)
            await p3.click("#menuBtn"); await p3.wait_for_timeout(400)
            async with p3.expect_navigation(): await p3.click('#themePick .thm[data-theme="modern"]')
            await p3.wait_for_timeout(700)
            t3 = await p3.evaluate(TJS)
            await c3.close()
            th = {"새 방문": t1["m"] or "classic", "기본값": t1["d"], "칸": t1["n"], "클래식 고른 뒤": t2["m"] or "classic", "저장": t2["k"], "모던 고른 뒤": t3["m"] or "classic"}   # 2026-10-15 G 그래파이트(th-g) 추가 → 칸 3
            okth = t1["n"] == 3 and th["새 방문"] == t1["d"] and th["클래식 고른 뒤"] == "classic" and t2["k"] == "classic" and th["모던 고른 뒤"] == "modern" and t3["k"] == "modern"
        except Exception as e:
            okth, th = False, {"err": str(e)[:100]}
        rec(okth, "화면 디자인 고르기 — 새 방문자 = 기본값, ☰ 서랍 📰 클래식/✨ 모던 누르면 이 기기에 저장·다시 열어도 유지(창 없음)", th)
        # 화면 폭(iPhone SE 320 ~ iPad 가로 1024): 옆으로 넘치는 곳 없음
        try:
            ow = {}
            for wdt in (320, 360, 430, 768, 1024):
                c4 = await b.new_context(viewport={"width": wdt, "height": 800}, is_mobile=wdt < 1000, has_touch=wdt < 1000, locale="ko-KR")
                await c4.add_init_script(SEED); p4 = await c4.new_page()
                await p4.goto(URL + ("&" if "?" in URL else "?") + "_=%d" % time.time(), wait_until="load"); await p4.wait_for_timeout(900)
                ow[wdt] = await p4.evaluate("document.documentElement.scrollWidth - innerWidth"); await c4.close()
            okw = all(v <= 1 for v in ow.values())
        except Exception as e:
            okw, ow = False, {"err": str(e)[:100]}
        rec(okw, "화면 폭 320·360·430·768·1024 — 옆으로 넘침 없음", ow)
        # ฿ 는 헤더 숫자 칸(#ticker .tk-u)에만(2026-10-04 Max 승인) — 기사·브리핑·서랍·가게·임대·구인·승인함·내 주변·하트 화면 글은 '바트'
        BAHT_JS = r"""()=>{const out=[]; let hdr=0; const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while(w.nextNode()){const n=w.currentNode, t=n.textContent; if(t.indexOf('฿')<0) continue; const el=n.parentElement; if(!el.getClientRects().length) continue;
            if(el.closest('#ticker .tk-u')){hdr++; continue;} const c=el.closest('[data-id],[id]'); const i=t.indexOf('฿');
            out.push((c?(c.getAttribute('data-id')||'#'+c.id):'?')+' '+el.tagName.toLowerCase()+' “…'+t.slice(Math.max(0,i-14),i+6)+'…”');}
          document.querySelectorAll('[aria-label*="฿"],[title*="฿"],[alt*="฿"],[placeholder*="฿"]').forEach(e=>{ if(!e.closest('#ticker .tk-u')) out.push('속성 '+e.tagName.toLowerCase()); });
          return {hdr, out};}"""
        bh = {"hdr": 0, "out": []}
        for rt in ["?tab=all", "#places", "#rent", "#jobs", "#approve", "#hearts", "#nearby/food"]:
            try:
                await pg.goto("about:blank")
                await pg.goto(URL + ("?tab=all&_=%d" % time.time() if rt.startswith("?") else "?_=%d%s" % (time.time(), rt)), wait_until="networkidle"); await pg.wait_for_timeout(900)
                if rt.startswith("?"):
                    await pg.evaluate("document.querySelectorAll('#feed .card:not(.is-open) .card__head').forEach(b=>b.click())"); await pg.wait_for_timeout(400)
                    r = await pg.evaluate(BAHT_JS); bh["hdr"] = r["hdr"]; bh["out"] += ["메인 " + x for x in r["out"]]
                    await pg.click("#menuBtn"); await pg.wait_for_timeout(400); rt = "서랍"
                r = await pg.evaluate(BAHT_JS); bh["out"] += [rt + " " + x for x in r["out"]]
            except Exception as e:
                bh["out"].append("%s 열기 실패 %s" % (rt, str(e)[:60]))
        rec(not bh["out"] and bh["hdr"] > 0, "'฿' 는 헤더 숫자 칸에만(메인·서랍·가게·임대·구인·승인함·하트·내 주변 글은 '바트')", "헤더 칸 ฿ %d개, 밖 %d곳 %s" % (bh["hdr"], len(bh["out"]), bh["out"][:6]))
        # 첫 방문 시작 화면(새 방문자): 보류 중엔 예전 '어떤 분이세요?'(페르소나 5개), 켜지면 2단계
        c2 = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, timezone_id="Asia/Bangkok", locale="ko-KR")
        p2 = await c2.new_page()
        await p2.goto(URL, wait_until="networkidle"); await p2.wait_for_timeout(800)
        # 2026-10-04: 첫 화면에 창이 저절로 뜨면 안 됨 → 피드 맨 위 '👋 … 고르기' 한 줄을 눌러야 열림
        auto = await p2.is_visible("#sheet"); hello = await p2.locator("[data-ob-start]").count()
        if not auto and hello: await p2.locator("[data-ob-start]").first.click(); await p2.wait_for_timeout(500)
        ob = {"auto_sheet": auto, "hello": hello, "personas": await p2.locator("#sheet [data-persona]").count(), "regions": await p2.locator("#sheet [data-region]").count()}
        try:
            if ob["regions"]:
                await p2.click('[data-region="bangkok"]'); await p2.click("[data-ob-next]"); await p2.wait_for_timeout(300)
                await p2.click('[data-int="biz"]'); await p2.click("[data-ob-done]")
            else:
                await p2.click('[data-persona="pattaya"]'); await p2.wait_for_timeout(300); await p2.click("[data-save]")
            await p2.wait_for_timeout(600)
            ob["closed"] = not await p2.is_visible("#sheet")
            ob["cards"] = await p2.locator("#feed .card").count()
        except Exception as e:
            ob["err"] = str(e)[:120]
        ok_ob = ob.get("auto_sheet") is False and ob.get("hello", 0) > 0 and ob.get("closed") and ob.get("cards", 0) > 0 and (ob["personas"] == 5 if not ob2 else ob["regions"] == 5)
        rec(ok_ob, "첫 방문: 창 저절로 안 뜸 + '👋 고르기' 한 줄 → 시작 화면(%s)" % ("2단계" if ob2 else "예전 '어떤 분이세요?' — 2단계는 보류"), ob)
        await c2.close()
        # 2026-10-05: 헤더 '빠른 정보' 최악 경우(PM2.5 '매우 나쁨'·두 자리 월/일·6자리 금값 등 가짜 시험값을 화면에만 넣음) — 320·360·412 넘침 0
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import header_worst as HW
            hw = {}
            for wdt in (320, 360, 412):
                m = await HW.worst(b, URL, wdt)
                hw[wdt] = {"넘침px": m and m["over"], "칸안넘침": m and m["tiles"], "칸": m and m["n"], "매우나쁨": m and m["vbad"], "단계": m and m["fit"], "높이": m and m["h"]}
            okhw = all(v["넘침px"] == 0 and v["칸안넘침"] == 0 and v["칸"] == 4 and v["매우나쁨"] for v in hw.values())
            rec(okhw, "헤더 빠른 정보 최악 경우('매우 나쁨'·가장 긴 값) 320·360·412 — 넘침 0, 칸 4개(단계 = 넘칠 때만 켠 줄이기 단계 수, 5 = 2줄)", hw)
        except Exception as e:
            rec(False, "헤더 빠른 정보 최악 경우 점검 실행 실패", str(e)[:160])
        # 2026-10-05(Max 04:30 ③): 광고 자리별 클릭 수(익명 adclicks) — 준비만, 꺼짐이어야 함. 코드 스위치 false + 광고 링크 눌러도 대기열·adclicks 요청 0
        try:
            c3 = await b.new_context(viewport={"width": 360, "height": 780}); await guard(c3); p3 = await c3.new_page()
            acreq = []
            p3.on("request", lambda r: acreq.append(r.url) if ("adclicks" in r.url or "adclicks" in (r.post_data or "")) else None)
            await p3.goto(URL, wait_until="load"); await p3.wait_for_timeout(2000)
            src = await p3.evaluate("async()=>{const s=[...document.scripts].map(x=>x.src).find(u=>/assets\\/social\\.js/.test(u)); return s ? await (await fetch(s)).text() : ''}")
            off = bool(re.search(r"var AD_CLICK_ON = false;", src)) and not re.search(r"var AD_CLICK_ON = true", src)
            nclk = await p3.evaluate("""()=>{addEventListener('click',e=>e.preventDefault(),true); const a=[...document.querySelectorAll('[data-ad-slot]:not([hidden]) a[href], .ad-slot--feed a[href]')].filter(x=>!x.hasAttribute('data-placeholder')).slice(0,3); a.forEach(x=>x.click()); return a.length}""")
            await p3.wait_for_timeout(3800)
            q = await p3.evaluate("localStorage.getItem('tnk.adq')")
            api = await p3.evaluate("!!(window.TNSocial && TNSocial.adClickOn && TNSocial.adClickOn() === false)")
            rec(off and api and nclk > 0 and not q and not acreq, "광고 자리별 클릭 수(익명) = 꺼짐(AD_CLICK_ON=false, 준비만) — 광고 링크 눌러도 이 기기 대기열·adclicks 요청 0",
                {"코드스위치false": off, "adClickOn()=false": api, "누른 광고 링크": nclk, "대기열": q, "adclicks 요청": len(acreq)})
            await c3.close()
        except Exception as e:
            rec(False, "광고 클릭 수 꺼짐 점검 실행 실패", str(e)[:160])
        # 2026-10-05(Max 05:23 ③): 받은 양 정상 범위. 클래식 197KB(04:23)→241KB(05:19)는 코드 변화가 아니라 글꼴 조각(Pretendard unicode-range,
        #  화면 글자에 따라 받는 조각)이 perf.py 창(load 뒤 2.5초) 끝에 걸렸다 안 걸렸다 한 것(글꼴 제외는 5회 모두 199KB). → 비교는 '글꼴 제외'로:
        #  글꼴 제외 150~240KB = 통과(10-05 05:3x 라이브: 클래식 199·모던 215KB, +약 10~20% 여유) / 글꼴 조각은 글자 따라 달라서 실패로 안 봄(1,000KB 넘으면 참고)
        try:
            c4 = await b.new_context(viewport={"width": 390, "height": 844}); await guard(c4); p4 = await c4.new_page()
            await p4.goto(URL + ("&" if "?" in URL else "?") + "_=" + str(int(time.time())), wait_until="load"); await p4.wait_for_timeout(4000)
            bb = await p4.evaluate("""()=>{const n=performance.getEntriesByType('navigation')[0], rs=performance.getEntriesByType('resource'), isF=r=>/pretendard/i.test(r.name)&&/[.]woff2?/.test(r.name);
                return {nf: rs.filter(r=>!isF(r)).reduce((a,r)=>a+(r.transferSize||0), n.transferSize||0), f: rs.filter(isF).reduce((a,r)=>a+(r.transferSize||0),0), fn: rs.filter(r=>isF(r)&&r.transferSize>0).length}}""")
            nfk, fk = round(bb["nf"] / 1024), round(bb["f"] / 1024)
            okb = 150 <= nfk <= 240
            if "github.io" not in URL: okb = None   # 로컬 서버(python http.server)는 압축 안 함 → 범위는 라이브(GitHub Pages, gzip) 기준이라 참고만
            rec(okb if (okb is not True or fk <= 1000) else None, "받은 양 정상 범위 — 글꼴 제외 150~240KB(글꼴 조각은 화면 글자 따라 달라서 따로 표시, 1,000KB 넘으면 참고)",
                {"글꼴 제외KB": nfk, "글꼴 조각": "%d개 %dKB" % (bb["fn"], fk)})
            await c4.close()
        except Exception as e:
            rec(False, "받은 양 점검 실행 실패", str(e)[:160])
        # 2026-10-05(Max 06:28 ①): 승인함(#approve) 대기 = data/pending.json items 뿐(drafts/discussion 은 안 읽음). 게시된 질문이 대기에 끼면 실패
        #  (점검 본체 = tools/dev/pending_check.py, 일부러 깨뜨린 시험: pending_check.py --break-test → 실패)
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import pending_check
            _base = URL.split("?")[0]; _pub = pending_check.published(_base); _ok, _info = pending_check.check(pending_check.get(_base, "data/pending.json"), _pub)
            rec(_ok if _pub else None, "게시된 질문은 승인함 대기에 없음(승인함 = data/pending.json, 게시된 질문·운영자 댓글이 대기 항목에 있으면 실패)", _info)
        except Exception as e:
            rec(False, "게시된 질문 승인함 점검 실행 실패", str(e)[:160])
        # 2026-10-05(Max 07:32 A②): 최신 판 'generated' = 실제 만든 시각인지(미래 금지 · 그 값을 담은 커밋과 15분 안 · index.json 과 같음). 본체 tools/gen_time_check.py
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import gen_time_check
            _b = URL.split("?")[0].rstrip("/") + "/"
            _ix = json.loads(urllib.request.urlopen(_b + "data/index.json?_=" + str(int(time.time())), timeout=30).read().decode("utf-8"))
            _le = _ix["latest"]; _lg = json.loads(urllib.request.urlopen(_b + "data/%s.json?_=%d" % (_le, time.time()), timeout=30).read().decode("utf-8")).get("generated", "")
            _gok, _gmsg = gen_time_check.check(_le, generated=_lg, root=pathlib.Path(__file__).resolve().parents[2], index_generated=next((e.get("generated") for e in _ix["editions"] if e["id"] == _le), None))
            rec(_gok, "최신 판 업데이트 시각(generated) = 실제 만든 시각(미래 아님 · 커밋과 15분 안 · index.json 같음)", _gmsg)
        except Exception as e:
            rec(False, "판 generated 시각 점검 실행 실패", str(e)[:160])
        # 2026-10-05: 정본 체크아웃(/workspace/thai-news-portal) = 받기만 하는 곳 — rebase/merge 중·main 아님·origin 보다 앞섬·바뀐/추적 안 된 파일이면 실패(tools/canon_guard.sh, 아무것도 안 고침)
        try:
            # 시험용 덮어쓰기(CANON_DIR·TNK_LOGDIR·CANON_NO_FETCH)는 TNK_TEST=1 일 때만 넘김(10-05 08:51: 남은 CANON_DIR 로 가짜 정본을 검사했음)
            _env = dict(os.environ)
            _left = [k for k in ("CANON_DIR", "TNK_LOGDIR", "CANON_NO_FETCH") if _env.get(k)]
            if _env.get("TNK_TEST") != "1":
                for k in _left: _env.pop(k, None)
            _cg = subprocess.run(["bash", str(pathlib.Path(__file__).resolve().parents[1] / "canon_guard.sh"), "regress"], capture_output=True, text=True, timeout=90, env=_env)
            _cgo = (_cg.stdout or _cg.stderr).strip().splitlines()[-1:] or [""]
            _note = (" · 남은 시험 변수 %s 무시(TNK_TEST 없음)" % "/".join(_left)) if (_left and _env.get("TNK_TEST") != "1") else (" · TNK_TEST=1 시험 모드" if _env.get("TNK_TEST") == "1" else "")
            rec(None if "SKIP" in _cgo[0] else _cg.returncode == 0, "정본 체크아웃 깨끗함(rebase/merge 중 아님 · main · origin 보다 앞서지 않음 · 바뀐/추적 안 된 파일 없음)", _cgo[0][:200] + _note)
        except Exception as e:
            rec(False, "정본 체크아웃 검사 실행 실패", str(e)[:160])
        rec(FS["blocked"] == 0 or None, "자동 점검이 실서버(Firestore)에 반응·신고를 안 씀(이 기기 스위치 끔 + 쓰기 요청 차단)", "막은 쓰기 요청 %d개" % FS["blocked"])
        await b.close()
    if OUT: pathlib.Path(OUT).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    nf = sum(1 for x in res if x["ok"] is False)
    print("== 결과: 통과 %d · 실패 %d · 참고 %d" % (sum(1 for x in res if x["ok"] is True), nf, sum(1 for x in res if x["ok"] is None)))
    return 1 if nf else 0

sys.exit(asyncio.run(main()))
