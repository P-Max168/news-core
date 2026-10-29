# -*- coding: utf-8 -*-
"""화면 한글 문구를 TNI("파일.k<해시>", "기본 문구")로 감싸기(R-zh-1 마무리, 2026-10-18 Grok).
한국판은 TNI 가 기본 문구를 그대로 돌려주므로 화면·동작 변화 0. 언어판은 i18n/<lang>.json 에 같은 키로 문구를 둔다.
안 감싸는 것(로직·데이터 비교): 객체 키("…":), ===/!==/case 비교, indexOf/test/RegExp/split/replace 인자, [..] 색인, "use strict",
이미 TNI/I 인자인 것, 주석·템플릿 문자열·정규식.
    python3 tools/dev/i18n_wrap.py assets/app.js [...] [--dry]      # 감싼 수·안 감싼 목록(이유) 출력
키 = 파일 이름 + 'k' + sha1(문구)[:7] — 줄이 옮겨져도 같고, 문구가 바뀌면 키도 바뀌어(언어판에 없으면 한국어로 보임) i18n_scan 이 '빠진 키'로 알려 줌.
"""
import hashlib, json, pathlib, re, sys

HANGUL = re.compile(r"[가-힣]")
REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
CMP_BEFORE = re.compile(r"(===|!==|==|!=|\bcase|\bin)\s*$")
CMP_AFTER = re.compile(r"^\s*(===|!==|==|!=)")
FN_BEFORE = re.compile(r"\.(indexOf|lastIndexOf|includes|test|split|replace|replaceAll|startsWith|endsWith|match|search)\(\s*$|\bRegExp\(\s*$")
TNI_BEFORE = re.compile(r"\b(?:TNI|I|T)\(\s*(\"[\w.]+\"|[^()]*?)\s*,\s*$")


def tokens(src):
    """(kind, start, end) for strings; kinds: str. Skips comments, templates (but scans ${} code), regex."""
    i, n, out, stack = 0, len(src), [], []
    last = ""   # last significant char/word in code
    while i < n:
        c = src[i]
        if stack and stack[-1] == "tpl":
            if c == "\\": i += 2; continue
            if c == "`": stack.pop(); i += 1; last = "`"; continue
            if c == "$" and src[i+1:i+2] == "{": stack.append("code"); i += 2; last = "{"; continue
            i += 1; continue
        if c == "}" and stack and stack[-1] == "code":
            stack.pop(); i += 1; continue
        if c in " \t\r\n": i += 1; continue
        if src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2; continue
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\": j += 1
                if src[j] == "\n": break
                j += 1
            out.append((i, j + 1)); i = j + 1; last = '"'; continue
        if c == "`":
            stack.append("tpl"); i += 1; continue
        if c == "{" and stack:
            stack.append("code"); i += 1; last = "{"; continue
        if c == "/" and (last in REGEX_PREV or last in ("return", "typeof", "")):
            j, cls = i + 1, False
            while j < n:
                if src[j] == "\\": j += 2; continue
                if src[j] == "[": cls = True
                elif src[j] == "]": cls = False
                elif src[j] == "/" and not cls: break
                elif src[j] == "\n": break
                j += 1
            j += 1
            while j < n and src[j].isalpha(): j += 1
            i = j; last = "/re"; continue
        m = re.match(r"[A-Za-z_$][\w$]*", src[i:])
        if m:
            last = m.group(0); i += len(last); continue
        if re.match(r"[0-9.]", c):
            m = re.match(r"[0-9.xa-fA-FeE_n]+", src[i:]); last = "0"; i += len(m.group(0)); continue
        last = c; i += 1
    return out


def js_value(lit):
    q, body = lit[0], lit[1:-1]
    if q == "'":
        body = re.sub(r'(\\\\)|\\\'|"', lambda m: m.group(1) or ("'" if m.group(0) == "\\'" else '\\"'), body)
    return json.loads('"' + body + '"')


def classify(src, s, e):
    before, after = src[max(0, s - 200):s], src[e:e + 40]
    b = before.rstrip()
    if CMP_BEFORE.search(b) or CMP_AFTER.match(after): return "비교"
    if FN_BEFORE.search(b): return "검색/정규식"
    if TNI_BEFORE.search(b): return "이미 TNI"
    if re.match(r"^\s*:", after) and (b.endswith("{") or b.endswith(",")): return "객체 키"
    if b.endswith("[") and re.match(r"^\s*\]", after): return "색인"
    return None


def wrap(path, dry=False):
    p = pathlib.Path(path); src = p.read_text(encoding="utf-8")
    stem = p.stem
    reps, skipped = [], []
    for s, e in tokens(src):
        lit = src[s:e]
        if not HANGUL.search(lit): continue
        why = classify(src, s, e)
        if why:
            if why != "이미 TNI":
                skipped.append((src.count("\n", 0, s) + 1, why, lit[:70]))
            continue
        try:
            val = js_value(lit)
        except Exception as ex:
            skipped.append((src.count("\n", 0, s) + 1, "해석 실패 %s" % ex, lit[:70])); continue
        key = "%s.k%s" % (stem, hashlib.sha1(val.encode("utf-8")).hexdigest()[:7])
        reps.append((s, e, 'TNI("%s", %s)' % (key, json.dumps(val, ensure_ascii=False))))
    out = src
    for s, e, r in reversed(reps):
        out = out[:s] + r + out[e:]
    if not dry and reps:
        p.write_text(out, encoding="utf-8")
    print("%s: 감쌈 %d · 안 감쌈 %d" % (path, len(reps), len(skipped)))
    for ln, why, lit in skipped:
        print("   %s:%d [%s] %s" % (stem, ln, why, lit))
    return len(reps)


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    for f in [a for a in sys.argv[1:] if not a.startswith("--")]:
        wrap(f, dry)
