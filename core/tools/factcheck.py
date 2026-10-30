# -*- coding: utf-8 -*-
"""발행 전 사실 대조 — 금액 단위·지명 (2026-10-30 Claude, 맥스님 '오역 에러 코드로 막기').

왜: 10-30 저녁판에서 제미나이가
  · 원문 "2.5 หมื่น ล."(250억 바트)를 중국어판 "2.5万亿"(2.5조), 한국어판 "2.5만 바트"로 옮김(100배·100만 배 오류)
  · 원문 춤폰(ชุมพร)을 "春武里(촌부리)", 우본을 "乌隆(우돈)"으로 옮김
  → 기존 검사(태국 글자·원화 환산 유무)는 '숫자가 원문과 같은지', '지명이 원문에 있는지'는 안 봤다.

무엇을 하나(판 저장 직전, gemini_edition.save_with_drop 안에서):
  1) 금액: 번역 글의 현지 통화 금액(바트·泰铢·동)을 원문(제목·본문·메모)의 숫자와 비교.
     원문에 같은 값(±5%)이 없고, 원문 숫자와 정확히 10^k 배(k≠0) 차이가 나면 = 단위 오류 → 그 기사 실패.
     (원문에 아예 없는 금액은 계산·환산일 수 있어 실패로 보지 않고 경고만 — 오탐으로 멀쩡한 기사를 빼지 않기)
  2) 지명(태국 채널): 번역 글에 나온 태국 주(州) 이름이 원문 어디에도(태국어·영어·별칭) 없으면 → 그 기사 실패.
     원문 본문이 없으면(가져오기 실패) 지명 검사는 건너뜀(근거 없이 빼지 않기). 방콕은 너무 흔해 검사 안 함.
  실패는 AssertionError(((기사 id, "factcheck"), 설명)) — save_with_drop 이 재번역 1회 → 그래도 틀리면 그 기사만 빼고 발행.

    python3 tools/factcheck.py demo     # 10-30 저녁판 실제 오류 3건이 잡히는지 확인(제미나이 안 부름)
"""
import math, re, sys

# ---------------------------------------------------------------- 숫자 읽기
_N = r"\d[\d,.]*\d|\d"

