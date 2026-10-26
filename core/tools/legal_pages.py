#!/usr/bin/env python3
"""안내 문서(개인정보 처리방침·이용약관·소개·연락) 정적 페이지 생성 — 2026-10-03 애드센스 준비.
지금은 '초안'(운영자 확인 전). 본문을 고치려면 이 파일의 PAGES 를 고치고 `python3 tools/legal_pages.py` 실행.
[대괄호] 칸 = 운영자가 정할 값(PENDING_APPROVAL.md 참고). DRAFT=False 로 바꾸면 초안 띠가 사라짐(운영자 승인 뒤)."""
import os, html
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = True
UPDATED = "2026-10-03"
SITE = "태국 뉴스 한눈에"

# 초안 띠 아이콘 = assets/modern-icons.svg 의 Lucide pen-line(예전 📝 이모지 대신, 2026-10-05)
DRAFT_ICON = ('<svg class="ic" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 21h8" /><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z" /></svg>')
CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;font:16px/1.7 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;color:#191F28;background:#F2F4F6;word-break:keep-all;overflow-wrap:anywhere}
header{background:#fff;color:#191F28;padding:12px 16px;padding-top:max(12px,env(safe-area-inset-top));box-shadow:0 1px 0 rgba(0,0,0,.05)}
header a{color:#191F28;text-decoration:none;font-weight:700}
main{max-width:720px;margin:0 auto;padding:16px 16px 40px}
.draft{background:#fff;border-radius:14px;padding:12px 16px;font-size:.875rem;margin:0 0 14px;color:#4E5968;display:flex;gap:8px;align-items:flex-start;line-height:1.5}
.draft .ic{flex:0 0 auto;margin-top:3px;color:#8B95A1}
h1{font-size:1.5rem;line-height:1.35;margin:6px 0 4px;letter-spacing:-.5px}
.upd{color:#5F6B7A;font-size:.875rem;margin:0 0 16px}
section{background:#fff;border-radius:16px;padding:18px 18px;margin:0 0 12px}
h2{font-size:1.125rem;margin:0 0 6px;letter-spacing:-.3px}
ul{padding-left:1.2em;margin:6px 0;color:#333D4B}
li{margin:3px 0}
.ph{background:#F2F4F6;border-radius:6px;padding:0 4px;font-weight:600}
nav.more{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:16px}
nav.more a{display:flex;align-items:center;justify-content:center;min-height:48px;background:#fff;border:0;border-radius:12px;color:#191F28;text-decoration:none;font-weight:600;text-align:center;padding:6px}
nav.more a[aria-current]{background:#1B64DA;color:#fff}
a{color:#1B64DA}
"""

def ph(s):  # 운영자가 정할 칸
    return '<span class="ph">[' + html.escape(s) + ']</span>'

CONTACT = ph("연락 이메일 — 운영자가 정할 주소(개인 메일 대신 사이트 전용 주소 권장)")
OPERATOR = ph("운영자 표시 이름")

PAGES = [
 ("privacy.html", "개인정보 처리방침", [
  ("한눈에", "<ul><li>로그인하지 않으면 이 사이트는 <b>이름·이메일·전화번호를 받지 않습니다</b>. 설정은 이 기기 브라우저에만 저장됩니다.</li><li>로그인(선택)하면 Google 계정의 고유 번호(UID)로 설정·취향을 다른 기기와 맞춥니다.</li><li>하트·🙌·🙅 반응은 <b>누가 눌렀는지 빼고</b> 기사별 숫자로만 모읍니다.</li></ul>"),
  ("1. 이 기기에만 저장되는 정보(브라우저 저장소)", "<ul><li>고른 페르소나·주제, 👍👎·🙌🙅·❤️ 반응, 화면 설정(날씨 지역, 내 주변 마지막 분류 등).</li><li>서버로 보내지 않으며, 브라우저의 사이트 데이터 지우기로 언제든 지울 수 있습니다. ☰ 메뉴 → 설정 → '내 취향 초기화'도 있습니다.</li></ul>"),
  ("2. 로그인(선택) 시 저장되는 정보", "<ul><li>Google 로그인은 Google(Firebase Authentication)이 처리합니다. 이 사이트는 비밀번호를 받지 않습니다.</li><li>Firebase(Google Cloud, 싱가포르 지역)에 계정 UID 기준으로 저장: 주제·페르소나·취향 점수, 댓글 닉네임, 쓴 댓글(닉네임·내용·시각).</li><li>계정 메뉴에서 로그아웃할 수 있습니다. 저장된 정보 삭제를 원하면 아래 연락처로 요청해 주세요 — "+ph("처리 기한 — 운영자 확인")+" 안에 지웁니다.</li></ul>"),
  ("3. 익명 반응 집계", "<ul><li>하트·🙌·🙅 를 누르거나 취소하면 <b>기사 번호, 반응 종류, 대략의 사는 곳(예: 동부), 관심 분야, 기사 주제, 시각</b>만 기록해 어떤 기사가 도움이 됐는지 봅니다.</li><li>UID·이름·이메일·기기 정보·정확한 위치는 함께 저장하지 않습니다. 사는 곳·관심은 고른 페르소나·주제에서 짐작한 값입니다.</li><li>"+ph("시작일 — 운영자 승인 뒤 표시. 지금은 이 기기에만 쌓이고 보내지 않음")+"</li></ul>"),
  ("4. 위치", "<ul><li>📍 내 주변에서 지도 버튼을 누를 때만 브라우저가 위치 권한을 묻습니다. 좌표는 Google 지도 주소를 만드는 데만 쓰고 저장하거나 보내지 않습니다.</li><li>날씨 칩은 고른 지역(파타야·시라차·방콕)의 공개 좌표로 Open-Meteo 에서 날씨를 받아 옵니다.</li></ul>"),
  ("5. 외부 서비스", "<ul><li>Google Firebase(로그인·동기화·댓글·반응 집계), Open-Meteo(날씨·대기질), Google 지도(링크를 누를 때만), 기사 원문 사이트(링크를 누를 때만).</li><li>광고: 지금은 사이트가 직접 넣은 광고(제휴 업체 소개)만 있습니다. "+ph("Google AdSense 등 광고 네트워크를 쓰게 되면 — 쿠키 사용, 맞춤 광고 끄는 방법(Google 광고 설정) 안내 문단을 이 자리에 추가")+"</li></ul>"),
  ("6. 아이·연락", "<ul><li>이 사이트는 만 14세 미만을 대상으로 하지 않습니다.</li><li>개인정보 관련 문의: "+CONTACT+"</li><li>방침이 바뀌면 이 페이지의 날짜를 고치고 사이트에 알립니다.</li></ul>"),
 ]),
 ("terms.html", "이용약관", [
  ("1. 서비스", "<ul><li>"+SITE+"은(는) 태국 언론 보도를 한국어로 <b>짧게 요약</b>하고 원문 링크를 붙여 보여 주는 개인 프로젝트입니다. 무료이며, 회원 가입 없이 쓸 수 있습니다.</li></ul>"),
  ("2. 기사 내용과 저작권", "<ul><li>요약·번역문은 이 사이트가 직접 쓴 글입니다. 기사 원문·사진의 저작권은 각 언론사에 있으며, 이 사이트는 원문 전체나 사진을 옮겨 싣지 않습니다.</li><li>요약은 이해를 돕기 위한 것이라 틀리거나 빠진 내용이 있을 수 있습니다. 비자·법·건강·돈 문제는 반드시 원문과 공식 기관(대사관·이민국 등)에서 확인하세요.</li><li>잘못된 요약이나 저작권 문제는 아래 연락처로 알려 주시면 확인 후 고치거나 내립니다.</li></ul>"),
  ("3. 댓글", "<ul><li>댓글은 Google 로그인 후 쓸 수 있고, 쓴 사람이 책임집니다.</li><li>욕설·비방·개인정보 노출·광고·불법 내용은 알림 없이 숨길 수 있습니다. 신고가 3번 쌓이면 자동으로 숨겨집니다.</li></ul>"),
  ("4. 광고와 업체 소개", "<ul><li>'광고' 표시가 있는 칸은 광고입니다. 업체 정보(시간·위치 등)는 바뀔 수 있으니 방문 전에 확인하세요. 이 사이트는 업체와 이용자 사이의 거래에 책임지지 않습니다.</li></ul>"),
  ("5. 책임의 한계·변경", "<ul><li>서비스는 있는 그대로 제공되며, 예고 없이 바뀌거나 멈출 수 있습니다.</li><li>약관이 바뀌면 이 페이지의 날짜를 고칩니다. 운영자: "+OPERATOR+" · 연락: "+CONTACT+"</li></ul>"),
 ]),
 ("about.html", "소개", [
  ("이 사이트는", "<ul><li>태국에 사는 한국인과 여행자를 위해, 태국 언론의 주요 뉴스를 하루 두 번(아침·저녁판) 한국어로 짧게 정리합니다.</li><li>기사마다 출처 언론사와 원문 링크를 붙입니다. 한인 생활에 주는 영향(비자·안전·물가 등)을 따로 표시합니다.</li></ul>"),
  ("어떻게 만드나요", "<ul><li>여러 태국 언론(영문·태국어)의 공개 기사를 읽고 요약합니다. 요약 작성에 AI 도구의 도움을 받으며, 운영자가 정한 규칙에 따라 출처를 확인합니다.</li><li>사진은 싣지 않습니다. 원문 전체를 옮기지 않습니다.</li></ul>"),
  ("운영", "<ul><li>운영자: "+OPERATOR+"</li><li>연락: "+CONTACT+"</li></ul>"),
 ]),
 ("contact.html", "연락하기", [
  ("문의·제보", "<ul><li>이메일: "+CONTACT+"</li><li>잘못된 요약 신고, 저작권 문의, 광고·업체 소개 문의, 개인정보 삭제 요청을 받습니다.</li><li>기사 내용에 대한 의견은 기사 아래 💬 댓글로 남겨도 됩니다(로그인 필요).</li></ul>"),
  ("답변", "<ul><li>"+ph("보통 답변까지 걸리는 기간 — 운영자 확인")+"</li></ul>"),
 ]),
]

# 검색 설명(2026-10-18 키워드 정리) — 화면에는 안 보임
DESC = {"about.html": "태국 뉴스 한눈에 소개 — 태국 현지 언론 보도를 매일 아침 7시·저녁 6시 한국어로 정리하는 태국 교민·여행자용 뉴스예요. 만드는 방식과 운영 원칙을 안내해요.",
        "contact.html": "태국 뉴스 한눈에 연락하기 — 잘못된 요약 신고, 제보, 저작권·광고·개인정보 문의 방법을 안내해요.",
        "privacy.html": "태국 뉴스 한눈에 개인정보 처리방침 — 기기에만 저장되는 정보, 로그인할 때 저장되는 정보, 위치·외부 서비스와 삭제 요청 방법을 안내해요.",
        "terms.html": "태국 뉴스 한눈에 이용약관 — 서비스 범위, 기사 요약과 저작권, 댓글 규칙, 광고·업체 소개 기준을 안내해요."}

NAV = [("privacy.html", "개인정보 처리방침"), ("terms.html", "이용약관"), ("about.html", "소개"), ("contact.html", "연락하기")]

def render(fn, title, secs):
    nav = "".join('<a href="%s"%s>%s</a>' % (f, ' aria-current="page"' if f == fn else "", t) for f, t in NAV)
    body = "".join("<section><h2>%s</h2>%s</section>" % (html.escape(h), b) for h, b in secs)
    draft = '<p class="draft">%s<span><b>초안</b>이에요 — 운영자 확인 전이라 [대괄호] 칸은 아직 정해지지 않았어요.</span></p>' % DRAFT_ICON if DRAFT else ""
    return """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://tnews.pmaxone.com/%s">
<meta name="theme-color" content="#ffffff">
<title>%s · %s</title>
<meta name="description" content="%s">
<link rel="icon" href="assets/icons/icon-192.png">
<style>%s</style>
<link rel="stylesheet" href="/assets/g-pages.css?v=1">
</head>
<body>
<header><a href="./">← %s</a></header>
<main>
%s<h1>%s</h1>
<p class="upd">마지막 수정: %s</p>
%s
<nav class="more" aria-label="안내 문서">%s</nav>
</main>
</body>
</html>
""" % (fn, html.escape(title), SITE, html.escape(DESC.get(fn, SITE)), CSS.strip(), SITE, draft, html.escape(title), UPDATED, body, nav)

if __name__ == "__main__":
    for fn, title, secs in PAGES:
        open(os.path.join(ROOT, fn), "w", encoding="utf-8").write(render(fn, title, secs))
        print("wrote", fn)
