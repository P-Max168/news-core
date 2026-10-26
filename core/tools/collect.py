# -*- coding: utf-8 -*-
"""수집 1단계 도우미: tools/sources.json 의 모든 소스를 훑어 '최근 N시간 후보 기사' 목록을 만든다.

  python3 tools/collect.py                 # 최근 14시간, 결과 drafts/candidates/<시각>.{json,md} + latest.{json,md}
  python3 tools/collect.py --hours 20      # 기간 바꾸기
  python3 tools/collect.py --out /tmp/c    # 저장 폴더 바꾸기(기본 drafts/candidates — .gitignore 대상)
  python3 tools/collect.py --verify        # 소스마다 접속·항목 수·최신 항목 나이만 점검(후보 저장 안 함)

- type: rss(RSS/Atom) · sitemap(Google News 뉴스 사이트맵: news:title + publication_date) ·
  gnews(Google News RSS — 날짜는 참고용, 원문 게재 시각 확인 필수) · html(손으로 확인할 곳: 접속만 점검)
- disabled 가 적힌 소스(box 에서 안 열림)는 건너뛴다 — 이유에 적힌 대체 경로로 손으로 확인.
- 실패한 소스(시간 초과·403 등)는 건너뛰고 끝에 목록으로 보여 준다.
- 주제는 제목 키워드로 붙이고(여러 개 가능), 소스가 한 주제 전용(예: 연예 섹션)이면 그 주제도 붙인다.
  Google News 검색(match 있음)은 검색어가 제목에 있을 때만 그 검색의 주제를 붙인다.
  키워드에 안 걸린 종합 피드 기사는 'other'(미분류)에 모은다.
- 같은 기사(제목이 거의 같음)는 하나로 합치고, 같이 보도한 매체는 also[] 에 남긴다
  → '가장 자세한 원 보도'를 고를 때 비교용. Google News 항목보다 매체 자체 피드 항목을 대표로 남긴다.
- Pantip·태사랑·SNS·동영상 플랫폼 항목은 버린다(사실 출처 아님 — README). sources.json 의 exclude_outlets
  (Google News 에 섞이는 재게시·기계번역 매체)도 버리고, 소스에 require(정규식)가 있으면 제목이 맞는 것만 남긴다.
- 매체 이름은 도메인으로 통일해 센다(Thairath 섹션 피드와 Google News 의 thairath.co.th = 한 매체).
- 이 목록은 '후보'일 뿐: 주제별 최소 건수를 채우려고 약한 기사를 넣지 않는다(README 고르는 규칙).
"""
import argparse, gzip, html, json, pathlib, re, sys, time, difflib, calendar
import concurrent.futures as cf
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
try:
    import feedparser
except ImportError:  # pip install feedparser
    feedparser = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tools" / "sources.json"
BKK = timezone(timedelta(hours=7))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "th,en;q=0.8"}
TOPICS = ["east", "bangkok", "north", "south", "poleco", "society", "visa", "life", "travel", "ent", "weather"]
# 2026-10-03: pattaya·sriracha → east(동부(촌부리·라용)) 통합, north·south 추가. sources.json 의 옛 id 는 ALIAS 로 읽음
ALIAS = {"pattaya": "east", "sriracha": "east"}
TOPIC_KO = dict(east="동부(촌부리·라용)", bangkok="방콕", north="북부", south="남부", poleco="정치·경제", society="사회·사건사고",
                visa="외국인·비자", life="생활·물가·부동산", travel="여행·맛집", ent="연예·스포츠·SNS", weather="날씨·교통",
                other="미분류")
