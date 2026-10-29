# -*- coding: utf-8 -*-
"""환산 금액 3유효숫자 반올림 검사(2026-10-28 Max).
실행: python3 tools/dev/test_money_round.py
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import newslib as n

FAIL = 0

def eq(label, got, exp):
    global FAIL
    if got != exp:
        FAIL += 1
        print("FAIL", label, "got=%r exp=%r" % (got, exp))
    else:
        print("ok  ", label, "→", got)

def main():
    # Max 예시
    eq("588→590원", n.krw_text(588), "590원")
    eq("1234567→123만", n.krw_text(1234567), "123만 원")
    eq("123억", n.krw_text(12345678900), "123억 원")
    # 작은 금액·경계
    eq("99원", n.krw_text(99), "99원")
    eq("150원", n.krw_text(150), "150원")
    eq("999→1,000원", n.krw_text(999), "1,000원")  # 999→round 10 →1000? round(99.9)*10=1000
    eq("1000→1,000원", n.krw_text(1000), "1,000원")  # <1만, round_sig keeps 1000
    eq("10000→1만", n.krw_text(10000), "1만 원")
    eq("4019000→402만", n.krw_text(4019000), "402만 원")
    # krw_for
    eq("15@39.2", n.krw_for("15", 39.2), "약 590원")
    eq("350@40.194", n.krw_for("350", 40.194), "약 1.41만 원")
    eq("13억678만@40.19", n.krw_for("13억678만", 40.19), "약 525억 원")
    eq("range", n.krw_for("300~500", 40.19), "약 1.21만~2.01만 원")
    # cny
    eq("cny70", n.cny_text(70), "70")
    eq("cny12345", n.cny_text(12345), "1.23万")
    eq("cny1.23e8", n.cny_text(123456789), "1.23亿")
    # money_check 수용
    def miss(text):
        return n.krw_missing({"id": "2026-10-28-am", "fx": {"THB_KRW": 39.2},
                             "briefing": [{"text": text}], "stories": []})
    eq("accept 590", miss("요금 15바트(약 590원)"), [])
    eq("accept 1.41만", miss("요금 350바트(약 1.41만 원)"), [])
    eq("accept range", miss("요금 300~500바트(약 1.21만~2.01만 원)"), [])
    eq("accept old", miss("요금 350바트(약 14,068원)"), [])
    eq("reject .5원", bool(miss("요금 15바트(약 588.5원)")), True)
    eq("flag missing", bool(miss("요금 15바트 인상")), True)
    # fix_money 경로(바트→원 붙이기)
    import gemini_edition as g
    # site is ko in tnk-opcom
    t = g._fix_text("입장료 15바트입니다", 39.2, "krw")
    eq("fix_text 15바트", t, "입장료 15바트(약 590원)입니다")
    t2 = g._fix_text("벌금 350바트", 40.194, "krw")
    eq("fix_text 350바트", t2, "벌금 350바트(약 1.41만 원)")
    if FAIL:
        print("\n%d FAILED" % FAIL)
        return 1
    print("\nALL OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