TH_UNITS = [   # 긴 것부터. 'ล.' = ล้าน 줄임(태국 기사 제목에 흔함: "57 ล.", "2.5 หมื่น ล.", "1.5 แสน ล.")
    ("ล้านล้าน", 1e12), ("แสนล้าน", 1e11), ("หมื่นล้าน", 1e10), ("พันล้าน", 1e9), ("ร้อยล้าน", 1e8), ("สิบล้าน", 1e7),
    ("ล้าน", 1e6), ("แสน", 1e5), ("หมื่น", 1e4), ("พัน", 1e3),
]
TH_RE = re.compile(r"(?<![\d.,])(%s)\s*(ล้านล้าน|แสนล้าน|หมื่นล้าน|พันล้าน|ร้อยล้าน|สิบล้าน|ล้าน|แสน|หมื่น|พัน)?\s*(ล้าน|ลบ\.|ล\.)?" % _N)
EN_RE = re.compile(r"(?<![\d.,])(%s)\s*-?\s*(trillion|billion|million|thousand|bn|mn|tn|m|k)?\b" % _N, re.I)
KO_SRC_RE = re.compile(r"(?<![\d,.])((?:\d[\d,]*(?:\.\d+)?\s*[조억만]\s*)+(?:\d[\d,]*(?:\.\d+)?)?)")   # 한국어 원문(한국 매체) '5억', '1천억'은 드묾
VI_RE = re.compile(r"(?<![\d.,])(%s)\s*(nghìn tỷ|nghìn tỉ|ngàn tỷ|tỷ|tỉ|triệu|nghìn|ngàn)?" % _N, re.I)
EN_MUL = {"trillion": 1e12, "tn": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
RANGE_RE = re.compile(r"(?<![\d.,])(%s)\s*(?:-|–|~|ถึง|to|đến|tới)\s*(%s)\s*(ล้านล้าน|แสนล้าน|หมื่นล้าน|พันล้าน|ร้อยล้าน|สิบล้าน|ล้าน|แสน|หมื่น|พัน|ลบ\.|ล\.|trillion|billion|million|bn|nghìn tỷ|tỷ|tỉ|triệu)" % (_N, _N), re.I)
VI_MUL = {"nghìn tỷ": 1e12, "nghìn tỉ": 1e12, "ngàn tỷ": 1e12, "tỷ": 1e9, "tỉ": 1e9, "triệu": 1e6, "nghìn": 1e3, "ngàn": 1e3}


def _num(s, vi=False):
    """'2,500' → 2500, '2.5' → 2.5, 베트남식 '1.200' → 1200 · '2,5' → 2.5."""
    s = s.strip()
    if vi:
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            a, b = s.rsplit(",", 1)
            s = s.replace(",", "") if len(b) == 3 else a.replace(",", "") + "." + b
        elif s.count(".") >= 1 and all(len(p) == 3 for p in s.split(".")[1:]):
            s = s.replace(".", "")
    else:
        s = s.replace(",", "")
        if s.count(".") > 1:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def source_amounts(text, lang="th"):
    """원문 글의 숫자 → [(값, 단위있음)]. 단위 없는 숫자도 넣는다(같은 값 대조용 — 많을수록 오탐이 줄어듦).
    10^k 배 '단위 오류' 판정에는 단위가 붙은 값과 10,000 이상인 숫자만 쓴다('20년'·'700개' 같은 작은 숫자로 오탐하지 않게)."""
    out = []
    t = text or ""
    for m in TH_RE.finditer(t):
        v = _num(m.group(1))
        if v is None:
            continue
        mul = dict(TH_UNITS).get(m.group(2) or "", 1)
        if m.group(3):   # 'หมื่น ล.' = หมื่น × ล้าน, '57 ล.' = 57 × ล้าน
            mul = mul * 1e6 if m.group(2) != "ล้าน" else mul
        out.append((v * mul, bool(m.group(2) or m.group(3))))
    for m in EN_RE.finditer(t):
        v = _num(m.group(1))
        if v is not None and m.group(2):
            out.append((v * EN_MUL[m.group(2).lower()], True))
    for m in VI_RE.finditer(t):
        v = _num(m.group(1), vi=True)
        if v is not None and m.group(2):
            out.append((v * VI_MUL[m.group(2).lower()], True))
    for m in KO_SRC_RE.finditer(t):
        v = _ko_val(m.group(1))
        if v:
            out.append((v, True))
    # 범위의 앞 숫자에도 뒤 단위를 붙인다: '100-1,000 ล้านบาท' → 100 ล้าน 도 원문 값(코덱스 리뷰 2026-10-30)
    for m in RANGE_RE.finditer(t):
        a, unit = m.group(1), m.group(3).strip().lower()
        mul = dict(TH_UNITS).get(unit) or EN_MUL.get(unit) or VI_MUL.get(unit) or {"ล.": 1e6, "ลบ.": 1e6}.get(unit)
        v = _num(a, vi=unit in VI_MUL)
        if v is not None and mul:
            out.append((v * mul, True))
    return out


# 번역 글의 현지 통화 금액
KO_BAHT_RE = re.compile(r"(?<![\d,.])((?:\d[\d,]*(?:\.\d+)?\s*[조억만]\s*)*(?:\d[\d,]*(?:\.\d+)?)?)\s*바트")
KO_DONG_RE = re.compile(r"(?<![\d,.])((?:\d[\d,]*(?:\.\d+)?\s*[조억만]\s*)*(?:\d[\d,]*(?:\.\d+)?)?)\s*동(?![네부안시북남서쪽행료생기물작맹원아])")
ZH_BAHT_RE = re.compile(r"(?<![\d,.])(\d[\d,]*(?:\.\d+)?)\s*(万亿|亿|万)?\s*泰铢")


def _ko_val(s):
    s = re.sub(r"[\s,]", "", s or "")
    if not re.search(r"\d", s):
        return None
    total, units = 0.0, {"조": 1e12, "억": 1e8, "만": 1e4}
    for num, u in re.findall(r"(\d+(?:\.\d+)?)([조억만]?)", s):
        total += float(num) * units.get(u, 1)
    return total


def shown_amounts(text, cur):
    """번역 글 → [(금액 글, 값)]. cur: THB(ko 바트 / zh 泰铢) · VND(ko 동)."""
    out = []
    t = text or ""
    if cur == "THB":
        for m in KO_BAHT_RE.finditer(t):
            v = _ko_val(m.group(1))
            if v:
                out.append((m.group(0), v))
        for m in ZH_BAHT_RE.finditer(t):
            v = _num(m.group(1))
            if v:
                out.append((m.group(0), v * {"万亿": 1e12, "亿": 1e8, "万": 1e4}.get(m.group(2) or "", 1)))
    elif cur == "VND":
        for m in KO_DONG_RE.finditer(t):
            v = _ko_val(m.group(1))
            if v:
                out.append((m.group(0), v))
    return out


def unit_error(v, src, tol=0.05, min_big=1e6):
    """번역 값 v 가 원문 값과 같으면 None. 같은 값은 없고 어떤 원문 값(단위 있음 또는 10,000 이상)과 정확히 10^k 배(k≠0)면
    그 원문 값을 돌려줌(= 단위 오류). src = [(값, 단위있음)]."""
    if v <= 0:
        return None
    for s, _u in src:
        if s > 0 and abs(v - s) <= tol * max(v, s):
            return None
    for s, unit in src:
        if s <= 0 or max(v, s) < min_big or not (unit or s >= 1e4):
            continue
        r = math.log10(v / s)
        k = round(r)
        if k != 0 and abs(k) <= 8 and abs(v / s / (10 ** k) - 1) <= tol:
            return s
    return None


# ---------------------------------------------------------------- 태국 77개 주
# (태국어, [영어·로마자], [한국어], [중국어], [같은 주로 인정할 태국어/영어 별칭(도시·섬·공항)])
TH_PROVINCES = [
    ("กระบี่", ["Krabi"], ["끄라비", "크라비"], ["甲米"], ["ลันตา", "Lanta", "อ่าวนาง", "Ao Nang"]),
    ("กาญจนบุรี", ["Kanchanaburi"], ["깐짜나부리", "칸차나부리"], ["北碧"], []),
    ("กาฬสินธุ์", ["Kalasin"], ["깔라신", "칼라신"], ["加拉信"], []),
    ("กำแพงเพชร", ["Kamphaeng Phet"], ["깜팽펫", "캄팽펫"], ["甘烹碧"], []),
    ("ขอนแก่น", ["Khon Kaen"], ["콘깬", "컨깬", "콘캔"], ["孔敬"], []),
    ("จันทบุรี", ["Chanthaburi"], ["짠타부리", "찬타부리"], ["尖竹汶"], []),
    ("ฉะเชิงเทรา", ["Chachoengsao"], ["차층사오"], ["北柳"], []),
    ("ชลบุรี", ["Chonburi", "Chon Buri"], ["촌부리"], ["春武里"], ["พัทยา", "Pattaya", "ศรีราชา", "Si Racha", "Sriracha", "บางแสน", "Bang Saen", "สัตหีบ", "Sattahip", "บางละมุง", "Bang Lamung", "แหลมฉบัง", "Laem Chabang", "จอมเทียน", "Jomtien", "นาเกลือ", "Naklua", "พานทอง", "บ่อวิน", "บ้านบึง", "อีอีซี", "EEC"]),
    ("ชัยนาท", ["Chai Nat", "Chainat"], ["차이낫"], ["猜纳"], []),
    ("ชัยภูมิ", ["Chaiyaphum"], ["차이야품"], ["猜也蓬"], []),
    ("ชุมพร", ["Chumphon"], ["춤폰", "촘폰"], ["春蓬"], ["หลังสวน", "Lang Suan"]),
    ("เชียงราย", ["Chiang Rai"], ["치앙라이"], ["清莱"], ["แม่สาย", "Mae Sai"]),
    ("เชียงใหม่", ["Chiang Mai"], ["치앙마이"], ["清迈"], []),
    ("ตรัง", ["Trang"], ["뜨랑", "트랑"], ["董里"], []),
    ("ตราด", ["Trat"], ["뜨랏", "트랏"], ["达叻"], ["เกาะช้าง", "Koh Chang", "Ko Chang"]),
    ("ตาก", ["Tak"], [], ["达府", "来兴"], ["แม่สอด", "Mae Sot"]),
    ("นครนายก", ["Nakhon Nayok"], ["나콘나욕"], ["那空那育"], []),
    ("นครปฐม", ["Nakhon Pathom"], ["나콘빠톰", "나콘파톰"], ["佛统"], []),
    ("นครพนม", ["Nakhon Phanom"], ["나콘파놈"], ["那空拍侬", "那空帕农"], []),
    ("นครราชสีมา", ["Nakhon Ratchasima", "Korat"], ["나콘랏차시마", "나콘라차시마", "코랏"], ["呵叻", "那空叻差是玛"], ["โคราช"]),
    ("นครศรีธรรมราช", ["Nakhon Si Thammarat"], ["나콘시탐마랏"], ["洛坤", "那空是贪玛叻"], []),
    ("นครสวรรค์", ["Nakhon Sawan"], ["나콘사완"], ["北榄坡", "那空沙旺"], []),
    ("นนทบุรี", ["Nonthaburi"], ["논타부리"], ["暖武里"], []),
    ("นราธิวาส", ["Narathiwat"], ["나라티왓"], ["陶公", "那拉提瓦"], []),
    ("น่าน", ["Nan"], [], ["难府", "楠府"], []),
    ("บึงกาฬ", ["Bueng Kan"], ["븡깐", "붕깐"], ["汶干"], []),
    ("บุรีรัมย์", ["Buriram", "Buri Ram"], ["부리람"], ["武里南"], []),
    ("ปทุมธานี", ["Pathum Thani"], ["빠툼타니", "파툼타니"], ["巴吞他尼"], ["รังสิต", "Rangsit"]),
    ("ประจวบคีรีขันธ์", ["Prachuap Khiri Khan", "Prachuap"], ["쁘라추압", "프라추압"], ["巴蜀"], ["หัวหิน", "Hua Hin"]),
    ("ปราจีนบุรี", ["Prachinburi", "Prachin Buri"], ["쁘라찐부리", "프라친부리"], ["巴真"], []),
    ("ปัตตานี", ["Pattani"], ["빳따니", "파타니"], ["北大年"], []),
    ("พระนครศรีอยุธยา", ["Ayutthaya", "Ayuthaya"], ["아유타야", "아유따야"], ["大城"], ["อยุธยา"]),
    ("พะเยา", ["Phayao"], ["파야오"], ["帕尧"], []),
    ("พังงา", ["Phang Nga", "Phangnga"], ["팡아", "팡응아"], ["攀牙"], ["เขาหลัก", "Khao Lak"]),
    ("พัทลุง", ["Phatthalung"], ["팟탈룽"], ["博他仑", "博达伦"], []),
    ("พิจิตร", ["Phichit"], ["피찟", "피칫"], ["披集"], []),
    ("พิษณุโลก", ["Phitsanulok"], ["핏사눌록"], ["彭世洛"], []),
    ("เพชรบุรี", ["Phetchaburi"], ["펫차부리", "펫부리"], ["佛丕"], ["ชะอำ", "Cha-am", "Cha Am"]),
    ("เพชรบูรณ์", ["Phetchabun"], ["펫차분"], ["碧差汶"], []),
    ("แพร่", ["Phrae"], ["프래주", "프래 주"], ["帕府"], []),
    ("ภูเก็ต", ["Phuket"], ["푸껫", "푸켓"], ["普吉"], ["ป่าตอง", "Patong", "กะรน", "Karon", "กะตะ", "Kata"]),
    ("มหาสารคาม", ["Maha Sarakham"], ["마하사라캄"], ["玛哈沙拉堪"], []),
    ("มุกดาหาร", ["Mukdahan"], ["묵다한"], ["莫达汉", "穆达汉"], []),
    ("แม่ฮ่องสอน", ["Mae Hong Son"], ["매홍손"], ["夜丰颂"], ["ปาย", "Pai"]),
    ("ยโสธร", ["Yasothon"], ["야소톤"], ["益梭通"], []),
    ("ยะลา", ["Yala"], ["얄라", "야라"], ["也拉"], ["เบตง", "Betong"]),
    ("ร้อยเอ็ด", ["Roi Et"], ["로이엣", "러이엣"], ["黎逸"], []),
    ("ระนอง", ["Ranong"], ["라농"], ["拉廊"], []),
    ("ระยอง", ["Rayong"], ["라용"], ["罗勇"], ["มาบตาพุด", "Map Ta Phut", "อู่ตะเภา", "U-Tapao", "U Tapao", "เกาะเสม็ด", "Koh Samet", "อีอีซี", "EEC"]),
    ("ราชบุรี", ["Ratchaburi"], ["랏차부리", "라차부리"], ["叻丕"], []),
    ("ลพบุรี", ["Lopburi", "Lop Buri"], ["롭부리"], ["华富里"], []),
    ("ลำปาง", ["Lampang"], ["람빵", "람팡"], ["南邦"], []),
    ("ลำพูน", ["Lamphun"], ["람푼"], ["南奔"], []),
    ("เลย", ["Loei"], ["러이", "르이"], ["黎府"], []),
    ("ศรีสะเกษ", ["Sisaket", "Si Sa Ket"], ["시사껫", "시사켓"], ["四色菊"], []),
    ("สกลนคร", ["Sakon Nakhon"], ["사꼰나콘", "사콘나콘"], ["色军"], []),
    ("สงขลา", ["Songkhla"], ["송클라", "쏭크라"], ["宋卡"], ["หาดใหญ่", "Hat Yai", "Hatyai", "สะเดา", "Sadao"]),
    ("สตูล", ["Satun"], ["사뚠", "사툰"], ["沙敦"], []),
    ("สมุทรปราการ", ["Samut Prakan"], ["사뭇쁘라깐", "사뭇프라칸"], ["北榄"], ["สุวรรณภูมิ", "Suvarnabhumi", "บางพลี", "Bang Phli"]),
    ("สมุทรสงคราม", ["Samut Songkhram"], ["사뭇송크람"], ["夜功"], []),
    ("สมุทรสาคร", ["Samut Sakhon"], ["사뭇사콘"], ["龙仔厝"], ["มหาชัย", "Mahachai"]),
    ("สระแก้ว", ["Sa Kaeo"], ["사깨우", "사깨오"], ["沙缴"], ["อรัญประเทศ", "Aranyaprathet"]),
    ("สระบุรี", ["Saraburi"], ["사라부리"], ["北标"], []),
    ("สิงห์บุรี", ["Sing Buri"], ["싱부리"], ["信武里"], []),
    ("สุโขทัย", ["Sukhothai"], ["수코타이"], ["素可泰"], []),
    ("สุพรรณบุรี", ["Suphan Buri", "Suphanburi"], ["수판부리"], ["素攀"], []),
    ("สุราษฎร์ธานี", ["Surat Thani"], ["수랏타니", "수라타니"], ["素叻他尼"], ["สมุย", "Samui", "พะงัน", "Phangan", "Pha Ngan", "เกาะเต่า", "Koh Tao"]),
    ("สุรินทร์", ["Surin"], ["수린"], ["素林"], []),
    ("หนองคาย", ["Nong Khai"], ["농카이"], ["廊开"], []),
    ("หนองบัวลำภู", ["Nong Bua Lamphu"], ["농부아람푸"], ["廊磨南蒲"], []),
    ("อ่างทอง", ["Ang Thong"], ["앙통"], ["红统"], []),
    ("อำนาจเจริญ", ["Amnat Charoen"], ["암낫짜른", "암낫차른"], ["安纳乍伦"], []),
    ("อุดรธานี", ["Udon Thani", "Udon"], ["우돈타니", "우돈"], ["乌隆他尼", "乌隆"], []),
    ("อุตรดิตถ์", ["Uttaradit"], ["웃따라딧", "우타라딧"], ["程逸"], []),
    ("อุทัยธานี", ["Uthai Thani"], ["우타이타니"], ["乌泰他尼"], []),
    ("อุบลราชธานี", ["Ubon Ratchathani", "Ubon"], ["우본랏차타니", "우본라차타니", "우본"], ["乌汶叻差他尼", "乌汶"], []),
]


def _shown_names():
    """(표시 이름, 주 index) — 긴 이름부터(나콘○○ 처럼 앞이 같은 이름을 짧은 것으로 잘못 잡지 않게)."""
    names = []
    for i, (_th, _en, ko, zh, _al) in enumerate(TH_PROVINCES):
        for n in ko + zh:
            names.append((n, i))
    return sorted(names, key=lambda x: -len(x[0]))


SHOWN_NAMES = _shown_names()


# 지명이 아닌 보통 낱말(코덱스 리뷰: '大城市'=큰 도시 ≠ 아유타야 '大城')
NOT_PLACE = {"大城": ("大城市", "大城镇", "大城区"), "北标": ("北标准",), "董里": (), "华富里": ()}
HANGUL = re.compile(r"[\uAC00-\uD7A3]")


def provinces_in(text):
    """번역 글에 나온 주 → {index: 글에 쓰인 이름}(긴 이름부터 찾고 그 자리는 지움).
    한국어 2글자 이름은 낱말 첫머리일 때만(앞에 한글이 붙으면 다른 낱말의 일부)."""
    t, found = text or "", {}
    for w in [x for v in NOT_PLACE.values() for x in v]:
        t = t.replace(w, " " * len(w))
    for n, i in SHOWN_NAMES:
        start = 0
        while True:
            k = t.find(n, start)
            if k < 0:
                break
            if HANGUL.match(n) and len(n) <= 2 and k > 0 and HANGUL.match(t[k - 1]):
                start = k + len(n); continue
            found.setdefault(i, n)
            t = t[:k] + " " * len(n) + t[k + len(n):]
            start = k + len(n)
    return found


def province_in_source(i, src):
    """원문에 이 주가 있나 — 태국어·영어·별칭, 그리고 한국어·중국어 원문(한국 매체·중국어 매체)이면 그 표기도."""
    th, en, ko, zh, al = TH_PROVINCES[i]
    low = (src or "").lower()
    if th in src or any(n in src for n in ko + zh):
        return True
    for a in en + al:
        if a and (a in src or a.lower() in low or a.replace(" ", "").lower() in low.replace(" ", "")):
            return True
    return False


# ---------------------------------------------------------------- 판 대조
STORY_FIELDS = ("headline", "summary", "context", "region", "for_me")


def _story_text(s):
    parts = []
    for k in STORY_FIELDS:
        v = s.get(k)
        parts += [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str)]
    return "\n".join(parts)


