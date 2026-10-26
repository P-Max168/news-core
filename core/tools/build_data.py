# -*- coding: utf-8 -*-
"""판(edition) 생성 진입점.

  python3 tools/build_data.py tools/editions/2026-09-29-am.py   # 해당 판 json/js 저장 + index 갱신
  python3 tools/build_data.py                                   # index 만 다시 만들기

새 판을 만들 때는 tools/editions/<YYYY-MM-DD>-am.py (또는 -pm.py)를 새로 만들고
(기존 파일을 복사해 stories/briefing/highlights 교체; X 트렌드는 수집·생성하지 않음) 위 명령으로 실행한다.
파일 이름 규칙과 검증 규칙은 tools/newslib.py 참고.
"""
import sys, runpy, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import newslib

if len(sys.argv) > 1:
    runpy.run_path(sys.argv[1], run_name="__main__")
else:
    newslib.build_index()