# 제목 키워드 → 주제 (태국어·영어). 너무 넓은 말(ชน, ร้อน, หนัง, อากาศ 단독 등)은 일부러 뺐다.
KW = {
    # 동부 = 촌부리 도 전체(파타야·좀티엔·싸따힙·시라차·램차방·방센·촌부리 시내 …) + 라용 도
    "east": r"파타야|좀티엔|시라차|촌부리|라용|พัทยา|บางละมุง|จอมเทียน|นาเกลือ|สัตหีบ|หนองปรือ|ห้วยใหญ่|อู่ตะเภา|เกาะล้าน|"
            r"ศรีราชา|แหลมฉบัง|อมตะ|ชลบุรี|บางแสน|บ้านบึง|พนัสนิคม|บ่อวิน|ระยอง|มาบตาพุด|เกาะเสม็ด|บ้านฉาง|แกลง|"
            r"Pattaya|Jomtien|Bang ?Lamung|Sattahip|Naklua|Walking Street|U-?Tapao|Koh Larn|Sriracha|Si Racha|Laem Chabang|Chon ?Buri|"
            r"Amata|Bang ?Saen|Rayong|Map Ta Phut|Koh Samet|EEC|อีอีซี",
    "bangkok": r"방콕|수쿰빗|กทม|กรุงเทพ(?!ธุรกิจ)|ชัชชาติ|สุขุมวิท|สีลม|สาทร|อโศก|ทองหล่อ|เอกมัย|รัชดา|ห้วยขวาง|ดินแดง|ข้าวสาร|จตุจักร|"
               r"สุวรรณภูมิ|ดอนเมือง|ลาดกระบัง|ลาดพร้าว|บางนา|บางกะปิ|หนองจอก|ประตูน้ำ|ราชประสงค์|เยาวราช|สำเพ็ง|บีทีเอส|รฟม\.|สายสีเขียว|"
               r"สายสีม่วง|สายสีน้ำเงิน|สายสีชมพู|สายสีเหลือง|สายสีส้ม|Bangkok|BMA|Chadchart|Sukhumvit|Silom|Sathorn|Asok|Thonglor|"
               r"Khao ?San|Chatuchak|Ratchada|Suvarnabhumi|Don Mueang|Lat Krabang|BTS (?:Skytrain|line|station)|Skytrain|MRT",
    # 북부: 치앙마이·치앙라이·람빵·람푼·매홍손·난·프래·파야오·핏사눌록·수코타이·딱(매솟) 등. น่าน/แพร่/ตาก 단독은 다른 낱말에 섞여서 จ./จังหวัด 붙은 것만
    "north": r"치앙마이|치앙라이|람빵|매홍손|핏사눌록|수코타이|매솟|เชียงใหม่|เชียงราย|ลำปาง|ลำพูน|แม่ฮ่องสอน|พะเยา|พิษณุโลก|สุโขทัย|"
             r"อุตรดิตถ์|แม่สอด|แม่สาย|เชียงแสน|เชียงของ|ดอยสุเทพ|ดอยอินทนนท์|(?:จ\.|จังหวัด|เมือง)(?:น่าน|แพร่|ตาก)|(?<![\u0E00-\u0E7F])ปาย(?=\s|$)|"
             r"Chiang ?Mai|Chiang ?Rai|Lampang|Lamphun|Mae Hong Son|Mae Sot|Mae Sai|Phitsanulok|Sukhothai|Phayao|Phrae|Uttaradit|"
             r"\bNan (?:province|city)|\bTak province|\bPai\b",
    # 남부: 푸껫·끄라비·팡아·수랏타니(사무이·팡안·따오)·송클라(핫야이)·나콘시탐마랏·뜨랑·사뚠·춤폰·라농 + 빳따니·얄라·나라티왓(남부 국경)
    "south": r"푸껫|푸켓|끄라비|사무이|팡안|핫야이|송클라|ภูเก็ต|ป่าตอง|กระบี่|อ่าวนาง|เกาะพีพี|พังงา|เขาหลัก|สุราษฎร์|สมุย|พะงัน|เกาะเต่า|"
             r"สงขลา|หาดใหญ่|นครศรีธรรมราช|ตรัง(?!กานู)|สตูล|ชุมพร|ระนอง|ปัตตานี|ยะลา|นราธิวาส|ชายแดนใต้|สุไหงโก-?ลก|เบตง|"
             r"Phuket|Patong|Krabi|Ao Nang|Phi Phi|Phang ?Nga|Khao Lak|Surat Thani|Samui|Phangan|Koh Tao|Songkhla|Hat ?Yai|"
             r"Nakhon Si Thammarat|\bTrang\b|Satun|Chumphon|Ranong|Pattani|Yala|Narathiwat|deep south|Betong",
    "poleco": r"총리|정부|경제|환율|증시|นายกฯ|นายกรัฐมนตรี|รัฐบาล|ครม\.|สภา|ส\.ส\.|ส\.ว\.|พรรค|รัฐมนตรี|รมว|รมช|เลือกตั้ง|กกต|ศาลรัฐธรรมนูญ|ป\.ป\.ช|เศรษฐกิจ|GDP|จีดีพี|ส่งออก|หุ้น|ตลาดหลักทรัพย์|ธปท|แบงก์ชาติ|ค่าเงินบาท|ลงทุน|IMF|ภาษี|งบประมาณ|minister|government|parliament|election|economy|economic|baht|export|stocks?|SET index|Bank of Thailand|investment|tariff|budget|cabinet",
    "society": r"사고|사망|체포|경찰|살해|사기|อุบัติเหตุ|รถชน|ชนกัน|ฆ่า|ยิง|จับกุม|รวบ|ตำรวจ|คดี|ไฟไหม้|เพลิงไหม้|จมน้ำ|ยาเสพติด|ยาบ้า|โกง|แก๊ง|คอลเซ็นเตอร์|ศพ|เสียชีวิต|ดับ|crash|killed|arrest|police|murder|fire|scam|drug|dead|death|shooting|stabb",
    "visa": r"วีซ่า|ชาวต่างชาติ|นักท่องเที่ยวต่างชาติ|ต่างด้าว|ตม\.|สตม|ตรวจคนเข้าเมือง|ชาวเกาหลี|คนเกาหลี|นักท่องเที่ยวเกาหลี|สถานทูตเกาหลี|อยู่เกินกำหนด|ใบอนุญาตทำงาน|นอมินี|visa|immigration|expats?|foreigners?|overstay|DTV|TM30|LTR|work permit|South Korean (?:man|woman|men|women|tourists?|nationals?)|Korean (?:man|woman|men|women|tourists?|nationals?)|한국인|교민|대사관|영사|비자|입국|관광객",
    "life": r"ราคาน้ำมัน|น้ำมัน|ดีเซล|แก๊สโซฮอล์|ค่าไฟ|ค่าน้ำ|ราคาทอง|ทองคำ|คอนโด|อสังหา|บ้านมือสอง|ค่าครองชีพ|ราคาสินค้า|ราคาไข่|ราคาหมู|ค่าแรง|ประกันสังคม|เงินเฟ้อ|ของแพง|โรงพยาบาล|สาธารณสุข|fuel|petrol|diesel|electricity|condo|property|housing|cost of living|minimum wage|prices?\b|inflation|hospital",
    "travel": r"여행|항공|공항|호텔|맛집|ท่องเที่ยว|นักท่องเที่ยว|ร้านอาหาร|คาเฟ่|โรงแรม|เทศกาล|สายการบิน|เที่ยวบิน|สนามบิน|ชายหาด|tourism|tourists?|travel|hotels?|restaurants?|festival|airlines?|flights?|airport|beach",
    "ent": r"아이돌|배우|가수|드라마|축구|복싱|아시안게임|ดารา|นักแสดง|ซีรีส์|ละคร|ภาพยนตร์|เพลง|นักร้อง|คอนเสิร์ต|ศิลปิน|ไอดอล|ไวรัล|โซเชียล|ชาวเน็ต|ฟุตบอล|ทีมชาติ|มวย|เอเชียนเกมส์|วอลเลย์|แบดมินตัน|กีฬา|นักเตะ|พรีเมียร์ลีก|ไทยลีก|เทนนิส|กอล์ฟ|K-?pop|concert|actor|actress|singer|series|film|movie|football|soccer|Asian Games|Muay Thai|boxing|viral|volleyball|badminton",
    "weather": r"폭우|홍수|태풍|날씨|미세먼지|กรมอุตุ|อุตุนิยม|ฝนตก|ฝนหนัก|ฝนฟ้าคะนอง|พายุ|น้ำท่วม|อุทกภัย|สภาพอากาศ|อากาศแปรปรวน|อากาศหนาว|ฝุ่น|PM ?2\.5|คลื่นลม|มรสุม|ทางด่วน|รถไฟฟ้า|BTS|MRT|รถติด|จราจร|ปิดถนน|รถไฟ|weather|storm|flood|rain|traffic|expressway|skytrain|haze|monsoon",
}
KW_RE = {t: re.compile(p, re.I) for t, p in KW.items()}
BAD_SRC = re.compile(r"pantip|thailove|facebook|tiktok|youtube|instagram|twitter|x\.com|blockdit|lemon8|threads", re.I)