def check_story(s, body, cur="THB", places=True, memo="", min_body=300):
    """기사 하나 → 문제 목록[(종류, 설명)]. 종류: 'amount'(단위 오류) · 'place'(원문에 없는 주).
    body = 원문 본문(가져온 것). 본문이 없으면(min_body 미만) 원문 제목과 짝인 '번역 제목' 금액만 보고, 지명은 안 본다 —
    본문에만 있는 숫자·지명을 몰라서 멀쩡한 기사를 빼지 않게."""
    probs = []
    full = len(body or "") >= min_body
    txt = _story_text(s) if full else str(s.get("headline") or "")
    src_all = "\n".join(x for x in (s.get("title_th") or "", memo or "", body or "") if x)
    src_vals = source_amounts(src_all)
    for shown, v in shown_amounts(txt, cur):
        s0 = unit_error(v, src_vals)
        if s0 is not None:
            k = round(math.log10(v / s0))
            msg = ("금액 단위 오류: '%s'(=%s) 인데 원문 숫자는 %s — %s배 %s. 원문 단위(태국어 ล.=ล้าน=백만, หมื่น ล.=100억, แสน ล.=1,000억 · 베트남어 tỷ=10억, triệu=100만)를 다시 읽을 것"
                   % (shown.strip(), "{:,.0f}".format(v), "{:,.0f}".format(s0), "{:,}".format(10 ** abs(k)), "큼" if k > 0 else "작음"))
            if ("amount", msg) not in probs:
                probs.append(("amount", msg))
    if places and full:
        for i, name in sorted(provinces_in(txt).items()):
            if not province_in_source(i, src_all):
                th, en, _ko, _zh, _ = TH_PROVINCES[i]
                probs.append(("place", "지명 오류: 번역에 '%s'(%s, %s) 가 나오는데 원문에는 이 주가 없음 — 원문 지명을 그대로 옮길 것" % (name, en[0], th)))
    return probs


