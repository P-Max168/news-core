# -*- coding: utf-8 -*-
"""헤더 시세 칩용 데이터 — data/ticker.json + data/ticker.js(window.TN_TICKER, file:// 용).

  python3 tools/fetch_ticker.py        # GitHub Actions(.github/workflows/korea.yml)가 2시간마다 실행

- fx  : 바트→원 환율(THB_KRW, + 참고용 USD_THB·USD_KRW). 1순위 open.er-api.com(ExchangeRate-API, 하루 1번 갱신),
        실패하면 api.frankfurter.app(ECB 기준환율, 평일 1번).
- gold: 태국 금시세 — 금 거래상 협회(สมาคมค้าทองคำ, goldtraders.or.th) 공식 발표 '금괴 96.5% 1바트(15.244 g)' 판매가(bar_sell)·매입가(bar_buy).
        협회 사이트가 쓰는 공개 JSON(/api/GoldPrices/Latest). 주말·공휴일엔 발표가 없어 마지막 발표값이 그대로다.
- fuel: 방콕 소매 휘발유 가격 — 방짝(Bangchak) 공식 유가 JSON(oil-price.bangchak.co.th/ApiOilPrice2/th)의 '가소홀 95'(แก๊สโซฮอล์ 95) 오늘 가격(바트/L).
        방콕(กทม.) 소매가, 방콕 지방세 미포함(방짝 표기). 찾지 못하면 항목 없음(지어내지 않음).
- usdt: 테더(USDT) 1개 = 몇 바트(USDT/THB). 운영자 요청 = '구글에 나오는 값과 같게'.
        1순위 구글 파이낸스 시세 페이지(google.com/finance/quote/USDT-THB — 키 없음, 페이지 안 데이터의 현재가·시각),
        막히면(동의 화면·429·구조 변경) CoinGecko simple price(tether→thb, 여러 거래소 평균 — 구글 값도 비슷한 집계 시세),
        그것도 실패하면 Bitkub(태국 거래소) 공개 ticker 의 USDT_THB 마지막 체결가. source 에 실제로 쓴 곳을 적는다(구글일 때만 '구글 기준').
- wx/aq: 날씨·미세먼지 PM2.5(Open-Meteo, 파타야·시라차·방콕) — 화면은 브라우저에서 Open-Meteo 를 직접 부르고(30/60분 캐시),
        그게 실패할 때(요청 한도 429·오프라인 등)만 이 값(3시간 안의 것)을 쓴다.
- 한 항목이 실패하면 그 항목은 이전 값을 그대로 둔다(fetched_at 도 그대로 → 화면이 24시간 넘은 값은 숨김).
  값을 지어내지 않는다. 둘 다 실패하면 exit 1(워크플로에 빨간색으로 표시).
"""
import json, pathlib, sys, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
BKK = timezone(timedelta(hours=7))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"}


def now():
    return datetime.now(BKK).isoformat(timespec="seconds")


