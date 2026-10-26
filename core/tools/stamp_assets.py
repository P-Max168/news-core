# -*- coding: utf-8 -*-
"""정적 파일(assets/*.css|js, 아이콘, manifest) 내용 해시로 버전을 매겨
index.html 의 ?v= 와 sw.js 의 VERSION·SHELL_FILES 를 갱신한다(서비스 워커 캐시 교체용).
  python3 tools/stamp_assets.py      # 바뀐 게 있으면 파일 수정, 없으면 그대로
deploy.sh 가 커밋 전에 자동 실행한다. data/ 는 대상 아님(네트워크 우선이라 버전 불필요)."""
import hashlib, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ["assets/ads/campaign.js", "assets/style.css", "assets/topics.js", "assets/prefs.js", "assets/taste.js", "assets/adsafe.js", "assets/app.js", "assets/social.js", "assets/ticker.js", "assets/nearby.css", "assets/late.css", "assets/nearby.js", "assets/pages.js", "assets/places.js", "assets/jobs.js", "assets/ads/massage/dragon-ad.css", "assets/ads/massage/dragon-ad.js", "assets/modern.css", "assets/modern.js", "assets/g.css"]
# social.js 가 import() 하는 모듈(index.html 에 직접 없음): social.js 안의 FB_URL ?v= 를 먼저 갱신
MODULES = {"assets/fb.js": "assets/social.js", "assets/report.js": "assets/app.js", "assets/modern-icons.svg": "assets/modern.js"}   # modern.js 안의 아이콘 묶음 ?v=
EXTRA = ["manifest.json", "offline.html", "assets/ads/massage/dragon.svg"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "assets/icons").glob("*.png"))

EXTRA += sorted(str(p.relative_to(ROOT)) for p in (ROOT / "assets/ads/partners").glob("*") if p.is_file())


def h(paths):
    m = hashlib.sha256()
    for p in paths:
        m.update(p.encode()); m.update((ROOT / p).read_bytes())
    return m.hexdigest()[:10]


def main():
    html_p, sw_p = ROOT / "index.html", ROOT / "sw.js"
    html = html_p.read_text(encoding="utf-8")
    sw = sw_p.read_text(encoding="utf-8")
    changed = False
    for mod, host in MODULES.items():
        hp = ROOT / host
        src = hp.read_text(encoding="utf-8")
        new_src = re.sub(r'(%s)\?v=[0-9a-zA-Z]+' % re.escape(mod), r"\1?v=" + h([mod])[:8], src)
        if new_src != src:
            hp.write_text(new_src, encoding="utf-8"); changed = True
    new_html = html
    for a in ASSETS:
        v = h([a])[:8]
        new_html = re.sub(r'(%s)\?v=[0-9a-zA-Z]+' % re.escape(a), r"\1?v=" + v, new_html)
        sw = re.sub(r'("%s)\?v=[0-9a-zA-Z]+"' % re.escape(a), r'\1?v=%s"' % v, sw)
    # 앱 셸 전체 버전(index.html 의 정적 부분 포함)
    ver = "tnk-" + hashlib.sha256((new_html + h(ASSETS + list(MODULES) + EXTRA)).encode()).hexdigest()[:10]
    sw = re.sub(r'var VERSION = "[^"]*";', 'var VERSION = "%s";' % ver, sw)
    if new_html != html:
        html_p.write_text(new_html, encoding="utf-8"); changed = True
    if sw != sw_p.read_text(encoding="utf-8"):
        sw_p.write_text(sw, encoding="utf-8"); changed = True
    # index.html 의 ?v= 와 sw.js 목록이 일치하는지 확인
    for a in ASSETS:
        m1 = re.search(r'%s\?v=([0-9a-zA-Z]+)' % re.escape(a), new_html)
        m2 = re.search(r'"%s\?v=([0-9a-zA-Z]+)"' % re.escape(a), sw)
        assert m1 and m2 and m1.group(1) == m2.group(1), "index.html/sw.js 버전 불일치: " + a
    print("stamp:", ver, "(changed)" if changed else "(unchanged)")


if __name__ == "__main__":
    main()