def get(url, timeout, verify=True):
    if not verify:
        import urllib3
        urllib3.disable_warnings()
    r = requests.get(url, headers=UA, timeout=timeout, verify=verify)
    b = r.content
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    return r.status_code, b


def parse_dt(s):
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def items_rss(src, body):
    out = []
    for e in feedparser.parse(body).entries:
        st = e.get("published_parsed") or e.get("updated_parsed")
        dt = datetime.fromtimestamp(calendar.timegm(st), timezone.utc) if st else None
        title = html.unescape(e.get("title", "")).strip()
        outlet = src["name"]
        if src["type"] == "gnews":   # 'title - 매체' 꼴 → 매체 이름 분리
            so = e.get("source") or {}
            outlet = so.get("title") or outlet
            dom = domain(so.get("href", ""))
            outlet = CANON.get(dom, outlet)
            title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)
        if src["type"] != "gnews":
            outlet = CANON.get(domain(e.get("link", "")), outlet)
        out.append(dict(title=title, url=e.get("link", ""), published=dt, outlet=outlet))
    return out


def items_sitemap(src, body):
    s = body.decode("utf-8", "replace")
    out = []
    for x in re.findall(r"<url>(.*?)</url>", s, re.S):
        t = re.search(r"<news:title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</news:title>", x, re.S)
        if not t:
            continue
        d = re.search(r"<news:publication_date>(.*?)</news:publication_date>", x)
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", x, re.S)
        out.append(dict(title=html.unescape(html.unescape(t.group(1))).strip(), url=loc.group(1) if loc else "",
                        published=parse_dt(d.group(1)) if d else None,
                        outlet=CANON.get(domain(loc.group(1) if loc else ""), src["name"])))
    return out


