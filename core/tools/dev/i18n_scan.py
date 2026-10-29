# -*- coding: utf-8 -*-
"""화면 문구 목록(R-zh-1, 2026-10-18 Grok). 공유 코드의 TNI("key", "기본 문구")·index.html data-i18n 을 모아
i18n/ko.json(= 한국판 기본 문구, 코드에서 자동 생성 — 손으로 고치지 말 것)을 만들고, 언어판 i18n 파일에 빠진 키와
아직 TNI 로 빼지 않은 한글 문구 수(파일별)를 보여 준다.
    python3 tools/dev/i18n_scan.py                       # i18n/ko.json 갱신 + 요약
    python3 tools/dev/i18n_scan.py --lang zh --zh-root /workspace/tnk-zh-site   # zh 에 빠진 키 목록
"""
import html, argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = ["app.js", "topics.js", "ticker.js", "social.js", "pages.js", "places.js", "prefs.js", "taste.js", "report.js", "nearby.js", "jobs.js", "modern.js", "fb.js"]
TNI_RE = re.compile(r'\b(?:TNI|I|T)\(\s*"([\w.]+)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')
ATTR_RE = re.compile(r'<(\w+)\b[^>]*\sdata-i18n(?:-html)?="([\w.]+)"[^>]*>(.*?)</\1>', re.S)
ARIA_RE = re.compile(r'<\w+\b(?=[^>]*\sdata-i18n-aria="([\w.]+)")(?=[^>]*\saria-label="([^"]*)")[^>]*>')
STR_RE = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'')
HANGUL = re.compile(r"[가-힣]")


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", l) for l in src.splitlines())


def nest(flat):
    out = {}
    for k, v in sorted(flat.items()):
        d, ks = out, k.split(".")
        for x in ks[:-1]:
            d = d.setdefault(x, {})
            if not isinstance(d, dict):
                break
        else:
            d[ks[-1]] = v
    return out


def scan():
    keys, left = {}, {}
    for n in JS:
        p = ROOT / "assets" / n
        if not p.exists():
            continue
        # 'i18n:data' 표시 줄 = 데이터 값 비교·욕설 거르기 단어 등(화면 문구 아님) → 남은 문구 수에서 뺌(2026-10-18)
        raw = p.read_text(encoding="utf-8")
        data_lines = sum(1 for l in raw.splitlines() if "i18n:data" in l)
        src = strip_comments("\n".join(l for l in raw.splitlines() if "i18n:data" not in l))
        keys_src = strip_comments(raw)
        for k, v in TNI_RE.findall(keys_src):
            keys.setdefault(k, json.loads('"%s"' % v))
        for k, v in TNI_RE.findall(src):
            keys.setdefault(k, json.loads('"%s"' % v))
        rest = TNI_RE.sub("", src)
        left[n] = sum(1 for m in STR_RE.finditer(rest) if HANGUL.search(m.group(1) or m.group(2) or ""))
    t = (ROOT / "index.html").read_text(encoding="utf-8")
    for tag, k, inner in ATTR_RE.findall(t):
        keys.setdefault(k, re.sub(r"\s+", " ", inner).strip())
    for k, v in ARIA_RE.findall(t):
        keys.setdefault(k, html.unescape(v))
    body = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>|<head>.*?</head>", "", t, flags=re.S)
    body = ATTR_RE.sub("", body)
    left["index.html"] = len(set(re.findall(r">([^<>]*[가-힣][^<>]*)<", body)))
    return keys, left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang")
    ap.add_argument("--zh-root")
    a = ap.parse_args()
    keys, left = scan()
    keys.setdefault("_locale", "ko-KR")
    out = {"_note": "자동 생성(tools/dev/i18n_scan.py) — 한국판 화면 기본 문구. 언어판 i18n/<lang>.json 은 같은 키로 언어별 문구를 둔다(번역이 아니라 그 판 독자용 문구)."}
    out.update(nest(keys))
    (ROOT / "i18n" / "ko.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("i18n/ko.json: 키 %d개" % len(keys))
    print("아직 TNI 로 안 뺀 한글 문구(파일별): " + (", ".join("%s %d" % (k, v) for k, v in left.items() if v) or "0"))
    if a.lang:
        r = pathlib.Path(a.zh_root or ROOT)
        lp = r / "i18n" / ("%s.json" % a.lang)
        have = set()
        def walk(d, pre=""):
            for k, v in d.items():
                if isinstance(v, dict): walk(v, pre + k + ".")
                else: have.add(pre + k)
        walk(json.loads(lp.read_text(encoding="utf-8")))
        miss = sorted(k for k in keys if k not in have)
        print("%s 에 빠진 키 %d개%s" % (lp, len(miss), (": " + ", ".join(miss)) if miss else ""))
        return 1 if miss else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
