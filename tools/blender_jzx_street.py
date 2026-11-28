"""东苑集装箱美食街 — street furniture between the container shops (dongyuan_jzx.glb) and 硕园5栋.
Detail-correction session, 2026-11-28, from the user photo data/zones/fix_dongyuan_jzx/user_photo.jpg (taken from
the west end, looking east along the street) — only what the photo shows clearly:
  * three food trucks parked along the dorm wall, cabs to the west, serving hatch facing the shops:
    pink/white (nearest), cream with a grey-green roof (opposite 沪溪河桃酥), green/white (further east);
    artificial-turf mats under them;
  * a big hydrangea mound (blue / purple / pink) on turf just west of the pink truck;
  * e-bike bays: white bars across the street on the dorm side with dark-grey accent bars between them, private
    e-bikes (white / black / yellow trim, not 7ma) parked in some of them;
  * an orange bench with blue legs and a round back in front of 购好超市; two yellow A-frame caution signs and a
    yellow bin at 芒可; three black queue stanchions with a green sign by 沪溪河桃酥;
  * the planter garden at the west end (kerb, gravel, round topiary, a cloud-pruned tree) and the golden flower stand.
The paving bands themselves (red-brown pavers along the shops, grey tiles beyond) are roads in road_audit.json
(jzx-brick + 1316175151) so they follow the terrain; everything here stands on top of them (+0.21 m).
Not visible / unclear in the photo (street lamps, the far pink object, other bollards) is left out and listed in
docs/questions/jzx_street.md.

Run: G:\\Blender\\blender.exe --background --factory-startup --python-use-system-env --python tools\\blender_jzx_street.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_landmarks as L  # noqa: E402
from blender_landmarks import MB, Frame, box, cyl  # noqa: E402
from blender_dongdamen import blob, fill, terrain  # noqa: E402  (also registers the ddm_* materials)

KEY, TITLE = "jzx_street", "东苑美食街街面"
P0 = (784.1, -684.8)                          # back line of the container strip (extra_buildings jzx-*)
_L = math.hypot(867.2 - 784.1, -705.8 + 684.8)
U = ((867.2 - 784.1) / _L, (-705.8 + 684.8) / _L)     # along the street, eastwards
N = (-U[1], U[0])                             # across, towards 硕园5栋 (south)
FRONT = 5.5                                   # shop fronts at o = 5.5
DORM_A, DORM_B = (791.2, -673.4), (878.6, -687.8)     # 硕园5栋 north facade


def pos(s, o):
    return (P0[0] + U[0] * s + N[0] * o, P0[1] + U[1] * s + N[1] * o)


def o_dorm(s):
    """Offset of the dorm facade at along-position s."""
    ax, az = pos(s, 0)
    dx, dz = DORM_B[0] - DORM_A[0], DORM_B[1] - DORM_A[1]
    # ax + N*o = A + t*d
    det = N[0] * (-dz) - N[1] * (-dx)
    o = ((DORM_A[0] - ax) * (-dz) - (DORM_A[1] - az) * (-dx)) / det
    return o


O = pos(40.0, 11.0)                           # model origin, mid-street
ANG = math.atan2(U[1], U[0])

L.MAT_SPEC.update({
    "jzx_pink": ("#e58ea6", 0.5, 0.1, None),
    "jzx_cream": ("#efe6cf", 0.5, 0.1, None),
    "jzx_sage": ("#7d8f84", 0.5, 0.1, None),
    "jzx_green": ("#2f6b4c", 0.5, 0.1, None),
    "jzx_truckwhite": ("#f3f3ef", 0.45, 0.1, None),
    "jzx_glass": ("#2d3b45", 0.15, 0.3, None),
    "jzx_hatch": ("#3a3330", 0.6, 0.0, None),
    "jzx_tyre": ("#1d1d1f", 0.9, 0.0, None),
    "jzx_chrome": ("#cfd3d6", 0.25, 0.85, None),
    "jzx_turf": ("#4f9a3a", 0.95, 0.0, "green_roof.jpg"),
    "jzx_bar_white": ("#e9e5da", 0.8, 0.0, None),
    "jzx_bar_dark": ("#5b5f63", 0.85, 0.0, None),
    "jzx_hyd_blue": ("#6f8fd8", 0.8, 0.0, None),
    "jzx_hyd_purple": ("#8d7ad0", 0.8, 0.0, None),
    "jzx_hyd_pink": ("#e59ab8", 0.8, 0.0, None),
    "jzx_hyd_lilac": ("#c9b8ea", 0.8, 0.0, None),
    "jzx_orange": ("#ec6f22", 0.55, 0.05, None),
    "jzx_blue": ("#2459b5", 0.5, 0.1, None),
    "jzx_yellow": ("#f2c230", 0.6, 0.0, None),
    "jzx_black": ("#1c1d1f", 0.5, 0.2, None),
    "jzx_signgreen": ("#1f6b45", 0.6, 0.0, None),
    "jzx_concrete": ("#bdbab2", 0.9, 0.0, "concrete.jpg"),
    "jzx_gravel": ("#8b8a86", 0.95, 0.0, "ddm_pebble.jpg"),
    "jzx_gold": ("#d9a93a", 0.6, 0.2, None),
    "jzx_wrap": ("#bcd6ec", 0.5, 0.0, None),
    "jzx_topiary": ("#8fae3a", 0.9, 0.0, "ddm_leaves.jpg"),
    "jzx_trunk": ("#6b4a33", 0.9, 0.0, None),
    "eb_white": ("#efefec", 0.4, 0.1, None),
    "eb_black": ("#202124", 0.45, 0.1, None),
    "eb_grey": ("#9ea3a8", 0.4, 0.2, None),
    "eb_yellow": ("#e8c23a", 0.45, 0.1, None),
})

BASE = terrain(*O)
LIFT = 0.21                                   # top of the paving ribbons above the terrain


def gy(x, z):
    return terrain(x, z) - BASE + LIFT


# ------------------------------------------------------------------ helpers
def hcyl(mb, F, u, y, v0, v1, r, n, mat, cap_mat=None):
    """Cylinder with its axis across the frame (along v): wheels."""
    pts = [(u + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    for k in range(n):
        (a0, b0), (a1, b1) = pts[k], pts[(k + 1) % n]
        am = 2 * math.pi * (k + 0.5) / n
        nu, ny = math.cos(am), math.sin(am)
        o = F.vec(nu, 0)
        mb.face([F.p3(a0, b0, v0), F.p3(a1, b1, v0), F.p3(a1, b1, v1), F.p3(a0, b0, v1)], None, mat, True, out=(o[0], ny, o[1]))
    for v, sg in ((v0, -1), (v1, 1)):
        o = F.vec(0, sg)
        mb.face([F.p3(a, b, v) for a, b in pts], None, cap_mat or mat, out=(o[0], 0, o[1]))


def deck_quad(mb, corners, y_off, mat):
    """Flat decal on the paving: corners in plan, each at its own height."""
    P = [(x, gy(x, z) + y_off, z) for x, z in corners]
    mb.face(P, [(p[0] / 2, -p[2] / 2) for p in P], mat, out=(0, 1, 0))


def strip_so(mb, s0, s1, o0, o1, y_off, mat, step=2.0):
    """Decal rectangle in street coordinates, split along s so it follows the terrain."""
    n = max(1, math.ceil((s1 - s0) / step))
    for k in range(n):
        a, b = s0 + (s1 - s0) * k / n, s0 + (s1 - s0) * (k + 1) / n
        deck_quad(mb, [pos(a, o0), pos(b, o0), pos(b, o1), pos(a, o1)], y_off, mat)


# ------------------------------------------------------------------ food truck
TRUCKS = {
    "pink": dict(lower="jzx_pink", upper="jzx_truckwhite", roof="jzx_truckwhite", awn="jzx_pink"),
    "cream": dict(lower="jzx_cream", upper="jzx_cream", roof="jzx_sage", awn="jzx_sage"),
    "green": dict(lower="jzx_green", upper="jzx_truckwhite", roof="jzx_green", awn="jzx_green"),
}


def truck(mb, s_mid, style):
    """Retro food van parked along the dorm wall: cab to the west (-u), hatch towards the shops (-v of the street)."""
    st = TRUCKS[style]
    od = o_dorm(s_mid)
    c = pos(s_mid, od - 1.45)
    F = Frame(c[0], c[1], ANG + math.pi)      # +u = west (cab), +v = towards the shops
    g = min(gy(*F.p(u, v)) for u in (-2.3, 2.3) for v in (-1.0, 1.0))
    y0 = g + 0.38
    hl, hw = 2.3, 0.98
    # body: lower band, upper box, rounded roof
    box(mb, F, -hl, hl - 0.35, -hw, hw, y0, y0 + 0.75, st["lower"], bot="jzx_tyre", bay=4.6, fh=1)
    box(mb, F, -hl, 0.9, -hw, hw, y0 + 0.75, y0 + 2.0, st["upper"], bay=3.2, fh=1.25)
    L.frustum(mb, F, -hl, 0.9, -hw, hw, y0 + 2.0, y0 + 2.22, 0.12, 0.12, st["roof"], top=st["roof"])
    # cab: lower nose + cab box + raked windscreen
    box(mb, F, hl - 0.35, hl, -hw + 0.05, hw - 0.05, y0, y0 + 0.72, st["lower"], top=st["lower"], bay=1, fh=1)
    box(mb, F, 0.9, 1.95, -hw, hw, y0 + 0.75, y0 + 1.85, st["upper"], bay=1, fh=1)
    L.frustum(mb, F, 0.9, 1.95, -hw, hw, y0 + 1.85, y0 + 2.0, 0.05, 0.08, st["roof"], top=st["roof"])
    mb.face([F.p3(1.95, y0 + 0.78, -hw + 0.08), F.p3(1.95, y0 + 0.78, hw - 0.08), F.p3(1.8, y0 + 1.78, hw - 0.12),
             F.p3(1.8, y0 + 1.78, -hw + 0.12)], None, "jzx_glass", out=(*_pl(F.vec(1, 0)),))
    box(mb, F, 0.9, 1.95, -hw - 0.005, hw + 0.005, y0 + 1.05, y0 + 1.65, "jzx_glass", bay=1, fh=1)   # side windows
    box(mb, F, hl - 0.05, hl + 0.08, -hw + 0.05, hw - 0.05, y0 + 0.12, y0 + 0.3, "jzx_chrome", top="jzx_chrome", bay=1, fh=1)
    box(mb, F, -hl - 0.08, -hl + 0.05, -hw + 0.05, hw - 0.05, y0 + 0.12, y0 + 0.3, "jzx_chrome", top="jzx_chrome", bay=1, fh=1)
    for v in (-0.62, 0.62):                                                           # headlights
        cyl(mb, F.p(hl + 0.01, v), 0.11, y0 + 0.45, y0 + 0.62, 10, "jzx_chrome", top="jzx_chrome")
    # serving hatch on the shop side: dark opening, counter, awning propped up
    vh = hw + 0.01
    mb.face([F.p3(-1.9, y0 + 0.95, vh), F.p3(0.55, y0 + 0.95, vh), F.p3(0.55, y0 + 1.8, vh), F.p3(-1.9, y0 + 1.8, vh)],
            None, "jzx_hatch", out=(*_pl(F.vec(0, 1)),))
    box(mb, F, -1.95, 0.6, hw, hw + 0.3, y0 + 0.9, y0 + 0.96, "jzx_truckwhite", top="jzx_truckwhite", bot="jzx_truckwhite", bay=1, fh=1)
    mb.face([F.p3(-2.0, y0 + 1.85, hw), F.p3(0.65, y0 + 1.85, hw), F.p3(0.65, y0 + 2.25, hw + 0.85),
             F.p3(-2.0, y0 + 2.25, hw + 0.85)], None, st["awn"], out=(0, 1, 0))
    mb.face([F.p3(-2.0, y0 + 2.25, hw + 0.85), F.p3(0.65, y0 + 2.25, hw + 0.85), F.p3(0.65, y0 + 1.85, hw),
             F.p3(-2.0, y0 + 1.85, hw)], None, st["awn"], out=(0, -1, 0))
    for u in (-1.9, 0.55):
        L.beam(mb, F.p3(u, y0 + 0.96, hw + 0.3), F.p3(u, y0 + 2.22, hw + 0.8), 0.04, "jzx_chrome")
    for u in (-1.45, 1.35):                                                           # wheels
        for v0, v1 in ((-hw - 0.02, -hw + 0.22), (hw - 0.22, hw + 0.02)):
            hcyl(mb, F, u, g + 0.36, v0, v1, 0.36, 14, "jzx_tyre", "jzx_chrome")
    # turf mat under and beside the van
    strip_so(mb, s_mid - 3.2, s_mid + 3.2, od - 2.75, od - 0.15, 0.012, "jzx_turf")


def _pl(v):
    return (v[0], 0.0, v[1])


# ------------------------------------------------------------------ hydrangeas, bays, e-bikes
def hydrangeas(mb, s0, s1):
    od = o_dorm((s0 + s1) / 2)
    strip_so(mb, s0 - 0.4, s1 + 0.4, od - 2.5, od - 0.15, 0.012, "jzx_turf")
    c = pos((s0 + s1) / 2, od - 1.3)
    rx, rz, ry = (s1 - s0) / 2, 1.0, 0.75
    g = gy(*c)
    blob(mb, (c[0], g + 0.05, c[1]), rx, ry, rz, "ddm_leaves", yaw=ANG, nu=18, nv=8, rough=0.12, seed=3, flat=g + 0.02)
    rnd = random.Random(7)
    cols = ["jzx_hyd_blue", "jzx_hyd_blue", "jzx_hyd_purple", "jzx_hyd_pink", "jzx_hyd_lilac", "jzx_hyd_blue"]
    for k in range(90):
        a, t = rnd.uniform(0, 2 * math.pi), math.sqrt(rnd.uniform(0, 0.92))
        lx, lz = rx * t * math.cos(a), rz * t * math.sin(a)
        h = ry * math.sqrt(max(0.0, 1 - t * t)) * 0.95
        x = c[0] + lx * math.cos(ANG) - lz * math.sin(ANG)
        z = c[1] + lx * math.sin(ANG) + lz * math.cos(ANG)
        r = rnd.uniform(0.15, 0.24)
        blob(mb, (x, g + 0.05 + h, z), r, r * 0.8, r, cols[k % len(cols)], nu=7, nv=4, rough=0.15, seed=k)


def bays(mb, s0, s1):
    """White bay bars across the dorm-side strip every 2.4 m, dark-grey accent bars between (photo)."""
    s = s0
    while s <= s1:
        od = o_dorm(s)
        if not any(a - 1.0 <= s <= b + 1.0 for a, b in BUSY):
            strip_so(mb, s - 0.08, s + 0.08, od - 4.3, od - 2.5, 0.008, "jzx_bar_white", step=1)
        if od - 4.9 > 9.6:            # dark accent bar, only where it stays on the grey tiles
            strip_so(mb, s + 1.05, s + 1.35, od - 4.9, od - 4.0, 0.006, "jzx_bar_dark", step=1)
        s += 2.4


_EBIKE = None


def ebike_template():
    """Geometry of the shared-bike model (blender_landmarks.m_ebike), captured once: origin on the ground, front -z."""
    global _EBIKE
    if _EBIKE is None:
        got = []

        class Cap(L.MB):
            def build(self, coll):
                got.append(self)
                return None
        orig = L.MB
        L.MB = Cap
        try:
            L.m_ebike(None)
        finally:
            L.MB = orig
        _EBIKE = got[0]
    return _EBIKE


def ebike(mb, x, z, yaw, colours):
    """Private e-bike: the shared-bike body recoloured (no 7ma livery). colours maps ebike_* material names."""
    t = ebike_template()
    g = gy(x, z)
    ca, sa = math.cos(yaw), math.sin(yaw)
    for f, uv, mi in zip(t.F, t.UV, t.MI):
        P = []
        for vi in f:
            bx, by, bz = t.V[vi]
            lx, ly, lz = bx, bz, -by                 # Blender (x, -z, y) back to game axes
            P.append((x + lx * ca - lz * sa, g + ly, z + lx * sa + lz * ca))
        m = t.mats[mi]
        mb.face(P, uv, colours.get(m, m))


# ------------------------------------------------------------------ small street items
def bench(mb, s0, s1, o):
    a, b = pos(s0, o), pos(s1, o)
    F = Frame((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, ANG)
    hl = (s1 - s0) / 2
    g = gy(*F.p(0, 0))
    for u in (-hl + 0.25, hl - 0.25):
        box(mb, F, u - 0.06, u + 0.06, -0.2, 0.2, g, g + 0.4, "jzx_blue", top="jzx_blue", bay=1, fh=1)
    box(mb, F, -hl, hl, -0.26, 0.26, g + 0.4, g + 0.48, "jzx_orange", top="jzx_orange", bot="jzx_orange", bay=1, fh=1)
    # round back at the west end (photo: an orange disc standing up behind the seat)
    cu, cy, r = -hl + 0.45, g + 0.95, 0.5
    pts = [(cu + r * math.cos(t), cy + r * math.sin(t)) for t in [math.pi * k / 12 for k in range(25)]]
    for v, sg in ((-0.24, -1), (-0.16, 1)):
        o_ = F.vec(0, sg)
        mb.face([F.p3(pu, py, v) for pu, py in pts] + [F.p3(cu - r, g + 0.48, v), F.p3(cu + r, g + 0.48, v)],
                None, "jzx_orange", out=(o_[0], 0, o_[1]))


def aframe(mb, x, z, yaw):
    g = gy(x, z)
    F = Frame(x, z, yaw)
    for sg in (-1, 1):
        P = [F.p3(-0.2, g, sg * 0.22), F.p3(0.2, g, sg * 0.22), F.p3(0.2, g + 0.62, sg * 0.02), F.p3(-0.2, g + 0.62, sg * 0.02)]
        o_ = F.vec(0, sg)
        mb.face(P, None, "jzx_yellow", out=(o_[0], 0.4, o_[1]))
        mb.face(P[::-1], None, "jzx_yellow")


def stanchions(mb, pts):
    prev = None
    for k, (x, z) in enumerate(pts):
        g = gy(x, z)
        cyl(mb, (x, z), 0.17, g, g + 0.03, 12, "jzx_black", top="jzx_black")
        cyl(mb, (x, z), 0.035, g + 0.03, g + 0.95, 8, "jzx_black", top="jzx_black")
        if k == 0:                                     # green notice board on the first post
            F = Frame(x, z, ANG)
            box(mb, F, -0.2, 0.2, -0.02, 0.02, g + 0.95, g + 1.45, "jzx_signgreen", top="jzx_signgreen", bay=1, fh=1)
        if prev:
            L.beam(mb, (prev[0], prev[2] + 0.88, prev[1]), (x, g + 0.88, z), 0.05, "jzx_black")
        prev = (x, z, g)


def west_garden(mb):
    """Raised planter west of the end block (photo, bottom left): kerb, gravel strip, round topiary, a cloud-pruned tree."""
    corners = [pos(-6.0, 0.4), pos(-0.5, 0.4), pos(-0.5, 5.2), pos(-6.0, 5.2)]
    inner = [pos(-5.75, 0.65), pos(-0.75, 0.65), pos(-0.75, 4.95), pos(-5.75, 4.95)]
    g = min(gy(*p) for p in corners)
    F = Frame(*pos(-3.25, 2.8), ANG)
    box(mb, F, -2.75, 2.75, -2.4, 2.4, g - 0.35, g + 0.42, "jzx_concrete", bay=1.2, fh=1)
    fill(mb, inner, lambda x, z: g + 0.36, "lawn", tile=3.0)
    strip_so(mb, -5.6, -0.9, 4.2, 4.85, g + 0.38 - gy(*pos(-3.0, 4.5)), "jzx_gravel")
    for (s, o, r) in ((-1.6, 1.6, 0.55), (-2.8, 1.3, 0.5), (-4.4, 1.8, 0.6), (-1.5, 3.4, 0.45), (-5.1, 3.3, 0.5)):
        x, z = pos(s, o)
        blob(mb, (x, g + 0.36 + r * 0.8, z), r, r * 0.85, r, "jzx_topiary", nu=10, nv=6, rough=0.08, seed=int(s * 13))
    tx, tz = pos(-3.4, 3.0)                              # cloud-pruned tree: trunk + foliage pads
    cyl(mb, (tx, tz), 0.09, g + 0.36, g + 2.6, 8, "jzx_trunk", top="jzx_trunk")
    for k, (du, dv, h, r) in enumerate(((0.0, 0.0, 2.75, 0.5), (0.45, 0.25, 2.2, 0.38), (-0.4, -0.2, 1.85, 0.4),
                                        (0.25, -0.35, 1.45, 0.34))):
        x, z = pos(-3.4 + du, 3.0 + dv)
        blob(mb, (x, g + 0.36 + h, z), r, r * 0.6, r, "jzx_topiary", nu=10, nv=6, rough=0.1, seed=k + 40)


def flower_stand(mb, s, o):
    x, z = pos(s, o)
    g = gy(x, z)
    for a in (0, 2.1, 4.2):
        L.beam(mb, (x + 0.3 * math.cos(a), g, z + 0.3 * math.sin(a)), (x, g + 0.9, z), 0.04, "jzx_black")
    blob(mb, (x, g + 1.0, z), 0.42, 0.28, 0.42, "jzx_wrap", nu=10, nv=5, rough=0.2, seed=2)
    rnd = random.Random(11)
    for k in range(26):                                 # golden wheat-like sprays
        a, rr = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.05, 0.35)
        top = (x + rr * math.cos(a) * 1.6, g + 1.55 + rnd.uniform(-0.1, 0.25), z + rr * math.sin(a) * 1.6)
        L.beam(mb, (x + rr * 0.3 * math.cos(a), g + 1.05, z + rr * 0.3 * math.sin(a)), top, 0.09, "jzx_gold")


# ------------------------------------------------------------------ layout (along-street positions from the photo)
TRUCK_AT = [(20.8, "pink"), (32.6, "cream"), (57.3, "green")]
HYDRANGEA = (11.0, 17.6)
BUSY = [(s - 3.2, s + 3.2) for s, _ in TRUCK_AT] + [HYDRANGEA]
EBIKES = [  # (s, colours) parked in the bays, front towards the dorm (photo: white/yellow, white, black, grey; one more by the cream van)
    (9.4, {"ebike_blue": "eb_white", "ebike_gray": "eb_yellow"}),
    (10.3, {"ebike_blue": "eb_white", "ebike_gray": "eb_grey"}),
    (11.2, {"ebike_blue": "eb_black", "ebike_gray": "eb_grey"}),
    (13.9, {"ebike_blue": "eb_white", "ebike_gray": "eb_black"}),
    (37.2, {"ebike_blue": "eb_black", "ebike_gray": "eb_white"}),
    (61.6, {"ebike_blue": "eb_grey", "ebike_gray": "eb_black"}),
]


def m_street(coll):
    mb = MB(TITLE, O)
    bays(mb, 6.0, 82.0)
    hydrangeas(mb, *HYDRANGEA)
    for s, st in TRUCK_AT:
        truck(mb, s, st)
    for s, cols in EBIKES:
        od = o_dorm(s)
        x, z = pos(s, od - 3.3)
        ebike(mb, x, z, ANG + math.pi / 2, cols)           # front (-z of the template) towards the dorm
    bench(mb, 28.0, 30.2, FRONT + 0.55)
    for s, o in ((8.4, FRONT + 1.1), (10.1, FRONT + 1.6)):
        x, z = pos(s, o)
        aframe(mb, x, z, ANG + 0.4)
    bx, bz = pos(9.2, FRONT + 0.5)
    F = Frame(bx, bz, ANG)
    g = gy(bx, bz)
    box(mb, F, -0.23, 0.23, -0.23, 0.23, g, g + 0.6, "jzx_yellow", top="jzx_black", bay=1, fh=1)
    stanchions(mb, [pos(s, 9.4) for s in (38.2, 39.3, 40.4)])
    west_garden(mb)
    flower_stand(mb, 6.9, FRONT + 0.9)
    return dict(objs=[mb.build(coll)], origin=O, height=3.0)


def main():
    bpy.ops.wm.read_homefile(use_empty=True)
    L._MATS.clear()
    coll = bpy.data.collections.new(TITLE)
    bpy.context.scene.collection.children.link(coll)
    info = m_street(coll)
    objs = info["objs"]
    tris = L.tri_count(objs)
    glb = L.MODELS / f"{KEY}.glb"
    L.export_glb(objs, glb)
    if "--no-render" not in sys.argv:
        L.setup_preview(objs, KEY, (300, 34), (O[0] - 22, 2.0, O[1] + 4, 30.0), O)
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(L.BL / f"{KEY}.blend"), compress=True, relative_remap=True)
    mj = L.BL / "models.json"
    entries = json.loads(mj.read_text(encoding="utf-8"))
    e = dict(name=TITLE, file=f"models/{KEY}.glb", x=round(O[0], 2), z=round(O[1], 2), rotY=0, replaces=[],
             replaces_names=[], height=info["height"], tris=tris)
    for i, old in enumerate(entries):
        if old["file"] == e["file"]:
            entries[i] = e
            break
    else:
        entries.append(e)
    mj.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[jzx_street] tris {tris}, origin ({O[0]:.2f}, {O[1]:.2f}), base {BASE:.2f}, glb {glb.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