def fetch(src, timeout):
    t0 = time.time()
    try:
        code, body = get(src["url"], timeout, verify=not src.get("insecure_tls"))
        if code != 200:
            return src, None, "HTTP %d" % code, time.time() - t0
        if src["type"] == "html":
            return src, [], None, time.time() - t0
        its = items_sitemap(src, body) if src["type"] == "sitemap" else items_rss(src, body)
        if not its:
            return src, None, "항목 0개", time.time() - t0
        return src, its, None, time.time() - t0
    except Exception as e:  # 시간 초과·SSL·파싱 오류 → 건너뜀
        return src, None, type(e).__name__, time.time() - t0


def domain(u):
    h = urlparse(u if "//" in u else "//" + u).netloc.lower().split(":")[0]
    for p in ("www.", "rssfeeds.", "feeds.", "m."):
        if h.startswith(p):
            h = h[len(p):]
    return h


CANON = {}   # 도메인 → 매체 이름(소스별 건수를 매체 단위로 세기 위해)


def build_canon(srcs):
    for s in srcs:
        if s["type"] in ("rss", "sitemap"):
            d = domain(s["url"])
            n = re.sub(r"\s*\([^)]*[가-힣][^)]*\)|\s+[가-힣][^\s]*$", "", s["name"]).strip()
            n = re.sub(r"\s+[가-힣].*$", "", n).strip() or s["name"]
            if d not in CANON or len(n) < len(CANON[d]):
                CANON[d] = n
    CANON.setdefault("bbc.co.uk", "BBC Thai")
    CANON.setdefault("bbc.com", "BBC Thai")


def norm(t):
    return re.sub(r"[\W_]+", "", t.lower())


