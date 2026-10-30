# -*- coding: utf-8 -*-
"""공유 코드 동기화(R-zh-4, 2026-10-18 Grok — 민구님 08:00 승인으로 Claude 대신).
한국판 저장소의 '정해진 커밋'에서 **공유 코드만** 언어판 저장소(작업 폴더)로 복사한다. 원칙: 시스템 공유·편집 기준 분리.

    python3 tools/dev/sync_core.py <한국판 커밋|HEAD> <언어판 저장소 폴더> [--dry]
    (보통은 bash tools/dev/sync_core.sh — 같은 인자)

복사(공유): index.html 404.html offline.html sw.js manifest.json firestore.rules .gitignore assets/ tools/(아래 제외) i18n/ko.json
            .github/workflows/edition-watch.yml
안 건드림(언어별): data/ e/ og/ share/ site/(LANG·<lang>.json·topics.<lang>.json) i18n/<lang>.json CNAME robots.txt sitemap.xml
            collab/ *.md(문서) tools/editions/ tools/discussions/ tools/sources*.json tools/TRANSLATION_RULES*.md tools/DISCUSSION_PERSONA*.md
            tools/issues.json tools/places/ tools/rentals/ tools/fetch_china.py(언어판 수집기) .github/workflows/(korea.yml·china.yml 등)
지우기: 공유 경로(assets/·tools/) 안에서 한국판에 없어진 파일은 지움(언어별 보호 목록은 안 지움).
끝나면 언어판 폴더에서 tools/site_build.py 를 돌려 화면에 언어를 입히고, .core-version 에 한국판 커밋을 적는다.
git commit·push 는 하지 않는다(언어판 ship.sh 로).
"""
import fnmatch, io, os, pathlib, subprocess, sys, tarfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHARED_FILES = ["index.html", "404.html", "offline.html", "sw.js", "manifest.json", "firestore.rules", ".gitignore", "i18n/ko.json"]
# .github/ 는 언어별(zh 는 china.yml·edition-watch 일정 끔 — 13:00 빌드 루틴 전까지). 2026-10-18 Grok
SHARED_DIRS = ["assets/", "tools/"]
PROTECT = ["tools/editions/*", "tools/discussions/*", "tools/sources*.json", "tools/TRANSLATION_RULES*.md", "tools/DISCUSSION_PERSONA*.md",
           "tools/issues.json", "tools/places/*", "tools/rentals/*", "tools/fetch_china.py", "tools/fetch_*_home.py", "tools/__pycache__/*",
           "tools/dev/__pycache__/*", "assets/ads/*/zh*", "assets/ads/*.zh.*"]


def prot(rel):
    return any(fnmatch.fnmatch(rel, p) for p in PROTECT)


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    dry = "--dry" in sys.argv
    if len(a) != 2:
        sys.exit(__doc__)
    rev, dst = a[0], pathlib.Path(a[1]).resolve()
    if dst == ROOT or not (dst / "site" / "LANG").exists():
        sys.exit("대상이 언어판 저장소가 아님(site/LANG 없음 또는 한국판 자신): %s" % dst)
    lang = (dst / "site" / "LANG").read_text().strip()
    if lang == "ko":
        sys.exit("대상 site/LANG = ko — 한국판에는 동기화하지 않음")
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", rev], text=True).strip()
    tar = tarfile.open(fileobj=io.BytesIO(subprocess.check_output(["git", "-C", str(ROOT), "archive", sha])))
    src = {}
    for m in tar.getmembers():
        if m.isfile():
            rel = m.name
            if rel in SHARED_FILES or (any(rel.startswith(d) for d in SHARED_DIRS) and not prot(rel)):
                src[rel] = tar.extractfile(m).read()
    changed = added = removed = 0
    for rel, data in sorted(src.items()):
        p = dst / rel
        if p.exists() and p.read_bytes() == data:
            continue
        if p.exists(): changed += 1
        else: added += 1
        if not dry:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
    for d in SHARED_DIRS:
        for p in (dst / d).rglob("*"):
            rel = p.relative_to(dst).as_posix()
            if p.is_file() and rel not in src and not prot(rel):
                removed += 1
                print("지움(한국판에 없음):", rel)
                if not dry:
                    p.unlink()
    print("sync_core: 한국판 %s → %s(%s) · 바뀜 %d · 새로 %d · 지움 %d%s" % (sha, dst, lang, changed, added, removed, " (--dry, 안 씀)" if dry else ""))
    if not dry:
        (dst / ".core-version").write_text(sha + "\n")
        subprocess.check_call([sys.executable, str(dst / "tools" / "site_build.py"), "--root", str(dst)], env=dict(os.environ, TNK_LANG=lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