def get_json(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8"))


def fx_er_api():
    d = get_json("https://open.er-api.com/v6/latest/THB")   # 판 환율(README '사용 환율')과 같은 THB 기준
    if d.get("result") != "success":
        raise ValueError("open.er-api result=%r" % d.get("result"))
    r = d["rates"]
    krw, usd = float(r["KRW"]), float(r["USD"])
    if not (5 < krw < 200 and 0 < usd < 1):
        raise ValueError("환율 값 이상: KRW=%r USD=%r" % (krw, usd))
    t = datetime.fromtimestamp(int(d["time_last_update_unix"]), BKK).isoformat(timespec="seconds")
    out = dict(THB_KRW=round(krw, 4), USD_THB=round(1 / usd, 4), USD_KRW=round(krw / usd, 2), rate_time=t,
               source="ExchangeRate-API (open.er-api.com)", url="https://www.exchangerate-api.com/")
    cny = r.get("CNY")   # 중국어판 헤더 칩용(2026-10-18 R-zh-3) — 값이 이상하면 넣지 않음(한국판 값에는 영향 없음)
    if isinstance(cny, (int, float)) and 0.05 < cny < 1:
        out["THB_CNY"] = round(float(cny), 5)
    return out


def fx_live(pair):
    """판 환율 즉시 조회(2026-10-30): 'THB_KRW' → open.er-api latest/THB 의 KRW. {rate, rate_time, source, url}. 실패하면 예외.
    시세 파일(data/ticker.json)이 오늘 갱신(07:02 BKK) 전 값일 때 gemini_edition.fx_now 가 부른다."""
    base, quote = pair.split("_")
    d = get_json("https://open.er-api.com/v6/latest/%s" % base)
    if d.get("result") != "success":
        raise ValueError("open.er-api result=%r" % d.get("result"))
    rate = float(d["rates"][quote])
    if not rate > 0:
        raise ValueError("환율 값 이상: %s=%r" % (pair, rate))
    t = datetime.fromtimestamp(int(d["time_last_update_unix"]), BKK).isoformat(timespec="seconds")
    return dict(rate=rate, rate_time=t, source="ExchangeRate-API (open.er-api.com)", url="https://www.exchangerate-api.com/")


def fx_frankfurter():
    d = get_json("https://api.frankfurter.app/latest?from=USD&to=THB,KRW,CNY")
    thb, krw = float(d["rates"]["THB"]), float(d["rates"]["KRW"])
    if not (5 < krw / thb < 200):
        raise ValueError("환율 값 이상")
    out = dict(THB_KRW=round(krw / thb, 4), USD_THB=round(thb, 4), USD_KRW=round(krw, 2), rate_time=datetime.fromisoformat(d["date"] + "T16:00:00+01:00").astimezone(BKK).isoformat(timespec="seconds"),
               source="Frankfurter (유럽중앙은행 ECB 기준환율)", url="https://www.frankfurter.app/")
    cny = d["rates"].get("CNY")
    if isinstance(cny, (int, float)) and 0.05 < cny / thb < 1:
        out["THB_CNY"] = round(float(cny) / thb, 5)
    return out


def gold_gta():
    d = get_json("https://www.goldtraders.or.th/api/GoldPrices/Latest?readjson=false")
    sell, buy = float(d["bL_SellPrice"]), float(d["bL_BuyPrice"])
    if not (10000 < sell < 500000 and 10000 < buy <= sell):
        raise ValueError("금시세 값 이상: sell=%r buy=%r" % (sell, buy))
    at = d["asTime"]  # 방콕 현지 시각(오프셋 없음)
    at = datetime.fromisoformat(at).replace(tzinfo=BKK).isoformat(timespec="seconds")
    return dict(bar_sell=sell, bar_buy=buy, change=d.get("priceChangeFromPrevRow"), round=d.get("priceSeq") or d.get("seq"),
                announced_at=at, unit="금괴 96.5% · 1바트(15.244 g)",
                source="태국 금거래상협회(Gold Traders Association)", url="https://www.goldtraders.or.th/")


def _be_date(dmy, hm="00:00"):  # '01/10/2569' (불기) + '21:15' → ISO(+07:00)
    d, m, y = [int(x) for x in dmy.split("/")]
    hh, mm = [int(x) for x in (hm or "00:00").replace(".", ":").split(":")[:2]]
    return datetime(y - 543 if y > 2400 else y, m, d, hh, mm, tzinfo=BKK).isoformat(timespec="seconds")


TH_MON = {"ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6, "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12}


def _th_effective(txt):  # 'ราคามีผล ณ วันที่ 2 ต.ค. 69 เวลา 05.00 น.' → ISO(+07:00) 또는 None
    import re
    m = re.search(r"วันที่\s*(\d{1,2})\s*([ก-๙.]+)\s*(\d{2,4})\s*เวลา\s*(\d{1,2})[.:](\d{2})", txt or "")
    if not m or m.group(2) not in TH_MON:
        return None
    y = int(m.group(3)); y = y + 2500 if y < 100 else y; y = y - 543 if y > 2400 else y
    return datetime(y, TH_MON[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), tzinfo=BKK).isoformat(timespec="seconds")


def fuel_bangchak():
    d = get_json("https://oil-price.bangchak.co.th/ApiOilPrice2/th")
    d = d[0] if isinstance(d, list) else d
    lst = json.loads(d["OilList"]) if isinstance(d["OilList"], str) else d["OilList"]
    g95 = [o for o in lst if "แก๊สโซฮอล์ 95" in o.get("OilName", "") or "Gasohol 95" in o.get("OilName", "")]
    if not g95:
        raise ValueError("가소홀 95 없음: %s" % [o.get("OilName") for o in lst])
    o = g95[0]; price = float(o["PriceToday"])
    if not (15 < price < 100):
        raise ValueError("유가 값 이상: %r" % price)
    # 화면에 태국 글자를 보이지 않게(운영자 요청 10-03): name = 한국어+로마자, 원래 이름은 name_th(화면에 안 씀)
    name = o["OilName"].replace("แก๊สโซฮอล์", "가소홀").strip()
    name = (name if "가소홀" in name else "가소홀 95 " + name) + "(Gasohol 95)"
    import re as _re
    name = _re.sub(r"\s*[\u0E00-\u0E7F]+\s*", " ", name).strip()
    return dict(gasohol95=price, name=name, name_th=o["OilName"], yesterday=o.get("PriceYesterday"), tomorrow=o.get("PriceTomorrow"),
                feed_date=_be_date(d["OilDateNow"]), announced_at=_be_date(d["OilPriceDate"], d.get("OilPriceTime")),
                effective=d.get("OilRemark2"), effective_at=_th_effective(d.get("OilRemark2")), note="방콕 소매가(방콕 지방세 미포함)",
                source="방짝(Bangchak) 유가 공지", url="https://www.bangchak.co.th/th/oilprice")


def _usdt_ok(p):
    if not (20 < p < 60):
        raise ValueError("USDT/THB 값 이상: %r" % p)
    return p


def usdt_google():
    import re
    html = urllib.request.urlopen(urllib.request.Request("https://www.google.com/finance/quote/USDT-THB?hl=en",
                                  headers=dict(UA, Accept="text/html", **{"Accept-Language": "en-US,en;q=0.9"})), timeout=30).read().decode("utf-8", "replace")
    # 페이지 안 데이터: ["/g/…",null,"Tether (USDT / THB)",3,null,[현재가,변동,변동%,…],null,전일종가,null,null,null,[유닉스시각]
    m = re.search(r'"Tether \(USDT / THB\)",\d+,null,\[([\d.]+),(-?[\d.eE-]+),(-?[\d.eE-]+)[^\]]*\],null,([\d.]+)(?:,null){3},\[(\d{9,11})\]', html)
    if not m:
        raise ValueError("구글 파이낸스 페이지에서 USDT/THB 값을 못 찾음(동의 화면·차단·구조 변경?) len=%d" % len(html))
    p = _usdt_ok(float(m.group(1))); ts = int(m.group(5))
    if abs(datetime.now(timezone.utc).timestamp() - ts) > 2 * 86400:
        raise ValueError("구글 시세 시각이 이틀 넘게 지남: %s" % ts)
    return dict(USDT_THB=round(p, 4), change=round(float(m.group(2)), 4), change_pct=round(float(m.group(3)), 3), prev_close=round(float(m.group(4)), 4),
                price_time=datetime.fromtimestamp(ts, BKK).isoformat(timespec="seconds"), google=True,
                source="구글 파이낸스 (Google Finance)", url="https://www.google.com/finance/quote/USDT-THB")


def usdt_coingecko():
    d = get_json("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=thb&include_last_updated_at=true&include_24hr_change=true")["tether"]
    p = _usdt_ok(float(d["thb"]))
    return dict(USDT_THB=round(p, 4), change_pct=round(float(d["thb_24h_change"]), 3) if d.get("thb_24h_change") is not None else None,
                price_time=datetime.fromtimestamp(int(d["last_updated_at"]), BKK).isoformat(timespec="seconds"), google=False,
                source="CoinGecko (여러 거래소 집계 시세)", url="https://www.coingecko.com/en/coins/tether/thb")


def usdt_bitkub():
    d = get_json("https://api.bitkub.com/api/v3/market/ticker?sym=USDT_THB")
    d = [x for x in (d if isinstance(d, list) else [d]) if x.get("symbol") == "USDT_THB"][0]
    p = _usdt_ok(float(d["last"]))
    return dict(USDT_THB=round(p, 4), change_pct=float(d["percent_change"]) if d.get("percent_change") not in (None, "") else None,
                price_time=None, google=False, source="Bitkub (태국 거래소 마지막 체결가)", url="https://www.bitkub.com/market/USDT")


REGIONS = [("pattaya", 12.9236, 100.8825), ("sriracha", 13.1682, 100.9310), ("bangkok", 13.7563, 100.5018)]  # assets/ticker.js 와 같게


def _multi(url):
    lat = ",".join(str(r[1]) for r in REGIONS); lon = ",".join(str(r[2]) for r in REGIONS)
    d = get_json(url + "&latitude=" + lat + "&longitude=" + lon + "&timezone=Asia%2FBangkok")
    d = d if isinstance(d, list) else [d]
    if len(d) != len(REGIONS):
        raise ValueError("지역 수 불일치")
    return zip([r[0] for r in REGIONS], d)


def wx_open_meteo():
    out = {}
    for rid, j in _multi("https://api.open-meteo.com/v1/forecast?current=temperature_2m,weather_code,is_day&hourly=precipitation_probability&forecast_hours=6"):
        c = j["current"]; pp = [x for x in j.get("hourly", {}).get("precipitation_probability", []) if isinstance(x, (int, float))]
        out[rid] = dict(t=c["temperature_2m"], code=c["weather_code"], day=c["is_day"], time=c["time"] + ":00+07:00", rain=max(pp) if pp else None)
    return dict(regions=out, source="Open-Meteo", url="https://open-meteo.com/")


MET_UA = {"User-Agent": "thai-news-kr/1.0 https://github.com/P-Max168/thai-news-kr", "Accept": "application/json"}


def _met_code(sym):  # MET Norway symbol_code → WMO 날씨 코드(화면 아이콘용 대략 대응)
    s = sym.split("_")[0]
    for k, c in (("thunder", 95), ("snow", 71), ("sleet", 71), ("drizzle", 51), ("rainshowers", 80), ("rain", 61), ("fog", 45),
                 ("cloudy", 3), ("partlycloudy", 2), ("fair", 1), ("clearsky", 0)):
        if s == k or (k in ("thunder", "snow", "sleet", "drizzle", "rainshowers", "rain") and k in s):
            return c
    return 3


def wx_met_no():  # Open-Meteo 가 막혔을 때(429 등) 대체 — 강수'확률'은 없어서 rain=None, 6시간 강수량(mm)만
    out = {}
    for rid, lat, lon in REGIONS:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%.4f&lon=%.4f" % (lat, lon), headers=MET_UA), timeout=30).read())
        now_ = datetime.now(timezone.utc)
        ts = [t for t in d["properties"]["timeseries"] if datetime.fromisoformat(t["time"].replace("Z", "+00:00")) <= now_] or d["properties"]["timeseries"][:1]
        t = ts[-1]; dd = t["data"]
        sym = (dd.get("next_1_hours") or dd.get("next_6_hours") or {}).get("summary", {}).get("symbol_code", "cloudy")
        out[rid] = dict(t=dd["instant"]["details"]["air_temperature"], code=_met_code(sym), day=0 if sym.endswith("_night") else 1,
                        time=datetime.fromisoformat(t["time"].replace("Z", "+00:00")).astimezone(BKK).isoformat(timespec="seconds"), rain=None,
                        rain6_mm=(dd.get("next_6_hours") or {}).get("details", {}).get("precipitation_amount"))
    return dict(regions=out, source="MET Norway (yr.no)", url="https://api.met.no/")


def aq_open_meteo():
    out = {}
    for rid, j in _multi("https://air-quality-api.open-meteo.com/v1/air-quality?current=pm2_5"):
        c = j["current"]
        if not isinstance(c.get("pm2_5"), (int, float)):
            raise ValueError("pm2_5 없음")
        out[rid] = dict(pm=c["pm2_5"], time=c["time"] + ":00+07:00")
    return dict(regions=out, source="Open-Meteo 대기질 (CAMS)", url="https://open-meteo.com/en/docs/air-quality-api")


def main():
    jf, js = ROOT / "data" / "ticker.json", ROOT / "data" / "ticker.js"
    try:
        old = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    out = {"v": 1, "updated_at": now()}
    ok = 0
    for key, fns in (("fx", [fx_er_api, fx_frankfurter]), ("usdt", [usdt_google, usdt_coingecko, usdt_bitkub]), ("gold", [gold_gta]), ("fuel", [fuel_bangchak]), ("wx", [wx_open_meteo, wx_met_no]), ("aq", [aq_open_meteo])):
        val = None
        for fn in fns:
            try:
                val = fn(); val["fetched_at"] = now(); break
            except Exception as e:
                print("%s: %s 실패 — %s" % (key, fn.__name__, e), file=sys.stderr)
        if val:
            ok += 1; out[key] = val
            print(key, json.dumps(val, ensure_ascii=False))
        elif old.get(key):
            out[key] = old[key]; print("%s: 이전 값 유지(fetched_at %s)" % (key, old[key].get("fetched_at")), file=sys.stderr)
    # 환율 직전 값(2026-10-15, 화면 ▲▼용): 기준 시각(rate_time)이 바뀌었으면 이전 파일 값을 prev_* 로, 같으면 이전 prev_* 를 이어 씀 — 실제로 받았던 값만
    of, nf = old.get("fx") or {}, out.get("fx") or {}
    if nf and of and nf is not of:
        for k in ("THB_KRW", "USD_THB", "THB_CNY"):
            if of.get("rate_time") and of.get("rate_time") != nf.get("rate_time") and isinstance(of.get(k), (int, float)):
                nf["prev_" + k] = of[k]; nf["prev_rate_time"] = of["rate_time"]
            elif "prev_" + k in of:
                nf["prev_" + k] = of["prev_" + k]; nf["prev_rate_time"] = of.get("prev_rate_time")
    if not out.get("fx") and not out.get("gold") or not ok:
        print("fx·gold 모두 실패 — 파일 그대로", file=sys.stderr); sys.exit(1)
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    jf.write_text(txt + "\n", encoding="utf-8")
    js.write_text("/* tools/fetch_ticker.py 가 만듦(GitHub Actions) — 직접 고치지 말 것 */\nwindow.TN_TICKER = " + txt + ";\n", encoding="utf-8")
    print("저장:", jf.relative_to(ROOT), js.relative_to(ROOT))


if __name__ == "__main__":
    main()
