# -*- coding: utf-8 -*-
"""factcheck(금액 단위·지명 대조) + 위안 이중 환산 + 비라틴 매체명 시험 (2026-10-30). 제미나이·네트워크 안 씀.

    python3 tools/dev/test_factcheck.py
"""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import factcheck as f  # noqa: E402

FAIL = []


def ok(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAIL.append(name)


BODY = "x" * 400   # 본문이 있다고 보는 최소 길이


def probs(story, body="", cur="THB"):
    return [k for k, _ in f.check_story(story, body, cur=cur)]


# ---- 숫자 읽기
v = [x for x, _ in f.source_amounts("ดึงลงทุน 2.5 หมื่น ล. และ 57 ล้าน และ 1.5 แสน ล. รวม 25,664 ล้านบาท")]
ok(2.5e10 in v and 57e6 in v and 1.5e11 in v and 25664e6 in v, "태국어 단위·줄임말(หมื่น ล., ล้าน, แสน ล.)")
v = [x for x, _ in f.source_amounts("rút 97 tỷ đồng, 400 triệu đồng, hơn 15.000 tỷ đồng, 2,5 tỷ")]
ok(97e9 in v and 4e8 in v and 1.5e13 in v and 2.5e9 in v, "베트남어 tỷ·triệu·천 단위 점·소수 쉼표")
v = [x for x, _ in f.source_amounts("a 37-million-baht robbery, Bt25bn, B3.7m")]
ok(37e6 in v and 25e9 in v and 3.7e6 in v, "영어 million(하이픈)·bn·m")

# ---- 10-30 저녁판 실제 오류
ok("amount" in probs(dict(id="pe1", title_th="ดึงลงทุน 2.5 หมื่น ล.", headline="预计吸引投资2.5万亿泰铢")), "ZH pe1 2.5万亿 (원문 2.5 หมื่น ล.) 잡음")
ok("amount" in probs(dict(id="ea2", title_th="EEC อีก 4 แห่ง", headline="… 2.5만 바트(약 99.1만 원) 규모 투자",
                         summary=["총 256억6,400만 바트 규모"]), "มูลค่า 25,664 ล้านบาท " * 20), "KR ea2 2.5만 바트 (본문 25,664 ล้าน) 잡음")
ok("place" in probs(dict(id="cn2", title_th="รวบจีนเทา", headline="春武里移民局破获灰色产业"), "ตม.จว.ชุมพร อ.หลังสวน จ.ชุมพร " * 20), "ZH cn2 춤폰→촌부리 잡음")
ok("place" in probs(dict(id="so4", title_th="ปิดเว็บหนังเถื่อน", headline="泰国警方突查乌隆府"), "บุกค้นบ้านพักใน จ.อุบลราชธานี " * 20), "우본→우돈(乌隆) 잡음")
ok("amount" in probs(dict(id="v1", title_th="trúng độc đắc 20 tỷ đồng", headline="복권 1등 당첨…총 20억 동(약 1.04억 원)"), cur="VND"), "VN 20 tỷ → 20억 동(10배 작음) 잡음")

# ---- 오탐 방지(통과해야 함)
ok(not probs(dict(id="k1", title_th="ตม.1 รวบ…พนันออนไลน์นับพันล้าน", headline="涉案千亿韩元",
                  summary=["1000亿韩元（约合25亿泰铢（约4.95亿元））"]), "มากกว่า 1 แสนล้านวอน ราว 2,500 ล้านบาท " * 20), "환산 금액(원문에 있음) 통과")
ok(not probs(dict(id="k2", title_th="Five suspects flee after 37-million-baht robbery", headline="3,700만 바트 강도 용의자 5명 출국")), "영어 하이픈 단위 통과")
ok(not probs(dict(id="k3", title_th="รวบ 5 ชาวเวียดนาม ยึดของกลาง 3,200 ชิ้น", headline="缴获500万泰铢货物")), "작은 숫자(5명) 때문에 오탐 안 함")
ok(not probs(dict(id="k5", title_th="น้ำท่วม", headline="촌부리주 파타야 도로 침수"), "น้ำท่วมถนนสุขุมวิท พัทยา " * 20), "파타야 원문 → 촌부리 표기 허용")
ok(not probs(dict(id="k6", title_th="น้ำท่วม", headline="춤폰 홍수", summary=["춤폰주"]), ""), "본문 없으면 지명 검사 안 함")
ok(not probs(dict(id="k7", title_th="EEC 4 แห่ง ชลบุรี-ระยอง", headline="촌부리·라용 EEC 특구"), "ชลบุรี ระยอง " * 40), "원문에 있는 주는 통과")

# ---- 위안 이중 환산 제거(gemini_edition._fix_text)
sys.argv = [sys.argv[0]]
try:
    import gemini_edition as ge
    t = ge._fix_text("涉案金额高达1000亿韩元（约合25亿泰铢/约4.95亿元）的大型", 0.198, "cny")
    ok(t.count("元）") == 1 and "/约" not in t, "위안 이중 환산 제거: " + t)
except SystemExit:
    print("SKIP 위안 시험(사이트 설정 없음)")

# ---- 판 저장 단계 연결(save_with_drop + make_checker): 틀린 기사만 빠지고 나머지는 발행
try:
    import gemini_edition as ge
    import newslib as nl
    saved = {}
    _orig = nl.write_edition
    nl.write_edition = lambda d, **k: saved.setdefault("n", len(d["stories"]))
    items = [dict(url="https://a/%d" % i, title="ข่าว %d" % i, memo="", text="ข้อความ " * 80) for i in range(5)]
    vnd = ge.SITE.get("currency", {}).get("check") == "vnd_check"   # 채널 통화에 맞춰(VN = 동)
    items[2]["title"] = "đầu tư 2,5 tỷ đồng" if vnd else "ดึงลงทุน 2.5 หมื่น ล."
    stories = [dict(id="s%d" % i, url="https://a/%d" % i, title_th=items[i]["title"], topic="poleco", region="", headline="뉴스 %d" % i,
                    summary=["내용"]) for i in range(5)]
    stories[2]["headline"] = "투자 2,500만 동 유치" if vnd else "투자 2.5조 바트 유치"
    data = dict(stories=stories, briefing=[], highlights=["s0"])
    okk = ge.save_with_drop(data, retranslate_fn=lambda d, sid, defect_note="": False, extra_check=__import__("factcheck").make_checker(items, ge.SITE))
    ok(okk and saved.get("n") == 4 and [s["id"] for s in data["stories"]] == ["s0", "s1", "s3", "s4"], "저장 단계: 단위 오류 기사 1건만 격리, 4건 발행")
    ok(ge.FACT_DROPS and ge.FACT_DROPS[0]["id"] == "s2", "격리 기록(factcheck_drops)")
    nl.write_edition = _orig
except SystemExit:
    print("SKIP 저장 단계 시험(사이트 설정 없음)")

# ---- 비라틴 매체명이 e/ 페이지를 깨지 않음(source_label)
try:
    import newslib
    lab = newslib.source_label("Bangkok Biz News(กรุงเทพธุรกิจ)", "bangkokbiznews.com")
    ok("ก" not in lab, "매체명 태국 글자 제거: " + lab)
    lab2 = newslib.source_label("กรุงเทพธุรกิจ", "bangkokbiznews.com")
    ok(lab2 == "bangkokbiznews.com", "전부 태국어 매체명 → 도메인: " + lab2)
    lab3 = newslib.source_label("泰国头条新闻", "thaiheadlines.com")
    ok(bool(lab3), "중국어 매체명 유지/대체: " + lab3)
    lab4 = newslib.source_label("Tuổi Trẻ", "tuoitre.vn")
    ok(bool(lab4), "베트남어 매체명 유지: " + lab4)
except SystemExit:
    print("SKIP 매체명 시험(사이트 설정 없음)")

print("\n결과:", "모두 통과" if not FAIL else "실패 %d: %s" % (len(FAIL), FAIL))
sys.exit(1 if FAIL else 0)
