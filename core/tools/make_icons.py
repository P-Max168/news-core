# -*- coding: utf-8 -*-
"""PWA 아이콘 생성(헤더의 태국 국기 로고와 같은 모양). python3 tools/make_icons.py
assets/icons/: icon-192.png, icon-512.png(any), maskable-512.png, maskable-192.png, apple-touch-icon.png(180), favicon-32.png"""
import pathlib
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icons"
NAVY = (11, 42, 74, 255)
RED, WHITE, BLUE = (239, 51, 64, 255), (255, 255, 255, 255), (45, 42, 110, 255)


def flag(size):
    """둥근 모서리 국기(헤더 .brand__mark: 40px, radius 11px)."""
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bands = [(0, 1, RED), (1, 2, WHITE), (2, 4, BLUE), (4, 5, WHITE), (5, 6, RED)]
    for a, b, c in bands:
        d.rectangle([0, round(S * a / 6), S, round(S * b / 6)], fill=c)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=round(S * 11 / 40), fill=255)
    im.putalpha(mask)
    return im.resize((size, size), Image.LANCZOS)


def icon(size, flag_ratio, rounded_bg, path):
    S = size * 4
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    if rounded_bg:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=round(S * 0.22), fill=NAVY)
    else:
        d.rectangle([0, 0, S, S], fill=NAVY)
    f = round(S * flag_ratio)
    # 헤더처럼 옅은 흰 테두리
    ring = round(S * 0.012) or 1
    d.rounded_rectangle([(S - f) // 2 - ring, (S - f) // 2 - ring, (S + f) // 2 + ring, (S + f) // 2 + ring],
                        radius=round(f * 11 / 40) + ring, fill=(255, 255, 255, 60))
    bg.alpha_composite(flag(f), ((S - f) // 2, (S - f) // 2))
    bg.resize((size, size), Image.LANCZOS).save(path, optimize=True)
    print("saved", path.name, size)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192, 0.66, True, OUT / "icon-192.png")
    icon(512, 0.66, True, OUT / "icon-512.png")
    icon(512, 0.52, False, OUT / "maskable-512.png")   # 안전 영역(지름 80%) 안에 국기
    icon(192, 0.52, False, OUT / "maskable-192.png")
    icon(180, 0.62, False, OUT / "apple-touch-icon.png")  # iOS 가 모서리를 둥글게 깎음
    flag(32).save(OUT / "favicon-32.png", optimize=True); print("saved favicon-32.png")
