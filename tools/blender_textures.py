"""Procedural facade / roof textures for the Blender landmark models.

Run with the project venv:  .venv\\Scripts\\python.exe tools\\blender_textures.py
Writes data/blender/textures/*.jpg (all <= 1024 px). Image bottom = UV v 0 = bottom of a floor/facade.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "blender" / "textures"
FONTS = Path("C:/Windows/Fonts")
rng = np.random.default_rng(7)


def hexc(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def noise(img: Image.Image, amp: float = 6, blur: float = 0.0) -> Image.Image:
    a = np.asarray(img).astype(np.float32)
    n = rng.normal(0, amp, a.shape[:2])[..., None]
    if blur:
        n = np.asarray(Image.fromarray(np.clip(n[..., 0] + 128, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(blur))).astype(np.float32)[..., None] - 128
    return Image.fromarray(np.clip(a + n, 0, 255).astype(np.uint8))


def vgrad(d: ImageDraw.ImageDraw, box, top: str, bot: str) -> None:
    x0, y0, x1, y1 = box
    c0, c1 = np.array(hexc(top)), np.array(hexc(bot))
    for y in range(int(y0), int(y1)):
        t = (y - y0) / max(1, (y1 - y0 - 1))
        d.line([(x0, y), (x1 - 1, y)], fill=tuple(int(v) for v in c0 * (1 - t) + c1 * t))


def window(d, box, glass_top="#4f6a80", glass_bot="#2f4458", frame="#e6e6e2", fw=3, mullion=True, transom=None):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=hexc(frame))
    vgrad(d, (x0 + fw, y0 + fw, x1 - fw + 1, y1 - fw + 1), glass_top, glass_bot)
    if mullion:
        xm = (x0 + x1) // 2
        d.rectangle((xm - fw // 2, y0, xm + fw // 2, y1), fill=hexc(frame))
    if transom:
        yt = int(y0 + (y1 - y0) * transom)
        d.rectangle((x0, yt - fw // 2, x1, yt + fw // 2), fill=hexc(frame))


def arch_window(d, box, glass_top="#5a7388", glass_bot="#2f4458", frame="#f3eee2", fw=4):
    x0, y0, x1, y1 = box
    r = (x1 - x0) / 2
    d.rectangle((x0, y0 + r, x1, y1), fill=hexc(frame))
    d.ellipse((x0, y0, x1, y0 + 2 * r), fill=hexc(frame))
    gx0, gx1 = x0 + fw, x1 - fw
    gr = (gx1 - gx0) / 2
    vgrad(d, (gx0, y0 + fw + gr, gx1 + 1, y1 - fw + 1), glass_top, glass_bot)
    d.ellipse((gx0, y0 + fw, gx1, y0 + fw + 2 * gr), fill=hexc(glass_top))
    xm = (x0 + x1) // 2
    d.rectangle((xm - fw // 2, y0 + r, xm + fw // 2, y1), fill=hexc(frame))
    d.rectangle((x0, y0 + r - fw // 2, x1, y0 + r + fw // 2), fill=hexc(frame))


def _pot(n: int) -> int:
    return min(2048, 1 << max(0, round(np.log2(n))))


def save(img: Image.Image, name: str, q: int = 88) -> None:
    """Saved at power-of-two size (UVs are normalised, so the resample does not change the mapping)."""
    OUT.mkdir(parents=True, exist_ok=True)
    w, h = img.size
    if (_pot(w), _pot(h)) != (w, h):
        img = img.resize((_pot(w), _pot(h)), Image.Resampling.LANCZOS)
    img.convert("RGB").save(OUT / name, quality=q)
    print("wrote", name, img.size)


# ---------------------------------------------------------------- 气象楼 -----
def qx_facade():
    """1 bay (3.4 m) x 1 floor: white wall, grey-blue window."""
    s = 256
    im = Image.new("RGB", (s, s), hexc("#f1f0eb"))
    d = ImageDraw.Draw(im)
    d.rectangle((0, s - 14, s, s), fill=hexc("#e3e2dc"))  # floor band
    window(d, (40, 50, 216, 196), frame="#d8d9d6", transom=0.3)
    d.line([(40, 50), (216, 50)], fill=hexc("#c9c9c4"), width=3)
    save(noise(im, 3), "qx_facade.jpg")


def glass_curtain(name="glass_blue.jpg", top="#86b3d8", bot="#3b6c9c", mull="#cfd8e0", spandrel="#2f5478"):
    s = 256
    im = Image.new("RGB", (s, s))
    d = ImageDraw.Draw(im)
    vgrad(d, (0, 0, s, s), top, bot)
    d.rectangle((0, s - 34, s, s), fill=hexc(spandrel))
    for x in (0, s // 2, s - 1):
        d.rectangle((x - 3, 0, x + 3, s), fill=hexc(mull))
    d.rectangle((0, s - 36, s, s - 32), fill=hexc(mull))
    d.rectangle((0, 0, s, 3), fill=hexc(mull))
    save(noise(im, 2), name)


def radome():
    """White radome with faint geodesic panel lines (equirect)."""
    w, h = 512, 256
    im = Image.new("RGB", (w, h), hexc("#f4f5f6"))
    d = ImageDraw.Draw(im)
    for i in range(0, w, 32):
        d.line([(i, 0), (i, h)], fill=hexc("#d5d9dc"), width=2)
    for j in range(0, h, 28):
        off = 16 if (j // 28) % 2 else 0
        d.line([(0, j), (w, j)], fill=hexc("#d5d9dc"), width=2)
        for i in range(off, w, 32):
            d.line([(i, j), (i + 16, j + 28)], fill=hexc("#dfe2e4"), width=1)
    save(im, "radome.jpg")


# --------------------------------------------------------------- 图书馆 ------
def classical(name, wall, bay_px, floors, arch_top=True, glass=("#566c7e", "#2c3d4d"), trim="#f6f1e6", groove="#d5c6ab"):
    """Span texture: 1 bay wide, whole facade high (bottom = ground, top = cornice).
    floors: list of floor heights (m); last one gets arched windows. 64 px per metre."""
    ppm = 52
    H = int(sum(floors) * ppm) + int(1.3 * ppm)
    W = bay_px
    im = Image.new("RGB", (W, H), hexc(wall))
    d = ImageDraw.Draw(im)
    # cornice (top 1.3 m)
    d.rectangle((0, 0, W, int(1.3 * ppm)), fill=hexc(trim))
    d.rectangle((0, int(1.0 * ppm), W, int(1.3 * ppm)), fill=hexc(groove))
    d.rectangle((0, int(0.35 * ppm), W, int(0.45 * ppm)), fill=hexc(groove))
    y = H
    pil = max(10, W // 11)
    for i, fh in enumerate(floors):
        top = y - int(fh * ppm)
        if i == 0:  # rusticated base
            for gy in range(top, y, int(0.55 * ppm)):
                d.line([(0, gy), (W, gy)], fill=hexc(groove), width=3)
            d.rectangle((0, top, W, top + 8), fill=hexc(trim))
            wx0, wx1 = int(W * 0.24), int(W * 0.76)
            arch_window(d, (wx0, top + int(0.5 * ppm), wx1, y - int(0.15 * ppm)), *glass, frame=trim)
        else:
            d.rectangle((0, top, pil, y), fill=hexc(trim))
            d.rectangle((W - pil, top, W, y), fill=hexc(trim))
            wx0, wx1 = int(W * 0.28), int(W * 0.72)
            wy0, wy1 = top + int(0.55 * ppm), y - int(0.75 * ppm)
            if i == len(floors) - 1 and arch_top:
                arch_window(d, (int(W * 0.3), wy0 - int(0.2 * ppm), int(W * 0.7), wy1), *glass, frame=trim)
            else:
                d.rectangle((wx0 - 6, wy0 - 6, wx1 + 6, wy1 + 6), fill=hexc(trim))
                window(d, (wx0, wy0, wx1, wy1), *glass, frame=trim, fw=4, transom=0.28)
                d.polygon([(wx0 - 10, wy0 - 6), (wx1 + 10, wy0 - 6), ((wx0 + wx1) // 2, wy0 - 22)], fill=hexc(trim)) if i % 2 else \
                    d.rectangle((wx0 - 10, wy0 - 16, wx1 + 10, wy0 - 6), fill=hexc(trim))
                d.rectangle((wx0 - 8, wy1 + 6, wx1 + 8, wy1 + 14), fill=hexc(trim))
            d.line([(0, y - 2), (W, y - 2)], fill=hexc(groove), width=4)
        y = top
    save(noise(im, 3), name)


def slate(name="slate.jpg", base="#3e4f68", line="#2f3d52"):
    s = 256
    im = Image.new("RGB", (s, s), hexc(base))
    d = ImageDraw.Draw(im)
    for k, y in enumerate(range(0, s, 16)):
        d.line([(0, y), (s, y)], fill=hexc(line), width=2)
        off = 8 if k % 2 else 0
        for x in range(off, s, 16):
            d.line([(x, y), (x, y + 16)], fill=hexc(line), width=1)
    save(noise(im, 5), name)


def metal_roof(name="metal_roof.jpg", base="#6e7f91", seam="#93a3b2"):
    s = 256
    im = Image.new("RGB", (s, s), hexc(base))
    d = ImageDraw.Draw(im)
    for x in range(0, s, 32):
        d.rectangle((x, 0, x + 3, s), fill=hexc(seam))
        d.rectangle((x + 4, 0, x + 5, s), fill=hexc("#5b6b7c"))
    save(noise(im, 3), name)


def clock():
    s = 256
    im = Image.new("RGB", (s, s), hexc("#2e4366"))
    d = ImageDraw.Draw(im)
    c, r = s / 2, s / 2 - 6
    d.ellipse((c - r, c - r, c + r, c + r), fill=hexc("#c9a24e"))
    r2 = r - 10
    d.ellipse((c - r2, c - r2, c + r2, c + r2), fill=hexc("#f7f5ee"))
    import math
    for k in range(12):
        a = math.radians(k * 30)
        r0, r1 = r2 - (22 if k % 3 == 0 else 14), r2 - 4
        d.line([(c + r0 * math.sin(a), c - r0 * math.cos(a)), (c + r1 * math.sin(a), c - r1 * math.cos(a))],
               fill=hexc("#1d1d1d"), width=6 if k % 3 == 0 else 4)
    for ang, ln, w in ((-60, r2 * 0.5, 9), (60, r2 * 0.75, 6)):  # 10:10
        a = math.radians(ang)
        d.line([(c, c), (c + ln * math.sin(a), c - ln * math.cos(a))], fill=hexc("#1d1d1d"), width=w)
    d.ellipse((c - 8, c - 8, c + 8, c + 8), fill=hexc("#1d1d1d"))
    save(im, "clock.jpg", 92)


# --------------------------------------------------------------- 临江楼 ------
def lj_tower():
    """1 bay (3 m) x 1 floor (3.8 m): light grey vertical fins + dark glass."""
    W, H = 192, 243
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    vgrad(d, (0, 0, W, H), "#5f7486", "#34485a")
    d.rectangle((0, H - 30, W, H), fill=hexc("#c7ccd0"))
    for x in (0, W // 2):
        d.rectangle((x, 0, x + 22, H), fill=hexc("#eef0f1"))
        d.rectangle((x + 22, 0, x + 30, H), fill=hexc("#aeb5ba"))
    save(noise(im, 2), "lj_tower.jpg")


def lj_podium():
    """6 m bay x 4 m floor: white wall with ribbon window."""
    W, H = 384, 256
    im = Image.new("RGB", (W, H), hexc("#f1f2ef"))
    d = ImageDraw.Draw(im)
    y0, y1 = int(H * 0.18), int(H * 0.68)
    vgrad(d, (0, y0, W, y1), "#6b8090", "#3b4d5b")
    for x in range(0, W, W // 4):
        d.rectangle((x, y0, x + 5, y1), fill=hexc("#dfe3e5"))
    d.rectangle((0, y1, W, y1 + 6), fill=hexc("#d6d8d6"))
    save(noise(im, 2), "lj_podium.jpg")


# --------------------------------------------------------------- 体育馆 ------
def gym():
    W = H = 256  # 6 m x 6 m
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    vgrad(d, (0, 0, W, H), "#a9c2d1", "#6c8ca2")
    for x in (0, W // 3, 2 * W // 3, W - 1):
        d.rectangle((x - 4, 0, x + 4, H), fill=hexc("#d8dcdf"))
    for y in (0, H // 2, H - 1):
        d.rectangle((0, y - 4, W, y + 4), fill=hexc("#d8dcdf"))
    save(noise(im, 2), "gym_glass.jpg")
    im = Image.new("RGB", (W, H), hexc("#c9cdd0"))  # 3 m x 3 m louvered panel
    d = ImageDraw.Draw(im)
    for y in range(0, H, 16):
        d.rectangle((0, y, W, y + 5), fill=hexc("#9fa5aa"))
    for x in (0, W // 2):
        d.rectangle((x, 0, x + 3, H), fill=hexc("#8c9297"))
    save(noise(im, 3), "gym_panel.jpg")


# --------------------------------------------------------------- 见山园 ------
def js_wall():
    """2.5 m bay x 3 m: white wall with a full-height slit window."""
    W, H = 160, 192
    im = Image.new("RGB", (W, H), hexc("#f3f3ef"))
    d = ImageDraw.Draw(im)
    x0, x1 = 58, 102
    vgrad(d, (x0, 0, x1, H), "#56687a", "#3a4a5a")
    d.rectangle((x0, 0, x0 + 3, H), fill=hexc("#cfd3d6"))
    d.rectangle((x1 - 3, 0, x1, H), fill=hexc("#cfd3d6"))
    d.rectangle((x0, H - 4, x1, H), fill=hexc("#cfd3d6"))
    save(noise(im, 2), "js_wall.jpg")


# ----------------------------------------------------------------- 老校门 -----
def gate():
    s = 256  # brown-red tile, 2 m
    im = Image.new("RGB", (s, s), hexc("#9a5a3d"))
    d = ImageDraw.Draw(im)
    for y in range(0, s, 32):
        d.line([(0, y), (s, y)], fill=hexc("#7b4430"), width=3)
        off = 32 if (y // 32) % 2 else 0
        for x in range(off, s, 64):
            d.line([(x, y), (x, y + 32)], fill=hexc("#7b4430"), width=3)
    save(noise(im, 7), "brick_red.jpg")
    # inscription beam: 13.8 m x 2.2 m
    W, H = 1024, 164
    im = noise(Image.new("RGB", (W, H), hexc("#bdb6a6")), 8, 1.2)
    d = ImageDraw.Draw(im)
    text = "南京气象学院"
    for fname in ("STXINGKA.TTF", "STKAITI.TTF", "simkai.ttf", "msyh.ttc"):
        p = FONTS / fname
        if p.exists():
            font = ImageFont.truetype(str(p), 112)
            break
    else:
        font = ImageFont.load_default()
    step = W / (len(text) + 0.6)
    for i, ch in enumerate(text):
        bb = d.textbbox((0, 0), ch, font=font)
        cx = step * (i + 0.8)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], H / 2 - (bb[3] - bb[1]) / 2 - bb[1]), ch, font=font, fill=hexc("#1e1c1a"))
    d.rectangle((0, 0, W, 5), fill=hexc("#a39c8c"))
    d.rectangle((0, H - 6, W, H), fill=hexc("#a39c8c"))
    save(im, "gate_beam.jpg", 92)


def ring_sign():
    """气象楼 rooftop ring: white lattice band with 南京信息工程大学 twice around (2048 x 128)."""
    W, H = 2048, 128
    im = Image.new("RGB", (W, H), hexc("#f2f3f4"))
    d = ImageDraw.Draw(im)
    for x in range(-H, W, 24):
        d.line([(x, 0), (x + H, H)], fill=hexc("#d3d8dc"), width=2)
        d.line([(x + H, 0), (x, H)], fill=hexc("#d3d8dc"), width=2)
    d.rectangle((0, 0, W, 6), fill=hexc("#c9ced2"))
    d.rectangle((0, H - 6, W, H), fill=hexc("#c9ced2"))
    font = ImageFont.truetype(str(FONTS / "STXINGKA.TTF"), 100)
    text = "南京信息工程大学" * 2
    step = W / len(text)
    for i, ch in enumerate(text):
        bb = d.textbbox((0, 0), ch, font=font)
        cx = step * (i + 0.5)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], H / 2 - (bb[3] - bb[1]) / 2 - bb[1]), ch, font=font, fill=hexc("#1f3d7a"))
    save(im, "ring_sign.jpg", 90)


def misc():
    s = 128
    save(noise(Image.new("RGB", (s, s), hexc("#6f9449")), 14, 1.0), "green_roof.jpg")
    save(noise(Image.new("RGB", (s, s), hexc("#c9c7c0")), 5), "concrete.jpg")


# ======================================================== batch 2 ==========
def _font(size, name="STXINGKA.TTF"):
    return ImageFont.truetype(str(FONTS / name), size)


def text_plate(name, text, size, bg, fg, font="STXINGKA.TTF", noise_amp=0, gap=0.6):
    W, H = size
    im = Image.new("RGB", (W, H), hexc(bg))
    if noise_amp:
        im = noise(im, noise_amp, 1.2)
    d = ImageDraw.Draw(im)
    f = _font(int(H * 0.72), font)
    step = W / (len(text) + gap)
    for i, ch in enumerate(text):
        bb = d.textbbox((0, 0), ch, font=f)
        cx = step * (i + 0.5 + gap / 2)
        d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], H / 2 - (bb[3] - bb[1]) / 2 - bb[1]), ch, font=f, fill=hexc(fg))
    save(im, name, 90)


def white_band():
    """文德楼 / 滨江楼: 4 m bay x 3.8 m floor, white wall + window band with mullions."""
    W, H = 256, 243
    im = Image.new("RGB", (W, H), hexc("#f0f0ec"))
    d = ImageDraw.Draw(im)
    y0, y1 = int(H * 0.22), int(H * 0.72)
    vgrad(d, (10, y0, W - 10, y1), "#6f8594", "#3f5260")
    for x in range(10, W - 9, (W - 20) // 4):
        d.rectangle((x - 2, y0, x + 2, y1), fill=hexc("#e9ebea"))
    d.rectangle((6, y1, W - 6, y1 + 7), fill=hexc("#d9dad6"))
    d.rectangle((0, H - 10, W, H), fill=hexc("#e2e2dd"))
    save(noise(im, 2), "white_band.jpg")


def sx_brick():
    """尚贤楼: 3.6 m bay x 3.3 m floor, brown brick with a tall window and brick piers."""
    W, H = 256, 235
    im = noise(Image.new("RGB", (W, H), hexc("#a8825d")), 6)
    d = ImageDraw.Draw(im)
    for y in range(0, H, 8):
        d.line([(0, y), (W, y)], fill=hexc("#94704f"), width=1)
    d.rectangle((0, 0, 26, H), fill=hexc("#9a7552"))
    d.rectangle((W - 26, 0, W, H), fill=hexc("#9a7552"))
    window(d, (62, 48, 194, 196), "#7f97a8", "#40566a", frame="#e8e3d8", fw=5, transom=0.3)
    d.rectangle((56, 196, 200, 204), fill=hexc("#d8cfbf"))
    save(im, "sx_brick.jpg")


def sx_panel():
    """尚贤楼 (2020/2021/2024 photos): 3.6 m bay x 3.5 m floor, light-brown spandrel panels in a white frame grid
    (white piers + white floor bands), wide window with dark frame."""
    W, H = 256, 249
    im = noise(Image.new("RGB", (W, H), hexc("#c89b77")), 4)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 18, H), fill=hexc("#ecebe6"))
    d.rectangle((W - 18, 0, W, H), fill=hexc("#ecebe6"))
    d.rectangle((0, H - 22, W, H), fill=hexc("#e6e4de"))
    window(d, (40, 34, W - 40, 150), "#6f8798", "#3d5163", frame="#4b4f52", fw=4, transom=None)
    d.rectangle((36, 150, W - 36, 157), fill=hexc("#e2ddd2"))
    save(im, "sx_panel.jpg")


def xz_facade():
    """行政楼: 3.6 m bay x 3.8 m floor. Cream stone pier (~1.1 m) + tall recessed glazed bay with transoms and a grey
    spandrel at the floor line (photo xingzhenglou_0, 2024-12 oblique drone view, building asset)."""
    W, H = 256, 270
    im = Image.new("RGB", (W, H), hexc("#e9e2d2"))
    d = ImageDraw.Draw(im)
    g0, g1 = 80, W - 6
    vgrad(d, (g0, 0, g1, H - 30), "#a9bcc4", "#6f8b98")
    d.rectangle((g0, H - 30, g1, H), fill=hexc("#7d8388"))            # spandrel
    for x in (g0, (g0 + g1) // 2, g1):
        d.rectangle((x - 2, 0, x + 2, H - 30), fill=hexc("#d8dcda"))   # mullions
    for y in (int(H * 0.36), H - 32):
        d.rectangle((g0, y - 2, g1, y + 2), fill=hexc("#d8dcda"))      # transoms
    d.rectangle((g0 - 6, 0, g0 - 1, H), fill=hexc("#cfc6b4"))          # pier reveal shadow
    d.rectangle((g1, 0, W, H), fill=hexc("#ddd5c3"))
    save(noise(im, 2), "xz_facade.jpg")


def xz_end():
    """行政楼 end / chamfer walls: cream stone with one punched window per 3.6 m bay x 3.8 m floor."""
    W, H = 256, 270
    im = noise(Image.new("RGB", (W, H), hexc("#e9e2d2")), 3)
    d = ImageDraw.Draw(im)
    window(d, (70, 60, 186, 200), "#9fb3bd", "#5f7a88", frame="#d8dcda", fw=4, transom=0.3)
    d.rectangle((62, 200, 194, 208), fill=hexc("#d9d0bd"))
    d.rectangle((0, H - 6, W, H), fill=hexc("#ddd5c3"))
    save(im, "xz_end.jpg")


def gj_facade():
    """国际教育学院 / 雷丁学院: 4 m bay x 4.4 m floor, white grid frame around grey glass."""
    W, H = 256, 282
    im = Image.new("RGB", (W, H), hexc("#f3f3f0"))
    d = ImageDraw.Draw(im)
    vgrad(d, (22, 38, W - 22, H - 46), "#8fa2ae", "#55697a")
    d.rectangle((W // 2 - 4, 38, W // 2 + 4, H - 46), fill=hexc("#eceeed"))
    d.rectangle((22, 110, W - 22, 116), fill=hexc("#eceeed"))
    d.rectangle((0, H - 46, W, H - 36), fill=hexc("#dcdedb"))
    save(noise(im, 2), "gj_facade.jpg")


def of_facade(name="of_facade.jpg", wall="#d3b088"):
    """藕舫楼: 3.4 m bay x 3.6 m floor, tan wall with white-framed window (also pink variant for 科创楼)."""
    W, H = 256, 271
    im = noise(Image.new("RGB", (W, H), hexc(wall)), 5)
    d = ImageDraw.Draw(im)
    d.rectangle((44, 50, 212, 200), fill=hexc("#f2ede4"))
    window(d, (54, 60, 202, 190), "#7d93a3", "#3f5465", frame="#f2ede4", fw=4, transom=0.32)
    d.rectangle((0, H - 18, W, H), fill=hexc("#eee7da"))
    save(im, name)


def stone_column():
    """东大门 granite column: beige-grey with carved horizontal bands (u wraps round the column)."""
    W, H = 256, 512
    im = noise(Image.new("RGB", (W, H), hexc("#b9b0a2")), 9, 1.0)
    d = ImageDraw.Draw(im)
    for y in range(20, H, 64):
        d.rectangle((0, y, W, y + 26), fill=hexc("#a59c8e"))
        for x in range(0, W, 32):
            d.arc((x, y - 4, x + 32, y + 30), 200, 340, fill=hexc("#8f8678"), width=3)
    save(noise(im, 4), "stone_column.jpg")


def flags():
    """8 x 4 atlas of flags (cell 0 = 中国, cell 1 = light-blue UN/WMO style, others generic)."""
    import math
    cw, ch = 96, 64
    im = Image.new("RGB", (cw * 8, ch * 4), "white")
    d = ImageDraw.Draw(im)
    pal = ["#c8102e", "#ffffff", "#0033a0", "#009639", "#fcd116", "#000000", "#ff8200", "#75aadb", "#00843d", "#ce1126"]
    r = np.random.default_rng(3)

    def star(cx, cy, R, col, rot=0.0):
        pts = []
        for k in range(10):
            rr = R if k % 2 == 0 else R * 0.38
            a = rot - math.pi / 2 + k * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=hexc(col))

    for idx in range(32):
        x0, y0 = (idx % 8) * cw, (idx // 8) * ch
        box = (x0, y0, x0 + cw - 1, y0 + ch - 1)
        if idx == 0:
            d.rectangle(box, fill=hexc("#de2910"))
            star(x0 + 16, y0 + 16, 10, "#ffde00")
            for sx, sy in ((32, 6), (38, 12), (38, 21), (32, 27)):
                star(x0 + sx, y0 + sy, 3.2, "#ffde00", math.atan2(16 - sy, 16 - sx) + math.pi / 2)
            continue
        if idx == 1:
            d.rectangle(box, fill=hexc("#5b92e5"))
            d.ellipse((x0 + 32, y0 + 16, x0 + 64, y0 + 48), outline=hexc("#ffffff"), width=4)
            continue
        cols = [pal[i] for i in r.choice(len(pal), 3, replace=False)]
        kind = idx % 5
        if kind == 0:
            for k in range(3):
                d.rectangle((x0, y0 + k * ch // 3, x0 + cw - 1, y0 + (k + 1) * ch // 3), fill=hexc(cols[k]))
        elif kind == 1:
            for k in range(3):
                d.rectangle((x0 + k * cw // 3, y0, x0 + (k + 1) * cw // 3, y0 + ch - 1), fill=hexc(cols[k]))
        elif kind == 2:
            d.rectangle(box, fill=hexc(cols[0]))
            d.rectangle((x0 + 26, y0, x0 + 38, y0 + ch - 1), fill=hexc(cols[1]))
            d.rectangle((x0, y0 + 26, x0 + cw - 1, y0 + 38), fill=hexc(cols[1]))
        elif kind == 3:
            d.rectangle(box, fill=hexc(cols[0]))
            d.ellipse((x0 + 34, y0 + 18, x0 + 62, y0 + 46), fill=hexc(cols[1]))
        else:
            d.rectangle((x0, y0, x0 + cw - 1, y0 + ch // 2), fill=hexc(cols[0]))
            d.rectangle((x0, y0 + ch // 2, x0 + cw - 1, y0 + ch - 1), fill=hexc(cols[1]))
            d.polygon([(x0, y0), (x0 + 34, y0 + ch // 2), (x0, y0 + ch - 1)], fill=hexc(cols[2]))
    save(im, "flags.jpg", 92)


def batch2():
    white_band()
    sx_brick()
    sx_panel()
    xz_facade()
    xz_end()
    gj_facade()
    of_facade()
    stone_column()
    flags()
    text_plate("rock_text.jpg", "南京信息工程大学", (1024, 128), "#c29a72", "#5a3a22", noise_amp=10, gap=0.4)
    text_plate("bj_name.jpg", "滨江楼", (512, 128), "#f3f3ef", "#b8913f", font="STKAITI.TTF", gap=1.0)


# ======================================================== campus bus ========
def bus_atlas():
    """2048 x 1024 atlas for models/bus.glb (UV v=0 at the image bottom):
    left side u0-.5 v.5-1 (front at left) | right side u.5-1 v.5-1 (front at right)
    front u0-.25 v0-.5 | back u.25-.5 v0-.5 | roof u.5-.75 v0-.5 (front at bottom) | rim u.75-.875 v0-.25"""
    import math
    W, H = 2048, 1024
    L, BW, BH = 6.2, 2.1, 2.65
    blue, white, glass0, glass1 = "#2a6fc9", "#f4f5f6", "#3a4d5e", "#1b2731"
    im = Image.new("RGB", (W, H), hexc(white))
    d = ImageDraw.Draw(im)
    kai = lambda px: ImageFont.truetype(str(FONTS / "STXINGKA.TTF"), px)
    hei = lambda px: ImageFont.truetype(str(FONTS / "msyhbd.ttc"), px)

    def ctext(xy, text, font, fill, dd=None):
        dd = dd or d
        bb = dd.textbbox((0, 0), text, font=font)
        dd.text((xy[0] - (bb[2] - bb[0]) / 2 - bb[0], xy[1] - (bb[3] - bb[1]) / 2 - bb[1]), text, font=font, fill=hexc(fill))

    def side(x_paste, front_left, door):
        """Drawn on its own 1024 x 512 canvas, so nothing spills into the neighbouring regions."""
        sim = Image.new("RGB", (1024, 512), hexc(white))
        d = ImageDraw.Draw(sim)
        x0 = 0
        sx, sy = 1024 / L, 512 / BH

        def P(sm, y):
            return (x0 + (sm * sx if front_left else 1024 - sm * sx), 512 - y * sy)

        def rect(s0, s1, y0, y1, col=None, grad=None):
            a, b = P(s0, y1), P(s1, y0)
            box = (min(a[0], b[0]), a[1], max(a[0], b[0]), b[1])
            if grad:
                vgrad(d, (box[0], box[1], box[2] + 1, box[3] + 1), *grad)
            else:
                d.rectangle(box, fill=hexc(col))
            return box

        rect(0, L, 0.30, 0.42, "#c9ccce")
        d.polygon([P(1.0, 0.42)] + [P(sm, 1.06 + 0.10 * math.sin(sm * 1.3)) for sm in np.linspace(1.0, L, 40)] + [P(L, 0.42)],
                  fill=hexc(blue))
        for k, (y0, amp) in enumerate(((0.55, 0.10), (0.67, 0.08), (0.79, 0.06))):
            d.line([P(sm, y0 + amp * math.sin(sm * 1.6 + k)) for sm in np.linspace(1.8, L - 0.1, 50)], fill=hexc(white), width=7 - 2 * k)
        rect(0.18, L - 0.22, 1.26, 2.38, "#d9dcde")
        rect(0.24, L - 0.28, 1.30, 2.34, grad=(glass0, glass1))
        for k in range(5):
            sm = 1.25 + 1.12 * k
            rect(sm - 0.05, sm + 0.05, 1.30, 2.34, "#d9dcde")
        if door:
            rect(0.20, 1.02, 0.42, 2.34, "#d9dcde")
            rect(0.26, 0.96, 0.50, 2.30, grad=(glass0, glass1))
            rect(0.60, 0.62, 0.50, 2.30, "#c9ccce")
        for sc in (1.40, 4.85):
            a, b = P(sc - 0.47, 0.83), P(sc + 0.47, -0.11)
            d.ellipse((min(a[0], b[0]), a[1], max(a[0], b[0]), b[1]), fill=hexc("#1c1d20"))
        rect(0, L, 0.0, 0.30, "#1c1d20")
        # logo + school name on the blue band, slogan at the rear
        cx, cy = P(2.15, 0.93)
        d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), outline=hexc(white), width=5)
        d.arc((cx - 14, cy - 14, cx + 14, cy + 14), 200, 520, fill=hexc(white), width=4)
        ctext(P(3.35, 0.93), "南京信息工程大学", kai(46), white, d)
        ctext(P(5.35, 1.06), "争先号校园巴士", kai(34), white, d)
        if not door:
            ctext(P(0.62, 0.80), "南京信息工程大学", kai(18), blue, d)
        im.paste(sim, (x_paste, 0))

    side(0, True, False)
    side(1024, False, True)

    # front (viewer's left = bus right side)
    fx, fy = 512 / BW, 512 / BH
    Fp = lambda xm, y: (xm * fx, 1024 - y * fy)

    def frect(x0, x1, y0, y1, col=None, grad=None, ox=0):
        a, b = Fp(x0, y1), Fp(x1, y0)
        box = (a[0] + ox, a[1], b[0] + ox, b[1])
        if grad:
            vgrad(d, (box[0], box[1], box[2] + 1, box[3] + 1), *grad)
        else:
            d.rectangle(box, fill=hexc(col))

    for ox, rear in ((0, False), (512, True)):
        frect(0, BW, 0.30, 0.42, "#c9ccce", ox=ox)
        frect(0, BW, 0.0, 0.30, "#1c1d20", ox=ox)
        frect(0, BW, 2.38, BH, blue, ox=ox)
        if not rear:
            frect(0.06, 2.04, 1.22, 2.40, "#202326")
            frect(0.12, 1.98, 1.28, 2.16, grad=("#4b6072", "#1b2731"))
            d.polygon([Fp(0.4, 2.16), Fp(0.75, 2.16), Fp(0.35, 1.28), Fp(0.12, 1.28)], fill=hexc("#5d7588"))
            frect(0.12, 1.98, 2.18, 2.36, "#0d0f10")
            ctext(Fp(1.10, 2.27), "争 先 号", hei(30), "#46e07a")
            c = Fp(0.30, 2.27)
            d.ellipse((c[0] - 19, c[1] - 19, c[0] + 19, c[1] + 19), fill=hexc("#e8f5ec"))
            ctext(c, "12", hei(22), "#1f7a46")
            ctext(Fp(1.05, 1.02), "南京信息工程大学", kai(30), blue)
            frect(0.82, 1.28, 0.84, 0.90, "#2a2d31")
            frect(0.77, 1.33, 0.43, 0.59, grad=("#56d38c", "#21a35c"))
            ctext(Fp(1.05, 0.51), "校园公交·012", hei(22), "#101010")
        else:
            frect(0.22, 1.88, 1.42, 2.32, grad=(glass0, glass1), ox=ox)
            for xm in (0.10, 1.84):
                frect(xm, xm + 0.16, 0.62, 1.15, "#c8202a", ox=ox)
            a = Fp(1.05, 1.05)
            ctext((a[0] + ox, a[1]), "争先号校园巴士", kai(34), blue)
            a = Fp(0.80, 0.43)
            vgrad(d, (a[0] + ox, Fp(0, 0.59)[1], Fp(1.30, 0)[0] + ox, a[1]), "#56d38c", "#21a35c")
            b = Fp(1.05, 0.51)
            ctext((b[0] + ox, b[1]), "校园公交·012", hei(22), "#101010")

    # roof: white with seams, blue front strip (front at the region bottom)
    for y in range(512, 1024, 64):
        d.line([(1024, y), (1536, y)], fill=hexc("#dde0e2"), width=2)
    d.rectangle((1024, 966, 1536, 1024), fill=hexc(blue))
    # rim
    c, r = (1664, 896), 120
    d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=hexc("#2a2b2e"))
    d.ellipse((c[0] - 96, c[1] - 96, c[0] + 96, c[1] + 96), fill=hexc("#c9ced3"))
    for k in range(6):
        a = math.radians(k * 60 + 30)
        d.ellipse((c[0] + 58 * math.cos(a) - 18, c[1] + 58 * math.sin(a) - 18, c[0] + 58 * math.cos(a) + 18,
                   c[1] + 58 * math.sin(a) + 18), fill=hexc("#3a3c40"))
    d.ellipse((c[0] - 22, c[1] - 22, c[0] + 22, c[1] + 22), fill=hexc("#8d9399"))
    save(im, "bus_atlas.jpg", 92)


# ======================================================== batch 3 ==========
def batch3():
    W, H = 256, 256  # 气象谷: 3 m bay x 3.75 m floor, blue-green glass with a white slab band
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    vgrad(d, (0, 0, W, H), "#8fc0c4", "#3e7d86")
    for x in (0, W // 3, 2 * W // 3):
        d.rectangle((x, 0, x + 4, H), fill=hexc("#c6dadb"))
    d.rectangle((0, H - 30, W, H), fill=hexc("#f1f3f2"))
    save(noise(im, 2), "qg_glass.jpg")
    text_plate("shelter_sign.jpg", "校园公交", (512, 128), "#2a6fc9", "#ffffff", font="msyhbd.ttc", gap=1.2)


# ======================================================== batch 4 ==========
def batch4():
    W, H = 256, 235  # 中苑老食堂: dark red brick, white-framed window (3.6 m bay x 3.6 m floor)
    im = noise(Image.new("RGB", (W, H), hexc("#9b3b2c")), 6)
    d = ImageDraw.Draw(im)
    for y in range(0, H, 8):
        d.line([(0, y), (W, y)], fill=hexc("#843124"), width=1)
    window(d, (58, 50, 198, 190), "#7f97a8", "#40566a", frame="#f1eee8", fw=6, transom=0.3)
    d.rectangle((0, H - 12, W, H), fill=hexc("#efece6"))
    save(im, "red_brick.jpg")
    W, H = 256, 512  # 风云剧场: span texture, tall tan panels between grey bays with slit windows
    im = Image.new("RGB", (W, H), hexc("#a9aaa7"))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 100, H), fill=hexc("#d68c4c"))
    d.rectangle((96, 0, 104, H), fill=hexc("#b9763f"))
    vgrad(d, (150, 60, 206, H - 40), "#5d7282", "#33444f")
    d.rectangle((0, 0, W, 26), fill=hexc("#e8e6e1"))
    save(noise(im, 3), "theater.jpg")


# ======================================================== generic + normal maps
def generic():
    """Neutral (near-white) facades for the generic buildings; tinted per building with vertex colours."""
    W, H = 256, 216  # gen_dorm: 3.6 m bay x 3.0 m floor, punched window with sill
    im = Image.new("RGB", (W, H), hexc("#f4f4f2"))
    d = ImageDraw.Draw(im)
    d.rectangle((50, 46, 206, 168), fill=hexc("#e4e4e0"))
    window(d, (58, 52, 198, 160), "#7a8c99", "#3d4c58", frame="#fbfbfa", fw=5, transom=0.3)
    d.rectangle((48, 166, 208, 176), fill=hexc("#fdfdfc"))
    save(noise(im, 3), "gen_dorm.jpg")
    W, H = 256, 243  # gen_office: 4 m bay x 3.8 m floor, wide paired windows
    im = Image.new("RGB", (W, H), hexc("#f4f4f2"))
    d = ImageDraw.Draw(im)
    for x0 in (18, 134):
        window(d, (x0, 50, x0 + 104, 196), "#7f93a1", "#3a4a57", frame="#fbfbfa", fw=4, transom=0.28)
    d.rectangle((0, 200, W, 210), fill=hexc("#e2e2de"))
    save(noise(im, 3), "gen_office.jpg")
    W, H = 256, 256  # gen_hall: 6 m x 6 m, panels with a high glass band
    im = Image.new("RGB", (W, H), hexc("#efefec"))
    d = ImageDraw.Draw(im)
    vgrad(d, (0, 20, W, 92), "#8094a2", "#46586a")
    for x in range(0, W, 64):
        d.rectangle((x, 20, x + 4, 92), fill=hexc("#f6f6f4"))
        d.rectangle((x, 92, x + 2, H), fill=hexc("#d8d8d4"))
    for y in range(110, H, 36):
        d.line([(0, y), (W, y)], fill=hexc("#dededa"), width=2)
    save(noise(im, 3), "gen_hall.jpg")
    s_ = 256  # gen_tile: roof tiles (hip roofs), gen_flat: flat roof membrane with joints
    im = noise(Image.new("RGB", (s_, s_), hexc("#e8e8e8")), 7)
    d = ImageDraw.Draw(im)
    for y in range(0, s_, 16):
        d.line([(0, y), (s_, y)], fill=hexc("#b9b9b9"), width=3)
        for x in range((y // 16 % 2) * 16, s_, 32):
            d.line([(x, y), (x, y + 16)], fill=hexc("#cdcdcd"), width=1)
    save(im, "gen_tile.jpg")
    im = noise(Image.new("RGB", (s_, s_), hexc("#f0f0f0")), 5)
    d = ImageDraw.Draw(im)
    for k in range(0, s_, 64):
        d.line([(k, 0), (k, s_)], fill=hexc("#dadada"), width=2)
        d.line([(0, k), (s_, k)], fill=hexc("#dadada"), width=2)
    save(im, "gen_flat.jpg")


def old_res():
    """E3 old residential blocks: grey stained render, aluminium window with security grille (3.3 m bay x 3.0 m)."""
    W, H = 256, 233
    base = noise(Image.new("RGB", (W, H), hexc("#8e8f8b")), 10, 1.5)
    a = np.asarray(base).astype(np.float32)
    for x in rng.integers(0, W, 9):  # water stains running down from the sills
        w = int(rng.integers(6, 18))
        a[:, x:x + w] *= np.linspace(0.97, 0.84, H)[:, None, None]
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    x0, x1, y0, y1 = 70, 186, 54, 168
    window(d, (x0, y0, x1, y1), "#5f6a70", "#2f383e", frame="#b9bcbb", fw=4, transom=0.32)
    for x in range(x0 - 6, x1 + 7, 11):
        d.line([(x, y0 - 6), (x, y1 + 4)], fill=hexc("#5d5a55"), width=2)
    d.rectangle((x0 - 8, y0 - 8, x1 + 8, y0 - 5), fill=hexc("#5d5a55"))
    d.rectangle((x0 - 8, y1 + 2, x1 + 8, y1 + 9), fill=hexc("#a3a39f"))
    d.rectangle((0, H - 8, W, H), fill=hexc("#7d7e7a"))
    save(im, "old_res.jpg")


def container_street():
    """东苑集装箱美食街: corrugated container skin (white, tinted per shop), shopfront glazing with black frames,
    shop-sign atlas (8 cells, generic shop names) and the street title plate."""
    W = H = 256  # container skin: 2.4 m x 2.6 m, vertical corrugation + top/bottom rails
    im = Image.new("RGB", (W, H), hexc("#f2f2f0"))
    d = ImageDraw.Draw(im)
    for x in range(0, W, 16):
        d.rectangle((x, 0, x + 5, H), fill=hexc("#d6d6d3"))
        d.line([(x + 6, 0), (x + 6, H)], fill=hexc("#fbfbfa"), width=2)
    d.rectangle((0, 0, W, 10), fill=hexc("#bdbdba"))
    d.rectangle((0, H - 12, W, H), fill=hexc("#bdbdba"))
    save(noise(im, 3), "container.jpg")
    W, H = 256, 256  # shopfront: 2 m bay, black aluminium frame, transom
    im = Image.new("RGB", (W, H), hexc("#1d1f21"))
    d = ImageDraw.Draw(im)
    vgrad(d, (8, 8, W - 8, 60), "#6f8a99", "#3c4e5a")
    vgrad(d, (8, 70, W // 2 - 4, H - 8), "#7b97a6", "#33444f")
    vgrad(d, (W // 2 + 4, 70, W - 8, H - 8), "#7b97a6", "#33444f")
    d.rectangle((W // 2 - 4, 70, W // 2 + 4, H - 8), fill=hexc("#1d1f21"))
    save(noise(im, 2), "shopfront.jpg")
    # shop-sign atlas, 2 x 6 cells: ground floor g1..g6 = cells 0..5, upper floor u1..u6 = cells 6..11
    # (names in the user's photo 信藕空间·文创街区; cells 3-5 and 9-11 are generic, not real shop names)
    names = [("芒可24h 鲜饮市集", "#a9d3ef", "#1f3d7a"), ("购好超市", "#3b3f42", "#ffffff"), ("沪溪河桃酥", "#2f6b4c", "#ffffff"),
             ("鲜果水吧", "#cfd2d3", "#2b2b2b"), ("特色小吃", "#922c25", "#ffffff"), ("便利店", "#3b3f42", "#ffffff"),
             ("不如麻辣烫", "#efc441", "#2b2b2b"), ("李堡长", "#962c26", "#ffffff"), ("禾香楼", "#b9b4aa", "#2b2b2b"),
             ("奶茶咖啡", "#e8742a", "#ffffff"), ("文创小店", "#cfd2d3", "#2b2b2b"), ("简餐", "#efc441", "#2b2b2b")]
    cw, ch = 512, 96
    im = Image.new("RGB", (cw * 2, ch * 6), "black")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONTS / "msyhbd.ttc"), 54)
    for k, (nm, bg, fg) in enumerate(names):
        x0, y0 = (k % 2) * cw, (k // 2) * ch
        d.rectangle((x0, y0, x0 + cw - 1, y0 + ch - 1), fill=hexc(bg))
        bb = d.textbbox((0, 0), nm, font=f)
        d.text((x0 + cw / 2 - (bb[2] - bb[0]) / 2 - bb[0], y0 + ch / 2 - (bb[3] - bb[1]) / 2 - bb[1]), nm, font=f, fill=hexc(fg))
    save(im, "jzx_signs.jpg", 92)
    W, H = 256, 384  # west-end poster: cartoon-style poster on the end wall (generic shapes)
    im = Image.new("RGB", (W, H), hexc("#f6e7a8"))
    d = ImageDraw.Draw(im)
    d.rectangle((10, 10, W - 10, H - 10), outline=hexc("#1f4fa3"), width=8)
    d.rectangle((30, 40, W - 30, 120), fill=hexc("#1f4fa3"))
    for cx, cy, r, c in ((80, 200, 46, "#e8742a"), (170, 250, 38, "#2f6b4c"), (110, 300, 30, "#922c25"), (190, 170, 26, "#ffffff")):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hexc(c))
    ft = ImageFont.truetype(str(FONTS / "msyhbd.ttc"), 40)
    d.text((48, 58), "文创街区", font=ft, fill=hexc("#ffffff"))
    save(im, "jzx_poster.jpg", 90)
    text_plate("jzx_title.jpg", "信藕空间  文创街区", (1024, 128), "#e8742a", "#ffffff", font="msyhbd.ttc", gap=0.4)


def relief_column():
    """东大门 九龙柱: granite with deep swirling (cloud / dragon) relief, u wraps the column, 2 m tall tile."""
    W, H = 256, 512
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (np.sin(xx / W * 2 * np.pi * 3 + yy / 37.0) + np.sin(yy / 23.0 - xx / W * 2 * np.pi * 2) +
         0.6 * np.sin((xx + yy) / 15.0)) / 2.6
    base = np.array(hexc("#bfb5a4"), np.float32)
    a = base[None, None, :] * (0.82 + 0.18 * t[..., None])
    im = noise(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), 8, 0.8)
    save(im, "relief_column.jpg")


NORMAL_FOR = ["qx_facade", "glass_blue", "glass_dark", "lib_facade", "yf_facade", "yf4_facade", "slate", "metal_roof",
              "metal_light", "lj_tower", "lj_podium", "gym_glass", "gym_panel", "js_wall", "brick_red", "white_band",
              "sx_brick", "sx_panel", "xz_facade", "xz_end", "gj_facade", "of_facade", "pink_facade", "red_brick", "theater", "qg_glass",
              "stone_column", "gen_dorm", "gen_office", "gen_hall", "gen_tile", "gen_flat", "concrete", "old_res", "container",
              "shopfront", "relief_column"]


def normal_maps(strength=6.0):
    """Tangent-space normal maps (OpenGL / glTF convention) derived from each texture: dark glass is recessed,
    bright frames and trims stand proud, so flat walls read with depth."""
    for stem in NORMAL_FOR:
        src = OUT / f"{stem}.jpg"
        if not src.exists():
            continue
        a = np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255.0
        lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
        glass = np.clip((0.55 - lum) / 0.25, 0, 1)
        h = 0.65 * lum - 0.6 * glass
        hi = Image.fromarray(np.clip(h * 255 + 100, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
        h = np.asarray(hi).astype(np.float32) / 255.0
        gy, gx = np.gradient(h)
        nx, ny = -gx * strength, gy * strength  # image rows grow downwards; glTF normal maps are +Y up
        nz = np.ones_like(nx)
        n = np.stack([nx, ny, nz], -1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        save(Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)), f"{stem}_n.jpg", 92)


def emblem():
    """School emblem disc for the grandstand (generic: blue disc, white rings, stylised swirl)."""
    s_ = 256
    im = Image.new("RGB", (s_, s_), hexc("#ffffff"))
    d = ImageDraw.Draw(im)
    d.ellipse((6, 6, s_ - 6, s_ - 6), fill=hexc("#1f4fa3"))
    d.ellipse((24, 24, s_ - 24, s_ - 24), outline=hexc("#ffffff"), width=6)
    d.arc((70, 70, 186, 186), 200, 520, fill=hexc("#ffffff"), width=14)
    d.ellipse((116, 116, 140, 140), fill=hexc("#ffffff"))
    save(im, "emblem.jpg", 92)


if __name__ == "__main__":
    qx_facade()
    glass_curtain()
    glass_curtain("glass_dark.jpg", "#4d6f8f", "#223a52", "#8ea2b4", "#1f3247")
    radome()
    # library: 6 floors to a 20 m cornice (18.7 m of floors + 1.3 m cornice band)
    classical("lib_facade.jpg", "#eadcc3", 224, [3.7, 3.0, 3.0, 3.0, 3.0, 3.0], groove="#d8c7a6", trim="#f4ecdc")
    # 逸夫楼: 5 floors to a 17 m cornice
    classical("yf_facade.jpg", "#eef0f2", 208, [3.6, 3.0, 3.0, 3.0, 3.1], glass=("#7593ad", "#3d5871"),
              groove="#cfd5da", trim="#ffffff")
    slate()
    metal_roof()
    metal_roof("metal_light.jpg", "#c6cacd", "#dde0e2")
    clock()
    lj_tower()
    lj_podium()
    gym()
    js_wall()
    gate()
    ring_sign()
    misc()
    batch2()
    bus_atlas()
    batch3()
    batch4()
    of_facade("pink_facade.jpg", "#dcb3a6")
    generic()
    emblem()
    old_res()
    container_street()
    relief_column()
    normal_maps()
    classical("yf4_facade.jpg", "#eef0f2", 208, [3.4, 3.0, 3.0, 3.0], glass=("#7593ad", "#3d5871"), groove="#cfd5da",
              trim="#ffffff")  # 学科1号楼: 4 floors to a 13.7 m cornice
