"""Textures for the 东大门 model (tools/blender_dongdamen.py): carved dragon relief, inscribed rock, ashlar cladding,
plaza paving, pebbles, boulders, rusted beams, flower beds. Writes data/blender/textures/ddm_*.jpg (+ *_n.jpg normal maps).

Reference: user panorama data/zones/fix_dongdamen/user_panorama_2.jpg (columns with dragon reliefs, sandstone rock with
red-brown calligraphy, beige ashlar gatehouses, grey-blue tiles, white pebbles, rust-red beams and grey boulders).

Usage: .venv\\Scripts\\python.exe tools\\ddm_textures.py
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "blender" / "textures"
FONT_CAL = "C:/Windows/Fonts/STXINGKA.TTF"     # 华文行楷, close to the rock's running-script inscription
RNG = np.random.default_rng(20261128)


# ------------------------------------------------------------------ helpers
def noise(h, w, scale, octaves=4, wrap=True, seed=0):
    """Tileable value noise in [0, 1] (bicubic-upsampled random grids, summed octaves)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh, gw = max(2, int(h / scale * 2 ** o)), max(2, int(w / scale * 2 ** o))
        g = rng.random((gh, gw))
        if wrap:
            g = np.pad(g, ((0, 1), (0, 1)), mode="wrap")
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((w + (w // gw if wrap else 0), h + (h // gh if wrap else 0)),
                                                                 Image.BICUBIC)
        a = np.asarray(im, dtype=float)[:h, :w] / 255
        out += a * amp
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, r):
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), dtype=float) / 255


def normal_map(hgt, strength=4.0, wrap_x=True):
    """Height field [0,1] -> tangent-space normal map (OpenGL / glTF: +Y up in the image = +V)."""
    if wrap_x:
        dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) / 2
    else:
        dx = np.gradient(hgt, axis=1)
    dy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) / 2
    nx, ny, nz = -dx * strength, dy * strength, np.ones_like(hgt)
    L = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / L, ny / L, nz / L], -1)
    return Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8))