def topics_for(src, title):
    ts = [t for t in TOPICS if KW_RE[t].search(title)]
    if src.get("match") and not re.search(src["match"], title, re.I):
        return ts or ["other"]      # Google News 검색어가 본문에만 걸린 기사 → 제목 키워드로만 분류
    st = []
    for t in src["topics"]:
        t = ALIAS.get(t, t)
        if t not in st:
            st.append(t)
    if len(st) == 1 and st[0] not in ts:
        ts.append(st[0])
        ts.sort(key=TOPICS.index)
    return ts or ["other"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=14)
    ap.add_argument("--out", default=str(ROOT / "drafts" / "candidates"))
    ap.add_argument("--timeout", type=float, default=20)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--verify", action="store_true")
    # 언어판(2026-10-18 Grok): 소스 파일을 바꿔 쓸 수 있게(zh 13:00 빌드 = 한국판 정본 sources.json + sources.zh.json 보강을 합친 임시 파일). 기본은 그대로 tools/sources.json
    ap.add_argument("--sources", default=str(SOURCES))
    a = ap.parse_args()
    if feedparser is None:
        sys.exit("feedparser 필요: pip install feedparser")
    cfg = json.loads(pathlib.Path(a.sources).read_text(encoding="utf-8"))
    build_canon(cfg["sources"])
    excl = [re.compile(x, re.I) for x in cfg.get("exclude_outlets", [])]
    disabled = [s for s in cfg["sources"] if s.get("disabled")]
    srcs = [s for s in cfg["sources"] if not s.get("disabled")]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=a.hours)
    results = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda s: fetch(s, a.timeout), srcs):
            results.append(r)

    if a.verify:
        bad = 0
        for src, its, err, dt in results:
            if err:
                bad += 1
                print("FAIL\t%s\t%s\t%s" % (err, src["name"], src["url"]))
                continue
            ds = [i["published"] for i in its if i["published"]]
            age = "%.1fh" % ((now - max(ds)).total_seconds() / 3600) if ds else "-"
            print("OK\t%d\t%s\t%s\t%s" % (len(its), age, src["type"], src["name"]))
        for s in disabled:
            print("SKIP\t%s\t%s" % (s["name"], s["disabled"]))
        print("\n%d/%d OK (건너뜀 %d)" % (len(results) - bad, len(results), len(disabled)))
        return

    fails, raw, undated, skipped = [], [], 0, 0
    for src, its, err, _ in results:
        if err:
            fails.append((src["name"], err))
            continue
        req = re.compile(src["require"], re.I) if src.get("require") else None
        for it in its:
            if not it["title"] or BAD_SRC.search(it["outlet"]) or BAD_SRC.search(urlparse(it["url"]).netloc):
                continue
            if any(x.fullmatch(it["outlet"]) for x in excl) or (req and not req.search(it["title"])):
                skipped += 1
                continue
            if it["published"] is None:
                undated += 1
                continue
            if it["published"] < cutoff or it["published"] > now + timedelta(hours=1):
                continue
            it.update(src=src["name"], type=src["type"], lang=src["language"], topics=topics_for(src, it["title"]))
            raw.append(it)

    # 중복 합치기: 매체 자체 피드(rss/sitemap)를 Google News 보다 앞에, 그다음 이른 게재 순(원 보도 우선)
    raw.sort(key=lambda i: (i["type"] == "gnews", i["published"]))
    seen_url, keep = {}, []
    for it in raw:
        u = re.sub(r"[?#].*$", "", it["url"]).rstrip("/")
        n = norm(it["title"])
        if u in seen_url:
            seen_url[u]["topics"] = sorted(set(seen_url[u]["topics"]) | set(it["topics"]), key=(TOPICS + ["other"]).index)
            continue
        dup = None
        for k in keep:
            kn = k["_n"]
            if n == kn or (min(len(n), len(kn)) > 12 and (n[:30] == kn[:30] or (
                    difflib.SequenceMatcher(None, n, kn).quick_ratio() > 0.85 and
                    difflib.SequenceMatcher(None, n, kn).ratio() > 0.85))):
                dup = k
                break
        if dup:
            if it["outlet"] != dup["outlet"] and it["outlet"] not in [x["outlet"] for x in dup["also"]]:
                dup["also"].append(dict(outlet=it["outlet"], url=it["url"], title=it["title"]))
            ts = set(dup["topics"]) | set(it["topics"])
            if len(ts) > 1:
                ts.discard("other")
            dup["topics"] = sorted(ts, key=(TOPICS + ["other"]).index)
            seen_url[u] = dup
            continue
        it["_n"] = n
        it["also"] = []
        keep.append(it)
        seen_url[u] = it

    by_topic = defaultdict(list)
    for it in keep:
        for t in it["topics"]:
            by_topic[t].append(it)
    for t in by_topic:
        by_topic[t].sort(key=lambda i: (-len(i["also"]), -i["published"].timestamp()))

    stamp = now.astimezone(BKK)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    def ser(i):
        return dict(title=i["title"], outlet=i["outlet"], url=i["url"], via=i["src"], type=i["type"], lang=i["lang"],
                    published=i["published"].astimezone(BKK).isoformat(timespec="minutes"),
                    date_note="Google News 날짜 — 원문 게재 시각 확인" if i["type"] == "gnews" else "",
                    topics=i["topics"], also=i["also"])
    data = dict(generated=stamp.isoformat(timespec="seconds"), hours=a.hours,
                sources_total=len(srcs), sources_ok=len(srcs) - len(fails), failed=[dict(name=n, error=e) for n, e in fails],
                candidates=len(keep),
                topics={t: dict(count=len(by_topic.get(t, [])),
                                outlets=Counter(i["outlet"] for i in by_topic.get(t, [])).most_common(),
                                items=[ser(i) for i in by_topic.get(t, [])]) for t in TOPICS + ["other"]})
    base = stamp.strftime("%Y%m%d-%H%M")
    js = json.dumps(data, ensure_ascii=False, indent=1)
    lines = ["# 후보 기사 %s (최근 %g시간, 소스 %d/%d 성공, 후보 %d건)" % (stamp.strftime("%Y-%m-%d %H:%M BKK"), a.hours,
             data["sources_ok"], len(srcs), len(keep)), "",
             "※ 후보일 뿐 — 뉴스 가치·한국인 관련성으로 고르고, 숫자를 채우려고 약한 기사를 넣지 않는다. Google News(gnews) 날짜는 원문에서 확인.", ""]
    for t in TOPICS + ["other"]:
        L = by_topic.get(t, [])
        lines.append("## %s `%s` — %d건 · 매체 %d곳" % (TOPIC_KO[t], t, len(L), len({i["outlet"] for i in L})))
        lines.append("매체별: " + ", ".join("%s %d" % kv for kv in Counter(i["outlet"] for i in L).most_common()))
        for i in L[:60]:
            also = (" (+%d: %s)" % (len(i["also"]), ", ".join(x["outlet"] for x in i["also"][:4]))) if i["also"] else ""
            lines.append("- %s | %s | %s%s  \n  %s" % (i["published"].astimezone(BKK).strftime("%m-%d %H:%M"), i["outlet"],
                                                      i["title"], also, i["url"]))
        if len(L) > 60:
            lines.append("- … %d건 더(json 참고)" % (len(L) - 60))
        lines.append("")
    if fails:
        lines.append("## 실패한 소스(건너뜀)")
        lines += ["- %s: %s" % f for f in fails]
    md = "\n".join(lines) + "\n"
    for name in (base, "latest"):
        (out / (name + ".json")).write_text(js, encoding="utf-8")
        (out / (name + ".md")).write_text(md, encoding="utf-8")

    print("후보 %d건 (최근 %gh, 소스 %d/%d 성공, 날짜 없는 항목 %d개·제외 매체/조건 %d개 뺌) → %s/%s.{json,md}" % (
        len(keep), a.hours, data["sources_ok"], len(srcs), undated, skipped, out, base))
    for t in TOPICS + ["other"]:
        L = by_topic.get(t, [])
        oc = Counter(i["outlet"] for i in L)
        print("  %-9s %-14s %4d건  매체 %3d곳  상위: %s" % (t, TOPIC_KO[t], len(L), len(oc),
              ", ".join("%s %d" % kv for kv in oc.most_common(4))))
    if fails:
        print("실패(건너뜀): " + "; ".join("%s(%s)" % f for f in fails))


if __name__ == "__main__":
    main()
