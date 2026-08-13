"""Generate the WinDorso app icon (assets/win_dorso.ico + assets/icon.png).

Style: minimalist Apple-like line art — pure white background, black
single-weight strokes of a seated side profile. Only two shapes: a
circle head and ONE continuous line (spine -> thigh -> shin -> foot),
so there are no stroke crossings to smudge.

Every .ico size is rendered separately at 8x supersampling with a
minimum stroke width, then downsampled — thin strokes stay solid and
crisp at 16-48 px instead of going gray.

Run with the project env:  python assets/make_icon.py
"""

from PIL import Image, ImageDraw

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
S = 1024
STROKE = 38                      # at 1024
MIN_STROKE_AT_TARGET = 2.0       # px, floors the stroke at small sizes

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# Seated side profile facing right. One continuous polyline starting
# inside the head circle so the round cap merges into it — no gaps.
_HEAD = (610, 250)
_HEAD_R = 90

# spine (two quadratic segments), then straight thigh / shin / foot
_BODY = [
    ((610, 340), (610, 430), (565, 510)),   # neck -> mid back
    ((565, 510), (535, 560), (520, 600)),   # mid back -> hip
    ((520, 600), (300, 610)),               # hip -> knee
    ((300, 610), (300, 820)),               # knee -> ankle
    ((300, 820), (400, 820)),               # ankle -> toe
]


def _bezier(p0, p1, p2, n=90):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        pts.append((x, y))
    return pts


def _body_points():
    pts = []
    for seg in _BODY:
        if len(seg) == 3:
            pts += _bezier(*seg)
        else:
            pts.append(seg[0])
            pts.append(seg[1])
    return pts


def _render(size: int) -> Image.Image:
    """Render one icon size at 8x supersampling with a floored stroke."""
    sc = 8 * size / S
    stroke = max(STROKE * sc, MIN_STROKE_AT_TARGET * 8)
    w = size * 8
    img = Image.new("RGBA", (w, w), WHITE)
    d = ImageDraw.Draw(img)

    hx, hy, hr = _HEAD[0] * sc, _HEAD[1] * sc, _HEAD_R * sc
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], outline=BLACK, width=int(stroke))

    pts = [(x * sc, y * sc) for x, y in _body_points()]
    d.line(pts, fill=BLACK, width=int(stroke), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def main():
    master = _render(S)
    master.save("assets/icon.png")  # 1024x1024 source
    icons = {s: _render(s) for s in ICO_SIZES}
    icons[256].save(
        "assets/win_dorso.ico",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=[icons[s] for s in ICO_SIZES if s != 256],
    )
    print("wrote assets/icon.png and assets/win_dorso.ico")


if __name__ == "__main__":
    main()