def colorize(base_hex, shade, var=None, var_amt=0.0):
    c = np.array([int(base_hex[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)
    img = c[None, None, :] * shade[..., None]
    if var is not None:
        img = img * (1 + (var[..., None] - 0.5) * var_amt)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def granite_speckle(h, w, seed):
    rng = np.random.default_rng(seed)
    sp = np.zeros((h, w))
    n = h * w // 18
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    sp[ys, xs] = rng.normal(0, 1, n)
    return blur(np.clip(sp * 0.5 + 0.5, 0, 1), 0.7) - 0.5


def save(img, name, q=90):
    img.convert("RGB").save(OUT / name, quality=q)
    print("wrote", name, img.size)


# ------------------------------------------------------------------ 1. dragon-relief column (wraps once round the shaft)
def dragon_column():
    W, H = 512, 1024
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    hgt = noise(H, W, 64, 4, seed=1) * 0.18
    # auspicious clouds: small double spirals (raised grooves), tiled in x
    clouds = np.zeros((H, W))
    for k in range(34):
        cx, cy, r0 = RNG.uniform(0, W), RNG.uniform(0, H), RNG.uniform(14, 26)
        for t in np.linspace(0, 3.2 * math.pi, 220):
            r = r0 * (1 - t / (3.6 * math.pi))
            for side in (1, -1):
                px = (cx + side * (r0 * 0.9 + r * math.cos(t))) % W
                py = cy + r * math.sin(t) * side
                if 0 <= py < H:
                    clouds[int(py), int(px)] = 1
    clouds = np.clip(blur(clouds, 2.2) * 6, 0, 1)
    hgt = np.maximum(hgt, clouds * 0.55)
    # dragon body: a fat tube winding up the shaft (1.6 turns), scales + dorsal spines, head near the top
    body = np.zeros((H, W))
    scales = np.zeros((H, W))
    path = []
    for t in np.linspace(0, 1, 2600):
        px = (W * 1.6 * t + 40 * math.sin(t * 19)) % W
        py = H * (0.04 + 0.86 * t) + 30 * math.sin(t * 31)
        path.append((px, py, t))
    yyi, xxi = np.mgrid[0:H, 0:W]
    for px, py, t in path[::6]:
        rad = 34 * (0.55 + 0.45 * math.sin(math.pi * min(1, t * 1.15)))   # tapering tail
        x0, x1, y0, y1 = int(px - rad - 2), int(px + rad + 2), int(max(0, py - rad - 2)), int(min(H, py + rad + 2))
        for xo in (0, W, -W):
            xs0, xs1 = max(0, x0 + xo), min(W, x1 + xo)
            if xs0 >= xs1 or y0 >= y1:
                continue
            sub_y, sub_x = yyi[y0:y1, xs0:xs1], xxi[y0:y1, xs0:xs1]
            d = np.hypot(sub_x - (px + xo), sub_y - py) / rad
            prof = np.sqrt(np.clip(1 - d * d, 0, 1))
            body[y0:y1, xs0:xs1] = np.maximum(body[y0:y1, xs0:xs1], prof)
    # scale pattern: overlapping arcs along v
    sc = (np.sin(xx / 7.0 + np.sin(yy / 9.0) * 2) * np.sin(yy / 6.0)) * 0.5 + 0.5
    scales = (sc > 0.62).astype(float)
    body_h = body * 0.85 + body * scales * 0.12
    # head: a lump with horns and eyes near the end of the path
    hx, hy, _ = path[-120]
    for xo in (0, W, -W):
        d = np.hypot(xx - hx - xo, (yy - hy) * 1.2) / 62
        body_h = np.maximum(body_h, np.sqrt(np.clip(1 - d * d, 0, 1)) * 0.95)
    # claws: small blobs off the body
    for px, py, t in path[200::330]:
        for xo in (0, W, -W):
            d = np.hypot(xx - px - 38 - xo, yy - py - 26) / 16
            body_h = np.maximum(body_h, np.sqrt(np.clip(1 - d * d, 0, 1)) * 0.7)
    hgt = np.maximum(hgt, body_h)
    hgt = blur(hgt, 1.0)
    # carved bands at the very top/bottom (moulding rings)
    band = ((yy < 26) | (yy > H - 26)).astype(float)
    hgt = np.where(band > 0, 0.55 + 0.08 * np.sin(yy / 3.0), hgt)
    ao = np.clip(1 - (blur(hgt, 6) - hgt) * 2.2, 0.55, 1.05)          # darker in the hollows
    light = 0.88 + 0.22 * (np.roll(hgt, 2, 0) - hgt) * 6               # light from above
    sp = granite_speckle(H, W, 3)
    shade = np.clip(ao * light + sp * 0.35, 0.35, 1.2)
    save(colorize("#cdbfa8", shade, noise(H, W, 128, 3, seed=5), 0.18), "ddm_dragon.jpg")
    save(normal_map(hgt, 6.0), "ddm_dragon_n.jpg")


# ------------------------------------------------------------------ 2. granite (plinths, caps, kerbs, lions)
def granite():
    S = 512
    hgt = noise(S, S, 64, 5, seed=11)
    sp = granite_speckle(S, S, 12)
    shade = 0.92 + (hgt - 0.5) * 0.18 + sp * 0.5
    save(colorize("#cfc4b1", shade), "ddm_granite.jpg")
    save(normal_map(hgt * 0.4 + sp * 0.6, 2.0), "ddm_granite_n.jpg")


# ------------------------------------------------------------------ 3. ashlar cladding (gatehouses): 2 x 4 blocks per tile
def ashlar():
    S = 512                                   # tile = 2.4 m x 2.4 m: blocks 1.2 m x 0.6 m, staggered courses
    img = np.zeros((S, S))
    hgt = np.ones((S, S))
    bw, bh = S // 2, S // 4
    rng = np.random.default_rng(21)
    for r in range(4):
        off = (bw // 2) * (r % 2)
        for c in range(-1, 3):
            x0 = c * bw + off
            tint = rng.uniform(-0.07, 0.07)
            xs0, xs1 = max(0, x0), min(S, x0 + bw)
            if xs0 < xs1:
                img[r * bh:(r + 1) * bh, xs0:xs1] = tint
    yy, xx = np.mgrid[0:S, 0:S]
    joint = np.zeros((S, S), bool)
    for r in range(5):
        joint |= np.abs(yy - r * bh) < 3
    for r in range(4):
        off = (bw // 2) * (r % 2)
        for c in range(-1, 4):
            joint[r * bh:(r + 1) * bh] |= (np.abs(xx[r * bh:(r + 1) * bh] - (c * bw + off)) < 3)
    hgt[joint] = 0.0
    hgt = blur(hgt, 1.2) + noise(S, S, 48, 4, seed=22) * 0.12
    sp = granite_speckle(S, S, 23)
    shade = 0.93 + img + sp * 0.35 - joint * 0.25 + (noise(S, S, 96, 3, seed=24) - 0.5) * 0.12
    save(colorize("#cfc6b5", shade), "ddm_ashlar.jpg")
    save(normal_map(hgt, 3.0), "ddm_ashlar_n.jpg")


# ------------------------------------------------------------------ 4. glazing (gatehouse windows), one 1.5 m bay x one 3.6 m storey
def glazing():
    W, H = 256, 512
    im = Image.new("RGB", (W, H), (196, 200, 202))
    d = ImageDraw.Draw(im)
    g = np.linspace(0, 1, H)[:, None] * np.ones((1, W))
    glass = np.stack([60 + 55 * (1 - g), 82 + 60 * (1 - g), 96 + 62 * (1 - g)], -1)
    gl = Image.fromarray(glass.astype(np.uint8))
    im.paste(gl.crop((14, 40, W - 14, H - 70)), (14, 40))
    d.rectangle((0, 0, W, 40), fill=(205, 207, 206))            # head
    d.rectangle((0, H - 70, W, H), fill=(190, 186, 178))        # sill / stone base
    d.rectangle((W // 2 - 5, 40, W // 2 + 5, H - 70), fill=(214, 216, 216))
    d.rectangle((14, 190, W - 14, 198), fill=(214, 216, 216))
    for x in (0, W - 1):
        d.line((x, 0, x, H), fill=(150, 150, 148), width=6)
    save(im, "ddm_glazing.jpg")


# ------------------------------------------------------------------ 5. plaza paving: grey-blue tiles, buff brick, pebbles
def tiles():
    S = 512                                    # tile = 2.4 m: 8 x 8 pavers of 0.3 m
    n = 8
    p = S // n
    rng = np.random.default_rng(31)
    img = np.zeros((S, S))
    for i in range(n):
        for j in range(n):
            img[i * p:(i + 1) * p, j * p:(j + 1) * p] = rng.uniform(-0.06, 0.06)
    yy, xx = np.mgrid[0:S, 0:S]
    grout = ((yy % p) < 3) | ((xx % p) < 3)
    hgt = np.where(grout, 0.0, 1.0)
    hgt = blur(hgt, 1.0) + noise(S, S, 32, 3, seed=32) * 0.1
    shade = 0.95 + img - grout * 0.22 + (noise(S, S, 128, 3, seed=33) - 0.5) * 0.12
    save(colorize("#9aa4ad", shade), "ddm_tiles.jpg")
    save(normal_map(hgt, 2.0), "ddm_tiles_n.jpg")


def brick():
    S = 512                                    # tile = 2.4 m: running bond 0.24 x 0.12 m bricks
    bw, bh = S // 10, S // 20
    rng = np.random.default_rng(41)
    img = np.zeros((S, S))
    yy, xx = np.mgrid[0:S, 0:S]
    grout = np.zeros((S, S), bool)
    for r in range(20):
        off = (bw // 2) * (r % 2)
        rows = slice(r * bh, (r + 1) * bh)
        for c in range(-1, 11):
            x0 = c * bw + off
            img[rows, max(0, x0):max(0, min(S, x0 + bw))] = rng.uniform(-0.09, 0.09)
            grout[rows] |= np.abs(xx[rows] - x0) < 2
        grout[r * bh:r * bh + 2] = True
    hgt = blur(np.where(grout, 0.0, 1.0), 0.8)
    shade = 0.95 + img - grout * 0.25 + (noise(S, S, 64, 3, seed=42) - 0.5) * 0.1
    save(colorize("#c99a6e", shade), "ddm_brick.jpg")
    save(normal_map(hgt, 2.0), "ddm_brick_n.jpg")


def pebbles():
    S = 512                                    # tile = 1.6 m of white river pebbles
    rng = np.random.default_rng(51)
    hgt = np.zeros((S, S))
    col = np.zeros((S, S))
    yy, xx = np.mgrid[0:S, 0:S]
    for _ in range(2600):
        cx, cy = rng.uniform(0, S), rng.uniform(0, S)
        rx, ry = rng.uniform(4, 9), rng.uniform(3, 7)
        a = rng.uniform(0, math.pi)
        x0, x1, y0, y1 = int(cx - 10), int(cx + 10), int(cy - 10), int(cy + 10)
        for xo in (0, S, -S):
            for yo in (0, S, -S):
                xs0, xs1, ys0, ys1 = max(0, x0 + xo), min(S, x1 + xo), max(0, y0 + yo), min(S, y1 + yo)
                if xs0 >= xs1 or ys0 >= ys1:
                    continue
                dx = xx[ys0:ys1, xs0:xs1] - cx - xo
                dy = yy[ys0:ys1, xs0:xs1] - cy - yo
                u = (dx * math.cos(a) + dy * math.sin(a)) / rx
                v = (-dx * math.sin(a) + dy * math.cos(a)) / ry
                d = np.sqrt(np.clip(1 - u * u - v * v, 0, 1))
                m = d > hgt[ys0:ys1, xs0:xs1]
                hgt[ys0:ys1, xs0:xs1] = np.where(m, d, hgt[ys0:ys1, xs0:xs1])
                col[ys0:ys1, xs0:xs1] = np.where(m, rng.uniform(-0.1, 0.06), col[ys0:ys1, xs0:xs1])
    shade = 0.62 + 0.42 * hgt + col
    save(colorize("#efe9dc", shade), "ddm_pebble.jpg")
    save(normal_map(hgt, 3.5), "ddm_pebble_n.jpg")


# ------------------------------------------------------------------ 6. boulders, sandstone, rusted beams, bronze
def rock():
    S = 512
    hgt = noise(S, S, 40, 6, seed=61)
    cr = noise(S, S, 120, 3, seed=62)
    sp = granite_speckle(S, S, 63)
    shade = 0.78 + (hgt - 0.5) * 0.55 + sp * 0.45 + (cr - 0.5) * 0.3
    save(colorize("#9d9283", shade), "ddm_rock.jpg")
    save(normal_map(hgt, 5.0), "ddm_rock_n.jpg")


def sandstone():
    S = 512                                    # tile = 2 m, pink-beige with faint bedding strata
    yy, xx = np.mgrid[0:S, 0:S]
    strata = np.sin(yy / 9.0 + noise(S, S, 90, 3, seed=71) * 9) * 0.5 + 0.5
    hgt = noise(S, S, 36, 6, seed=72) * 0.7 + strata * 0.3
    sp = granite_speckle(S, S, 73)
    shade = 0.9 + (hgt - 0.5) * 0.35 + sp * 0.3
    save(colorize("#d2a98a", shade), "ddm_sandstone.jpg")
    save(normal_map(hgt, 4.0), "ddm_sandstone_n.jpg")


def rust():
    W, H = 512, 128                            # along the beam (u) x round it (v)
    yy, xx = np.mgrid[0:H, 0:W]
    grain = np.sin(yy / 2.2 + noise(H, W, 40, 3, seed=81) * 12) * 0.5 + 0.5
    spots = noise(H, W, 18, 4, seed=82)
    shade = 0.78 + grain * 0.16 + (spots - 0.5) * 0.45
    save(colorize("#8e4b2c", shade, noise(H, W, 60, 2, seed=83), 0.3), "ddm_rust.jpg")
    save(normal_map(grain * 0.5 + spots * 0.5, 2.5), "ddm_rust_n.jpg")


def flowers():
    W, H = 512, 256                            # tile = 2 m x 1 m of dense bedding plants
    rng = np.random.default_rng(91)
    img = Image.new("RGB", (W, H), (52, 92, 38))
    d = ImageDraw.Draw(img)
    for _ in range(1600):
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2, 5)
        g = int(rng.uniform(70, 125))
        d.ellipse((x - r * 1.6, y - r, x + r * 1.6, y + r), fill=(g // 2, g, g // 3))
    save(img, "ddm_leaves.jpg")
    for name, cols in (("ddm_flower_y.jpg", [(236, 196, 50), (247, 214, 80), (222, 170, 34)]),
                       ("ddm_flower_r.jpg", [(196, 44, 40), (220, 70, 60), (170, 30, 40)])):
        im = img.copy()
        d = ImageDraw.Draw(im)
        for _ in range(2300):
            x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2.5, 4.5)
            d.ellipse((x - r, y - r, x + r, y + r), fill=cols[int(rng.integers(0, 3))])
        save(im, name)


# ------------------------------------------------------------------ 7. inscription: sandstone face with red-brown calligraphy
def inscription():
    W, H = 2048, 384                           # whole front face of the rock (about 12.4 m x 2.3 m)
    base = np.asarray(Image.open(OUT / "ddm_sandstone.jpg").resize((W // 4, H // 4 * 2)), dtype=float)
    tile = np.tile(base, (2, 4, 1))[:H, :W]
    hgt = noise(H, W, 60, 6, wrap=False, seed=101)
    # block joints (four stones)
    joints = [0.27, 0.51, 0.76]
    jm = np.zeros((H, W))
    yy, xx = np.mgrid[0:H, 0:W]
    for j in joints:
        jx = j * W + 6 * np.sin(yy / 23.0)
        jm = np.maximum(jm, np.clip(1 - np.abs(xx - jx) / 5, 0, 1))
    # calligraphy, carved: text mask -> depression, filled with red-brown paint
    txt = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(txt)
    font = ImageFont.truetype(FONT_CAL, 230)
    s = "南京信息工程大学"
    xs = np.linspace(W * 0.08, W * 0.92, len(s))
    for ch, x in zip(s, xs):
        bb = d.textbbox((0, 0), ch, font=font)
        d.text((x - (bb[2] - bb[0]) / 2 - bb[0], H * 0.5 - (bb[3] - bb[1]) / 2 - bb[1]), ch, font=font, fill=255)
    tm = np.asarray(txt, dtype=float) / 255
    tm_soft = blur(tm, 1.5)
    shade = (0.92 + (hgt - 0.5) * 0.3)[..., None] * (tile / 255 * 0.55 + 0.45)
    col = tile * (0.92 + (hgt - 0.5) * 0.3)[..., None]
    paint = np.array([150, 52, 34], dtype=float)
    col = col * (1 - tm_soft[..., None]) + paint[None, None, :] * tm_soft[..., None] * (0.85 + 0.15 * hgt[..., None])
    col = col * (1 - jm[..., None] * 0.45)
    # edge lip: highlight just below/right of each stroke (carving catches the light)
    lip = np.clip(blur(tm, 2.5) - tm_soft, 0, 1)
    col = col + lip[..., None] * 40
    save(Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)), "ddm_inscription.jpg", 92)
    h2 = hgt * 0.35 + 0.65 - tm_soft * 0.5 - jm * 0.4
    save(normal_map(h2, 4.0, wrap_x=False), "ddm_inscription_n.jpg")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    granite()
    sandstone()
    dragon_column()
    ashlar()
    glazing()
    tiles()
    brick()
    pebbles()
    rock()
    rust()
    flowers()
    inscription()


if __name__ == "__main__":
    main()