def make_checker(items, site):
    """gemini_edition 용: data → 문제가 있는 첫 기사에서 AssertionError. items = 제미나이에 넘긴 기사(url·text·memo·title)."""
    by_url = {it.get("url"): it for it in items}
    cur = "VND" if site.get("currency", {}).get("check") == "vnd_check" else "THB"
    places = site.get("factcheck", {}).get("places", cur == "THB")   # 태국 지명 표는 태국 뉴스 채널(KR·ZH)만
    warned = set()

    def _check(data):
        for s in data.get("stories") or []:
            it = by_url.get(s.get("url")) or {}
            probs = check_story(s, it.get("text") or "", cur=cur, places=places, memo=it.get("memo") or "")
            hard = [p for p in probs if p[0] in ("amount", "place")]
            if hard:
                raise AssertionError(((s["id"], "factcheck"), "; ".join(p[1] for p in hard)[:400]))
            for p in probs:
                if (s["id"], p[1]) not in warned:
                    warned.add((s["id"], p[1])); print("factcheck 참고:", s["id"], p[1], flush=True)
    return _check


# ---------------------------------------------------------------- 시연(10-30 저녁판 실제 오류)
def demo():
    cases = [
        ("ZH pe1 (2.5조)", dict(id="pe1", title_th="รัฐบาลอนุมัติขยาย EEC อีก 4 แห่ง ชลบุรี-ระยอง ดึงลงทุน 2.5 หมื่น ล.",
                                headline="泰国政府批准在春武里和罗勇新增4处东部经济走廊特区，预计吸引投资2.5万亿泰铢",
                                summary=["此举旨在进一步吸引高附加值产业和外资投入，预计将带来超过2.5万亿泰铢（约4952亿元）的新增投资额。"]), "", "THB"),
        ("KR ea2 (2.5만 바트)", dict(id="ea2", title_th="รัฐบาลไฟเขียว ขยายเขตส่งเสริมเศรษฐกิจพิเศษ EEC อีก 4 แห่ง ในชลบุรี-ระยอง",
                                   headline="태국 정부, 촌부리·라용 EEC 경제특구 4곳 추가 승인… 2.5만 바트(약 99.1만 원) 규모 투자 유치",
                                   summary=["총 256억6,400만 바트(약 1조 164억 원) 규모의 투자와 최대 1만 4,700개의 일자리가 창출될 것으로 기대된다."]),
         "มูลค่าการลงทุนรวม 25,664 ล้านบาท จ้างงาน 14,700 อัตรา " * 6, "THB"),
        ("ZH cn2 (춤폰→촌부리)", dict(id="cn2", title_th="รวบจีนเทา! สวมบัตรคนไทย กว้านซื้อที่ดิน 57 ล้าน-ตั้งล้งทุเรียนนอมินี",
                                    headline="春武里移民局破获灰色产业：中国籍女子冒用泰籍身份证买地，涉案金额巨大",
                                    summary=["非法购买了7块土地，价值达5700万泰铢（约1129万元）。"]),
         "สารวัตร ตม.จว.ชุมพร ร่วมกับตำรวจภูธร อ.หลังสวน จ.ชุมพร ตรวจสอบ ที่ดิน 7 แปลง มูลค่า 57 ล้านบาท " * 5, "THB"),
        ("정상 기사(통과해야 함)", dict(id="ok1", title_th="ตม.1 รวบหนุ่มแดนกิมจิ Overstay หนีหมายแดงคดีพนันออนไลน์นับพันล้าน",
                                     headline="曼谷移民局抓获涉案千亿韩元网络赌博案的韩国籍红通逃犯",
                                     summary=["涉案金额高达1000亿韩元（约合25亿泰铢（约4.95亿元））。"]),
         "ความเสียหายมากกว่า 1 แสนล้านวอน ราว 2,500 ล้านบาท ซอยสุขุมวิท 42 กรุงเทพฯ " * 5, "THB"),
    ]
    bad = 0
    for name, s, src, cur in cases:
        p = check_story(s, src, cur=cur)
        print("%-24s → %s" % (name, "; ".join("%s: %s" % x for x in p) if p else "통과"))
        bad += (1 if p else 0) != (0 if name.startswith("정상") else 1)
    print("결과:", "OK" if bad == 0 else "기대와 다름 %d건" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(demo() if sys.argv[1:2] == ["demo"] else 0)
