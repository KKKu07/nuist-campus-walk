"""东大门 (east main gate), detailed model — detail-correction session, 2026-11-28.

Sources (all registered to game coordinates, see data/zones/fix_dongdamen/):
  * 480 m nadir photo DJI_20241202160820_0023 (the user's top view), homography to the ortho, rms 0.7 m:
    spindle-shaped green island between the north and south gate lanes, five columns on a west-concave arc at its
    east end, the inscribed rock in front of them, a curved yellow/red flower bed along the island's east edge,
    the round plaza (r ~ 10.8 m) east of the island.
  * user panoramas (data/zones/fix_dongdamen/user_panorama_2.jpg, data/source/航拍/东大门全景.jpg): 九龙柱 — five tall
    dragon-relief columns (stone lions on the outer two, globes on the inner three) + two shorter relief columns with
    drum capitals at each gatehouse (9 in all); long sandstone rock with the red calligraphy 南京信息工程大学; beige
    ashlar gatehouses with a glazed bay; barrier arms, a sentry box with a red umbrella, blue/yellow bollards with
    rails; plaza = buff brick rim with granite kerb blocks, grey-blue tiles, a white pebble field (taiji-like S edge),
    the Big Dipper as seven boulders joined by rust-red beams, and a bronze disc.
Every part stands on the game terrain at its own position (the gate area falls ~1.2 m from the island to the plaza);
the game places the model at the terrain height of its origin (the plaza centre), so local y = terrain - T0.
Nothing solid on the two gate lanes (road_audit.json 590302085 north lane, 404874362 south lane): barrier arms are
modelled raised.

Run (background, never writes to the Blender install):
    set PYTHONDONTWRITEBYTECODE=1
    G:\\Blender\\blender.exe --background --factory-startup --python-use-system-env --python tools\\blender_dongdamen.py
Textures: .venv\\Scripts\\python.exe tools\\ddm_textures.py (data/blender/textures/ddm_*.jpg).
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_landmarks as L  # noqa: E402  (shared mesh builder, materials, preview, export)
from blender_landmarks import MB, Frame, box, cap, cyl, frustum, inset, sphere  # noqa: E402

KEY, TITLE = "dongdamen", "东大门"
O = (1405.5, -520.8)                       # plaza centre = model origin (nadir photo)

L.MAT_SPEC.update({
    "ddm_dragon": ("#cdbfa8", 0.85, 0.0, "ddm_dragon.jpg"),
    "ddm_granite": ("#cfc4b1", 0.8, 0.0, "ddm_granite.jpg"),
    "ddm_ashlar": ("#cfc6b5", 0.85, 0.0, "ddm_ashlar.jpg"),
    "ddm_glazing": ("#6a8493", 0.25, 0.2, "ddm_glazing.jpg"),
    "ddm_tiles": ("#9aa4ad", 0.85, 0.0, "ddm_tiles.jpg"),
    "ddm_brick": ("#c99a6e", 0.9, 0.0, "ddm_brick.jpg"),
    "ddm_pebble": ("#efe9dc", 0.95, 0.0, "ddm_pebble.jpg"),
    "ddm_rock": ("#9d9283", 0.9, 0.0, "ddm_rock.jpg"),
    "ddm_sandstone": ("#d2a98a", 0.9, 0.0, "ddm_sandstone.jpg"),
    "ddm_inscription": ("#d2a98a", 0.85, 0.0, "ddm_inscription.jpg"),
    "ddm_rust": ("#8e4b2c", 0.75, 0.15, "ddm_rust.jpg"),
    "ddm_leaves": ("#4f7c35", 0.95, 0.0, "ddm_leaves.jpg"),
    "ddm_flower_y": ("#e2bf3a", 0.9, 0.0, "ddm_flower_y.jpg"),
    "ddm_flower_r": ("#c23a33", 0.9, 0.0, "ddm_flower_r.jpg"),
    "ddm_bronze": ("#a8834a", 0.32, 0.85, None),
    "ddm_bronze_dark": ("#5e4325", 0.4, 0.8, None),
    "ddm_disc": ("#8c4a2c", 0.45, 0.6, None),
    "ddm_white": ("#ece8e0", 0.7, 0.0, None),
    "ddm_frame": ("#d6d8d8", 0.4, 0.3, None),
    "ddm_umbrella": ("#c8303a", 0.7, 0.0, None),
})

# ------------------------------------------------------------------ terrain (same bilinear triangles as the game)
_T = json.loads((L.ROOT / "web" / "public" / "campus" / "terrain.json").read_text(encoding="utf-8"))
_W, _D = L.CAMPUS["size"]


def terrain(x, z):
    nx, nz, h = _T["nx"], _T["nz"], _T["h"]
    gx, gz = (x + _W / 2) / _W * (nx - 1), (z + _D / 2) / _D * (nz - 1)
    i, k = max(0, min(nx - 2, math.floor(gx))), max(0, min(nz - 2, math.floor(gz)))
    fx, fz = min(1, max(0, gx - i)), min(1, max(0, gz - k))
    ha, hd, hb, hc = h[k * nx + i], h[k * nx + i + 1], h[(k + 1) * nx + i], h[(k + 1) * nx + i + 1]
    v = ha + (hd - ha) * fx + (hb - ha) * fz if fx + fz <= 1 else hc + (hb - hc) * (1 - fx) + (hd - hc) * (1 - fz)
    return v / 10


T0 = terrain(*O)


def gy(x, z):
    """Ground height in model space."""
    return terrain(x, z) - T0


# ------------------------------------------------------------------ small mesh helpers (game coordinates)
def fill(mb, poly, yf, mat, tile=2.4, up=True):
    """Triangulated polygon, every vertex at its own height yf(x, z)."""
    vs = [Vector((x, z, 0)) for x, z in poly]
    for a, b, c in tessellate_polygon([vs]):
        P = [(poly[i][0], yf(*poly[i]), poly[i][1]) for i in (a, b, c)]
        mb.face(P, [(p[0] / tile, -p[2] / tile) for p in P], mat, out=(0, 1 if up else -1, 0))


def band(mb, A, B, ya, yb, mat, along=1.0, ylen=1.0, closed=False, out_sign=None):
    """Vertical strip along polyline A (heights ya[i] .. yb[i])."""
    n = len(A)
    s = 0.0
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        L_ = math.hypot(A[j][0] - A[i][0], A[j][1] - A[i][1])
        P = [(A[i][0], ya[i], A[i][1]), (A[j][0], ya[j], A[j][1]), (A[j][0], yb[j], A[j][1]), (A[i][0], yb[i], A[i][1])]
        U = [(s / along, ya[i] / ylen), ((s + L_) / along, ya[j] / ylen), ((s + L_) / along, yb[j] / ylen), (s / along, yb[i] / ylen)]
        o = None
        if out_sign is not None:
            ex, ez = A[j][0] - A[i][0], A[j][1] - A[i][1]
            o = (ez * out_sign, 0, -ex * out_sign)
        mb.face(P, U, mat, out=o)
        s += L_


def strip(mb, A, B, ya, yb, mat, tile=1.0):
    """Horizontal-ish ribbon between matched polylines A and B."""
    s = 0.0
    for i in range(len(A) - 1):
        L_ = math.hypot(A[i + 1][0] - A[i][0], A[i + 1][1] - A[i][1])
        P = [(A[i][0], ya[i], A[i][1]), (A[i + 1][0], ya[i + 1], A[i + 1][1]), (B[i + 1][0], yb[i + 1], B[i + 1][1]),
             (B[i][0], yb[i], B[i][1])]
        U = [(s / tile, 0), ((s + L_) / tile, 0), ((s + L_) / tile, 1), (s / tile, 1)]
        mb.face(P, U, mat, out=(0, 1, 0))
        s += L_


def blob(mb, c, rx, ry, rz, mat, yaw=0.0, nu=14, nv=8, rough=0.0, seed=0, flat=None):
    """Ellipsoid (optionally lumpy: rocks) with yaw; `flat` cuts the bottom at that absolute height."""
    cx, cy, cz = c
    rnd = random.Random(seed)
    k = [[1 + rnd.uniform(-rough, rough) for _ in range(nu)] for _ in range(nv + 1)]
    for i in range(nu):
        k[0][i], k[nv][i] = k[0][0], k[nv][0]
    ca, sa = math.cos(yaw), math.sin(yaw)

    def P(i, j):
        lat, lon = -math.pi / 2 + math.pi * j / nv, 2 * math.pi * (i % nu) / nu
        f = k[j][i % nu]
        x, y, z = rx * math.cos(lat) * math.cos(lon) * f, ry * math.sin(lat) * f, rz * math.cos(lat) * math.sin(lon) * f
        yy = cy + y
        if flat is not None:
            yy = max(yy, flat)
        return (cx + x * ca - z * sa, yy, cz + x * sa + z * ca)

    for j in range(nv):
        for i in range(nu):
            pts = [P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)]
            m = [sum(q[t] for q in pts) / 4 for t in range(3)]
            mb.face(pts, [(i / nu * 2, j / nv), ((i + 1) / nu * 2, j / nv), ((i + 1) / nu * 2, (j + 1) / nv), (i / nu * 2, (j + 1) / nv)],
                    mat, True, out=(m[0] - cx, m[1] - cy, m[2] - cz))


def bar(mb, a, b, w, y0, y1, mat, bay=1.0):
    """Box beam from plan point a to b (width w), y0..y1."""
    L_ = math.hypot(b[0] - a[0], b[1] - a[1])
    F = Frame((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, math.atan2(b[1] - a[1], b[0] - a[0]))
    box(mb, F, -L_ / 2, L_ / 2, -w / 2, w / 2, y0, y1, mat, top=mat, bay=bay, fh=1.0)


def ring_band(mb, c, r, y0, y1, n, mat):
    cyl(mb, c, r, y0, y1, n, mat, smooth=True)


def offset_line(P, d):
    """Offset an open polyline by d (positive = left of travel direction in map view, i.e. towards -z for eastward)."""
    out = []
    for i in range(len(P)):
        a, b = P[max(0, i - 1)], P[min(len(P) - 1, i + 1)]
        ex, ez = b[0] - a[0], b[1] - a[1]
        L_ = math.hypot(ex, ez) or 1
        nx, nz = ez / L_, -ex / L_
        out.append((P[i][0] + nx * d, P[i][1] + nz * d))
    return out


def lane_edge(pts, x, side, half):
    """z of a lane edge at x: pts = centre polyline (west -> east), side = -1 north edge, +1 south edge."""
    for i in range(len(pts) - 1):
        (x0, z0), (x1, z1) = pts[i], pts[i + 1]
        if min(x0, x1) <= x <= max(x0, x1):
            t = (x - x0) / (x1 - x0)
            return z0 + (z1 - z0) * t + side * half
    return None


NORTH_LANE = [(1349.5, -521.8), (1359.0, -530.2), (1369.0, -536.2), (1381.0, -540.3), (1393.0, -541.1), (1404.5, -538.8),
              (1420.8, -539.5)]
SOUTH_LANE = [(1349.5, -521.8), (1357.0, -517.4), (1367.0, -515.4), (1378.0, -511.9), (1388.0, -508.2), (1396.0, -504.3),
              (1404.0, -499.6)]


# ------------------------------------------------------------------ 1. island
ISLAND = [  # map outline, west tip -> north edge -> east arc -> south edge (nadir, columns C1/C5 sit inside)
    (1355.4, -521.8), (1358.0, -524.3), (1363.2, -527.2), (1368.0, -529.5), (1372.3, -531.4), (1378.0, -532.8),
    (1384.0, -534.0), (1387.3, -535.9), (1390.5, -535.4),
    (1392.3, -532.0), (1393.1, -528.5), (1393.0, -525.0), (1392.4, -521.5), (1391.2, -518.6), (1389.2, -516.3),
    (1386.6, -514.9),
    (1382.3, -514.95), (1379.5, -516.6), (1375.0, -517.9), (1372.3, -518.8), (1367.0, -519.8), (1363.2, -520.4),
    (1358.0, -521.2)]
EAST_ARC = list(range(8, 16))               # NE corner .. S tip (flower beds)
CURB_H, LAWN_H = 0.22, 0.17


def island(mb):
    poly = L.ccw(ISLAND)
    inner = inset(poly, 0.3)
    n = len(poly)
    top = [gy(x, z) + CURB_H for x, z in poly]
    bot = [gy(x, z) - 0.35 for x, z in poly]
    ctr = (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    for i in range(n):                        # granite kerb: outer face + top
        j = (i + 1) % n
        a, b = poly[i], poly[j]
        mx, mz = (a[0] + b[0]) / 2 - ctr[0], (a[1] + b[1]) / 2 - ctr[1]
        L_ = math.hypot(b[0] - a[0], b[1] - a[1])
        mb.face([(a[0], bot[i], a[1]), (b[0], bot[j], b[1]), (b[0], top[j], b[1]), (a[0], top[i], a[1])],
                [(0, 0), (L_ / 1.2, 0), (L_ / 1.2, 0.5), (0, 0.5)], "ddm_granite", out=(mx, 0, mz))
        c, d = inner[j], inner[i]
        yc, yd = gy(*c) + CURB_H, gy(*d) + CURB_H
        mb.face([(a[0], top[i], a[1]), (b[0], top[j], b[1]), (c[0], yc, c[1]), (d[0], yd, d[1])],
                [(0, 0), (L_ / 1.2, 0), (L_ / 1.2, 0.25), (0, 0.25)], "ddm_granite", out=(0, 1, 0))
        # inner kerb face down to the lawn
        mb.face([(d[0], yd, d[1]), (c[0], yc, c[1]), (c[0], gy(*c) + LAWN_H, c[1]), (d[0], gy(*d) + LAWN_H, d[1])],
                None, "ddm_granite", out=(-mx, 0, -mz))
    fill(mb, inner, lambda x, z: gy(x, z) + LAWN_H, "lawn", tile=4.0)
    # paved circle walk on the west lawn (nadir: a ring path round a small lawn)
    c0, r0, r1, nseg = (1371.4, -526.4), 4.3, 5.0, 40
    A = [(c0[0] + r1 * math.cos(2 * math.pi * k / nseg), c0[1] + r1 * math.sin(2 * math.pi * k / nseg)) for k in range(nseg + 1)]
    B = [(c0[0] + r0 * math.cos(2 * math.pi * k / nseg), c0[1] + r0 * math.sin(2 * math.pi * k / nseg)) for k in range(nseg + 1)]
    strip(mb, A, B, [gy(*p) + LAWN_H + 0.03 for p in A], [gy(*p) + LAWN_H + 0.03 for p in B], "ddm_granite", tile=1.2)
    # curved flower beds along the east edge: yellow outside, red inside, on a low leafy bank
    arc = [ISLAND[i] for i in EAST_ARC]
    # inward offsets of the arc (towards the island centre)
    def inward(d):
        out = []
        for i, p in enumerate(arc):
            a, b = arc[max(0, i - 1)], arc[min(len(arc) - 1, i + 1)]
            ex, ez = b[0] - a[0], b[1] - a[1]
            L_ = math.hypot(ex, ez) or 1
            nx, nz = -ez / L_, ex / L_                # left of north->south travel = west = inwards
            if (p[0] + nx - ctr[0]) ** 2 + (p[1] + nz - ctr[1]) ** 2 > (p[0] - ctr[0]) ** 2 + (p[1] - ctr[1]) ** 2:
                nx, nz = -nx, -nz
            out.append((p[0] + nx * d, p[1] + nz * d))
        return out
    for d0, d1, mat in ((0.35, 1.05, "ddm_flower_y"), (1.05, 1.8, "ddm_flower_r")):
        A, B = inward(d0), inward(d1)
        ya = [gy(*p) + LAWN_H + 0.34 for p in A]
        yb = [gy(*p) + LAWN_H + 0.40 for p in B]
        strip(mb, A, B, ya, yb, mat, tile=2.0)
        band(mb, A, None, [gy(*p) + LAWN_H - 0.02 for p in A], ya, "ddm_leaves", along=2.0, ylen=1.0)
        band(mb, B, None, [gy(*p) + LAWN_H - 0.02 for p in B], yb, "ddm_leaves", along=2.0, ylen=1.0)
        for P_, Q_ in ((A[0], B[0]), (A[-1], B[-1])):
            mb.face([(P_[0], gy(*P_) + LAWN_H, P_[1]), (Q_[0], gy(*Q_) + LAWN_H, Q_[1]), (Q_[0], gy(*Q_) + LAWN_H + 0.4, Q_[1]),
                     (P_[0], gy(*P_) + LAWN_H + 0.34, P_[1])], None, "ddm_leaves")
    # clipped shrubs either side of the rock (panorama: round box-leaf bushes)
    for (x, z, r) in ((1389.0, -532.6, 0.95), (1387.2, -517.6, 0.85), (1379.6, -529.6, 0.8), (1379.4, -522.6, 0.75)):
        blob(mb, (x, gy(x, z) + LAWN_H + r * 0.55, z), r, r * 0.75, r, "ddm_leaves", nu=12, nv=7, rough=0.08, seed=int(x * 7))


# ------------------------------------------------------------------ 2. the five dragon columns
COLUMNS = [(1387.3, -534.8), (1384.1, -531.4), (1381.8, -526.1), (1381.4, -520.8), (1382.3, -516.0)]   # north -> south


def facing(c):
    """Unit plan vector from a column towards the plaza (the gate faces east-south-east)."""
    dx, dz = O[0] - c[0], O[1] - c[1]
    L_ = math.hypot(dx, dz)
    return dx / L_, dz / L_


def lion(mb, p, f, scale=1.0):
    """Seated stone lion on a small plinth, facing plan direction f, base at p (x, y, z)."""
    x, y, z = p
    a = math.atan2(f[1], f[0])
    F = Frame(x, z, a)
    s = scale
    box(mb, F, -0.62 * s, 0.62 * s, -0.42 * s, 0.42 * s, y, y + 0.26 * s, "ddm_granite", top="ddm_granite", bay=1, fh=1)
    y += 0.26 * s

    def at(u, h, v):
        px, pz = F.p(u * s, v * s)
        return (px, y + h * s, pz)
    blob(mb, at(-0.22, 0.42, 0), 0.42 * s, 0.38 * s, 0.34 * s, "ddm_granite", yaw=a, nu=14, nv=8)          # haunches
    blob(mb, at(0.12, 0.72, 0), 0.30 * s, 0.46 * s, 0.30 * s, "ddm_granite", yaw=a, nu=14, nv=8)           # chest
    for v in (-0.15, 0.15):                                                                              # forelegs
        px, pz = F.p(0.30 * s, v * s)
        cyl(mb, (px, pz), 0.085 * s, y, y + 0.62 * s, 8, "ddm_granite", top="ddm_granite")
        blob(mb, at(0.36, 0.06, v), 0.13 * s, 0.07 * s, 0.09 * s, "ddm_granite", yaw=a, nu=8, nv=4)       # paws
    blob(mb, at(0.20, 1.12, 0), 0.36 * s, 0.34 * s, 0.38 * s, "ddm_granite", yaw=a, nu=14, nv=8, rough=0.12, seed=5)  # mane
    blob(mb, at(0.36, 1.13, 0), 0.24 * s, 0.24 * s, 0.25 * s, "ddm_granite", yaw=a, nu=12, nv=7)          # face
    blob(mb, at(0.56, 1.06, 0), 0.12 * s, 0.10 * s, 0.13 * s, "ddm_granite", yaw=a, nu=8, nv=5)           # muzzle
    for v in (-0.17, 0.17):
        blob(mb, at(0.30, 1.38, v), 0.07 * s, 0.09 * s, 0.06 * s, "ddm_granite", yaw=a, nu=6, nv=4)       # ears
    blob(mb, at(-0.58, 0.78, 0.12), 0.13 * s, 0.22 * s, 0.13 * s, "ddm_granite", yaw=a, nu=8, nv=5, rough=0.15, seed=9)  # tail


def globe(mb, c, y0):
    """Bronze globe on a short neck, equator band and a tilted meridian ring."""
    x, z = c
    cyl(mb, c, 0.40, y0, y0 + 0.28, 16, "ddm_granite", top="ddm_granite")
    frustum(mb, Frame(x, z, 0), -0.3, 0.3, -0.3, 0.3, y0 + 0.28, y0 + 0.42, 0.08, 0.08, "ddm_bronze_dark", top="ddm_bronze_dark")
    yc, r = y0 + 0.42 + 0.80, 0.80
    sphere(mb, (x, yc, z), r, 28, 16, "ddm_bronze")
    cyl(mb, c, r * 1.025, yc - 0.045, yc + 0.045, 32, "ddm_bronze_dark")
    tilt, n = math.radians(23.5), 32
    pts = []
    for k in range(n + 1):
        t = 2 * math.pi * k / n
        px, py, pz = r * 1.03 * math.cos(t), r * 1.03 * math.sin(t), 0.0
        py, pz = py * math.cos(tilt) - pz * math.sin(tilt), py * math.sin(tilt) + pz * math.cos(tilt)
        pts.append((x + px, yc + py, z + pz))
    for a, b in zip(pts, pts[1:]):
        L.beam(mb, a, b, 0.07, "ddm_bronze_dark")
    cyl(mb, c, 0.06, yc + r, yc + r + 0.22, 8, "ddm_bronze_dark", top="ddm_bronze_dark")


def dragon_column(mb, c, g, shaft_r=0.78, shaft_top=12.0, plinth=1.7, ornament=None, f=(1, 0), drum=False):
    """Granite plinth, moulded base, dragon-relief shaft, lotus capital, abacus; ornament = 'lion' | 'globe' | None."""
    x, z = c
    a = math.atan2(f[1], f[0])
    F = Frame(x, z, a)
    hp = plinth / 2
    box(mb, F, -hp, hp, -hp, hp, g - 0.3, g + 0.55, "ddm_granite", top="ddm_granite", bay=plinth, fh=0.85)
    frustum(mb, F, -hp, hp, -hp, hp, g + 0.55, g + 0.75, 0.16, 0.16, "ddm_granite", top="ddm_granite")
    cyl(mb, c, shaft_r + 0.22, g + 0.75, g + 1.05, 24, "ddm_granite", top="ddm_granite")
    cyl(mb, c, shaft_r + 0.16, g + 1.05, g + 1.25, 24, "ddm_granite", r1=shaft_r + 0.06)
    cyl(mb, c, shaft_r, g + 1.25, g + shaft_top, 24, "ddm_dragon")
    cyl(mb, c, shaft_r + 0.07, g + shaft_top, g + shaft_top + 0.22, 24, "ddm_granite")
    if drum:   # gatehouse columns: plain drum capital (panorama: light, slightly wider than the shaft)
        cyl(mb, c, shaft_r + 0.16, g + shaft_top + 0.22, g + shaft_top + 0.95, 24, "ddm_granite", top="ddm_granite")
        cyl(mb, c, shaft_r + 0.02, g + shaft_top + 0.95, g + shaft_top + 1.1, 24, "ddm_granite", top="ddm_granite")
        return g + shaft_top + 1.1
    cyl(mb, c, shaft_r + 0.07, g + shaft_top + 0.22, g + shaft_top + 0.62, 24, "ddm_granite", r1=shaft_r + 0.27)  # lotus flare
    cyl(mb, c, shaft_r + 0.30, g + shaft_top + 0.62, g + shaft_top + 0.92, 24, "ddm_granite", top="ddm_granite")  # abacus
    ytop = g + shaft_top + 0.92
    if ornament == "globe":
        globe(mb, c, ytop)
    elif ornament == "lion":
        lion(mb, (x, ytop, z), f, 1.05)
    return ytop


# ------------------------------------------------------------------ 3. inscribed rock on its planter
ROCK_C, ROCK_A = (1386.8, -524.75), math.atan2(-11.5, 2.4)     # axis south->north end, +v faces the plaza


def rock(mb):
    F = Frame(ROCK_C[0], ROCK_C[1], ROCK_A)
    if F.vec(0, 1)[0] < 0:
        F = Frame(ROCK_C[0], ROCK_C[1], ROCK_A + math.pi)
    g = max(gy(*F.p(u, v)) for u in (-7, 0, 7) for v in (-1.7, 1.9)) + CURB_H
    # planter: granite kerb, lawn top, low hedge along the front
    box(mb, F, -7.2, 7.2, -1.8, 2.3, g - 0.45, g + 0.28, "ddm_granite", bay=1.2, fh=0.6)
    cap(mb, F.rect(-7.0, 7.0, -1.6, 2.1), g + 0.26, "lawn", tile=4.0)
    box(mb, F, -6.6, 6.6, 1.55, 2.05, g + 0.26, g + 0.62, "ddm_leaves", top="ddm_leaves", bay=2.0, fh=1.0)
    y0 = g + 0.22
    Lh = 6.2
    joints = (-2.85, 0.12, 3.22)

    def top(u):          # four blocks: domed tops, dips at the joints, rounded ends
        h = 2.32 + 0.22 * math.sin(u * 0.9 + 0.7) + 0.12 * math.sin(u * 2.3)
        for j in joints:
            h -= 0.32 * math.exp(-((u - j) / 0.35) ** 2)
        h -= 0.9 * max(0.0, (abs(u) - 5.0) / 1.2) ** 2
        return h

    us = [-Lh + 2 * Lh * k / 48 for k in range(49)]
    fr = lambda y, h: 0.78 - 0.20 * (y / h)     # front face leans back slightly
    bk = lambda y, h: -0.98 + 0.40 * (y / h)
    for k in range(48):
        u0, u1 = us[k], us[k + 1]
        h0, h1 = top(u0), top(u1)
        # front (inscription): u -> texture u, y -> texture v (text band centred at ~1.25 m)
        Pf = [F.p3(u0, y0, fr(0, h0)), F.p3(u1, y0, fr(0, h1)), F.p3(u1, y0 + h1, fr(h1, h1)), F.p3(u0, y0 + h0, fr(h0, h0))]
        Uf = [((u0 + Lh) / (2 * Lh), 0.0), ((u1 + Lh) / (2 * Lh), 0.0), ((u1 + Lh) / (2 * Lh), h1 / 2.6), ((u0 + Lh) / (2 * Lh), h0 / 2.6)]
        mb.face(Pf, Uf, "ddm_inscription", out=(*_plan(F.vec(0, 1)), ))
        # back
        Pb = [F.p3(u1, y0, bk(0, h1)), F.p3(u0, y0, bk(0, h0)), F.p3(u0, y0 + h0, bk(h0, h0)), F.p3(u1, y0 + h1, bk(h1, h1))]
        mb.face(Pb, [(u1 / 2, 0), (u0 / 2, 0), (u0 / 2, h0 / 2), (u1 / 2, h1 / 2)], "ddm_sandstone", out=_plan(F.vec(0, -1)))
        # top: front edge -> ridge -> back edge
        r0, r1 = h0 + 0.16 * min(1, h0 / 1.6), h1 + 0.16 * min(1, h1 / 1.6)
        for (va0, ya0, va1, ya1, vb0, yb0, vb1, yb1) in (
                (fr(h0, h0), h0, fr(h1, h1), h1, -0.15, r0, -0.15, r1),
                (-0.15, r0, -0.15, r1, bk(h0, h0), h0, bk(h1, h1), h1)):
            P = [F.p3(u0, y0 + ya0, va0), F.p3(u1, y0 + ya1, va1), F.p3(u1, y0 + yb1, vb1), F.p3(u0, y0 + yb0, vb0)]
            mb.face(P, [(u0 / 2, va0 / 2), (u1 / 2, va1 / 2), (u1 / 2, vb1 / 2), (u0 / 2, vb0 / 2)], "ddm_sandstone", out=(0, 1, 0))
    for u, sgn in ((-Lh, -1), (Lh, 1)):          # end caps
        h = top(u)
        P = [F.p3(u, y0, fr(0, h)), F.p3(u, y0 + h, fr(h, h)), F.p3(u, y0 + h + 0.1, -0.15), F.p3(u, y0 + h, bk(h, h)),
             F.p3(u, y0, bk(0, h))]
        mb.face(P, [(p[0] / 2, p[1] / 2) for p in P], "ddm_sandstone", out=_plan(F.vec(sgn, 0)))


def _plan(v):
    return (v[0], 0.0, v[1])


# ------------------------------------------------------------------ 4. gatehouses, barriers, booth, bollards
HOUSES = [((1387.5, -553.0), -0.225, 1), ((1374.4, -500.6), 0.348 + math.pi, -1)]   # (centre, angle, u-sign of the east end)


def gatehouse(mb, c, ang, se):
    F = Frame(c[0], c[1], ang)                                # +v = towards the gate lane
    corners = [F.p(u, v) for u in (-6.4, 6.4) for v in (-4.0, 4.8)]
    g = min(gy(*p) for p in corners)
    gh = max(gy(*p) for p in corners)
    # stone plinth, ashlar walls, projecting cornice, parapet
    box(mb, F, -6.2, 6.2, -3.8, 3.8, g - 0.4, gh + 0.55, "ddm_granite", bay=1.2, fh=0.6)
    box(mb, F, -6.0, 6.0, -3.6, 3.6, gh + 0.55, gh + 4.6, "ddm_ashlar", bay=2.4, fh=2.4)
    box(mb, F, -6.35, 6.35, -3.95, 3.95, gh + 4.6, gh + 4.95, "ddm_granite", top="ddm_granite", bot="ddm_granite", bay=1.2, fh=0.35)
    box(mb, F, -6.0, 6.0, -3.6, 3.6, gh + 4.95, gh + 5.45, "ddm_ashlar", bay=2.4, fh=2.4)
    box(mb, F, -6.15, 6.15, -3.75, 3.75, gh + 5.45, gh + 5.6, "ddm_granite", top="roof_flat", bay=1.2, fh=0.15)
    box(mb, F, -2.2, 2.2, -1.6, 1.6, gh + 5.6, gh + 6.3, "ddm_ashlar", top="ddm_granite", bay=2.4, fh=2.4)   # roof stair house
    # glazed bay on the lane side, wrapping round the east end
    u_e = 6.0 * se
    ua, ub = (u_e - 7.2 * se, u_e + 0.6 * se)
    u0, u1 = min(ua, ub), max(ua, ub)
    box(mb, F, u0, u1, 3.6, 4.7, gh + 0.0, gh + 0.7, "ddm_granite", top="ddm_granite", bay=1.2, fh=0.7)
    box(mb, F, u0 + 0.1, u1 - 0.1, 3.6, 4.6, gh + 0.7, gh + 3.9, "ddm_glazing", bay=1.5, fh=3.2)
    box(mb, F, u0 - 0.1, u1 + 0.1, 3.5, 4.85, gh + 3.9, gh + 4.25, "ddm_granite", top="ddm_granite", bot="ddm_granite", bay=1.2, fh=0.35)
    # east end: tall window band
    ue = 6.0 * se + 0.03 * se
    P = [F.p3(ue, gh + 1.0, -2.6), F.p3(ue, gh + 1.0, 2.6), F.p3(ue, gh + 3.8, 2.6), F.p3(ue, gh + 3.8, -2.6)]
    mb.face(P, [(0, 0), (3.5, 0), (3.5, 0.9), (0, 0.9)], "ddm_glazing", out=_plan(F.vec(se, 0)))
    # door on the lane side, west of the bay
    ud = u_e - 9.0 * se
    P = [F.p3(ud - 0.8, gh + 0.55, 3.63), F.p3(ud + 0.8, gh + 0.55, 3.63), F.p3(ud + 0.8, gh + 3.0, 3.63), F.p3(ud - 0.8, gh + 3.0, 3.63)]
    mb.face(P, [(0, 0.2), (1, 0.2), (1, 0.85), (0, 0.85)], "ddm_glazing", out=_plan(F.vec(0, 1)))
    # two relief columns with drum capitals at the east corners (panorama: same distance as the lane)
    f = (math.cos(ang) * se, math.sin(ang) * se)
    for v in (-3.3, 3.6):
        cp = F.p(6.0 * se + 0.95 * se, v)
        dragon_column(mb, cp, gy(*cp), shaft_r=0.56, shaft_top=8.6, plinth=1.35, f=f, drum=True)
    return F, gh


def barrier(mb, p, along):
    """Barrier cabinet with the arm raised (vertical), red/white stripes."""
    x, z = p
    g = gy(x, z)
    F = Frame(x, z, along)
    box(mb, F, -0.28, 0.28, -0.22, 0.22, g, g + 1.05, "container_yellow", top="ddm_white", bay=0.6, fh=1.05)
    for k in range(8):
        mat = "sign_red" if k % 2 == 0 else "ddm_white"
        L.beam(mb, (x, g + 1.05 + k * 0.5, z), (x, g + 1.05 + (k + 1) * 0.5, z), 0.09, mat)


def folding_gate(mb, p, along, length=1.8):
    x, z = p
    g = gy(x, z)
    F = Frame(x, z, along)
    box(mb, F, -length / 2, length / 2, -0.25, 0.25, g, g + 1.55, "ddm_frame", top="ddm_frame", bay=0.3, fh=1.55)
    box(mb, F, -length / 2 - 0.2, -length / 2, -0.3, 0.3, g, g + 1.75, "container_yellow", top="ddm_white", bay=0.3, fh=1.75)


def sentry(mb, p, along):
    x, z = p
    g = gy(x, z)
    F = Frame(x, z, along)
    box(mb, F, -0.8, 0.8, -0.8, 0.8, g, g + 0.5, "ddm_granite", top="ddm_granite", bay=1.6, fh=0.5)
    box(mb, F, -0.75, 0.75, -0.75, 0.75, g + 0.5, g + 2.45, "ddm_glazing", bay=1.5, fh=3.2)
    box(mb, F, -0.95, 0.95, -0.95, 0.95, g + 2.45, g + 2.7, "ddm_frame", top="ddm_frame", bot="ddm_frame", bay=1.9, fh=0.25)
    box(mb, F, -0.45, 0.45, 0.96, 1.0, g + 2.0, g + 2.4, "bus_blue", bay=0.9, fh=0.4)          # blue badge sign
    # red umbrella beside it
    ux, uz = F.p(2.2, 0.6)
    ug = gy(ux, uz)
    cyl(mb, (ux, uz), 0.05, ug, ug + 2.3, 8, "pole", top="pole")
    cyl(mb, (ux, uz), 1.6, ug + 1.95, ug + 2.5, 12, "ddm_umbrella", r1=0.05, smooth=False)
    cyl(mb, (ux, uz), 1.6, ug + 1.93, ug + 1.95, 12, "ddm_umbrella", smooth=False)


def bollard_row(mb, pts):
    """Blue posts with yellow bands and two grey rails (panorama)."""
    prev = None
    for x, z in pts:
        g = gy(x, z)
        cyl(mb, (x, z), 0.09, g, g + 0.62, 10, "bus_blue", top="bus_blue")
        cyl(mb, (x, z), 0.095, g + 0.62, g + 0.78, 10, "container_yellow", top="container_yellow")
        cyl(mb, (x, z), 0.16, g, g + 0.05, 10, "container_yellow", top="container_yellow")
        if prev:
            px, pz, pg = prev
            for h in (0.42, 0.72):
                L.beam(mb, (px, pg + h, pz), (x, g + h, z), 0.045, "pole")
        prev = (x, z, g)


# ------------------------------------------------------------------ 5. Big Dipper plaza
def plaza(mb):
    R_out, R_tile = 10.75, 9.45
    rim = [(O[0] + R_out * math.cos(t), O[1] + R_out * math.sin(t)) for t in [2 * math.pi * k / 48 for k in range(48)]]
    yP = max(0.0, max(gy(*p) for p in rim), gy(*O)) + 0.06
    ylow = min(gy(*p) for p in rim) - 0.3
    n = 64
    ang = [2 * math.pi * k / n for k in range(n + 1)]
    outer = [(O[0] + R_out * math.cos(t), O[1] + R_out * math.sin(t)) for t in ang]
    mid = [(O[0] + R_tile * math.cos(t), O[1] + R_tile * math.sin(t)) for t in ang]
    # skirt (where the ground falls away) + brick rim + tile field
    band(mb, outer, None, [ylow] * len(outer), [yP] * len(outer), "ddm_brick", along=2.4, ylen=2.4)
    for i in range(n):
        P = [(outer[i][0], yP, outer[i][1]), (outer[i + 1][0], yP, outer[i + 1][1]), (mid[i + 1][0], yP, mid[i + 1][1]),
             (mid[i][0], yP, mid[i][1])]
        mb.face(P, [(p[0] / 2.4, -p[2] / 2.4) for p in P], "ddm_brick", out=(0, 1, 0))
    fill(mb, mid[:-1], lambda x, z: yP + 0.005, "ddm_tiles", tile=2.4)
    # granite kerb blocks round the rim (low, so the plaza stays walkable: < 0.38 m)
    for k in range(34):
        t = 2 * math.pi * (k + 0.5) / 34
        c = (O[0] + (R_out + 0.2) * math.cos(t), O[1] + (R_out + 0.2) * math.sin(t))
        F = Frame(c[0], c[1], t + math.pi / 2)
        box(mb, F, -0.55, 0.55, -0.2, 0.2, yP - 0.1, yP + 0.3, "ddm_granite", top="ddm_granite", bay=1.1, fh=0.4)
    # pebble field: yin half of a taiji (S edge), edged with a thin granite strip
    C, R, th = (1406.4, -520.2), 7.3, math.radians(205)
    loc = []
    for k in range(25):                          # big arc, local 90 -> 270 deg
        a = math.pi / 2 + math.pi * k / 24
        loc.append((R * math.cos(a), R * math.sin(a)))
    for k in range(1, 13):                       # small arc centred (0, -R/2): 270 -> 450 deg (bulges +x)
        a = 1.5 * math.pi + math.pi * k / 12
        loc.append((R / 2 * math.cos(a), -R / 2 + R / 2 * math.sin(a)))
    for k in range(1, 12):                       # small arc centred (0, +R/2): 270 -> 90 deg via 180 (bulges -x)
        a = 1.5 * math.pi - math.pi * k / 12
        loc.append((R / 2 * math.cos(a), R / 2 + R / 2 * math.sin(a)))
    peb = [(C[0] + lx * math.cos(th) - ly * math.sin(th), C[1] - (lx * math.sin(th) + ly * math.cos(th))) for lx, ly in loc]
    fill(mb, peb, lambda x, z: yP + 0.03, "ddm_pebble", tile=1.6)
    edge = peb + [peb[0]]
    strip(mb, edge, offset_line(edge, 0.14), [yP + 0.06] * len(edge), [yP + 0.06] * len(edge), "ddm_granite", tile=1.2)
    # bronze disc (nadir: west of the centre, on the tiles)
    dc = (1400.9, -522.6)
    cyl(mb, dc, 2.05, yP, yP + 0.07, 40, "ddm_granite", top="ddm_granite", smooth=False)
    cyl(mb, dc, 1.85, yP + 0.07, yP + 0.1, 40, "ddm_disc", top="ddm_disc", smooth=False)
    cyl(mb, dc, 0.9, yP + 0.1, yP + 0.12, 32, "ddm_bronze", top="ddm_bronze", smooth=False)
    # the Big Dipper: seven boulders joined by rust-red beams (bowl closed, handle to the south-west)
    stars = [(0.0, 0.0), (0.05, -1.0), (1.45, -1.25), (1.75, -0.35), (2.8, -0.25), (3.75, -0.1), (4.75, -0.75)]
    s, phi = 2.15, math.radians(200)
    cx = sum(p[0] for p in stars) / 7
    cz = sum(p[1] for p in stars) / 7
    D0 = (1407.6, -518.6)
    pos = []
    for u, v in stars:
        lx, ly = (u - cx) * s, (v - cz) * s
        pos.append((D0[0] + lx * math.cos(phi) - ly * math.sin(phi), D0[1] - (lx * math.sin(phi) + ly * math.cos(phi))))
    for i, (a, b) in enumerate(((0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 5), (5, 6))):
        pa, pb = pos[a], pos[b]
        L_ = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        ux_, uz_ = (pb[0] - pa[0]) / L_, (pb[1] - pa[1]) / L_
        bar(mb, (pa[0] + ux_ * 0.5, pa[1] + uz_ * 0.5), (pb[0] - ux_ * 0.5, pb[1] - uz_ * 0.5), 0.44, yP + 0.03, yP + 0.34, "ddm_rust")
    for k, (x, z) in enumerate(pos):
        r = 0.62 + 0.12 * ((k * 37) % 5) / 4
        blob(mb, (x, yP + 0.22, z), r, r * 0.62, r * 0.85, "ddm_rock", yaw=k * 0.9, nu=12, nv=7, rough=0.16, seed=k + 3,
             flat=yP + 0.02)
    return yP


# ------------------------------------------------------------------ build
def m_dongdamen(coll):
    mb = MB(TITLE, O)
    island(mb)
    for k, c in enumerate(COLUMNS):
        g = gy(*c) + CURB_H
        dragon_column(mb, c, g, ornament="lion" if k in (0, 4) else "globe", f=facing(c))
    rock(mb)
    for c, ang, se in HOUSES:
        gatehouse(mb, c, ang, se)
    # barrier cabinets (arms raised), folding gates, booth, bollard rows - all outside the lane edges
    nb = (1388.4, lane_edge(NORTH_LANE, 1388.4, -1, 4.25) - 0.95)
    barrier(mb, nb, 0.0)
    folding_gate(mb, (1391.0, lane_edge(NORTH_LANE, 1391.0, -1, 4.25) - 1.0), math.radians(-4))
    sb = (1381.2, lane_edge(SOUTH_LANE, 1381.2, 1, 4.0) + 0.95)
    barrier(mb, sb, 0.0)
    folding_gate(mb, (1384.0, lane_edge(SOUTH_LANE, 1384.0, 1, 4.0) + 1.0), math.atan2(-3.7, 10))
    sentry(mb, (1396.6, lane_edge(NORTH_LANE, 1396.6, -1, 4.25) - 2.1), math.radians(-6))
    bollard_row(mb, [(x, lane_edge(NORTH_LANE, x, -1, 4.25) - 0.9) for x in [1399.5 + 1.7 * k for k in range(7)]])
    bollard_row(mb, [(x, lane_edge(SOUTH_LANE, x, 1, 4.0) + 0.9) for x in [1388.5 + 1.7 * k for k in range(6)]])
    plaza(mb)
    obj = mb.build(coll)
    return dict(objs=[obj], origin=O, replaces=[], replaces_poi="东大门", replaces_names=["东大门(poi 装饰)"], height=15.6,
                cam=(70, 26), focus=(1392.0, 5.0, -526.0, 36.0))


def main():
    for d in (L.BL, L.PREV, L.MODELS):
        d.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_homefile(use_empty=True)
    L._MATS.clear()
    coll = bpy.data.collections.new(TITLE)
    bpy.context.scene.collection.children.link(coll)
    info = m_dongdamen(coll)
    objs = info["objs"]
    tris = L.tri_count(objs)
    glb = L.MODELS / f"{KEY}.glb"
    L.export_glb(objs, glb)
    if "--no-render" not in sys.argv:
        L.setup_preview(objs, KEY, info["cam"], info["focus"], info["origin"])
        bpy.ops.render.render(write_still=True)
        sc = bpy.context.scene
        for name, cam, focus in ((f"{KEY}_2.jpg", (84, 7), (1388.0, 6.0, -525.0, 20.0)),
                                 (f"{KEY}_3.jpg", (150, 32), (1396.0, 3.0, -522.0, 30.0))):
            ctr = Vector((focus[0] - O[0], -(focus[2] - O[1]), focus[1]))
            L.aim_camera(ctr, focus[3], cam)
            sc.render.filepath = str(L.PREV / name)
            bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(L.BL / f"{KEY}.blend"), compress=True, relative_remap=True)
    # models.json: replace only this entry, keep the order
    mj = L.BL / "models.json"
    entries = json.loads(mj.read_text(encoding="utf-8"))
    e = dict(name=TITLE, file=f"models/{KEY}.glb", x=O[0], z=O[1], rotY=0, replaces=[], replaces_names=info["replaces_names"],
             height=info["height"], tris=tris, replaces_poi="东大门")
    for i, old in enumerate(entries):
        if old["file"] == e["file"]:
            entries[i] = e
            break
    else:
        entries.append(e)
    mj.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[dongdamen] tris {tris}, T0 {T0:.2f}, glb {glb.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
