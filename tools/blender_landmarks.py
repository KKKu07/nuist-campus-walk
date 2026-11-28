"""Build the NUIST landmark models in Blender, export GLB + preview renders + .blend files.

Run in background (never writes to the Blender install dir):
    set PYTHONDONTWRITEBYTECODE=1
    G:\\Blender\\blender.exe --background --factory-startup --python tools\\blender_landmarks.py -- [--only key,key] [--no-render]

Textures come from tools/blender_textures.py (data/blender/textures). Outputs:
    web/public/models/<key>.glb       one model per landmark, origin = model centre on the ground
    data/blender/<key>.blend          editable Blender file (collection named after the building)
    data/blender/previews/<key>.jpg   preview render
    data/blender/models.json          placement for the game

Coordinates: everything is authored in game coordinates (x east, y up, z south, metres) and converted
to Blender (X=x, Y=-z, Z=y). The glTF exporter's +Y-up conversion turns that back into game axes, so a
GLB vertex is exactly (game x - model x, y, game z - model z) and rotY is 0.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BL = DATA / "blender"
TEX = BL / "textures"
PREV = BL / "previews"
MODELS = ROOT / "web" / "public" / "models"


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


CAMPUS = _load(ROOT / "web" / "public" / "campus" / "campus.json")
POIS = {p["name"]: p for p in _load(DATA / "manual" / "pois.json")["pois"]}


def _has(bid):
    """True when the building is (still) in campus.json; dorms.csv may list demolished ones (e.g. 沁园43栋)."""
    key = int(bid) if isinstance(bid, str) and bid.isdigit() else bid
    return any(b["id"] == key for b in CAMPUS["buildings"])


def bld(bid):
    """Look buildings up by id: names in campus.json follow the official map and may change."""
    return next(b for b in CAMPUS["buildings"] if b["id"] == bid)


# ------------------------------------------------------------------ 2D helpers
def shoelace(p):
    n = len(p)
    return sum(p[i][0] * p[(i + 1) % n][1] - p[(i + 1) % n][0] * p[i][1] for i in range(n)) / 2


def ccw(p):
    """Counter-clockwise in map view (x right, north up) == negative shoelace in (x, z)."""
    p = [tuple(q) for q in p]
    return p if shoelace(p) < 0 else p[::-1]


def centroid(p):
    a = shoelace(p)
    cx = cz = 0.0
    n = len(p)
    for i in range(n):
        x0, z0 = p[i]
        x1, z1 = p[(i + 1) % n]
        c = x0 * z1 - x1 * z0
        cx += (x0 + x1) * c
        cz += (z0 + z1) * c
    return cx / (6 * a), cz / (6 * a)


def inset(p, d):
    """Mitred offset of a polygon: d > 0 moves edges inwards. Vertex i stays matched to input vertex i."""
    p = ccw(p)
    n = len(p)
    lines = []
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dz)
        nx, nz = -dz / L, dx / L  # outward normal
        lines.append(((a[0] - nx * d, a[1] - nz * d), (dx / L, dz / L)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-6:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


class Frame:
    """Local plan frame: u along angle `ang` (direction (cos, sin) in x/z), v = u rotated towards +z."""

    def __init__(self, cx, cz, ang):
        self.cx, self.cz, self.ang = cx, cz, ang
        self.c, self.s = math.cos(ang), math.sin(ang)

    def p(self, u, v):
        return (self.cx + u * self.c - v * self.s, self.cz + u * self.s + v * self.c)

    def p3(self, u, y, v):
        x, z = self.p(u, v)
        return (x, y, z)

    def vec(self, du, dv):
        return (du * self.c - dv * self.s, du * self.s + dv * self.c)

    def rect(self, u0, u1, v0, v1):  # map-ccw
        return [self.p(u0, v0), self.p(u0, v1), self.p(u1, v1), self.p(u1, v0)]


# ------------------------------------------------------------------ materials
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    h = h.lstrip("#")
    return tuple(_lin(int(h[i:i + 2], 16)) for i in (0, 2, 4))


MAT_SPEC = {
    # name: (base colour, roughness, metallic, texture)
    "white": ("#f2f2ee", 0.8, 0.0, None),
    "roof_flat": ("#b9bbb7", 0.9, 0.0, None),
    "concrete": ("#c9c7c0", 0.9, 0.0, "concrete.jpg"),
    "stone": ("#d3cec4", 0.85, 0.0, None),
    "qx_wall": ("#f1f0eb", 0.8, 0.0, "qx_facade.jpg"),
    "glass_blue": ("#5f8fbd", 0.2, 0.3, "glass_blue.jpg"),
    "glass_dark": ("#3a5876", 0.2, 0.3, "glass_dark.jpg"),
    "radome": ("#f4f5f6", 0.45, 0.0, "radome.jpg"),
    "steel_white": ("#e6e9ec", 0.45, 0.3, None),
    "cup": ("#2b4257", 0.3, 0.3, None),
    "lib_wall": ("#eadcc3", 0.8, 0.0, "lib_facade.jpg"),
    "cream": ("#f2e9d8", 0.8, 0.0, None),
    "slate": ("#3e4f68", 0.6, 0.1, "slate.jpg"),
    "slate_flat": ("#5c6a7d", 0.8, 0.0, None),
    "yf_wall": ("#eef0f2", 0.8, 0.0, "yf_facade.jpg"),
    "spire": ("#2c4469", 0.35, 0.35, "slate.jpg"),
    "gold": ("#c9a24e", 0.35, 0.8, None),
    "clock": ("#f7f5ee", 0.6, 0.0, "clock.jpg"),
    "lj_tower": ("#dfe2e4", 0.6, 0.1, "lj_tower.jpg"),
    "lj_podium": ("#f1f2ef", 0.8, 0.0, "lj_podium.jpg"),
    "green": ("#6f9449", 0.95, 0.0, "green_roof.jpg"),
    "gym_glass": ("#8fabbd", 0.2, 0.3, "gym_glass.jpg"),
    "gym_panel": ("#c9cdd0", 0.6, 0.2, "gym_panel.jpg"),
    "metal_light": ("#c6cacd", 0.5, 0.4, "metal_light.jpg"),
    "js_wall": ("#f3f3ef", 0.8, 0.0, "js_wall.jpg"),
    "metal_roof": ("#6e7f91", 0.5, 0.4, "metal_roof.jpg"),
    "brick_red": ("#9a5a3d", 0.85, 0.0, "brick_red.jpg"),
    "terracotta": ("#c4663f", 0.8, 0.0, None),
    "gate_beam": ("#bdb6a6", 0.85, 0.0, "gate_beam.jpg"),
    "gate_cream": ("#e8dfcc", 0.85, 0.0, None),
    "gate_top": ("#8e4a32", 0.8, 0.0, None),
    "wood": ("#7a4a2e", 0.8, 0.0, None),
    "ground": ("#a3a996", 1.0, 0.0, None),
    "sign": ("#f2f3f4", 0.6, 0.1, "ring_sign.jpg"),
    "white_band": ("#f0f0ec", 0.8, 0.0, "white_band.jpg"),
    "sx_brick": ("#a8825d", 0.85, 0.0, "sx_brick.jpg"),
    "xz_facade": ("#e7ddca", 0.6, 0.1, "xz_facade.jpg"),
    "xz_end": ("#e9e2d2", 0.8, 0.0, "xz_end.jpg"),
    "sx_panel": ("#c89b77", 0.75, 0.0, "sx_panel.jpg"),
    "gj_facade": ("#f3f3f0", 0.7, 0.0, "gj_facade.jpg"),
    "of_facade": ("#d3b088", 0.85, 0.0, "of_facade.jpg"),
    "stone_column": ("#b9b0a2", 0.85, 0.0, "stone_column.jpg"),
    "flags": ("#ffffff", 0.8, 0.0, "flags.jpg"),
    "rock_text": ("#c29a72", 0.9, 0.0, "rock_text.jpg"),
    "bj_name": ("#f3f3ef", 0.6, 0.0, "bj_name.jpg"),
    "bronze": ("#6b5236", 0.45, 0.6, None),
    "granite_dark": ("#2e2e31", 0.4, 0.0, None),
    "sandstone": ("#c29a72", 0.9, 0.0, None),
    "paving": ("#cfc8ba", 0.9, 0.0, None),
    "rust": ("#8a4b2c", 0.8, 0.0, None),
    "pole": ("#d9dcde", 0.3, 0.8, None),
    "dark_roof": ("#3b3f44", 0.7, 0.1, None),
    "lawn": ("#6f9449", 0.95, 0.0, "green_roof.jpg"),
    "bus": ("#f4f5f6", 0.35, 0.1, "bus_atlas.jpg"),
    "bus_under": ("#2a2b2e", 0.9, 0.0, None),
    "bus_tire": ("#1d1d1f", 0.9, 0.0, None),
    "bus_black": ("#18191b", 0.5, 0.2, None),
    "bus_grille": ("#5a5f64", 0.6, 0.3, None),
    "chrome": ("#d5d8db", 0.2, 0.9, None),
    "bus_lamp": ("#fffbe8", 0.2, 0.0, None),
    "qg_glass": ("#5f9aa2", 0.2, 0.3, "qg_glass.jpg"),
    "orange": ("#e98a2b", 0.7, 0.0, None),
    "bus_blue": ("#2a6fc9", 0.5, 0.1, None),
    "shelter_sign": ("#2a6fc9", 0.6, 0.0, "shelter_sign.jpg"),
    "ebike_blue": ("#1e88e5", 0.45, 0.1, None),
    "ebike_black": ("#1b1b1d", 0.7, 0.0, None),
    "ebike_gray": ("#b8bcc0", 0.35, 0.6, None),
    "red_brick": ("#9b3b2c", 0.85, 0.0, "red_brick.jpg"),
    "theater": ("#d68c4c", 0.8, 0.0, "theater.jpg"),
    "yellow": ("#e6b422", 0.6, 0.2, None),
    "roof_gray": ("#8f9398", 0.7, 0.2, None),
    "sky_roof": ("#8ec5ea", 0.6, 0.1, None),
    "yf4_wall": ("#eef0f2", 0.8, 0.0, "yf4_facade.jpg"),
    "pink_facade": ("#dcb3a6", 0.85, 0.0, "pink_facade.jpg"),
    # *_t = tinted per vertex (generic buildings): texture x Color Attribute "Col"
    "gen_dorm_t": ("#ffffff", 0.85, 0.0, "gen_dorm.jpg"),
    "gen_office_t": ("#ffffff", 0.8, 0.0, "gen_office.jpg"),
    "gen_hall_t": ("#ffffff", 0.75, 0.1, "gen_hall.jpg"),
    "gen_tile_t": ("#ffffff", 0.8, 0.0, "gen_tile.jpg"),
    "gen_flat_t": ("#ffffff", 0.9, 0.0, "gen_flat.jpg"),
    "gen_trim_t": ("#ffffff", 0.85, 0.0, None),
    "tile_brown": ("#7b6b5c", 0.8, 0.0, None),
    "emblem": ("#1f4fa3", 0.5, 0.0, "emblem.jpg"),
    "old_res": ("#8e8f8b", 0.95, 0.0, "old_res.jpg"),
    "old_grey": ("#7f807c", 0.95, 0.0, None),
    "old_roof": ("#8a8784", 0.95, 0.0, None),
    "old_dark": ("#2c2d2e", 0.9, 0.0, None),
    "solar": ("#27384a", 0.25, 0.4, None),
    "tile_red": ("#8e4a3a", 0.8, 0.0, None),
    "container_t": ("#ffffff", 0.55, 0.35, "container.jpg"),
    "shopfront": ("#3c4e5a", 0.25, 0.3, "shopfront.jpg"),
    "jzx_signs": ("#e8742a", 0.6, 0.0, "jzx_signs.jpg"),
    "jzx_title": ("#1d1f21", 0.6, 0.0, "jzx_title.jpg"),
    "glass_rail": ("#a8c1cc", 0.1, 0.2, None),
    "jzx_poster": ("#f6e7a8", 0.7, 0.0, "jzx_poster.jpg"),
    "awning_yellow": ("#f2c230", 0.7, 0.0, None),
    "awning_green": ("#2f6b4c", 0.7, 0.0, None),
    "relief_column": ("#bfb5a4", 0.85, 0.0, "relief_column.jpg"),
    "brick_buff": ("#c9a27f", 0.9, 0.0, None),
    "tile_greyblue": ("#8e9aa6", 0.85, 0.0, None),
    "pebble": ("#ece6d8", 0.95, 0.0, None),
    "flower_yellow": ("#e8c43a", 0.9, 0.0, None),
    "flower_red": ("#c8402f", 0.9, 0.0, None),
    "seat_tread": ("#c9c9c6", 0.9, 0.0, None),
    "container_yellow": ("#e8b923", 0.6, 0.2, None),
    "sign_red": ("#c8202a", 0.6, 0.0, None),
}
_MATS: dict = {}


def _principled(m):
    nt = m.node_tree
    b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if b is None:
        nt.nodes.clear()
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(b.outputs[0], o.inputs[0])
    return b


def M(name):
    if name in _MATS:
        return _MATS[name]
    col, rough, metal, tex = MAT_SPEC[name]
    m = bpy.data.materials.new(name)
    if m.node_tree is None:  # Blender < 5 creates materials without nodes
        m.use_nodes = True
    b = _principled(m)
    lc = hex_lin(col)
    b.inputs["Base Color"].default_value = (*lc, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*lc, 1.0)
    try:
        m.use_backface_culling = name not in ("flags",)  # exported as glTF doubleSided=false
    except AttributeError:
        pass
    tinted = name.endswith("_t")
    if tinted:
        vc = m.node_tree.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        if not tex:
            m.node_tree.links.new(vc.outputs["Color"], b.inputs["Base Color"])
    if name == "bus_lamp":
        for k, v in (("Emission Color", (1.0, 0.98, 0.9, 1.0)), ("Emission Strength", 0.8)):
            if k in b.inputs:
                b.inputs[k].default_value = v
    if tex:
        img = bpy.data.images.load(str(TEX / tex), check_existing=True)
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = img
        t.location = (-400, 200)
        if tinted:
            mix = m.node_tree.nodes.new("ShaderNodeMix")
            mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            m.node_tree.links.new(t.outputs["Color"], mix.inputs[6])
            m.node_tree.links.new(vc.outputs["Color"], mix.inputs[7])
            m.node_tree.links.new(mix.outputs[2], b.inputs["Base Color"])
        else:
            m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
        nfile = TEX / (Path(tex).stem + "_n.jpg")
        if nfile.exists():  # normal map -> glTF normalTexture
            ni = bpy.data.images.load(str(nfile), check_existing=True)
            ni.colorspace_settings.name = "Non-Color"
            tn = m.node_tree.nodes.new("ShaderNodeTexImage")
            tn.image = ni
            nm = m.node_tree.nodes.new("ShaderNodeNormalMap")
            m.node_tree.links.new(tn.outputs["Color"], nm.inputs["Color"])
            m.node_tree.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    _MATS[name] = m
    return m


# ------------------------------------------------------------------ mesh builder
def newell(P):
    nx = ny = nz = 0.0
    for i in range(len(P)):
        x0, y0, z0 = P[i]
        x1, y1, z1 = P[(i + 1) % len(P)]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return nx, ny, nz


class MB:
    """Accumulates faces in game coordinates, builds one Blender mesh object."""

    def __init__(self, name, origin):
        self.name, self.ox, self.oz = name, origin[0], origin[1]
        self.V, self.F, self.UV, self.MI, self.SM, self.mats = [], [], [], [], [], []
        self.C, self.col = [], None  # per-face sRGB colour (None = white); `col` is the current colour

    def face(self, pts, uvs=None, mat="white", smooth=False, out=None):
        uvs = list(uvs) if uvs else [(0.0, 0.0)] * len(pts)
        P, U = [], []
        for p, uv in zip(pts, uvs):  # drop consecutive duplicates (pyramids, cones)
            if P and sum((a - b) ** 2 for a, b in zip(P[-1], p)) < 1e-10:
                continue
            P.append(tuple(p))
            U.append(uv)
        while len(P) > 1 and sum((a - b) ** 2 for a, b in zip(P[0], P[-1])) < 1e-10:
            P.pop()
            U.pop()
        if len(P) < 3:
            return
        if out is not None:
            n = newell(P)
            if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] < 0:
                P.reverse()
                U.reverse()
        if mat not in self.mats:
            self.mats.append(mat)
        base = len(self.V)
        for x, y, z in P:
            self.V.append((x - self.ox, -(z - self.oz), y))
        self.F.append(list(range(base, base + len(P))))
        self.UV.append(U)
        self.MI.append(self.mats.index(mat))
        self.SM.append(smooth)
        self.C.append(self.col)

    def build(self, coll):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.V, [], self.F)
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for k, li in enumerate(poly.loop_indices):
                uvl.data[li].uv = self.UV[poly.index][k]
        for m in self.mats:
            me.materials.append(M(m))
        me.polygons.foreach_set("material_index", self.MI)
        me.polygons.foreach_set("use_smooth", self.SM)
        if any(c is not None for c in self.C):
            ca = me.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
            flat = []
            for poly in me.polygons:
                c = self.C[poly.index] or (1.0, 1.0, 1.0)
                lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
                flat += (lin + [1.0]) * poly.loop_total
            ca.data.foreach_set("color", flat)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
        for e in bm.edges:  # keep flat/smooth borders sharp
            fs = e.link_faces
            if len(fs) == 2 and fs[0].smooth != fs[1].smooth:
                e.smooth = False
        bm.to_mesh(me)
        bm.free()
        me.validate()
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        coll.objects.link(ob)
        return ob


# ------------------------------------------------------------------ primitives
def dist2(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def wall(mb, a, b, y0, y1, mat, bay=3.5, fh=3.5, vbase=0.0, vspan=None, fit=True):
    L = dist2(a, b)
    if L < 1e-3:
        return
    nb = max(1, round(L / bay)) if fit else L / bay

    def v(y):
        return (y - vbase) / (vspan if vspan else fh)

    mb.face([(a[0], y0, a[1]), (b[0], y0, b[1]), (b[0], y1, b[1]), (a[0], y1, a[1])],
            [(0, v(y0)), (nb, v(y0)), (nb, v(y1)), (0, v(y1))], mat)


def cap(mb, pts, y, mat, tile=4.0, down=False):
    pts = ccw(pts)
    P = [(x, y, z) for x, z in pts]
    U = [(x / tile, -z / tile) for x, z in pts]
    mb.face(P, U, mat, out=(0, -1 if down else 1, 0))


def prism(mb, pts, y0, y1, wmat, top=None, bot=None, tile=4.0, **kw):
    pts = ccw(pts)
    n = len(pts)
    for i in range(n):
        wall(mb, pts[i], pts[(i + 1) % n], y0, y1, wmat, **kw)
    if top:
        cap(mb, pts, y1, top, tile)
    if bot:
        cap(mb, pts, y0, bot, tile, down=True)


def box(mb, F, u0, u1, v0, v1, y0, y1, wmat, top=None, bot=None, **kw):
    prism(mb, F.rect(u0, u1, v0, v1), y0, y1, wmat, top, bot, **kw)


def parapet(mb, pts, y0, y1, t, mat):
    """Double-sided parapet wall of thickness t on the outline pts (outer face pushed out by t)."""
    pts = ccw(pts)
    outer = inset(pts, -t)
    n = len(pts)
    for i in range(n):
        wall(mb, outer[i], outer[(i + 1) % n], y0, y1, mat, 4, 4)
        wall(mb, pts[(i + 1) % n], pts[i], y0 + 0.01, y1, mat, 4, 4)  # inner face, facing the roof
    ring(mb, outer, y1, pts, y1, mat)


def floor_bands(mb, pts, ys, mat, out=0.1, th=0.22):
    """Projecting floor-slab bands (front, top and bottom faces) at heights ys."""
    pts = ccw(pts)
    outer = inset(pts, -out)
    n = len(pts)
    for y in ys:
        y0, y1 = y - th / 2, y + th / 2
        for i in range(n):
            wall(mb, outer[i], outer[(i + 1) % n], y0, y1, mat, 4, 1)
        ring(mb, outer, y1, pts, y1, mat)
        for i in range(n):
            a, b_, c, d = outer[i], outer[(i + 1) % n], pts[(i + 1) % n], pts[i]
            mb.face([(a[0], y0, a[1]), (d[0], y0, d[1]), (c[0], y0, c[1]), (b_[0], y0, b_[1])], None, mat, out=(0, -1, 0))


def ring(mb, lo, y0, hi, y1, mat, uvt=2.0):
    """Sloped band between two matched map-ccw loops (mansards, hips, cornices)."""
    n = len(lo)
    for i in range(n):
        a, b = lo[i], lo[(i + 1) % n]
        c, d = hi[(i + 1) % n], hi[i]
        ex, ez = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ex, ez) or 1.0
        ex, ez = ex / L, ez / L

        def uv(p, y):
            along = (p[0] - a[0]) * ex + (p[1] - a[1]) * ez
            inward = (p[0] - a[0]) * ez - (p[1] - a[1]) * ex
            return (along / uvt, math.hypot(inward, y - y0) / uvt)

        nx, nz = -ez, ex
        mb.face([(a[0], y0, a[1]), (b[0], y0, b[1]), (c[0], y1, c[1]), (d[0], y1, d[1])],
                [uv(a, y0), uv(b, y0), uv(c, y1), uv(d, y1)], mat, out=(nx, 0.5, nz))


def ring_down(mb, lo, y0, hi, y1, mat):
    """Band between a narrow lower loop and a wider upper loop (an underside that flares out), faces looking down-out."""
    n = len(lo)
    for i in range(n):
        a, b = lo[i], lo[(i + 1) % n]
        c, d = hi[(i + 1) % n], hi[i]
        mx, mz = (c[0] + d[0]) / 2 - (a[0] + b[0]) / 2, (c[1] + d[1]) / 2 - (a[1] + b[1]) / 2
        mb.face([(a[0], y0, a[1]), (b[0], y0, b[1]), (c[0], y1, c[1]), (d[0], y1, d[1])], None, mat, out=(mx, -abs(y1 - y0), mz))


def frustum(mb, F, u0, u1, v0, v1, y0, y1, du, dv, mat, top=None, ov=0.0, uvt=2.0):
    lo = F.rect(u0 - ov, u1 + ov, v0 - ov, v1 + ov)
    hi = F.rect(u0 + du, u1 - du, v0 + dv, v1 - dv)
    ring(mb, lo, y0, hi, y1, mat, uvt)
    if top:
        cap(mb, hi, y1, top)


def cyl(mb, c, r, y0, y1, n, mat, top=None, bot=None, r1=None, smooth=True, inside=False, flip_u=False):
    cx, cz = c
    r1 = r if r1 is None else r1
    ring0 = [(cx + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    ring1 = [(cx + r1 * math.cos(2 * math.pi * i / n), cz + r1 * math.sin(2 * math.pi * i / n)) for i in range(n)]

    def fu(u):
        return 1 - u if flip_u else u
    for i in range(n):
        j = (i + 1) % n
        am = 2 * math.pi * (i + 0.5) / n
        o = (math.cos(am), (r - r1) / max(1e-6, (y1 - y0)), math.sin(am))
        if inside:
            o = (-o[0], -o[1], -o[2])
        mb.face([(ring0[i][0], y0, ring0[i][1]), (ring0[j][0], y0, ring0[j][1]),
                 (ring1[j][0], y1, ring1[j][1]), (ring1[i][0], y1, ring1[i][1])],
                [(fu(i / n), 0), (fu((i + 1) / n), 0), (fu((i + 1) / n), 1), (fu(i / n), 1)], mat, smooth, out=o)
    if top and r1 > 0:
        cap(mb, ring1, y1, top, tile=2 * max(r1, 0.5))
    if bot:
        cap(mb, ring0, y0, bot, tile=2 * max(r, 0.5), down=True)


def sphere(mb, c, r, nu, nv, mat, ry=None):
    cx, cy, cz = c
    ry = r if ry is None else ry

    def P(i, j):
        lat = -math.pi / 2 + math.pi * j / nv
        lon = 2 * math.pi * i / nu
        return (cx + r * math.cos(lat) * math.cos(lon), cy + ry * math.sin(lat), cz + r * math.cos(lat) * math.sin(lon))

    for j in range(nv):
        for i in range(nu):
            pts = [P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)]
            ctr = [sum(q[k] for q in pts) / 4 for k in range(3)]
            mb.face(pts, [(i / nu, j / nv), ((i + 1) / nu, j / nv), ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv)],
                    mat, True, out=(ctr[0] - cx, ctr[1] - cy, ctr[2] - cz))


def beam(mb, p0, p1, t, mat):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    up = Vector((0, 1, 0)) if abs(d.normalized().y) < 0.9 else Vector((1, 0, 0))
    a = d.cross(up).normalized() * (t / 2)
    b = d.cross(a).normalized() * (t / 2)
    cs = [a + b, -a + b, -a - b, a - b]
    for i in range(4):
        q0, q1 = cs[i], cs[(i + 1) % 4]
        o = (q0 + q1) / 2
        mb.face([tuple(p0 + q0), tuple(p0 + q1), tuple(p1 + q1), tuple(p1 + q0)], None, mat, out=tuple(o))


def gable(mb, F, u0, u1, v0, v1, ea, eb, hr, t, wmat, rmat, ov=0.7, bay=2.5, fh=3.0, soffit=True):
    """Pitched block, ridge along u at v0 + t*(v1-v0); eave height ea on the v0 side, eb on the v1 side."""
    vr = v0 + t * (v1 - v0)
    wall(mb, F.p(u1, v0), F.p(u0, v0), 0, ea, wmat, bay, fh)
    wall(mb, F.p(u0, v1), F.p(u1, v1), 0, eb, wmat, bay, fh)
    for u, sgn in ((u0, -1), (u1, 1)):
        pts = [F.p3(u, 0, v0), F.p3(u, 0, v1), F.p3(u, eb, v1), F.p3(u, hr, vr), F.p3(u, ea, v0)]
        uvs = [((v - v0) / bay, y / fh) for v, y in ((v0, 0), (v1, 0), (v1, eb), (vr, hr), (v0, ea))]
        ox, oz = F.vec(sgn, 0)
        mb.face(pts, uvs, wmat, out=(ox, 0, oz))
    # roof planes with overhang
    for ve, ye, side in ((v0, ea, -1), (v1, eb, 1)):
        run = abs(vr - ve)
        slope = (hr - ye) / max(run, 1e-6)
        vo = ve + side * ov
        yo = ye - ov * slope
        a, b = u0 - ov, u1 + ov
        pts = [F.p3(a, yo, vo), F.p3(b, yo, vo), F.p3(b, hr, vr), F.p3(a, hr, vr)]
        L = math.hypot(run + ov, hr - yo)
        uvs = [(a / 2, 0), (b / 2, 0), (b / 2, L / 2), (a / 2, L / 2)]
        ox, oz = F.vec(0, side)
        mb.face(pts, uvs, rmat, out=(ox * slope, 1, oz * slope) if slope > 0 else (ox, 1, oz))
        if soffit:
            mb.face([(x, y - 0.06, z) for x, y, z in pts], uvs, rmat, out=(-ox * 0.1, -1, -oz * 0.1))


def dormer(mb, A, B, s, y0, h, d, w=1.7, hgt=2.0, depth=2.6, wmat="cream", gmat="glass_dark", rmat="slate"):
    """Dormer on a slope whose outer edge A->B (map-ccw) sits at y0 and rises h over a horizontal inset d."""
    ex, ez = B[0] - A[0], B[1] - A[1]
    L = math.hypot(ex, ez)
    ex, ez = ex / L, ez / L
    yb = y0 + 0.45
    e = d * (yb - y0) / h
    px, pz = A[0] + ex * s - (-ez) * e, A[1] + ez * s - ex * e
    Fd = Frame(px, pz, math.atan2(ez, ex))
    box(mb, Fd, -w / 2, w / 2, -depth, 0, yb, yb + hgt, wmat)
    frustum(mb, Fd, -w / 2 - 0.15, w / 2 + 0.15, -depth, 0.15, yb + hgt, yb + hgt + 0.75, w / 2 + 0.15, 0, rmat)
    n = Fd.vec(0, 1)
    mb.face([Fd.p3(-w / 2 + 0.25, yb + 0.25, 0.05), Fd.p3(w / 2 - 0.25, yb + 0.25, 0.05),
             Fd.p3(w / 2 - 0.25, yb + hgt - 0.2, 0.05), Fd.p3(-w / 2 + 0.25, yb + hgt - 0.2, 0.05)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], gmat, out=(n[0], 0, n[1]))


def dormers_rect(mb, F, u0, u1, v0, v1, y0, h, d, spacing, keep=None, edges=(0, 1, 2, 3), **kw):
    """Dormers along the edges (0 west, 1 south, 2 east, 3 north in frame terms) of a mansard on F.rect(u0,u1,v0,v1)."""
    lo = F.rect(u0, u1, v0, v1)
    for i in edges:
        A, B = lo[i], lo[(i + 1) % 4]
        L = dist2(A, B)
        k = int((L - 2.5) // spacing)
        if k < 1:
            continue
        start = (L - (k - 1) * spacing) / 2
        for j in range(k):
            s = start + j * spacing
            if keep and not keep(i, s, L):
                continue
            dormer(mb, A, B, s, y0, h, d, **kw)


def dormers_poly(mb, lo, y0, h, d, spacing, margin, **kw):
    """Dormers along every long edge of a mansard whose outer loop `lo` (map-ccw) sits at y0."""
    lo = ccw(lo)
    for i in range(len(lo)):
        A, B = lo[i], lo[(i + 1) % len(lo)]
        L = dist2(A, B)
        k = int((L - 2 * margin) // spacing) + 1
        if L < 2 * margin + 2:
            continue
        start = (L - (k - 1) * spacing) / 2
        for j in range(k):
            dormer(mb, A, B, start + j * spacing, y0, h, d, **kw)


# ------------------------------------------------------------------ models
def m_qixianglou(coll):
    b = bld(478390591)  # 气象楼 wings
    pts = b["pts"]
    O = centroid(pts)
    F = Frame(973.5, -441.0, -0.13)  # main tower: between the hand-traced rect and the DSM tower
    body, top = MB("气象楼_主体", O), MB("气象楼_雷达", O)
    prism(body, pts, 0, 12.0, "qx_wall", top="roof_flat", bay=3.4, fh=4.0)
    parapet(body, pts, 11.4, 12.8, 0.25, "white")
    for u, v, w, d in ((-44, -4, 6, 4), (-39, 6, 4, 3), (41, -4, 5, 4), (46, 5, 4, 3)):
        box(body, F, u - w / 2, u + w / 2, v - d / 2, v + d / 2, 12.0, 14.2, "concrete", top="concrete")
    # 15-storey tower
    box(body, F, -27, 27, -10.5, 10.5, 0, 50.0, "qx_wall", top="roof_flat", bay=4.0, fh=50.0 / 15)
    floor_bands(body, F.rect(-27, 27, -10.5, 10.5), [50.0 * k / 15 for k in range(4, 15)], "white", out=0.08, th=0.16)
    box(body, F, -27.25, 27.25, -10.75, 10.75, 49.0, 50.6, "white", bay=3.0, fh=1.6)
    # central glass strips (front rises above the roof)
    box(body, F, -3.6, 3.6, 10.5, 11.4, 12.0, 53.0, "glass_blue", top="white", bay=3.6, fh=50.0 / 15)
    box(body, F, -3.6, 3.6, -11.4, -10.5, 12.0, 53.0, "glass_blue", top="white", bay=3.6, fh=50.0 / 15)
    # entrance canopy, columns, steps
    box(body, F, -8, 8, 23.5, 30.0, 5.6, 6.3, "white", top="roof_flat", bot="white")
    for u in (-6.5, -2.2, 2.2, 6.5):
        cyl(body, F.p(u, 29.2), 0.3, 0, 5.6, 10, "white")
    box(body, F, -10, 10, 23.5, 30.0, 0, 1.2, "stone", top="stone")
    for i, hgt in enumerate((0.9, 0.6, 0.3)):
        box(body, F, -10, 10, 30.0 + i * 0.9, 30.9 + i * 0.9, 0, hgt, "stone", top="stone")
    # radar assembly on the roof
    R = (0.0, 1.5)
    rc = F.p(*R)
    cyl(top, rc, 9.0, 50.0, 53.6, 32, "sign", smooth=True, flip_u=True)
    cyl(top, rc, 8.85, 50.0, 53.6, 32, "steel_white", smooth=True, inside=True)
    lv = [(50.0, 4.4), (54.2, 3.5), (58.4, 2.5), (62.5, 1.6)]
    cs = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    for k in range(4):
        su, sv = cs[k]
        tu, tv = cs[(k + 1) % 4]
        beam(top, F.p3(R[0] + su * lv[0][1], lv[0][0], R[1] + sv * lv[0][1]),
             F.p3(R[0] + su * lv[-1][1], lv[-1][0], R[1] + sv * lv[-1][1]), 0.5, "steel_white")
        for li in range(1, 4):
            y, hw = lv[li]
            beam(top, F.p3(R[0] + su * hw, y, R[1] + sv * hw), F.p3(R[0] + tu * hw, y, R[1] + tv * hw), 0.3, "steel_white")
        for li in range(3):
            (ya, ha), (yb, hb) = lv[li], lv[li + 1]
            beam(top, F.p3(R[0] + su * ha, ya, R[1] + sv * ha), F.p3(R[0] + tu * hb, yb, R[1] + tv * hb), 0.22, "steel_white")
            beam(top, F.p3(R[0] + tu * ha, ya, R[1] + tv * ha), F.p3(R[0] + su * hb, yb, R[1] + sv * hb), 0.22, "steel_white")
    cyl(top, rc, 0.9, 50.0, 62.5, 10, "steel_white")
    cyl(top, rc, 1.8, 62.5, 66.0, 24, "cup", r1=6.6)
    cyl(top, rc, 6.9, 66.0, 66.6, 24, "steel_white", top="steel_white", bot="steel_white")
    cyl(top, rc, 2.2, 66.6, 67.2, 16, "steel_white")
    sphere(top, (rc[0], 71.6, rc[1]), 5.0, 24, 14, "radome")
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        x, z = rc[0] + 6.3 * math.cos(a), rc[1] + 6.3 * math.sin(a)
        beam(top, (x, 66.4, z), (x, 77.5, z), 0.16, "steel_white")
    objs = [body.build(coll), top.build(coll)]
    return dict(objs=objs, origin=O, replaces=[478390591, "manual-29"], replaces_names=["气象楼", "气象楼主楼(extra_buildings)"],
                height=76.6)


def m_tushuguan(coll):
    # The OSM outline (88.7 x 67.6 m) misses the projecting corner pavilions; the DSM and the
    # ortho both show ~94 x 78 m, centred ~5 m east / 3 m north of the OSM box.
    a = -0.1207
    O = (125.95, -271.26)
    F = Frame(O[0], O[1], a)
    mb, rf = MB("图书馆_主体", O), MB("图书馆_屋顶", O)
    U0, U1, V0, V1 = -47, 47, -27, 20
    box(mb, F, U0, U1, V0, V1, 0, 20.0, "lib_wall", bay=4.2, vspan=20.0)
    box(mb, F, U0 - 0.4, U1 + 0.4, V0 - 0.4, V1 + 0.4, 19.3, 20.0, "cream", bay=3, fh=0.7)
    frustum(rf, F, U0, U1, V0, V1, 20.0, 24.0, 2.6, 2.6, "slate", top="slate_flat", ov=0.4)
    frustum(rf, F, -15, 15, -16, 8, 24.0, 25.8, 2.5, 2.5, "glass_dark", top="glass_dark")
    pav = [(-47.2, -26, -39, -22, (0, 3)), (26, 47.2, -39, -22, (2, 3)), (-47.2, -24, 17, 39, (0, 1)),
           (24, 47.2, 17, 39, (2, 1))]
    for (u0, u1, v0, v1, outer) in pav:
        box(mb, F, u0, u1, v0, v1, 0, 21.5, "lib_wall", bay=4.2, vspan=21.5)
        box(mb, F, u0 - 0.4, u1 + 0.4, v0 - 0.4, v1 + 0.4, 20.8, 21.5, "cream", bay=3, fh=0.7)
        frustum(rf, F, u0, u1, v0, v1, 21.5, 28.5, 3.4, 3.4, "slate", top="slate_flat", ov=0.4)
        frustum(rf, F, u0 + 3.4, u1 - 3.4, v0 + 3.4, v1 - 3.4, 28.5, 29.3, 0.6, 0.6, "slate_flat", top="slate_flat")
        dormers_rect(rf, F, u0 - 0.4, u1 + 0.4, v0 - 0.4, v1 + 0.4, 21.5, 7.0, 3.4, 6.0, hgt=2.4, edges=outer)
    # core dormers, only where the core facade is exposed between the pavilions

    def keep_core(i, s, L):
        p = s / L
        return 0.27 < p < 0.73 if i in (0, 2) else 0.25 < p < 0.75

    dormers_rect(rf, F, U0 - 0.4, U1 + 0.4, V0 - 0.4, V1 + 0.4, 20.0, 4.0, 2.6, 5.6, keep=keep_core)
    # south portico (giant order) + steps
    for k in range(8):
        cyl(mb, F.p(-14 + 4 * k, 22.4), 0.62, 1.2, 13.0, 12, "cream")
    box(mb, F, -15.8, 15.8, 19.8, 23.3, 13.0, 14.6, "cream", top="slate_flat", bot="cream")
    box(mb, F, -16.5, 16.5, 19.5, 25.5, 0, 1.2, "stone", top="stone")
    for i, hgt in enumerate((0.8, 0.4)):
        box(mb, F, -14, 14, 25.5 + i * 0.8, 26.3 + i * 0.8, 0, hgt, "stone", top="stone")
    objs = [mb.build(coll), rf.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862952701, "tower-1"], replaces_names=["图书馆", "图书馆实测塔(tower-1)"],
                height=29.3)


def m_yifulou(coll):
    b = bld(862959368)  # 逸夫楼 (campus.json/official map: 学科4号楼)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb, rf, tw = MB("逸夫楼_主体", O), MB("逸夫楼_屋顶", O), MB("逸夫楼_钟楼", O)
    prism(mb, pts, 0, 17.0, "yf_wall", bay=3.8, vspan=17.0)
    prism(mb, inset(pts, -0.35), 16.4, 17.0, "white", bay=3, fh=0.6)
    hi = inset(pts, 2.1)
    ring(rf, inset(pts, -0.35), 17.0, hi, 20.6, "slate")
    cap(rf, hi, 20.6, "slate_flat")
    ang = -0.0682
    # corner pavilions with taller roofs (positions guessed from the plan + photos)
    for cx, cz, L, W in ((-137.5, -108.0, 13, 18), (-91.0, -173.0, 12, 19), (-55.0, -177.0, 12, 17), (-54.5, -135.0, 12, 11)):
        Fp = Frame(cx, cz, ang)
        box(mb, Fp, -L / 2 - 0.3, L / 2 + 0.3, -W / 2 - 0.3, W / 2 + 0.3, 0, 18.0, "yf_wall", bay=3.8, vspan=18.0)
        box(mb, Fp, -L / 2 - 0.35, L / 2 + 0.35, -W / 2 - 0.35, W / 2 + 0.35, 17.4, 18.0, "white", bay=3, fh=0.6)
        frustum(rf, Fp, -L / 2, L / 2, -W / 2, W / 2, 18.0, 24.5, 3.0, 3.0, "slate", top="slate_flat", ov=0.35)
        dormers_rect(rf, Fp, -L / 2 - 0.35, L / 2 + 0.35, -W / 2 - 0.35, W / 2 + 0.35, 18.0, 6.5, 3.0, 5.5,
                     wmat="white", hgt=2.3)
    dormers_poly(rf, inset(pts, -0.35), 17.0, 3.6, 2.45, 6.5, 3.5, wmat="white")
    # clock tower (DSM peak ~49 m at (-44.5, -148); attached to the east facade)
    Ft = Frame(-48.0, -148.0, ang)
    hw = 4.5
    box(tw, Ft, -hw, hw, -hw, hw, 0, 29.0, "white")
    for k in range(4):
        n = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]
        cu, cv = n[0] * hw, n[1] * hw
        if n[0]:
            box(tw, Ft, min(cu, cu + n[0] * 0.3), max(cu, cu + n[0] * 0.3), -1.2, 1.2, 3.0, 27.5, "glass_blue", top="white",
                bay=2.4, fh=3.2)
        else:
            box(tw, Ft, -1.2, 1.2, min(cv, cv + n[1] * 0.3), max(cv, cv + n[1] * 0.3), 3.0, 27.5, "glass_blue", top="white",
                bay=2.4, fh=3.2)
    box(tw, Ft, -5.0, 5.0, -5.0, 5.0, 29.0, 30.0, "white", top="white", bot="white")
    box(tw, Ft, -4.3, 4.3, -4.3, 4.3, 30.0, 36.5, "white")
    box(tw, Ft, -4.6, 4.6, -4.6, 4.6, 36.2, 36.7, "gold", top="spire", bot="gold")
    for k in range(4):  # clock faces + gables
        nu, nv = [(1, 0), (0, 1), (-1, 0), (0, -1)][k]
        ru, rv = -nv, nu  # right-hand direction seen from outside: (-n) x up
        rx, rz = Ft.vec(ru, rv)
        ox, oz = Ft.vec(nu, nv)
        c = Ft.p(nu * 4.35, nv * 4.35)
        s = 2.4
        tw.face([(c[0] - rx * s, 33.2 - s, c[1] - rz * s), (c[0] + rx * s, 33.2 - s, c[1] + rz * s),
                 (c[0] + rx * s, 33.2 + s, c[1] + rz * s), (c[0] - rx * s, 33.2 + s, c[1] - rz * s)],
                [(0, 0), (1, 0), (1, 1), (0, 1)], "clock", out=(ox, 0, oz))
        g = Ft.p(nu * 4.6, nv * 4.6)
        gb = Ft.p(0, 0)
        gl = (g[0] - rx * 3.3, 36.7, g[1] - rz * 3.3)
        gr = (g[0] + rx * 3.3, 36.7, g[1] + rz * 3.3)
        ga = (g[0], 41.2, g[1])
        tw.face([gl, gr, ga], None, "spire", out=(ox, 0, oz))
        bl = (gb[0] - rx * 3.3, 36.7, gb[1] - rz * 3.3)
        br = (gb[0] + rx * 3.3, 36.7, gb[1] + rz * 3.3)
        bt = (gb[0], 41.2, gb[1])
        tw.face([gl, ga, bt, bl], None, "spire", out=(-rx, 1, -rz))
        tw.face([ga, gr, br, bt], None, "spire", out=(rx, 1, rz))
        beam(tw, gl, ga, 0.22, "gold")
        beam(tw, ga, gr, 0.22, "gold")
    lo = Ft.rect(-4.4, 4.4, -4.4, 4.4)
    ap = Ft.p(0, 0)
    ring(tw, lo, 36.7, [ap] * 4, 49.5, "spire", uvt=2.0)
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        box(tw, Ft, su * 4.6 - 0.45, su * 4.6 + 0.45, sv * 4.6 - 0.45, sv * 4.6 + 0.45, 36.7, 37.6, "gold", top="gold")
        ring(tw, Ft.rect(su * 4.6 - 0.45, su * 4.6 + 0.45, sv * 4.6 - 0.45, sv * 4.6 + 0.45), 37.6,
             [Ft.p(su * 4.6, sv * 4.6)] * 4, 39.8, "gold")
    beam(tw, (ap[0], 49.0, ap[1]), (ap[0], 51.8, ap[1]), 0.25, "gold")
    objs = [mb.build(coll), rf.build(coll), tw.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862959368], replaces_names=["学科4号楼（逸夫楼，钟楼）"], height=51.8)


def m_linjianglou(coll):
    b = bld(1245445293)  # 信息科技大楼 = 临江楼
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb, tw = MB("临江楼_裙楼", O), MB("临江楼_塔楼", O)
    # heights re-checked 2026-11-27 (building audit): podium 6 floors / 25.5 m (re-registered DSM p70 25.1, building
    # asset 26.5; photos 临江楼*.jpg: tall ground floor + 5 floors, set-back blocks with roof gardens); was 17 m.
    # Tower roof 78 m (DSM tower-2 p70 78.5; asset 81.5); was 75 m.
    HP = 25.5
    prism(mb, pts, 0, HP, "lj_podium", top="green", bay=6.0, fh=HP / 6)
    parapet(mb, pts, HP - 0.1, HP + 1.1, 0.3, "white")
    up = inset(pts, 4.5)                                                      # set-back top floor
    prism(mb, up, HP, HP + 3.3, "lj_podium", top="roof_flat", bay=6.0, fh=3.3)
    parapet(mb, up, HP + 3.2, HP + 4.2, 0.25, "white")
    Ft = Frame(-264.6, 30.2, -0.5281)
    box(tw, Ft, -20.95, 20.95, -9.9, 9.9, 0, 69.0, "lj_tower", bay=3.0, fh=3.8)
    box(tw, Ft, -20.95, 20.95, -9.9, 9.9, 69.0, 78.0, "glass_dark", top="roof_flat", bay=3.0, fh=3.0)
    box(tw, Ft, -21.2, 21.2, -10.15, 10.15, 77.4, 78.6, "white", bay=3, fh=1.2)
    box(tw, Ft, -21.2, 21.2, -10.15, 10.15, 68.6, 69.4, "white", bay=3, fh=0.8)
    box(tw, Ft, -9, 9, -5.5, 5.5, 78.0, 81.2, "concrete", top="concrete")
    objs = [mb.build(coll), tw.build(coll)]
    return dict(objs=objs, origin=O, replaces=[1245445293, "tower-2"], replaces_names=["信息科技大楼", "临江楼实测塔(tower-2)"],
                height=81.2, cam=(68, 30))


def m_tiyuguan(coll):
    """东苑体育馆, re-calibrated 2026-11-27 against the building asset (roof profile by ray casting), the 2025-03 oblique
    drone photo (DJI_..._0226), photos/dongyuan_tiyuguan_*, the 2024-12 drone views and the official 2.5D map.
    Frame: u ~ east, v ~ south. North block (v -62..-33, mono-pitch 24.7 -> 20.7 m), plant link (15.6 m), hall whose
    roof falls from 30.6 m at the south front to 22 m at its north end; side ribs sweep from the hall eave down to the
    ground beside the north block; west glazed arcade under a sloping glass canopy; grey metal cladding (photo)."""
    b = bld(478388467)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], math.atan2(-722.4 + 711.42, 1203.29 - 1130.0))
    mb = MB("东苑体育馆", O)
    UW, UE = -36.0, 34.0          # hall west / east wall
    VN, VF, VR = -20.0, 54.0, 62.0  # hall north wall, front wall, roof front edge
    prof = [(-20, 21.9), (-14, 23.5), (-10, 24.6), (-6, 25.6), (-2, 26.5), (2, 27.3), (6, 28.1), (10, 28.7),
            (14, 29.2), (18, 29.7), (22, 30.1), (26, 30.3), (30, 30.5), (34, 30.6), (42, 30.6), (46, 30.4),
            (50, 30.2), (54, 29.9), (58, 29.6), (62, 29.1)]

    def h(v):
        v = min(max(v, prof[0][0]), prof[-1][0])
        for (va, ha), (vb, hb) in zip(prof, prof[1:]):
            if va <= v <= vb:
                return ha + (hb - ha) * (v - va) / (vb - va)
        return prof[-1][1]

    vs = [v for v, _ in prof]
    # hall long walls: glass curtain (4 bands) except the louvred stair section at the front end
    for u, sgn in ((UW, -1), (UE, 1)):
        ox, oz = F.vec(sgn, 0)
        for va, vb in zip(vs, vs[1:]):
            if va >= VF:
                break
            vb = min(vb, VF)
            mat, bay = ("gym_glass", 6.0) if vb <= 40 else ("gym_panel", 3.0)
            ya, yb = h(va) - 1.2, h(vb) - 1.2
            pa, pb = (F.p(u, va), F.p(u, vb)) if sgn > 0 else (F.p(u, vb), F.p(u, va))
            ha_, hb_ = (ya, yb) if sgn > 0 else (yb, ya)
            mb.face([(pa[0], 0, pa[1]), (pb[0], 0, pb[1]), (pb[0], hb_, pb[1]), (pa[0], ha_, pa[1])],
                    [(0, 0), ((vb - va) / bay, 0), ((vb - va) / bay, hb_ / bay), (0, ha_ / bay)], mat, out=(ox, 0, oz))
    # front (south) wall: glass centre, panels at the sides; hall north wall above the plant link
    for u0, u1, mat, bay in ((UW, -20, "gym_panel", 3.0), (-20, 20, "gym_glass", 6.0), (20, UE, "gym_panel", 3.0)):
        wall(mb, F.p(u0, VF), F.p(u1, VF), 0, h(VF) - 1.2, mat, bay, bay)
    wall(mb, F.p(UE, VN), F.p(UW, VN), 15.6, h(VN) - 1.2, "gym_panel", 3.0, 3.0)
    # roof: grey standing-seam metal, 1 m side overhang, cantilevered over the entrance; soffit + edge fascia
    rv = [v for v in vs if v <= VR]
    for va, vb in zip(rv, rv[1:]):
        ha, hb = h(va), h(vb)
        q = [F.p3(UW - 1.0, ha, va), F.p3(UE + 1.0, ha, va), F.p3(UE + 1.0, hb, vb), F.p3(UW - 1.0, hb, vb)]
        uv4 = [(UW / 3, va / 3), (UE / 3, va / 3), (UE / 3, vb / 3), (UW / 3, vb / 3)]
        mb.face(q, uv4, "metal_light", out=(0, 1, -(hb - ha)))
        mb.face([(x, y - 1.2, z) for x, y, z in q], uv4, "steel_white", out=(0, -1, 0))
        for u, sgn in ((UW - 1.0, -1), (UE + 1.0, 1)):
            ox, oz = F.vec(sgn, 0)
            pa, pb = F.p(u, va), F.p(u, vb)
            mb.face([(pa[0], ha - 1.2, pa[1]), (pb[0], hb - 1.2, pb[1]), (pb[0], hb, pb[1]), (pa[0], ha, pa[1])]
                    if sgn > 0 else
                    [(pb[0], hb - 1.2, pb[1]), (pa[0], ha - 1.2, pa[1]), (pa[0], ha, pa[1]), (pb[0], hb, pb[1])],
                    None, "steel_white", out=(ox, 0, oz))
    for v, a_, b_ in ((VR, UW - 1.0, UE + 1.0), (VN, UE + 1.0, UW - 1.0)):  # fascia across the two roof ends
        wall(mb, F.p(a_, v), F.p(b_, v), h(v) - 1.2, h(v), "steel_white", 4, 1.2)
    # tension rods from the cantilever edge to the front wall + under-eave struts along the glass sides
    for u in (-30, -18, -6, 6, 18, 30):
        beam(mb, F.p3(u, h(VR) - 1.2, VR - 0.5), F.p3(u, 18.0, VF), 0.25, "steel_white")
    for u in (UW - 0.5, UE + 0.5):
        for v in range(-14, 40, 6):
            beam(mb, F.p3(u, h(v) - 1.2, v), F.p3(u, h(v) - 4.0, v + 3), 0.25, "steel_white")
    # side ribs: hall eave down to the ground beside the north block (asset: 22.2 m at v -18 -> 3.5 m at v -58)
    rib = [(-18, 22.2), (-22, 20.9), (-26, 19.4), (-30, 17.8), (-34, 16.2), (-38, 14.4), (-42, 12.4), (-46, 10.4),
           (-50, 8.2), (-54, 6.0), (-58, 3.5), (-62, 0.6)]
    for u in (UW - 1.0, UE + 1.0):
        for (va, ha), (vb, hb) in zip(rib, rib[1:]):
            beam(mb, F.p3(u, ha - 0.6, va), F.p3(u, hb - 0.6, vb), 1.1, "steel_white")
    # north block (mono-pitch 24.7 -> 20.7 m) and the plant link with rooftop units
    NB = (-33.0, 33.0, -62.0, -33.0)
    u0, u1, v0, v1 = NB
    hN, hS = 24.7, 20.7
    for (ua, va, ya), (ub, vb_, yb), o in (((u1, v0, hN), (u0, v0, hN), (0, -1)), ((u0, v0, hN), (u0, v1, hS), (-1, 0)),
                                          ((u1, v1, hS), (u1, v0, hN), (1, 0))):
        wall(mb, F.p(ua, va), F.p(ub, vb_), 0, min(ya, yb), "gym_panel", 3.0, 3.0)
        if abs(ya - yb) > 0.01:  # sloping top of the side walls
            pa, pb = F.p(ua, va), F.p(ub, vb_)
            ox, oz = F.vec(*o)
            mb.face([(pa[0], min(ya, yb), pa[1]), (pb[0], min(ya, yb), pb[1]), (pb[0], yb, pb[1]), (pa[0], ya, pa[1])],
                    None, "gym_panel", out=(ox, 0, oz))
    wall(mb, F.p(u0, v1), F.p(u1, v1), 15.6, hS, "gym_panel", 3.0, 3.0)
    q = [F.p3(u0 - 0.6, hN + 0.1, v0 - 0.6), F.p3(u1 + 0.6, hN + 0.1, v0 - 0.6), F.p3(u1 + 0.6, hS + 0.1, v1),
         F.p3(u0 - 0.6, hS + 0.1, v1)]
    mb.face(q[::-1], [(0, 0), (0, 7), (17, 7), (17, 0)], "metal_light", out=(0, 1, 0.1))
    for u in (-24, -12, 0, 12, 24):  # tall entrance doors on the north face
        box(mb, F, u - 3.5, u + 3.5, v0 - 0.4, v0, 0, 7.0, "glass_dark", bay=3.5, fh=7.0)
    box(mb, F, -30, 30, -33, VN, 0, 15.6, "gym_panel", top="roof_flat", bay=3.0, fh=3.9)
    for k in range(12):
        box(mb, F, -27 + 4.6 * k, -24 + 4.6 * k, -29, -24, 15.6, 17.4, "steel_white", top="steel_white", bay=3, fh=1.8)
    # west glazed arcade under a sloping glass canopy (photo 0226): 11 m at the wall down to 8 m at the posts
    for va, vb in ((-14, 4), (4, 22), (22, 32)):
        q = [F.p3(UW - 6.0, 8.0, va), F.p3(UW - 6.0, 8.0, vb), F.p3(UW, 11.0, vb), F.p3(UW, 11.0, va)]
        mb.face(q, [(0, 0), (3, 0), (3, 1), (0, 1)], "gym_glass", out=(-0.5, 1, 0))
        mb.face(q[::-1], [(0, 0), (0, 1), (3, 1), (3, 0)], "gym_glass", out=(0.5, -1, 0))
    for v in range(-14, 33, 6):
        beam(mb, F.p3(UW - 5.8, 0, v), F.p3(UW - 5.8, 8.0, v), 0.35, "steel_white")
        beam(mb, F.p3(UW - 5.8, 8.0, v), F.p3(UW, 11.0, v), 0.25, "steel_white")
    # front: entrance canopy, podium terrace + stairs to the plaza
    box(mb, F, -22, 22, VF, VF + 4.5, 9.0, 9.8, "white", top="metal_light", bot="white", bay=4, fh=0.8)
    box(mb, F, -30, 30, VF - 1.0, VF + 6, 0, 4.5, "stone", top="stone")
    for k in range(8):
        box(mb, F, -26, 26, VF + 6 + k * 1.75, VF + 6 + (k + 1) * 1.75, 0, 4.0 - 0.5 * k, "stone", top="stone")
    for side in (-1, 1):
        box(mb, F, min(side * 26, side * 30), max(side * 26, side * 30), VF + 6, VF + 13, 0, 4.5, "stone", top="stone")
        box(mb, F, min(side * 26, side * 30), max(side * 26, side * 30), VF + 13, VF + 20, 0, 2.2, "stone", top="stone")
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[478388467], replaces_names=["东苑体育馆"], height=30.6)


def m_jianshanyuan(coll):
    """见山园: west hall (campus 862959362) + east main building (extra building jianshan-east: north block, atrium,
    main hall, south block); a lane between them crossed by two narrow glazed links. Positions follow the detail
    session's outlines from the 2024-12 orthophoto (position_audit 2026-11-27): west hall u -53..-30, v -19..43.5,
    east group shifted (-5.5, +19) m in this frame from the earlier OSM-based placement."""
    b = bld(862959362)
    O = centroid(b["pts"])
    F = Frame(-119.14, 15.49, -0.138)
    F2 = Frame(F.cx, F.cz, F.ang + math.pi / 2)  # u' = v, v' = -u
    E = Frame(*F.p(-5.5, 19.0), F.ang)           # east group frame
    mb = MB("见山园", O)
    gable(mb, F2, -18.7, 43.5, 30, 53, 11.0, 8.5, 17.5, 0.65, "js_wall", "metal_roof")    # west hall (ridge N-S)
    gable(mb, E, -12, 16, -41, -21, 7.5, 9.5, 14.5, 0.6, "js_wall", "metal_roof")        # north block
    gable(mb, E, -14, 16, -13, 12, 12.0, 9.0, 21.0, 0.3, "js_wall", "metal_roof")        # main hall
    gable(mb, E, -12, 16, 12.5, 31, 8.5, 8.0, 13.5, 0.45, "js_wall", "metal_roof")       # south block
    mb.face([E.p3(-10, 0, 31.06), E.p3(14, 0, 31.06), E.p3(14, 6.5, 31.06), E.p3(-10, 6.5, 31.06)],
            [(0, 0), (24 / 6, 0), (24 / 6, 6.5 / 6), (0, 6.5 / 6)], "gym_glass", out=(0, 0, 1))  # glazed south front
    box(mb, E, -4, 10, -21, -13, 0, 7.0, "glass_dark", top="roof_flat", bay=2.5, fh=3.5)   # atrium entrance
    for v0, v1 in ((-1.0, 3.0), (33.0, 37.0)):  # two narrow glazed links across the lane (in F, west hall -> east)
        box(mb, F, -30.2, -19.3, v0, v1, 0, 4.5, "glass_dark", top="roof_flat", bay=2.5, fh=4.5)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862959362, "jianshan-east"], replaces_names=["见山园", "见山园东侧主楼"],
                height=21.0, cam=(-58, 26))


def m_laoxiaomen(coll):
    p = POIS["老校门"]
    O = (float(p["x"]), float(p["z"]))
    F = Frame(O[0], O[1], math.radians(p.get("rot", 0)))
    mb = MB("老校门", O)
    # symmetric portal (photo 校门.jpg, ~25 m x 7.5 m): cream frame, brown-tile blocks at both ends,
    # inscription beam over the central opening, two posts making a ~6 m road bay
    box(mb, F, -12.5, 12.5, -2.8, 2.8, 6.2, 7.5, "gate_cream", top="gate_top", bot="gate_cream", bay=4, fh=1.3)
    for sg in (-1, 1):
        def ub(a, b):
            return (min(sg * a, sg * b), max(sg * a, sg * b))
        box(mb, F, *ub(10.8, 12.5), -2.8, 2.8, 0, 6.2, "gate_cream", bay=1.7, fh=2.0)
        box(mb, F, *ub(6.2, 10.8), -2.3, 2.3, 0, 6.2, "brick_red", bay=2.0, fh=2.0, fit=False)
        box(mb, F, *ub(5.4, 6.2), -2.0, 2.0, 0, 6.2, "wood", bay=0.8, fh=2.0)
        box(mb, F, *ub(2.8, 3.5), -0.35, 0.35, 0, 4.3, "gate_cream", bay=0.7, fh=2.0)
    box(mb, F, -5.4, 5.4, -1.6, 1.6, 4.8, 6.2, "stone", bot="stone", bay=2.0, fh=1.4)
    box(mb, F, -5.4, 5.4, -1.2, 1.2, 4.3, 4.8, "wood", bot="wood", bay=1.0, fh=0.5)
    for sv in (1, -1):  # inscription on both faces, readable from each side
        ox, oz = F.vec(0, sv)
        ua, ub_ = (-5.35, 5.35) if sv > 0 else (5.35, -5.35)
        v = sv * 1.65
        mb.face([F.p3(ua, 4.85, v), F.p3(ub_, 4.85, v), F.p3(ub_, 6.15, v), F.p3(ua, 6.15, v)],
                [(0, 0), (1, 0), (1, 1), (0, 1)], "gate_beam", out=(ox, 0, oz))
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[], replaces_poi="老校门", replaces_names=["老校门(poi 装饰)"], height=8.8)


# ================================================================== batch 2
def ray_hit(c, a, poly):
    dx, dz = math.cos(a), math.sin(a)
    best = None
    n = len(poly)
    for i in range(n):
        (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % n]
        ex, ez = x2 - x1, z2 - z1
        den = dx * ez - dz * ex
        if abs(den) < 1e-9:
            continue
        t = ((x1 - c[0]) * ez - (z1 - c[1]) * ex) / den
        u = ((x1 - c[0]) * dz - (z1 - c[1]) * dx) / den
        if t > 1e-6 and -1e-9 <= u <= 1 + 1e-9:
            best = t if best is None else min(best, t)
    return (c[0] + dx * best, c[1] + dz * best)


def courtyard_roof(mb, outer, inner, y, mat):
    """Flat roof between an outer outline and an inner courtyard loop (both star-shaped about the courtyard centre)."""
    c = centroid(inner)
    angs = sorted({round(math.atan2(p[1] - c[1], p[0] - c[0]), 9) for p in list(outer) + list(inner)}
                  | {round(-math.pi + 2 * math.pi * k / 32, 9) for k in range(32)})
    lo = [ray_hit(c, a, outer) for a in angs]
    hi = [ray_hit(c, a, inner) for a in angs]
    if shoelace(lo) > 0:
        lo, hi = lo[::-1], hi[::-1]
    ring(mb, lo, y, hi, y, mat, uvt=4.0)


def frame_tower(mb, F, u, v, s, h, mat, step=3.8):
    """Open concrete frame tower: 4 posts, ring beams every floor, zig-zag braces on every face."""
    cs = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    P = lambda k, y: F.p3(u + cs[k % 4][0] * s / 2, y, v + cs[k % 4][1] * s / 2)
    for k in range(4):
        beam(mb, P(k, 0), P(k, h), 0.65, mat)
    levels = [step * i for i in range(1, int(h // step) + 1)] + [h]
    prev = 0.0
    for li, y in enumerate(levels):
        for k in range(4):
            beam(mb, P(k, y), P(k + 1, y), 0.45, mat)
            a, b_ = (k, k + 1) if li % 2 else (k + 1, k)
            beam(mb, P(a, prev), P(b_, y), 0.35, mat)
        prev = y


def flag(mb, F, u, v, h, cell, w=1.5, fh=1.0, t=0.12):
    beam(mb, F.p3(u, 0, v), F.p3(u, h, v), t, "pole")
    ci, cj = cell % 8, cell // 8
    u0, u1, v0, v1 = ci / 8, (ci + 1) / 8, 1 - (cj + 1) / 4, 1 - cj / 4
    n = F.vec(0, 1)
    for sgn in (1, -1):
        o = 0.01 * sgn
        pts = [F.p3(u, h - 0.15 - fh, v + o), F.p3(u + w, h - 0.15 - fh, v + o), F.p3(u + w, h - 0.15, v + o),
               F.p3(u, h - 0.15, v + o)]
        mb.face(pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], "flags", out=(n[0] * sgn, 0, n[1] * sgn))


def text_face(mb, F, u0, u1, y0, y1, v, mat):
    """Readable text quad on a face whose outward normal is +v in frame F (u grows to the viewer's right)."""
    n = F.vec(0, 1)
    mb.face([F.p3(u0, y0, v), F.p3(u1, y0, v), F.p3(u1, y1, v), F.p3(u0, y1, v)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], mat, out=(n[0], 0, n[1]))


def m_wendelou(coll):
    b = bld(478391045)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb, ct = MB("文德楼_主体", O), MB("文德楼_门楼", O)
    prism(mb, pts, 0, 22.5, "white_band", top="roof_flat", bay=4.0, fh=3.75)
    floor_bands(mb, pts, [3.75 * k for k in range(1, 6)], "white")
    parapet(mb, pts, 22.3, 23.3, 0.25, "white")
    # entrance: west face of the waist between the north and middle courtyard blocks (DSM: low ramp in the notch)
    F = Frame(835.36, -359.55, -0.166)  # u into the building (east), v south
    box(ct, F, -1.5, 16, -9, 9, 0, 26.5, "white_band", bay=4.0, fh=3.75)
    n = F.vec(-1, 0)
    ct.face([F.p3(-1.55, 5.0, 6), F.p3(-1.55, 5.0, -6), F.p3(-1.55, 25.0, -6), F.p3(-1.55, 25.0, 6)],
            [(0, 0), (3, 0), (3, 5), (0, 5)], "glass_blue", out=(n[0], 0, n[1]))
    box(ct, F, -3.5, 18, -11, 11, 26.5, 27.3, "dark_roof", top="dark_roof", bot="dark_roof", bay=4, fh=0.8)
    box(ct, F, 2, 12, -6, 6, 27.3, 28.5, "dark_roof", top="dark_roof", bay=4, fh=1.2)
    for sv in (-1, 1):
        frame_tower(ct, F, -3.2, sv * 11.8, 4.6, 33.0, "white")
    for k in range(12):  # broad stair up to the 2nd-floor entrance
        box(ct, F, -26 + 2 * k, -24 + 2 * k if k < 11 else -1.5, -6, 6, 0, 0.4 * (k + 1), "stone", top="stone")
    for sv in (-1, 1):
        box(ct, F, -26, -1.5, sv * 6 - 0.3 if sv > 0 else -6.3, sv * 6 + 0.3 if sv > 0 else -5.7, 0, 5.6, "white",
            top="white", bay=4, fh=4)
    objs = [mb.build(coll), ct.build(coll)]
    return dict(objs=objs, origin=O, replaces=[478391045], replaces_names=["文德楼"], height=33.0, cam=(-62, 18),
                focus=(822.0, 16.0, -357.0, 34.0))


def m_shangxianlou(coll):
    """尚贤楼, reworked 2026-11-27 (main session brief + renovation check): facade light-brown panels in a white frame
    grid (unchanged 2020 / 2021 / 2024), main roof 31.5 m (asset 31.5 = DSM), dark grey membrane roof (re-roofed by
    2024-12), projecting central bay on the south front (asset 35.3 m), and the central radar tower: two-storey base to
    38.1 m (superseded), see the tower block below (user photo, 2026-11-27)."""
    b = bld(862952687)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], -0.1720)
    mb, st = MB("尚贤楼", O), MB("尚贤楼_雕像", O)
    L2, W2, H = 35.75, 8.85, 31.5
    box(mb, F, -L2, L2, -W2, W2, 0, H, "sx_panel", top="dark_roof", bay=3.6, fh=3.5)
    parapet(mb, F.rect(-L2, L2, -W2, W2), H - 0.2, H + 1.0, 0.25, "white")
    # central bay projecting from the south front, glazed, a storey higher than the roof
    box(mb, F, 7, 16, 2, W2 + 2.6, 0, 35.3, "glass_blue", top="dark_roof", bay=3.0, fh=3.5)
    for u in (7, 16):
        box(mb, F, u - 0.4, u + 0.4, W2, W2 + 2.8, 0, 35.6, "white", top="white", bay=0.8, fh=4)
    box(mb, F, -5, 1, -2, 2, H, 35.2, "white", top="dark_roof", bay=3, fh=3.7)       # small roof house
    # rooftop radar tower, rebuilt from the user's photo (data/zones/fix_shangxianlou/user_tower_sunset.jpg):
    # slender square concrete shaft with a vertical slot showing the zig-zag stair; wider observation cabin with
    # sloped top and bottom bands and a ring of windows; narrow neck; wide cantilevered platform with railings, corner
    # lights; white radome on a low fence ring; four tall lightning rods with nodes; thin antennas.
    # Scale: platform 52.5 m and radome top 55.9 m (asset) -> radome 3.0 m = shaft width; other parts by photo ratio.
    TU, TV, TW = 12.0, 0.0, 1.5  # tower centre (u east of centre ~11-12 m, asset) and half width
    sh0, sh1 = H, 46.9
    for (u0, u1, v0, v1) in ((TU - TW, TU + TW, TV - TW, TV - TW + 0.3), (TU - TW, TU - TW + 0.3, TV - TW, TV + TW),
                             (TU + TW - 0.3, TU + TW, TV - TW, TV + TW), (TU - TW, TU - 0.4, TV + TW - 0.3, TV + TW),
                             (TU + 0.4, TU + TW, TV + TW - 0.3, TV + TW)):
        box(mb, F, u0, u1, v0, v1, sh0, sh1, "concrete", top="concrete", bay=3, fh=3)
    box(mb, F, TU - TW + 0.3, TU + TW - 0.3, TV - TW + 0.3, TV + TW - 0.3, sh0, sh1, "glass_dark", bay=3, fh=3)  # dark core
    z = sh0 + 0.4
    k = 0
    while z + 1.6 < sh1:  # zig-zag stair flights seen through the slot (south face)
        a, b_ = (TU - 0.35, TU + 0.35) if k % 2 == 0 else (TU + 0.35, TU - 0.35)
        beam(mb, F.p3(a, z, TV + TW - 0.15), F.p3(b_, z + 1.6, TV + TW - 0.15), 0.12, "steel_white")
        z += 1.6
        k += 1
    # observation cabin
    ring_down(mb, F.rect(TU - TW, TU + TW, TV - TW, TV + TW), 46.9, F.rect(TU - 2.7, TU + 2.7, TV - 2.7, TV + 2.7), 48.1, "concrete")
    box(mb, F, TU - 2.7, TU + 2.7, TV - 2.7, TV + 2.7, 48.1, 49.4, "glass_dark", bay=0.9, fh=1.3)
    for su in (-1, 1):
        for x in (-1.8, -0.6, 0.6, 1.8):
            box(mb, F, TU + x - 0.06, TU + x + 0.06, TV + su * 2.7 - 0.06, TV + su * 2.7 + 0.06, 48.1, 49.4, "concrete", bay=0.2, fh=1.3)
            box(mb, F, TU + su * 2.7 - 0.06, TU + su * 2.7 + 0.06, TV + x - 0.06, TV + x + 0.06, 48.1, 49.4, "concrete", bay=0.2, fh=1.3)
    ring(mb, F.rect(TU - 2.7, TU + 2.7, TV - 2.7, TV + 2.7), 49.4, F.rect(TU - TW, TU + TW, TV - TW, TV + TW), 50.6, "concrete")
    box(mb, F, TU - TW, TU + TW, TV - TW, TV + TW, 50.6, 51.7, "concrete", bay=3, fh=1.1)  # neck
    # cantilevered platform (sloped underside) with railing and corner lights
    ring_down(mb, F.rect(TU - TW, TU + TW, TV - TW, TV + TW), 51.7, F.rect(TU - 3.85, TU + 3.85, TV - 3.85, TV + 3.85), 52.2, "concrete")
    box(mb, F, TU - 3.85, TU + 3.85, TV - 3.85, TV + 3.85, 52.2, 52.5, "concrete", top="concrete", bay=4, fh=0.3)
    for (u0, u1, v0, v1) in ((TU - 3.8, TU + 3.8, TV - 3.8, TV - 3.7), (TU - 3.8, TU + 3.8, TV + 3.7, TV + 3.8),
                             (TU - 3.8, TU - 3.7, TV - 3.8, TV + 3.8), (TU + 3.7, TU + 3.8, TV - 3.8, TV + 3.8)):
        box(mb, F, u0, u1, v0, v1, 53.4, 53.5, "steel_white", top="steel_white", bay=1, fh=0.1)
    for su in (-3.75, -1.25, 1.25, 3.75):
        for sv in (-3.75, 3.75):
            beam(mb, F.p3(TU + su, 52.5, TV + sv), F.p3(TU + su, 53.5, TV + sv), 0.08, "steel_white")
            beam(mb, F.p3(TU + sv, 52.5, TV + su), F.p3(TU + sv, 53.5, TV + su), 0.08, "steel_white")
    for su in (-1, 1):
        for sv in (-1, 1):
            box(mb, F, TU + su * 3.2 - 0.2, TU + su * 3.2 + 0.2, TV + sv * 3.2 - 0.2, TV + sv * 3.2 + 0.2, 52.5, 52.9,
                "steel_white", top="steel_white", bay=0.4, fh=0.4)  # lights / cameras
            rod = F.p(TU + su * 3.55, TV + sv * 3.55)
            cyl(mb, rod, 0.07, 52.5, 58.3, 6, "steel_white", top="steel_white")
            for zn in (54.5, 56.5):
                cyl(mb, rod, 0.16, zn, zn + 0.25, 6, "steel_white", top="steel_white", bot="steel_white")
    c = F.p(TU, TV)
    cyl(mb, c, 1.65, 52.5, 53.0, 16, "steel_white", top="steel_white")  # low fence ring under the radome
    sphere(mb, (c[0], 54.4, c[1]), 1.5, 18, 12, "radome")
    for du, dv in ((-2.2, 1.4), (2.0, -1.6)):
        cyl(mb, F.p(TU + du, TV + dv), 0.04, 52.5, 56.4, 4, "steel_white", top="steel_white")  # thin antennas
    # entrance canopy under the central bay (photo: "尚贤楼" sign on its fascia)
    box(mb, F, 3, 20, W2 + 2.6, W2 + 6.5, 4.2, 4.9, "white", top="roof_flat", bot="white", bay=3, fh=0.7)
    # bronze statue on a dark granite pedestal on the south lawn (ortho: ~45 m south of the facade)
    Fs = Frame(613.0, -342.0, -0.172)
    box(st, Fs, -4.5, 4.5, -3.5, 3.5, 0, 0.35, "paving", top="paving", bay=3, fh=1)
    box(st, Fs, -1.6, 1.6, -1.3, 1.3, 0.35, 3.6, "granite_dark", top="granite_dark", bay=3.2, fh=3.2)
    c = Fs.p(0, 0)
    cyl(st, c, 0.62, 3.6, 5.3, 12, "bronze", r1=0.46)
    cyl(st, c, 0.46, 5.3, 5.75, 12, "bronze", r1=0.52, top="bronze")
    sphere(st, (c[0], 6.08, c[1]), 0.27, 10, 6, "bronze")
    objs = [mb.build(coll), st.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862952687], replaces_names=["尚贤楼"], height=58.3, cam=(-20, 22))


def m_xingzhenglou(coll):
    """行政楼, re-checked 2026-11-27 (building asset ray-cast height map, 2024-12 oblique drone view, photo
    xingzhenglou_0, official map): 6 floors / main roof 22.8 m (asset 22.8, DSM 22.5); cream stone piers with tall
    glazed bays on the long faces, punched windows on the end/chamfer walls; dark roof; courtyard shifted to match the
    asset (u -23..17, v -4..9.5) with a round glass panoramic lift; four corner penthouses + plant rows; glazed central
    entrance bay on the south face."""
    b = bld(478391048)
    pts = ccw(b["pts"])
    O = centroid(pts)
    F = Frame(O[0], O[1], -0.0935)
    mb = MB("行政楼", O)
    H, NF = 22.8, 6
    n = len(pts)
    for k in range(n):  # long faces (outward normal ~ +-v): glazed bays; ends and chamfers: punched windows
        a, b_ = pts[k], pts[(k + 1) % n]
        ex, ez = b_[0] - a[0], b_[1] - a[1]
        L = math.hypot(ex, ez)
        vx, vz = F.vec(0, 1)
        along_u = abs(ex * vx + ez * vz) / L < 0.3   # edge runs along u -> long north/south face
        wall(mb, a, b_, 0, H, "xz_facade" if along_u and L > 40 else "xz_end", 3.6, H / NF)
    floor_bands(mb, pts, [H * k / NF for k in range(1, NF)], "stone", out=0.08, th=0.18)
    inner = F.rect(-23, 17, -4, 9.5)
    for k in range(4):
        wall(mb, inner[(k + 1) % 4], inner[k], 0, H, "xz_end", 3.6, H / NF)
    courtyard_roof(mb, pts, inner, H + 0.01, "dark_roof")
    parapet(mb, pts, H - 0.2, H + 1.0, 0.3, "stone")
    # round glass panoramic lift in the courtyard (user 2026-11-27: a glass lift shaft, not a stair tower)
    c = F.p(9.3, 7.0)
    cyl(mb, c, 3.2, 0, H + 1.6, 20, "glass_blue", top="white")
    for y in (0.0, H + 1.0):
        cyl(mb, c, 3.35, y, y + 0.6, 20, "white", top="white", bot="white")  # base and top rings of the shaft
    for (u0, u1, v0, v1) in ((-33, -26, -13, -8), (21, 29, -13, -8.5), (-33, -26, 14, 19), (23, 29, 14, 18.5)):
        box(mb, F, u0, u1, v0, v1, H, 25.5, "xz_end", top="dark_roof", bay=3.6, fh=2.7)
    box(mb, F, -7, -3, -9.5, -5.5, H, 26.2, "stone", top="dark_roof", bay=4, fh=3.4)
    for v0 in (-17.5, 15.0):  # plant rows along the north and south roof edges
        for k in range(7):
            box(mb, F, -24 + 4.2 * k, -21 + 4.2 * k, v0, v0 + 2.2, H, H + 1.3, "steel_white", top="steel_white", bay=3, fh=1.3)
    # central entrance bay on the south face: glazed curtain wall, slightly projecting, canopy + steps
    box(mb, F, -8, 8, 21.0, 23.2, 0, H + 0.6, "glass_blue", top="stone", bay=2.0, fh=H / NF)
    box(mb, F, -10, 10, 23.2, 27.0, 4.6, 5.2, "stone", top="stone", bot="stone", bay=4, fh=0.6)
    for k in range(4):
        box(mb, F, -9, 9, 23.2 + 1.2 * k, 24.4 + 1.2 * k, 0, 0.6 - 0.15 * k, "stone", top="stone")
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[478391048], replaces_names=["行政楼"], height=26.2, cam=(-40, 32))


def grid_block(mb, F, L2, W2, H, nf):
    """国际教育学院 / 雷丁学院 style: white grid facade, glass entrance bay, floating roof frame."""
    box(mb, F, -L2, L2, -W2, W2, 0, H, "gj_facade", top="roof_flat", bay=4.0, fh=H / nf)
    floor_bands(mb, F.rect(-L2, L2, -W2, W2), [H * k / nf for k in range(1, nf)], "white", out=0.18, th=0.35)
    box(mb, F, -6.5, 6.5, W2, W2 + 2.2, 0, H + 0.6, "glass_dark", top="white", bay=3.25, fh=H / nf)
    box(mb, F, -8, 8, W2 + 2.2, W2 + 6, 4.2, 4.8, "white", top="roof_flat", bot="white", bay=4, fh=0.6)
    o, y0, y1, bw = 1.8, H + 3.0, H + 4.0, 2.4  # frame slab edge ~1 m deep (photos 0228/0230), top ~21 m
    for (u0, u1, v0, v1) in ((-L2 - o, L2 + o, -W2 - o, -W2 - o + bw), (-L2 - o, L2 + o, W2 + o - bw, W2 + o),
                             (-L2 - o, -L2 - o + bw, -W2 - o, W2 + o), (L2 + o - bw, L2 + o, -W2 - o, W2 + o)):
        box(mb, F, u0, u1, v0, v1, y0, y1, "white", top="white", bot="white", bay=4, fh=1.0)
    u = -L2
    while u <= L2 + 0.01:
        box(mb, F, u - 0.25, u + 0.25, -W2 - o, W2 + o, y0 + 0.2, y1 - 0.1, "white", top="white", bot="white", bay=4, fh=0.7)
        u += 4.0
    for su in (-1, 1):
        for uu in [x * 8.0 for x in range(-int(L2 // 8), int(L2 // 8) + 1)]:
            box(mb, F, uu - 0.3, uu + 0.3, su * W2 - 0.3, su * W2 + 0.3, H, y0, "white", bay=0.6, fh=1)


def m_guojijiaoyu(coll):
    b = bld(1316175146)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], -0.1138)
    mb = MB("国际教育学院", O)
    grid_block(mb, F, 37.45, 15.6, 17.0, 4)  # 4 floors (photo 0230), main roof 17.0 (asset), frame top 21.0 (DSM)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[1316175146], replaces_names=["培训楼（国际教育学院）"], height=21.0, cam=(25, 25))


def m_leiding(coll):
    b = bld(478391050)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], -0.1211)
    mb = MB("雷丁学院", O)
    grid_block(mb, F, 30.85, 13.45, 17.0, 4)
    reading_drum(mb)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[478391050], replaces_names=["雷丁学院"], height=21.0, cam=(25, 25))


def reading_drum(mb):
    """The oval 'Reading Academy' drum in the courtyard between 雷丁学院 (north) and 培训楼 (south), joined to both:
    DSM 2024-12 (plan offset removed): ~39 x 19 m oval, ~14 m high, centred between the two wings; a 13 m link to
    雷丁学院 and a one-storey link to 培训楼 (the ground-floor connection; building assets have stubs there).
    Photo 0228: open colonnade on the ground floor, white band, three floors of dark glass facing west, white sides.
    User (2026-11-27): both wings 4 floors; floors 1-3 connected through the drum and links, the 4th floor not."""
    G = Frame(1200.0, -455.0, -0.1211)
    cu, cv, A, B = -1.5, 6.5, 19.5, 9.5
    N = 40
    outer = ccw([G.p(cu + A * math.cos(2 * math.pi * k / N), cv + B * math.sin(2 * math.pi * k / N)) for k in range(N)])
    inner = ccw([G.p(cu + (A - 2.4) * math.cos(2 * math.pi * k / N), cv + (B - 2.4) * math.sin(2 * math.pi * k / N))
                 for k in range(N)])
    prism(mb, inner, 0, 4.5, "glass_dark", bay=3.0, fh=4.5)
    for k in range(N):  # soffit over the colonnade (faces down)
        a, b_, c, d = outer[k], outer[(k + 1) % N], inner[(k + 1) % N], inner[k]
        mb.face([(a[0], 4.5, a[1]), (b_[0], 4.5, b_[1]), (c[0], 4.5, c[1]), (d[0], 4.5, d[1])], None, "white", out=(0, -1, 0))
    wx, wz = G.vec(-1, 0)
    for k in range(N):
        a, b_ = outer[k], outer[(k + 1) % N]
        mx, mz = (a[0] + b_[0]) / 2 - G.p(cu, cv)[0], (a[1] + b_[1]) / 2 - G.p(cu, cv)[1]
        west = (mx * wx + mz * wz) / max(1e-6, math.hypot(mx, mz)) > 0.55
        wall(mb, a, b_, 4.5, 6.8, "white", 3.0, 2.3)
        wall(mb, a, b_, 6.8, 12.8, "glass_dark" if west else "white", 3.0, 3.0)
        wall(mb, a, b_, 12.8, 14.0, "white", 3.0, 1.2)
        if k % 3 == 0:
            q = G.p(cu + (A - 0.7) * math.cos(2 * math.pi * (k + 0.5) / N), cv + (B - 0.7) * math.sin(2 * math.pi * (k + 0.5) / N))
            cyl(mb, q, 0.4, 0, 4.5, 10, "white")
    cap(mb, outer, 14.0, "roof_flat")
    parapet(mb, outer, 13.9, 14.7, 0.25, "white")
    # links to both wings: floors 1-3 connected, the 4th floor not (user, 2026-11-27); top at the 4th floor slab
    HL = 3 * 17.0 / 4
    box(mb, G, -2.5, 2.5, -10.5, -2.6, 0, HL, "gj_facade", top="roof_flat", bay=4.0, fh=17.0 / 4)  # to 雷丁学院
    box(mb, G, -3.5, 1.0, 15.6, 18.6, 0, HL, "gj_facade", top="roof_flat", bay=4.0, fh=17.0 / 4)   # to 培训楼


def m_shengqi(coll):
    p = POIS["升旗广场"]
    O = (float(p["x"]), float(p["z"]))
    F = Frame(O[0], O[1], -0.1138)  # aligned with 国际教育学院 (培训楼)
    mb = MB("升旗广场", O)
    k = 2
    for u0, n_u in ((-29, 7), (5, 9)):
        for i in range(n_u):
            for j in range(7):
                flag(mb, F, u0 + 4 * i, -8 + 4 * j, 7.5, k % 30 + 2)
                k += 7
    box(mb, F, -2.4, 2.4, -15.6, -13.4, 0, 1.1, "granite_dark", top="granite_dark", bay=2.4, fh=1.1)
    for u, cell, h in ((-1.5, 1, 13.0), (0.0, 0, 14.5), (1.5, 1, 13.0)):
        flag(mb, F, u - 0.75, -14.5, h, cell, w=2.4, fh=1.6, t=0.18)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[], replaces_poi="升旗广场", replaces_names=["升旗广场(poi 装饰)"], height=14.5,
                cam=(25, 30))


def m_oufanglou(coll):
    b = bld(1114839562)
    O = centroid(b["pts"])
    mb, tr = MB("藕舫楼_主楼", O), MB("藕舫楼_退台", O)
    tall = [(550.76, -540.52), (554.04, -521.58), (589.42, -527.65), (592.35, -510.76), (593.0, -499.13),
            (614.19, -502.89), (606.01, -550.01)]
    # tower: 9 floors, main roof 34.2 m (audit 2026-11-27: building asset and re-registered drone DSM both 34.3 m;
    # photo 藕舫楼.JPG); was 27 m
    HT = 34.2
    prism(mb, tall, 0, HT, "of_facade", top="roof_flat", bay=3.4, fh=3.8)
    floor_bands(mb, tall, [3.8 * k for k in range(1, 9)], "white")
    parapet(mb, tall, HT - 0.2, HT + 0.9, 0.25, "white")
    Fr = Frame(*centroid(tall), -0.1702)
    for u, v in ((10, -8), (-12, -10)):
        box(mb, Fr, u - 3, u + 3, v - 2.5, v + 2.5, HT, HT + 3.0, "of_facade", top="roof_flat", bay=3.4, fh=3)
    for k in range(10):  # outdoor AC units along the north wing roof (photo)
        box(mb, Fr, -14 + 2.2 * k, -12.6 + 2.2 * k, -2.5, -0.8, HT, HT + 1.4, "steel_white", top="steel_white", bay=2, fh=1.4)
    # raised courtyard garden between the L and the terrace wing: ~9.4 m (asset + DSM), green roof, pyramid skylights
    pod = [(554.04, -521.58), (589.42, -527.65), (592.35, -510.76), (563.73, -505.84)]
    prism(mb, pod, 0, 9.4, "of_facade", top="green", bay=3.4, fh=4.7)
    Fp = Frame(570.0, -516.0, -0.1702)
    for du in (-4.5, 0.0, 4.5):
        ring(mb, Fp.rect(du - 2, du + 2, -2, 2), 9.4, [Fp.p(du, 0)] * 4, 11.2, "glass_blue")
    # south wing: terraces stepping down to the west (photo 藕舫楼.JPG), roof gardens on each step
    E0, E1, W0, W1 = (592.35, -510.76), (593.0, -499.13), (563.73, -505.84), (565.68, -494.55)
    lerp = lambda a, b_, t: (a[0] + (b_[0] - a[0]) * t, a[1] + (b_[1] - a[1]) * t)
    for i, h in enumerate((23.4, 19.8, 16.2, 12.6)):
        t0, t1 = i / 4, (i + 1) / 4
        q = [lerp(E0, W0, t0), lerp(E0, W0, t1), lerp(E1, W1, t1), lerp(E1, W1, t0)]
        prism(tr, q, 0, h, "of_facade", top="roof_flat", bay=3.4, fh=3.6)
        g = inset(q, 1.3)
        prism(tr, g, h, h + 0.35, "white", top="green", bay=3, fh=1)
    objs = [mb.build(coll), tr.build(coll)]
    return dict(objs=objs, origin=O, replaces=[1114839562], replaces_names=["藕舫楼"], height=37.2, cam=(-35, 35))


def m_binjianglou(coll):
    b = bld(862959375)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb, ct = MB("滨江楼_主体", O), MB("滨江楼_门楼", O)
    prism(mb, pts, 0, 19.5, "white_band", top="roof_flat", bay=4.0, fh=3.8)
    floor_bands(mb, pts, [3.8 * k for k in range(1, 5)], "white")
    parapet(mb, pts, 19.3, 20.3, 0.25, "white")
    F = Frame(-327.8, 144.0, -0.54)  # centre of the south (front) facade; v points out of the building
    box(ct, F, -9, 9, -16, 2.5, 0, 23.5, "white", top="roof_flat", bay=4, fh=4)
    n = F.vec(0, 1)
    ct.face([F.p3(-5.5, 4.2, 2.55), F.p3(5.5, 4.2, 2.55), F.p3(5.5, 16.6, 2.55), F.p3(-5.5, 16.6, 2.55)],
            [(0, 0), (2, 0), (2, 3), (0, 3)], "glass_dark", out=(n[0], 0, n[1]))
    for y in (8.4, 12.6):
        box(ct, F, -5.5, 5.5, 2.5, 3.6, y, y + 0.3, "white", top="white", bot="white", bay=4, fh=0.3)
    text_face(ct, F, -4.2, 4.2, 18.6, 20.7, 2.56, "bj_name")
    for su in (-1, 1):
        box(ct, F, su * 6.5 - 1.8, su * 6.5 + 1.8, -2.5, 1.1, 23.5, 27.0, "white", bay=3.6, fh=3.5)
        box(ct, F, su * 6.5 - 2.4, su * 6.5 + 2.4, -3.1, 1.7, 27.0, 27.6, "dark_roof", top="dark_roof", bot="dark_roof",
            bay=4, fh=0.6)
    for k in range(6):
        box(ct, F, -7, 7, 2.5 + k * 1.1, 3.6 + k * 1.1, 0, 1.8 - 0.3 * k, "stone", top="stone")
    objs = [mb.build(coll), ct.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862959375], replaces_names=["滨江楼"], height=27.6, cam=(31, 24))


def _delegate(module, fn_name, defaults=None):
    """Registry entry for a model another session owns: run its builder with this module shared as
    `blender_landmarks` (one MAT_SPEC / material cache), filling any result keys main() needs."""
    def fn(coll):
        import importlib
        sys.modules.setdefault("blender_landmarks", sys.modules[__name__])
        if str(Path(__file__).resolve().parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
        info = getattr(importlib.import_module(module), fn_name)(coll)
        for k, v in (defaults or {}).items():
            info.setdefault(k, v)
        return info
    return fn


# 东苑美食街街面 (street furniture in front of the container street): detail-correction session, tools/blender_jzx_street.py
m_jzx_street = _delegate("blender_jzx_street", "m_street", dict(replaces=[], replaces_names=[]))


def m_dongdamen(coll):
    """东大门 is owned by the detail-correction session: tools/blender_dongdamen.py (v3, ~14k tris). Delegate to it,
    sharing this module's material cache: its `import blender_landmarks as L` must resolve to *this* module object
    (also when this file runs as __main__), otherwise it would get a second copy whose _MATS goes stale."""
    sys.modules.setdefault("blender_landmarks", sys.modules[__name__])
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import blender_dongdamen  # registers its ddm_* materials in MAT_SPEC on import
    return blender_dongdamen.m_dongdamen(coll)


# ================================================================== vehicles
BUS_L, BUS_W, BUS_H = 6.2, 2.1, 2.65  # body size covered by bus_atlas.jpg (AC units add 0.25 m)


def _bus_uv(p, reg):
    x, y, z = p
    L, W, H = BUS_L, BUS_W, BUS_H
    cl = lambda t: min(max(t, 0.002), 0.998)
    if reg == "L":
        return (0.5 * cl((z + L / 2) / L), 0.5 + 0.5 * cl(y / H))
    if reg == "R":
        return (0.5 + 0.5 * cl((L / 2 - z) / L), 0.5 + 0.5 * cl(y / H))
    if reg == "F":
        return (0.25 * cl((W / 2 - x) / W), 0.5 * cl(y / H))
    if reg == "B":
        return (0.25 + 0.25 * cl((x + W / 2) / W), 0.5 * cl(y / H))
    if reg == "T":
        return (0.5 + 0.25 * cl((x + W / 2) / W), 0.5 * cl((z + L / 2) / L))
    return (0.9, 0.35)


def bus_face(mb, pts, mat="bus"):
    """Box-projected UVs into the bus atlas, region picked from the face normal."""
    n = newell(pts)
    ax = max(range(3), key=lambda i: abs(n[i]))
    reg = ("R" if n[0] > 0 else "L") if ax == 0 else (("B" if n[2] > 0 else "F") if ax == 2 else ("T" if n[1] > 0 else "U"))
    mb.face(pts, [_bus_uv(p, reg) for p in pts], mat)


def rrect_loop(w, zf, zr, r, k=6):
    pts = []
    for cx, cz, a0 in ((w - r, zr - r, 0), (-w + r, zr - r, 90), (-w + r, zf + r, 180), (w - r, zf + r, 270)):
        for i in range(k + 1):
            a = math.radians(a0 + 90 * i / k)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    return pts[::-1]  # math-ccw in (x, z) -> map-ccw


def wheel(mb, cx, cy, cz, r, w, side, n=18):
    xo, xi = cx + side * w / 2, cx - side * w / 2
    ring_ = [(cy + r * math.sin(2 * math.pi * i / n), cz + r * math.cos(2 * math.pi * i / n)) for i in range(n)]
    for i in range(n):
        (y0, z0), (y1, z1) = ring_[i], ring_[(i + 1) % n]
        am = 2 * math.pi * (i + 0.5) / n
        mb.face([(xo, y0, z0), (xo, y1, z1), (xi, y1, z1), (xi, y0, z0)], None, "bus_tire", True,
                out=(0, math.sin(am), math.cos(am)))
    rim = [(xo + side * 0.004, cy + 0.92 * r * math.sin(2 * math.pi * i / n), cz + 0.92 * r * math.cos(2 * math.pi * i / n))
           for i in range(n)]
    uv = [(0.8125 + 0.0586 * math.cos(2 * math.pi * i / n), 0.125 + 0.117 * math.sin(2 * math.pi * i / n)) for i in range(n)]
    mb.face(rim, uv, "bus", out=(side, 0, 0))
    mb.face([(xo, y, z) for y, z in ring_], None, "bus_tire", out=(side, 0, 0))
    mb.face([(xi, y, z) for y, z in ring_], None, "bus_tire", out=(-side, 0, 0))


def disc(mb, c, r, n, mat, out):
    """Vertical disc facing -z (front lamps)."""
    cx, cy, cz = c
    mb.face([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), cz) for i in range(n)],
            [(0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 + 0.5 * math.sin(2 * math.pi * i / n)) for i in range(n)],
            mat, out=out)


def m_bus(coll):
    """校园小公交: 6.2 x 2.1 x 2.9 m, front towards -z, origin on the ground under the body centre."""
    mb = MB("校园小公交", (0.0, 0.0))
    loops = [(0.30, 0.98, -3.02, 3.02, 0.25), (0.42, 1.05, -3.10, 3.10, 0.30), (1.18, 1.05, -3.10, 3.10, 0.30),
             (1.26, 1.04, -3.06, 3.08, 0.30), (2.38, 1.00, -2.88, 3.02, 0.30), (2.56, 0.94, -2.76, 2.96, 0.26),
             (2.65, 0.82, -2.58, 2.82, 0.20)]
    L = [(y, rrect_loop(w, zf, zr, r)) for y, w, zf, zr, r in loops]
    for (ya, A), (yb, B) in zip(L, L[1:]):
        n = len(A)
        for j in range(n):
            k = (j + 1) % n
            bus_face(mb, [(A[j][0], ya, A[j][1]), (A[k][0], ya, A[k][1]), (B[k][0], yb, B[k][1]), (B[j][0], yb, B[j][1])])
    yt, T = L[-1]
    bus_face(mb, [(x, yt, z) for x, z in T])
    y0, B0 = L[0]
    mb.face([(x, y0, z) for x, z in B0][::-1], None, "bus_under", out=(0, -1, 0))
    for side in (-1, 1):
        for cz in (-1.70, 1.75):
            wheel(mb, side * 0.96, 0.36, cz, 0.36, 0.24, side)
        for y, r_ring, r_lens in ((0.80, 0.17, 0.125), (0.52, 0.08, 0.06)):
            disc(mb, (side * 0.62, y, -3.112), r_ring, 16, "chrome", (0, 0, -1))
            disc(mb, (side * 0.62, y, -3.118), r_lens, 16, "bus_lamp", (0, 0, -1))
        beam(mb, (side * 0.98, 2.05, -2.92), (side * 1.20, 2.12, -3.16), 0.06, "bus_black")
        box(mb, Frame(side * 1.24, -3.19, 0.0), -0.04, 0.04, -0.1, 0.1, 1.76, 2.14, "bus_black", top="bus_black",
            bot="bus_black", bay=1, fh=1)
    for zc in (-1.45, 1.05):  # roof air-conditioning units
        F = Frame(0.0, zc, 0.0)
        box(mb, F, -0.55, 0.55, -0.5, 0.5, 2.62, 2.90, "white", top="white", bay=1.1, fh=0.3)
        for sx in (-1, 1):
            mb.face([(sx * 0.556, 2.67, zc - 0.4), (sx * 0.556, 2.67, zc + 0.4), (sx * 0.556, 2.85, zc + 0.4),
                     (sx * 0.556, 2.85, zc - 0.4)], None, "bus_grille", out=(sx, 0, 0))
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=(0.0, 0.0), vehicle=True, height=2.9, length=6.2, width=2.1, cam=(150, 16),
                cam2=(-105, 10))


# ================================================================== batch 3
def m_shuiyunfang(coll):
    b = bld(1114843838)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb = MB("水云方", O)
    prism(mb, pts, 0, 6.0, "concrete", top="roof_flat", bay=4, fh=3)          # beige stone annex (north part)
    parapet(mb, pts, 5.9, 6.6, 0.2, "stone")
    # hall moved (-9, +8) with the detail session's outline (position_audit 2026-11-27), east wall ~5 m further east
    hall = [(-145.46, 144.46), (-137.78, 207.89), (-90.41, 201.25), (-98.75, 138.15)]
    prism(mb, hall, 0, 10.2, "gym_glass", bay=6.0, fh=5.1)                     # glazed pool hall
    prism(mb, hall, 10.2, 12.2, "white", top="metal_light", bay=4, fh=2)
    prism(mb, inset(hall, -1.0), 12.2, 12.6, "white", top="metal_light", bot="white", bay=4, fh=0.4)  # roof overhang
    Fe = Frame(-121.0, 114.2, -0.13)                                            # orange entrance portal, north side (guessed)
    box(mb, Fe, -3.0, 3.0, -1.2, 1.5, 0, 4.6, "orange", top="orange", bay=2, fh=2)
    # one-storey annex against the east side of the hall, dark roof (building audit 2026-11-27: building asset
    # "水云方附楼" 4.7 m and the re-registered drone DSM ~5 m both show it; ~16 x 41 m, parallel to the hall)
    Fa = Frame(-82.0, 168.0, -0.1325)
    box(mb, Fa, -8.0, 8.0, -20.0, 21.0, 0, 4.7, "concrete", top="roof_flat", bay=4, fh=4.7)  # light roof (drone)
    box(mb, Fa, -3.0, 3.0, -2.0, 4.0, 4.7, 4.95, "green", top="green", bay=3, fh=0.25)  # small roof garden
    parapet(mb, Fa.rect(-8.0, 8.0, -20.0, 21.0), 4.6, 5.2, 0.2, "stone")
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[1114843838], replaces_names=["水云方（游泳馆）"], height=12.6, cam=(-30, 30))


def m_qixianggu(coll):
    b = bld(1316305740)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb = MB("气象谷美食城", O)
    # 6 floors / main roof 21.6 m, penthouse 25.5 m (2026-11-27 audit: building asset 21.5 / 25.5, re-registered DSM
    # p70 22.2, p95 24.5; photos 气象谷*.jpg ~6 glass floors + rooftop box); was 7 x 3.75 m + penthouse = 29.3 m
    fh, nf = 3.6, 6
    prism(mb, pts, 0, fh * nf, "qg_glass", top="roof_flat", bay=3.0, fh=fh)
    for k in range(1, nf + 1):  # white floor slabs proud of the curtain wall
        prism(mb, inset(pts, -0.35 - 0.12 * (k % 2)), k * fh - 0.35, k * fh, "white", top="white" if k == nf else None,
              bot="white", bay=4, fh=0.35)
    F = Frame(O[0], O[1], -0.136)
    box(mb, F, -12, 6, -4, 4, fh * nf, 25.5, "white", top="roof_flat", bay=3, fh=3.9)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[1316305740], replaces_names=["气象谷美食城"], height=25.5, cam=(20, 24))


def m_leidata(coll):
    p = POIS["雷达塔"]
    O = (float(p["x"]), float(p["z"]))
    mb = MB("雷达塔", O)
    c = O
    cyl(mb, c, 3.0, 0, 1.0, 20, "stone", top="stone")
    cyl(mb, c, 1.7, 1.0, 26.0, 20, "white")
    F = Frame(c[0], c[1], 0.0)
    box(mb, F, -0.35, 0.35, 1.68, 1.76, 3.0, 24.5, "glass_dark", bay=0.7, fh=3)  # stair-window slit
    cyl(mb, c, 3.3, 26.0, 26.4, 24, "white", top="white", bot="white")
    cyl(mb, c, 2.8, 26.4, 31.0, 24, "white")
    cyl(mb, c, 2.83, 27.6, 29.8, 24, "glass_dark")
    cyl(mb, c, 3.3, 31.0, 31.5, 24, "white", top="white", bot="white")
    cyl(mb, c, 1.8, 31.5, 32.4, 16, "white")
    sphere(mb, (c[0], 36.3, c[1]), 4.2, 24, 14, "radome")
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[], replaces_poi="雷达塔", replaces_names=["雷达塔(poi 装饰)"], height=40.5,
                cam=(30, 12), focus=(419.0, 20.0, -538.0, 24.0))


def m_bus_shelter(coll):
    """Generic campus bus shelter, 4 m x 1.6 m, open side towards -z, origin on the ground at the centre."""
    mb = MB("公交候车亭", (0.0, 0.0))
    F = Frame(0.0, 0.0, 0.0)
    box(mb, F, -2.1, 2.1, -0.85, 0.85, 2.45, 2.62, "bus_blue", top="white", bot="white", bay=4.2, fh=0.17)
    for x in (-1.95, 1.95):
        for z in (-0.65, 0.65):
            box(mb, F, x - 0.05, x + 0.05, z - 0.05, z + 0.05, 0, 2.45, "bus_blue", bay=0.1, fh=1)
    box(mb, F, -1.9, 1.9, 0.62, 0.68, 0.25, 2.3, "glass_blue", top="white", bot="white", bay=1.27, fh=2.05)  # back panel
    box(mb, F, 1.88, 1.94, -0.2, 0.62, 0.25, 2.3, "glass_blue", top="white", bot="white", bay=0.8, fh=2.05)   # side panel
    box(mb, F, -1.4, 1.4, 0.22, 0.58, 0.44, 0.50, "concrete", top="concrete", bot="concrete", bay=2.8, fh=0.06)  # bench
    for x in (-1.2, 0.0, 1.2):
        box(mb, F, x - 0.03, x + 0.03, 0.3, 0.5, 0, 0.44, "bus_black", bay=0.1, fh=0.44)
    n = F.vec(0, -1)
    mb.face([(1.0, 2.465, -0.86), (-1.0, 2.465, -0.86), (-1.0, 2.605, -0.86), (1.0, 2.605, -0.86)],
            [(0, 0), (1, 0), (1, 1), (0, 1)], "shelter_sign", out=(n[0], 0, n[1]))
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=(0.0, 0.0), vehicle=True, height=2.62, length=1.7, width=4.2, cam=(160, 18),
                note="公交候车亭：开口朝 -z，背板在 +z，原点地面中心", kind="prop")


def m_gatehouse(coll):
    """Reusable campus-gate guard house (门卫岗亭), from the 2024-12 drone photo of the 东苑 gate by 东苑食堂 (NE corner):
    light-grey flat-roofed box ~10 x 4.6 m, dark roof with a white rim, window band, and three tall white fins at the
    west end. Long side along x, window/door side towards -z, fins at -x; origin on the ground at the centre of the body.
    Placed per gate from the detail session's gate list (not in models.json)."""
    mb = MB("门卫岗亭", (0.0, 0.0))
    F = Frame(0.0, 0.0, 0.0)
    L, D, H = 10.0, 4.6, 3.4
    box(mb, F, -L / 2, L / 2, -D / 2, D / 2, 0, H, "white", bay=L, fh=H)
    box(mb, F, -L / 2 - 0.3, L / 2 + 0.3, -D / 2 - 0.3, D / 2 + 0.3, H, H + 0.35, "white", top="dark_roof", bot="white",
        bay=4, fh=0.35)
    # window band on the front and the two ends, door near the east end of the front
    box(mb, F, -3.6, 2.4, -D / 2 - 0.05, -D / 2 + 0.05, 1.0, 2.5, "glass_blue", bay=1.5, fh=1.5)
    box(mb, F, 3.2, 4.3, -D / 2 - 0.05, -D / 2 + 0.05, 0.0, 2.4, "glass_blue", bay=1.1, fh=2.4)
    for x in (-L / 2, L / 2):
        box(mb, F, x - 0.05, x + 0.05, -1.4, 1.4, 1.0, 2.5, "glass_blue", bay=1.4, fh=1.5)
    box(mb, F, -L / 2 + 0.4, L / 2 - 0.4, -D / 2 - 0.12, -D / 2, 2.5, 2.62, "white", top="white", bay=4, fh=0.12)
    for k in range(3):  # white fins rising above the roof, slightly proud of both long faces
        x = -L / 2 + 0.5 + 1.2 * k
        box(mb, F, x - 0.25, x + 0.25, -D / 2 - 0.8, D / 2 + 0.4, 0, 6.0, "white", top="white", bay=1, fh=6.0)
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=(0.0, 0.0), vehicle=True, height=6.0, length=D, width=L, cam=(200, 22),
                note="门卫岗亭：长边沿 x（10 m），窗和门朝 -z，白色竖鳍在 -x 端，原点地面中心", kind="prop")


def m_ebike(coll):
    """7ma shared e-bike: blue, 3 materials, front towards -z, origin on the ground."""
    mb = MB("7ma电动车", (0.0, 0.0))
    F = Frame(0.0, 0.0, 0.0)
    for zc in (-0.62, 0.58):
        n, r, w = 14, 0.22, 0.06
        ring_ = [(0.22 + r * math.sin(2 * math.pi * i / n), zc + r * math.cos(2 * math.pi * i / n)) for i in range(n)]
        for i in range(n):
            (y0, z0), (y1, z1) = ring_[i], ring_[(i + 1) % n]
            am = 2 * math.pi * (i + 0.5) / n
            mb.face([(w / 2, y0, z0), (w / 2, y1, z1), (-w / 2, y1, z1), (-w / 2, y0, z0)], None, "ebike_black", True,
                    out=(0, math.sin(am), math.cos(am)))
        for sx in (1, -1):
            mb.face([(sx * w / 2, 0.22 + 0.13 * math.sin(2 * math.pi * i / 10), zc + 0.13 * math.cos(2 * math.pi * i / 10))
                     for i in range(10)], None, "ebike_gray", out=(sx, 0, 0))
            mb.face([(sx * w / 2 * 0.99, y, z) for y, z in ring_], None, "ebike_black", out=(sx, 0, 0))
    beam(mb, (0.06, 0.95, -0.50), (0.06, 0.22, -0.62), 0.04, "ebike_gray")   # fork
    beam(mb, (-0.06, 0.95, -0.50), (-0.06, 0.22, -0.62), 0.04, "ebike_gray")
    beam(mb, (0, 0.92, -0.49), (0, 0.36, -0.08), 0.13, "ebike_blue")         # step-through body
    box(mb, F, -0.13, 0.13, -0.12, 0.40, 0.28, 0.42, "ebike_blue", top="ebike_black", bot="ebike_black", bay=1, fh=1)
    beam(mb, (0, 0.36, 0.30), (0, 0.80, 0.33), 0.09, "ebike_blue")          # seat post cover
    box(mb, F, -0.11, 0.11, 0.14, 0.52, 0.80, 0.90, "ebike_black", top="ebike_black", bot="ebike_black", bay=1, fh=1)
    box(mb, F, -0.12, 0.12, 0.40, 0.82, 0.60, 0.76, "ebike_blue", top="ebike_blue", bot="ebike_blue", bay=1, fh=1)  # rear box
    beam(mb, (0, 0.40, 0.40), (0, 0.42, 0.80), 0.05, "ebike_gray")          # rear fender stay
    beam(mb, (0, 0.95, -0.50), (0, 1.08, -0.56), 0.05, "ebike_gray")        # stem
    beam(mb, (-0.32, 1.08, -0.56), (0.32, 1.08, -0.56), 0.035, "ebike_gray")  # handlebar
    for sx in (-1, 1):
        beam(mb, (sx * 0.22, 1.08, -0.56), (sx * 0.33, 1.08, -0.56), 0.05, "ebike_black")
    box(mb, F, -0.17, 0.17, -0.84, -0.60, 0.80, 0.98, "ebike_blue", top=None, bot="ebike_blue", bay=1, fh=1)  # basket
    box(mb, F, -0.06, 0.06, -0.62, -0.56, 0.86, 0.94, "ebike_gray", bay=1, fh=1)                              # headlamp
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=(0.0, 0.0), vehicle=True, height=1.1, length=1.75, width=0.66, cam=(140, 16),
                note="7ma 共享电动车：3 个材质，车头朝 -z，原点地面", kind="vehicle")


# ================================================================== generic buildings (non-landmarks)
def _hex(h, k=1.0):
    h = h.lstrip("#")
    return tuple(min(1.0, int(h[i:i + 2], 16) / 255.0 * k) for i in (0, 2, 4))


def point_in(x, z, pts):
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        xi, zi = pts[i]
        xj, zj = pts[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def gen_building(g, origin):
    """One generic building: tinted facade + plinth + floor bands + parapet/flat roof with plant, or hip roof,
    + entrance canopy. Mesh relative to `origin` (the building centroid)."""
    pts = ccw(g["pts"])
    mb = MB(str(g["id"]), origin)
    H = float(g["h"])
    kind = g.get("kind")
    lv = int(g.get("lv") or max(1, round((H - 1.2) / 3.3)))
    lv = max(1, min(lv, 30))
    hip = bool(g.get("roof"))
    wall_c, roof_c = _hex(g["wall"]), _hex(g["roofcol"])
    if wall_c[1] > max(wall_c[0], wall_c[2]) + 0.05:  # sampled vegetation, not a wall
        wall_c = (0.9, 0.9, 0.88)
    # the illustrated map over-saturates (blue shading): pull walls 45 % towards a light warm grey
    wall_c = tuple(0.55 * v + 0.45 * w for v, w in zip(wall_c, (0.93, 0.92, 0.9)))
    if not g.get("roof"):  # flat roofs: tone the sampled colour towards light grey
        roof_c = tuple(0.5 * v + 0.5 * 0.78 for v in roof_c)
    if kind == "hall" or (H / lv > 5.5):
        style, mat, bay = "hall", "gen_hall_t", 6.0
    elif kind in ("teach", "other", "canteen") and H / lv > 3.5:
        style, mat, bay = "office", "gen_office_t", 4.0
    else:
        style, mat, bay = "dorm", "gen_dorm_t", 3.6
    top_wall = H if hip else H - 0.6
    fh = top_wall / lv
    # walls, plinth, floor bands
    mb.col = wall_c
    prism(mb, pts, 0, top_wall, mat, bay=bay, fh=(6.0 if style == "hall" else fh))
    mb.col = tuple(v * 0.72 for v in wall_c)
    prism(mb, inset(pts, -0.08), 0, 0.7, "gen_trim_t", bay=4, fh=1)
    ring(mb, inset(pts, -0.08), 0.7, pts, 0.7, "gen_trim_t")
    if style != "hall" and lv > 1:
        mb.col = tuple(min(1.0, v * 1.06) for v in wall_c)
        floor_bands(mb, pts, [fh * k for k in range(1, lv)], "gen_trim_t", out=0.09, th=0.2)
    # roof
    if hip:
        cx, cz, L, W, a = g["roof"]["obb"]
        F = Frame(cx, cz, a)
        rise = float(g["roof"].get("rise", 4.0))
        mb.col = roof_c
        frustum(mb, F, -L / 2, L / 2, -W / 2, W / 2, H, H + rise, W / 2 - 0.05, W / 2 - 0.05, "gen_tile_t", ov=0.6)
        mb.col = tuple(v * 0.8 for v in wall_c)
        cap(mb, F.rect(-L / 2 - 0.6, L / 2 + 0.6, -W / 2 - 0.6, W / 2 + 0.6), H - 0.02, "gen_trim_t", down=True)
        top = H + rise
    else:
        mb.col = roof_c
        cap(mb, pts, top_wall, "gen_flat_t", tile=8.0)
        mb.col = tuple(min(1.0, v * 1.05) for v in wall_c)
        parapet(mb, pts, top_wall - 0.1, H + 0.3, 0.25, "gen_trim_t")
        top = H + 0.3
        # roof plant: stair/lift house + AC units, placed inside the outline
        best = max(range(len(pts)), key=lambda i: dist2(pts[i], pts[(i + 1) % len(pts)]))
        a0, a1 = pts[best], pts[(best + 1) % len(pts)]
        Fr = Frame(*centroid(pts), math.atan2(a1[1] - a0[1], a1[0] - a0[0]))
        us = [(x - Fr.cx) * Fr.c + (z - Fr.cz) * Fr.s for x, z in pts]
        vs = [-(x - Fr.cx) * Fr.s + (z - Fr.cz) * Fr.c for x, z in pts]
        hu, hv = (max(us) - min(us)) / 2, (max(vs) - min(vs)) / 2
        rnd = (int(g["id"]) if str(g["id"]).isdigit() else sum(map(ord, str(g["id"])))) % 997

        def fits(u0, u1, v0, v1):
            return all(point_in(*Fr.p(u, v), pts) for u in (u0, u1) for v in (v0, v1))

        if hu > 6 and hv > 4:
            mb.col = tuple(min(1.0, v * 0.95) for v in wall_c)
            uc = (0.25 if rnd % 2 else -0.25) * hu
            if fits(uc - 2.5, uc + 2.5, -2.0, 2.0):
                box(mb, Fr, uc - 2.5, uc + 2.5, -2.0, 2.0, top_wall, top_wall + 3.0, "gen_trim_t", top="gen_trim_t", bay=5, fh=3)
                top = max(top, top_wall + 3.0)
            mb.col = (0.72, 0.74, 0.76)
            for k in range(3 if hu > 15 else 1):
                u = (-0.45 + 0.3 * k) * hu
                v = (0.35 if (rnd + k) % 2 else -0.35) * hv
                if fits(u - 0.7, u + 0.7, v - 0.7, v + 0.7):
                    box(mb, Fr, u - 0.7, u + 0.7, v - 0.7, v + 0.7, top_wall, top_wall + 1.0, "gen_trim_t",
                        top="gen_trim_t", bay=1.4, fh=1)
    # entrance canopy on the longest south-ish facade (on-campus buildings)
    if g.get("campus", True) is not False and H < 45:
        try:
            Fe = edge_frame(pts, facing=(0, 1))
        except TypeError:
            Fe = None
        if Fe is not None and Fe.length > 8:
            mb.col = (0.95, 0.95, 0.94)
            box(mb, Fe, -2.6, 2.6, 0.0, 2.2, 3.1, 3.4, "gen_trim_t", top="gen_trim_t", bot="gen_trim_t", bay=5, fh=0.3)
            for su in (-1, 1):
                box(mb, Fe, su * 2.3 - 0.1, su * 2.3 + 0.1, 1.9, 2.1, 0, 3.1, "gen_trim_t", bay=0.2, fh=1)
    return mb, round(top, 1)


def build_generic(only=None, render=True):
    data = json.loads((BL / "generic_input.json").read_text(encoding="utf-8"))
    CH = data["chunk_m"]
    gdir_glb, gdir_bl = MODELS / "generic", BL / "generic"
    gdir_glb.mkdir(parents=True, exist_ok=True)
    gdir_bl.mkdir(parents=True, exist_ok=True)
    chunks: dict = {}
    for g in data["buildings"]:
        chunks.setdefault(g["chunk"], []).append(g)
    out = []
    for key in sorted(chunks):
        if only and key not in only:
            continue
        i, j = map(int, key.split("_"))
        chx, chz = (i + 0.5) * CH - 1650, (j + 0.5) * CH - 970
        bpy.ops.wm.read_homefile(use_empty=True)
        _MATS.clear()
        coll = bpy.data.collections.new(f"generic_{key}")
        bpy.context.scene.collection.children.link(coll)
        objs, items = [], []
        for g in chunks[key]:
            O = centroid(ccw(g["pts"]))
            mb, top = gen_building(g, O)
            ob = mb.build(coll)
            ob.location = (O[0] - chx, -(O[1] - chz), 0.0)
            objs.append(ob)
            items.append(dict(id=g["id"], node=str(g["id"]), name=g["name"], x=round(O[0], 2), z=round(O[1], 2), height=top))
        tris = tri_count(objs)
        glb = gdir_glb / f"{key}.glb"
        export_glb(objs, glb)
        if render:
            setup_preview(objs, f"generic_{key}", (30, 40))
            bpy.ops.render.render(write_still=True)
            gsel = max(chunks[key], key=lambda g: min(float(g["h"]), 30) * len(g["pts"]))
            O = centroid(ccw(gsel["pts"]))
            aim_camera(Vector((O[0] - chx, -(O[1] - chz), float(gsel["h"]) * 0.5)), 38.0, (28, 22))
            bpy.context.scene.render.filepath = str(PREV / f"generic_{key}_close.jpg")
            bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(gdir_bl / f"{key}.blend"), compress=True, relative_remap=True)
        out.append(dict(file=f"models/generic/{key}.glb", x=round(chx, 1), z=round(chz, 1), tris=tris, buildings=items))
        print(f"[generic] {key}: {len(items)} buildings, tris {tris}, glb {glb.stat().st_size / 1024:.0f} KB")
    gj = BL / "generic.json"
    prev = {c["file"]: c for c in (json.loads(gj.read_text(encoding="utf-8"))["chunks"] if gj.exists() else [])}
    for c in out:
        prev[c["file"]] = c
    gj.write_text(json.dumps(dict(
        note="Generic Blender buildings. Each chunk GLB sits at (x, 0, z); every building is a node named by its campus.json id "
             "whose translation is (bx - x, 0, bz - z) with the origin on the ground at the building centroid -- set each "
             "node's y to that building's ground height. Hide the procedural building with the same id.",
        chunk_m=CH, chunks=sorted(prev.values(), key=lambda c: c["file"])), ensure_ascii=False, indent=1), encoding="utf-8")
    print("[generic] wrote", gj)


# ================================================================== dorms (v0.5 stage B)
# 文园型: 6-storey white slab, dark ground floor, red-tile hip roof over the middle, a stair tower one storey
# higher at each end (one with a small red pyramid cap + railing, the other flat + railing). Per-building notes
# from the official zoom1 crops (data/dorms/dorms.csv): which end has the red cap, two roof sections.
WENYUAN = {  # id: (red-cap end(s), two roof sections)
    "862959378": ("W", False), "1245446262": ("E", True), "1245446261": ("WE", True), "862959384": ("E", False),
    "862959386": ("W", False), "862959390": ("W", False), "862959389": ("E", False), "862959387": ("E", False),
    "862959388": ("W", False), "862959383": ("E", False), "862959382": ("W", False), "862959380": ("W", False),
    "862959381": ("E", False), "862959379": ("E", False), "862959372": ("W", False), "862959385": ("W", False),
    "862959371": ("W", False), "862959370": ("W", False), "862959369": ("W", False), "862959374": ("W", False),
    "862959373": ("W", False),
}
DORM_FLOOR_H = 3.1
# Dorm eaves (main session rule, 2026-11-27): eave = official floors x 3.1 m, hip rise = 0.2 x depth, accepted when the
# model's DSM-equivalent p70 (eave + 0.6 x rise for a hip roof, eave for a flat one) is within 1.5 m of the re-registered
# DSM p70 and the ridge is not above p95 + 1 m. Otherwise the eave is fitted to the DSM (eave = p70 - 0.6 x rise, storey
# height kept within 2.9-3.6 m) and the building is listed in DORM_EAVE_LOG.
try:
    _V2 = json.loads((ROOT / "data" / "manual" / "measured_heights_v2.json").read_text(encoding="utf-8"))
    _V2 = _V2.get("buildings", _V2)
except FileNotFoundError:
    _V2 = {}
DORM_EAVE_LOG = []
# Footprint corrections from the 2024-12 480 m drone ortho (detail-correction session): game z of the north wall at the
# building's middle. 文园17: the OSM outline runs ~7 m too far north over the 长望西街 shop pavement.
WENYUAN_NORTH_Z = {"862959378": -530.0}
# Floor counts that override dorms.csv official_floors. 青教公寓6幢: official map 3, but the re-registered DSM has the eave
# ~14.3 m and the ridge ~16 m above the ground around it (2026-11-27) -> 4 floors (campus lv 4); asked in questions.
DORM_FLOORS_FIX = {"1316307762": 4}


def dorm_eave(bid, row, W, name="", hip=True, nf_default=6):
    rf = 0.2 if hip else 0.0
    rise = rf * W
    m = _V2.get(str(bid), {})
    p70, p95, cov = m.get("h"), m.get("p95"), m.get("cover", 0)
    nf = DORM_FLOORS_FIX.get(str(bid)) or int(row.get("official_floors") or 0)
    if not nf:  # no official floor count: from the DSM when there is one, else the default
        nf = max(1, round((p70 - 0.6 * rise) / DORM_FLOOR_H)) if (p70 is not None and cov >= 0.5) else nf_default
    eave = nf * DORM_FLOOR_H
    if p70 is None or cov < 0.5:
        DORM_EAVE_LOG.append((name or bid, "rule (no reliable DSM)", nf, round(eave, 1), round(eave + rise, 1)))
        return eave, rf, nf
    ok = abs(eave + 0.6 * rise - p70) <= 1.5 and (eave + rise) <= (p95 or 99) + 1.0
    if not ok:
        fit = min(max(p70 - 0.6 * rise, nf * 2.9), nf * 3.6)
        DORM_EAVE_LOG.append((name or bid, f"rule failed (p70 {p70}, p95 {p95}) -> DSM fit", nf, round(fit, 1), round(fit + rise, 1)))
        return fit, rf, nf
    DORM_EAVE_LOG.append((name or bid, "rule ok", nf, round(eave, 1), round(eave + rise, 1)))
    return eave, rf, nf



def _dorm_rows():
    import csv
    with open(DATA / "dorms" / "dorms.csv", encoding="utf-8-sig") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def _min_rect(pts):
    best = None
    for i in range(len(pts)):
        (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % len(pts)]
        a = math.atan2(z1 - z0, x1 - x0)
        c, s_ = math.cos(a), math.sin(a)
        us = [x * c + z * s_ for x, z in pts]
        vs = [-x * s_ + z * c for x, z in pts]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            um, vm = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (area, um * c - vm * s_, um * s_ + vm * c, max(us) - min(us), max(vs) - min(vs), a)
    _, cx, cz, L, W, a = best
    if W > L:
        L, W, a = W, L, a + math.pi / 2
    if math.cos(a) < 0:  # make +u point east so "E"/"W" ends are stable
        a += math.pi
    return cx, cz, L, W, a


def wenyuan_eave(row):
    """Eave height: the measured value when it agrees with a 6-storey slab (17-22.5 m), else 6 x 3.1 m."""
    h = float(row["h"] or 0)
    return h if (row["hsrc"] == "measured" and 17.0 <= h <= 22.5) else 6 * DORM_FLOOR_H


def wenyuan_building(bid, row, origin):
    b = bld(int(bid) if bid.isdigit() else bid)
    cx, cz, L, W, a = _min_rect([tuple(p) for p in b["pts"]])
    if bid in WENYUAN_NORTH_Z:  # move the north wall (v = -W/2) to the measured line, keep the south wall
        vn = (WENYUAN_NORTH_Z[bid] - cz) / math.cos(a)
        dv = (vn + W / 2) / 2
        W = W / 2 - vn
        cx, cz = cx - dv * math.sin(a), cz + dv * math.cos(a)
    F = Frame(cx, cz, a)
    red_ends, two = WENYUAN[bid]
    He, rf, nf = dorm_eave(bid, row, W, row.get("name", ""))
    fh = He / nf
    wall_c = _hex(row["wall"] or "#dfe3e6")
    wall_c = tuple(0.55 * v + 0.45 * w for v, w in zip(wall_c, (0.93, 0.92, 0.9)))
    roof_c = _hex(row["roofc"] or "#b04b40")
    mb = MB(bid, origin)
    Lt = min(8.0, L * 0.16)
    # slab + dark ground floor + floor bands
    mb.col = wall_c
    box(mb, F, -L / 2 + 0.5, L / 2 - 0.5, -W / 2, W / 2, 0, He, "gen_dorm_t", bay=3.6, fh=fh)
    mb.col = (0.32, 0.35, 0.38)
    box(mb, F, -L / 2 + 0.45, L / 2 - 0.45, -W / 2 - 0.05, W / 2 + 0.05, 0, fh * 0.95, "gen_trim_t", bay=4, fh=1)
    mb.col = (0.97, 0.97, 0.96)
    floor_bands(mb, F.rect(-L / 2 + 0.5, L / 2 - 0.5, -W / 2, W / 2), [fh * k for k in range(2, nf)], "gen_trim_t",
                out=0.08, th=0.18)
    # hip roof(s) between the towers
    rise = rf * W
    u0, u1 = -L / 2 + Lt - 0.3, L / 2 - Lt + 0.3
    secs = [(u0, -5.0), (5.0, u1)] if two else [(u0, u1)]
    for a0, a1 in secs:
        mb.col = roof_c
        frustum(mb, F, a0, a1, -W / 2, W / 2, He, He + rise, min(W / 2 - 0.05, (a1 - a0) / 2 - 0.05), W / 2 - 0.05,
                "gen_tile_t", ov=0.5)
        mb.col = tuple(v * 0.8 for v in wall_c)
        cap(mb, F.rect(a0 - 0.5, a1 + 0.5, -W / 2 - 0.5, W / 2 + 0.5), He - 0.02, "gen_trim_t", down=True)
    if two:
        mb.col = (0.82, 0.83, 0.82)
        cap(mb, F.rect(-5.0, 5.0, -W / 2, W / 2), He, "gen_flat_t")
        mb.col = wall_c
        parapet(mb, F.rect(-5.0, 5.0, -W / 2, W / 2), He - 0.1, He + 0.9, 0.2, "gen_trim_t")
        box(mb, F, -2.0, 2.0, -2.5, 2.5, He, He + 2.6, "gen_trim_t", top="gen_trim_t", bay=4, fh=2.6)
    # end stair towers (one storey higher), red pyramid cap + railing or flat + railing
    Ht = He + 3.4
    for end, sg in (("W", -1), ("E", 1)):
        ua, ub = (L / 2 - Lt, L / 2) if sg > 0 else (-L / 2, -L / 2 + Lt)
        rect = F.rect(ua, ub, -W / 2 - 0.6, W / 2 + 0.6)
        mb.col = wall_c
        box(mb, F, ua, ub, -W / 2 - 0.6, W / 2 + 0.6, 0, Ht, "gen_dorm_t", bay=3.6, fh=fh)
        mb.col = (0.32, 0.35, 0.38)
        prism(mb, inset(rect, -0.05), 0, fh * 0.95, "gen_trim_t", bay=4, fh=1)
        mb.col = (0.82, 0.83, 0.82)
        cap(mb, rect, Ht, "gen_flat_t")
        mb.col = (0.97, 0.97, 0.96)
        parapet(mb, rect, Ht - 0.1, Ht + 1.1, 0.12, "gen_trim_t")
        if end in red_ends:
            mb.col = roof_c
            ui, uo = ua + 1.2, ub - 1.2
            ring(mb, F.rect(ui, uo, -W / 2 + 0.6, W / 2 - 0.6), Ht + 1.6, [F.p((ui + uo) / 2, 0)] * 4, Ht + 4.8, "gen_tile_t")
            mb.col = (0.97, 0.97, 0.96)
            for su in (ui, uo):
                for sv in (-W / 2 + 0.6, W / 2 - 0.6):
                    box(mb, F, su - 0.15, su + 0.15, sv - 0.15, sv + 0.15, Ht, Ht + 1.6, "gen_trim_t", bay=0.3, fh=1)
            cap(mb, F.rect(ui, uo, -W / 2 + 0.6, W / 2 - 0.6), Ht + 1.6, "gen_trim_t", down=True)
    return mb, round(Ht + 4.8, 1)


def m_wenyuan_zone(zone):
    def fn(coll):
        rows = _dorm_rows()
        ids = [i for i, r in rows.items() if r["zone"] == zone and "文园" in r["name"] and _has(i)]
        pts = [p for i in ids for p in bld(int(i)).get("pts")]
        O = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        objs, top = [], 0
        for i in ids:
            mb, t = wenyuan_building(i, rows[i], O)
            objs.append(mb.build(coll))
            top = max(top, t)
        names = [rows[i]["name"] for i in ids]
        return dict(objs=objs, origin=O, replaces=[int(i) for i in ids], replaces_names=names, height=top, cam=(35, 32))
    return fn


# E3 old residential blocks (detail-correction session): 5-storey 1980s-90s brick-concrete, grey stained walls,
# grilled windows, AC units, stair cores with dark doorways, flat roofs (old-res-2 stair bumps, 3/4 solar heaters).
def _rect_frame(b):
    cx, cz, L, W, deg = b["rect"] if "rect" in b else (None,) * 5
    return Frame(cx, cz, -math.radians(deg)), L / 2, W / 2


def m_e3_old_res(coll):
    raw = {e["id"]: e for e in json.loads((DATA / "manual" / "extra_buildings.json").read_text(encoding="utf-8"))["buildings"]
           if str(e.get("id", "")).startswith(("old-res", "res-p"))}
    raw.setdefault("res-p1", {"id": "res-p1", "h": 20.0, "rect": [209.1, -396.0, 44.5, 12.5, 8.5]})
    ids = ["old-res-1", "old-res-2", "old-res-2a", "old-res-3", "old-res-4", "res-p1"]
    O = (sum(raw[i]["rect"][0] for i in ids) / len(ids), sum(raw[i]["rect"][1] for i in ids) / len(ids))
    objs = []
    import random
    for i in ids:
        e = raw[i]
        F, hu, hv = _rect_frame(e)
        mb = MB(i, O)
        rnd = random.Random(i)
        if i == "res-p1":  # newer 5-storey block, pitched (flat-to-pitched retrofit) red-brown roof, 6 north dormers
            rect = F.rect(-hu, hu, -hv, hv)
            mb.col = (0.66, 0.67, 0.66)
            prism(mb, rect, 0, 15.5, "gen_dorm_t", bay=3.3, fh=3.1)
            mb.col = (0.95, 0.95, 0.94)
            floor_bands(mb, rect, [3.1 * k for k in range(1, 5)], "gen_trim_t", out=0.07, th=0.16)
            prism(mb, inset(rect, -0.25), 15.1, 15.5, "gen_trim_t", bay=4, fh=0.4)  # white eave line
            mb.col = None
            frustum(mb, F, -hu, hu, -hv, hv, 15.5, 20.0, 4.0, hv - 0.05, "tile_red", ov=0.5)
            cap(mb, F.rect(-hu - 0.5, hu + 0.5, -hv - 0.5, hv + 0.5), 15.48, "white", down=True)
            dormers_rect(mb, F, -hu - 0.5, hu + 0.5, -hv - 0.5, hv + 0.5, 15.5, 4.5, hv + 0.5, 6.9, edges=(3,),
                         w=2.4, hgt=2.6, depth=3.0, wmat="white", rmat="tile_red")
            sv, n = 1, F.vec(0, 1)
            for k in range(3):  # stair doors on the south side
                u = -hu + (k + 0.5) * 2 * hu / 3
                mb.face([F.p3(u - 0.8, 0.05, hv + 0.02), F.p3(u + 0.8, 0.05, hv + 0.02), F.p3(u + 0.8, 2.4, hv + 0.02),
                         F.p3(u - 0.8, 2.4, hv + 0.02)], None, "old_dark", out=(n[0], 0, n[1]))
            for side in (-1, 1):
                for _ in range(int(2 * hu / 5)):
                    u = rnd.uniform(-hu + 1, hu - 1)
                    y = 3.1 * rnd.randint(0, 4) + 0.6
                    vv = side * hv
                    box(mb, F, u - 0.42, u + 0.42, min(vv, vv + side * 0.35), max(vv, vv + side * 0.35), y, y + 0.55,
                        "concrete", top="concrete", bot="concrete", bay=0.9, fh=0.6)
            objs.append(mb.build(coll))
            continue
        if i == "old-res-2a":  # one-storey store / bike shed against old-res-2's south side
            box(mb, F, -hu, hu, -hv, hv, 0, 3.0, "old_grey", bay=3, fh=3)
            box(mb, F, -hu - 0.2, hu + 0.2, -hv - 0.2, hv + 0.2, 3.0, 3.2, "old_dark", top="old_dark", bot="old_dark", bay=4, fh=0.2)
            n = F.vec(0, 1)
            for k in range(6):
                u = -hu + 2.5 + k * (2 * hu - 5) / 5
                mb.face([F.p3(u - 1.1, 0.05, hv + 0.02), F.p3(u + 1.1, 0.05, hv + 0.02), F.p3(u + 1.1, 2.3, hv + 0.02),
                         F.p3(u - 1.1, 2.3, hv + 0.02)], None, "old_dark", out=(n[0], 0, n[1]))
            objs.append(mb.build(coll))
            continue
        H = float(e["h"])
        try:  # campus h follows the adopted re-registered DSM heights (2026-11-27), e.g. old-res-1 17.4 m
            H = max(H, float(bld(i)["h"]))
        except (StopIteration, KeyError, TypeError):
            pass
        wall_top = max(15.0, H - 1.0)
        rect = F.rect(-hu, hu, -hv, hv)
        prism(mb, rect, 0, wall_top, "old_res", bay=3.3, fh=3.0, top="old_roof")
        parapet(mb, rect, wall_top - 0.1, H, 0.2, "old_grey")
        floor_bands(mb, rect, [3.0 * k for k in range(1, 5)], "old_grey", out=0.06, th=0.14)
        # stair cores: road side for old-res-1 (south), north side for the others (stair bumps / heaters there)
        sv = 1 if i == "old-res-1" else -1
        n_units = max(2, round(2 * hu / 15))
        for k in range(n_units):
            u = -hu + (k + 0.5) * 2 * hu / n_units
            v0, v1 = (hv, hv + 0.5) if sv > 0 else (-hv - 0.5, -hv)
            box(mb, F, u - 1.5, u + 1.5, v0, v1, 0, wall_top + 0.6, "old_grey", top="old_grey", bay=3, fh=3)
            n = F.vec(0, sv)
            vf = (v1 if sv > 0 else v0) + 0.02 * sv
            mb.face([F.p3(u - 0.8, 0.05, vf), F.p3(u + 0.8, 0.05, vf), F.p3(u + 0.8, 2.4, vf), F.p3(u - 0.8, 2.4, vf)],
                    None, "old_dark", out=(n[0], 0, n[1]))
            for fl in range(1, 5):
                y = fl * 3.0 + 1.0
                mb.face([F.p3(u - 0.5, y, vf), F.p3(u + 0.5, y, vf), F.p3(u + 0.5, y + 0.8, vf), F.p3(u - 0.5, y + 0.8, vf)],
                        None, "glass_dark", out=(n[0], 0, n[1]))
            if i == "old-res-2":  # stair bumps on the roof, north edge
                box(mb, F, u - 1.6, u + 1.6, -hv + 0.3, -hv + 3.0, wall_top, wall_top + 2.4, "old_grey", top="old_roof", bay=3, fh=2.4)
        # AC outdoor units scattered on both long facades
        for side in (-1, 1):
            for _ in range(int(2 * hu / 4)):
                u = rnd.uniform(-hu + 1, hu - 1)
                y = 3.0 * rnd.randint(0, 4) + 0.6
                vv = side * hv
                box(mb, F, u - 0.42, u + 0.42, min(vv, vv + side * 0.35), max(vv, vv + side * 0.35), y, y + 0.55,
                    "concrete", top="concrete", bot="concrete", bay=0.9, fh=0.6)
        if i in ("old-res-3", "old-res-4"):  # solar water heaters along the north edge, tilted to the south
            for k in range(int(2 * hu / 3.2)):
                u = -hu + 1.8 + k * 3.2
                vb, vf = -hv + 0.6, -hv + 2.0
                pts = [F.p3(u - 0.9, wall_top + 0.3, vf), F.p3(u + 0.9, wall_top + 0.3, vf), F.p3(u + 0.9, wall_top + 1.4, vb),
                       F.p3(u - 0.9, wall_top + 1.4, vb)]
                mb.face(pts, None, "solar", out=(0, 1, 0))
                box(mb, F, u - 0.9, u + 0.9, vb - 0.45, vb, wall_top + 1.3, wall_top + 1.75, "steel_white", top="steel_white",
                    bay=1.8, fh=0.45)
        if i == "old-res-2":  # worn, patched roof
            for _ in range(5):
                u, v = rnd.uniform(-hu + 3, hu - 3), rnd.uniform(-hv + 3, hv - 2)
                mb.face([F.p3(u - 2, wall_top + 0.02, v - 1.5), F.p3(u + 2, wall_top + 0.02, v - 1.5),
                         F.p3(u + 2, wall_top + 0.02, v + 1.5), F.p3(u - 2, wall_top + 0.02, v + 1.5)], None, "old_dark", out=(0, 1, 0))
        objs.append(mb.build(coll))
    return dict(objs=objs, origin=O, replaces=ids, replaces_names=["E3 老居民楼 4 栋 + 平房 + res-p1"], height=20.0, cam=(30, 30))


# 中苑沁园: types read from the official zoom1 crops (see data/dorms/dorms.csv roof_check / facade_check).
QY_TYPES = {
    "A": dict(wall="#dfe7dc", roof="#9a5a5e", band=None, tex="gen_dorm_t", hip=True, end_balc=True, bumps=True),
    "B": dict(wall="#d9e1e4", roof="#c0473b", band="#d9893a", tex="gen_office_t", hip=True, end_balc=True, bumps=False),
    "C": dict(wall="#e3d6b5", roof="#b84a3e", band="#f4f4f0", tex="gen_dorm_t", hip=True, end_balc=False, bumps=False),
    "D": dict(wall="#dde6d8", roof="#7d6c60", band="#f4f4f0", tex="gen_dorm_t", hip=True, end_balc=False, bumps=False, balc_rows=True),
    "E": dict(wall="#a5544a", roof="#9c9fa2", band=None, tex="red_brick", hip=False),
    "F": dict(wall="#eeeeea", roof="#79bde6", band=None, tex="gen_dorm_t", hip=False, pillars=True),
    "G": dict(wall="#eeeeec", roof="#c9cbc8", band=None, tex="gj_facade", hip=False),
}
QINYUAN = {  # id: (type, extras)
    "862959356": ("A", {}), "862959357": ("A", {"round": True}), "manual-33": ("G", {}), "1316148867": ("A", {}),
    "862959352": ("B", {}), "862959353": ("B", {}), "862959354": ("C", {}), "1316148866": ("A", {}),
    "862959355": ("A", {}), "1316148865": ("A", {}), "862959358": ("A", {"round": True}), "1316148868": ("B", {"wall": "#eef0ef"}),
    "1316307762": ("C", {}), "862959359": ("D", {}), "862959360": ("D", {"round": True}), "1316148869": ("E", {}),
    "862952696": ("F", {}), "862952694": ("F", {}), "862952695": ("F", {}), "1114843835": ("D", {"wall": "#d8cba8"}),
    "1316307763": ("C", {"two": True}),
}
QY_EXTRA_REPLACES = {"E4": ["tower-3"], "F4": ["tower-4"]}  # measured tall parts of 沁园40 / 沁园30


def qy_eave(row):
    h = float(row["h"] or 0)
    if row["hsrc"] == "measured" and h >= 7:
        return h, max(2, min(7, round(h / 3.25)))
    return 6 * DORM_FLOOR_H, 6


def qinyuan_building(bid, row, origin):
    b = bld(int(bid) if bid.isdigit() else bid)
    cx, cz, L, W, a = _min_rect([tuple(p) for p in b["pts"]])
    F = Frame(cx, cz, a)
    t, ex = QINYUAN[bid]
    P = dict(QY_TYPES[t], **ex)
    He, rf, nf = dorm_eave(bid, row, W, row.get("name", ""), hip=bool(P["hip"]))
    fh = He / nf
    wall_c = _hex(P["wall"])
    roof_c = _hex(P["roof"])
    mb = MB(bid, origin)
    rect = F.rect(-L / 2, L / 2, -W / 2, W / 2)
    tinted = P["tex"].endswith("_t")
    mb.col = wall_c if tinted else None
    prism(mb, rect, 0, He, P["tex"], bay=(3.6 if t != "B" else 4.0), fh=fh)
    mb.col = (0.34, 0.37, 0.4)
    prism(mb, inset(rect, -0.05), 0, min(fh * 0.9, 3.0), "gen_trim_t", bay=4, fh=1)
    mb.col = (0.96, 0.96, 0.95)
    floor_bands(mb, rect, [fh * k for k in range(1, nf)], "gen_trim_t", out=0.07, th=0.16)
    if P.get("band"):
        mb.col = _hex(P["band"])
        prism(mb, inset(rect, -0.18), He - 0.55, He, "gen_trim_t", bay=4, fh=0.55)
    top = He
    if P["hip"]:
        rise = rf * W
        secs = [(-L / 2, -6.0), (6.0, L / 2)] if P.get("two") else [(-L / 2, L / 2)]
        for a0, a1 in secs:
            mb.col = roof_c
            frustum(mb, F, a0, a1, -W / 2, W / 2, He, He + rise, min(W / 2, (a1 - a0) / 2) - 0.05, W / 2 - 0.05,
                    "gen_tile_t", ov=0.55)
            mb.col = tuple(v * 0.85 for v in wall_c)
            cap(mb, F.rect(a0 - 0.55, a1 + 0.55, -W / 2 - 0.55, W / 2 + 0.55), He - 0.02, "gen_trim_t", down=True)
        if P.get("two"):
            mb.col = (0.82, 0.83, 0.82)
            cap(mb, F.rect(-6.0, 6.0, -W / 2, W / 2), He, "gen_flat_t")
            mb.col = wall_c
            box(mb, F, -4.5, 4.5, -W / 2 + 1, W / 2 - 1, He, He + 3.2, "gen_dorm_t", top="gen_trim_t", bay=3, fh=3.2)
        if P.get("bumps"):  # two stair-roof bumps on the north slope
            mb.col = roof_c
            for u in (-L / 4, L / 4):
                box(mb, F, u - 1.6, u + 1.6, -W / 2 + 2.0, -W / 2 + 5.0, He, He + 0.3 * W * 0.75, "gen_tile_t",
                    top="gen_tile_t", bay=3, fh=2)
        top = He + rise
    else:
        mb.col = roof_c
        cap(mb, rect, He, "gen_flat_t")
        mb.col = (0.95, 0.95, 0.94)
        parapet(mb, rect, He - 0.1, He + 0.9, 0.2, "gen_trim_t")
        top = He + 0.9
    if P.get("end_balc"):  # stacked balconies on both short ends
        mb.col = (0.95, 0.95, 0.94)
        for sg in (-1, 1):
            for k in range(1, nf):
                y = k * fh
                ua, ub = (L / 2, L / 2 + 1.2) if sg > 0 else (-L / 2 - 1.2, -L / 2)
                box(mb, F, ua, ub, -2.2, 2.2, y - 0.1, y + 1.0, "gen_trim_t", top="gen_trim_t", bot="gen_trim_t", bay=4, fh=1.1)
    if P.get("balc_rows"):  # balcony slabs along the south facade
        mb.col = (0.95, 0.95, 0.94)
        for k in range(1, nf):
            y = k * fh
            for u0 in range(int(-L / 2 + 2), int(L / 2 - 4), 7):
                box(mb, F, u0, u0 + 4.5, W / 2, W / 2 + 1.1, y - 0.1, y + 0.9, "gen_trim_t", top="gen_trim_t", bot="gen_trim_t",
                    bay=4.5, fh=1)
    if P.get("pillars"):  # 外廊 type: red brick pillars on the south facade
        for u in range(int(-L / 2 + 1), int(L / 2), 4):
            box(mb, F, u - 0.3, u + 0.3, W / 2, W / 2 + 0.5, 0, He, "brick_red", top="brick_red", bay=2, fh=2, fit=False)
    if P.get("round"):  # round stair / entrance tower at the east end
        c = F.p(L / 2 + 0.5, 0.0)
        mb.col = wall_c
        cyl(mb, c, 4.2, 0, He + 1.2, 20, "gen_dorm_t", top="gen_trim_t")
    if t == "E":  # glazed central atrium with a glass gable
        box(mb, F, -5, 5, -W / 2 - 0.3, W / 2 + 0.3, 0, He + 0.5, "glass_blue", top="white", bay=2.5, fh=3.3)
        gable(mb, Frame(cx, cz, a + math.pi / 2), -W / 2 - 0.3, W / 2 + 0.3, -5, 5, He + 0.5, He + 0.5, He + 4.0, 0.5,
              "glass_blue", "roof_gray", ov=0.3, bay=2.5, fh=3)
        top = He + 4.0
    return mb, round(top, 1)


def m_qinyuan_zone(zone):
    def fn(coll):
        rows = _dorm_rows()
        ids = [i for i, r in rows.items() if r["zone"] == zone and i in QINYUAN and _has(i)]
        pts = [p for i in ids for p in bld(int(i) if i.isdigit() else i)["pts"]]
        O = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        objs, top = [], 0
        for i in ids:
            mb, t = qinyuan_building(i, rows[i], O)
            objs.append(mb.build(coll))
            top = max(top, t)
        rep = [int(i) if i.isdigit() else i for i in ids] + QY_EXTRA_REPLACES.get(zone, [])
        return dict(objs=objs, origin=O, replaces=rep, replaces_names=[rows[i]["name"] or i for i in ids], height=top,
                    cam=(35, 32))
    return fn


# D5 retired 2026-11-28: its only dorm 沁园42栋 (manual-33) was demolished (detail session, removed from campus.json)
DORM_DEF_QY = [(f"dorm_qinyuan_{z.lower()}", f"沁园宿舍 {z}", m_qinyuan_zone(z)) for z in ("D4", "E4", "E5", "F3", "F4")]
RETIRED = {"models/dorm_qinyuan_d5.glb"}  # dropped from models.json even though another run wrote them


# 东苑硕园/晖园: H = white walls with stacked bow-window bays + maroon (or taupe) hip roof; S = beige walls, taupe hip
# roof (硕园5 has a glazed shop ground floor); O = off-campus housing north of campus (not on the official map; ortho:
# flat roofs with rooftop solar heaters).
DONGYUAN = {
    "1425305061": "O", "1425305062": "O", "1425305063": "O", "1425305064": "O", "1425504864": "O", "1425504865": "O",
    "1425305071": "O", "1425305074": "O", "1425305075": "O", "1425504863": "O", "1425305080": "O",
    "862952674": "H", "862952686": "S", "862952675": "H", "862952676": "H", "862952677": "H",
    "860503921": "H", "862952685": "S", "860503919": "Ht", "860503920": "H", "1114843834": "H",
}


def dongyuan_building(bid, row, origin):
    b = bld(int(bid))
    t = DONGYUAN[bid]
    mb = MB(bid, origin)
    h = float(row["h"] or 0)
    if t == "O":  # off-campus residential slab, outline as drawn, flat roof + parapet + solar heaters
        pts = ccw(b["pts"])
        He, nf = 18.0, 6
        mb.col = _hex("#d9d4c8")
        prism(mb, pts, 0, He, "gen_dorm_t", bay=3.3, fh=3.0)
        mb.col = (0.93, 0.93, 0.91)
        floor_bands(mb, pts, [3.0 * k for k in range(1, nf)], "gen_trim_t", out=0.06, th=0.14)
        mb.col = (0.78, 0.77, 0.74)
        cap(mb, pts, He, "gen_flat_t")
        mb.col = (0.9, 0.89, 0.86)
        parapet(mb, pts, He - 0.1, He + 0.9, 0.2, "gen_trim_t")
        cx, cz, L, W, a = _min_rect([tuple(q) for q in b["pts"]])
        F = Frame(cx, cz, a)
        for k in range(int((L - 4) / 3.2)):
            u = -L / 2 + 2.6 + k * 3.2
            vb, vf = -W / 2 + 0.8, -W / 2 + 2.2
            if not (point_in(*F.p(u, vb), pts) and point_in(*F.p(u, vf), pts)):
                continue
            mb.col = None
            mb.face([F.p3(u - 0.9, He + 0.3, vf), F.p3(u + 0.9, He + 0.3, vf), F.p3(u + 0.9, He + 1.4, vb),
                     F.p3(u - 0.9, He + 1.4, vb)], None, "solar", out=(0, 1, 0))
        return mb, He + 1.4
    cx, cz, L, W, a = _min_rect([tuple(q) for q in b["pts"]])
    F = Frame(cx, cz, a)
    He, rf, nf = dorm_eave(bid, row, W, row.get("name", ""))
    fh = He / nf
    rect = F.rect(-L / 2, L / 2, -W / 2, W / 2)
    beige = t == "S"
    wall_c = _hex("#e2d6bd") if beige else (0.95, 0.96, 0.97)
    roof_c = _hex("#7a6f66") if (beige or t == "Ht") else _hex("#6e4950")
    mb.col = wall_c
    prism(mb, rect, 0, He, "gen_dorm_t" if beige else "gen_office_t", bay=3.6 if beige else 4.0, fh=fh)
    mb.col = (0.34, 0.37, 0.4)
    prism(mb, inset(rect, -0.05), 0, min(fh * 0.9, 3.0), "gen_trim_t", bay=4, fh=1)
    mb.col = (0.97, 0.97, 0.96)
    floor_bands(mb, rect, [fh * k for k in range(1, nf)], "gen_trim_t", out=0.07, th=0.16)
    if bid == "862952686":  # 硕园5栋-云中信大: glazed shop ground floor
        box(mb, F, -L / 2 - 0.2, L / 2 + 0.2, -W / 2 - 0.2, W / 2 + 0.2, 0, fh, "glass_blue", top="white", bay=3.6, fh=fh)
    rise = rf * W
    mb.col = roof_c
    frustum(mb, F, -L / 2, L / 2, -W / 2, W / 2, He, He + rise, W / 2 - 0.05, W / 2 - 0.05, "gen_tile_t", ov=0.55)
    mb.col = tuple(v * 0.85 for v in wall_c)
    cap(mb, F.rect(-L / 2 - 0.55, L / 2 + 0.55, -W / 2 - 0.55, W / 2 + 0.55), He - 0.02, "gen_trim_t", down=True)
    if not beige:  # stacked bow-window bays on the south face, balconies on both ends
        mb.col = (0.96, 0.97, 0.98)
        for k in range(int((L - 6) / 7.5)):
            u = -L / 2 + 4.5 + k * 7.5
            cyl(mb, F.p(u, W / 2), 1.4, fh, He - 0.3, 10, "gen_office_t", top="gen_trim_t", bot="gen_trim_t")
        for sg in (-1, 1):
            for k in range(1, nf):
                ua, ub = (L / 2, L / 2 + 1.2) if sg > 0 else (-L / 2 - 1.2, -L / 2)
                box(mb, F, ua, ub, -2.2, 2.2, k * fh - 0.1, k * fh + 1.0, "gen_trim_t", top="gen_trim_t", bot="gen_trim_t",
                    bay=4, fh=1.1)
    return mb, round(He + rise, 1)


def m_dongyuan_zone(zone):
    def fn(coll):
        rows = _dorm_rows()
        ids = [i for i, r in rows.items() if r["zone"] == zone and i in DONGYUAN and _has(i)]
        pts = [p for i in ids for p in bld(int(i))["pts"]]
        O = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        objs, top = [], 0
        for i in ids:
            mb, t = dongyuan_building(i, rows[i], O)
            objs.append(mb.build(coll))
            top = max(top, t)
        return dict(objs=objs, origin=O, replaces=[int(i) for i in ids], replaces_names=[rows[i]["name"] or i for i in ids],
                    height=top, cam=(35, 32))
    return fn


DORM_DEF_DY = [(f"dorm_dongyuan_{z.lower()}", f"东苑宿舍 {z}", m_dongyuan_zone(z)) for z in ("G1", "H1", "H2", "I1", "I2")]


def m_qinyuan26(coll):
    """沁园26栋 (G3): U-shaped, white walls with blue window strips, brown-grey hip-like roof (official zoom1)."""
    b = bld(1114843836)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb = MB("1114843836", O)
    He, nf, rise = 17.2, 5, 4.0  # re-registered DSM p70 19.9 / p95 20.7 (2026-11-27): eave + 0.6 x rise = p70 (was 18.1 + 4.5)
    prism(mb, pts, 0, He, "white_band", bay=4.0, fh=He / nf)
    floor_bands(mb, pts, [He * k / nf for k in range(1, nf)], "white")
    mb.col = _hex("#6f5e5c")
    hip_on_outline(mb, pts, He, He + rise, "gen_tile_t", d_max=6.0)
    mb.col = (0.85, 0.85, 0.84)
    cap(mb, inset(pts, -0.5), He - 0.02, "gen_trim_t", down=True)
    return dict(objs=[mb.build(coll)], origin=O, replaces=[1114843836], replaces_names=["沁园26栋"], height=He + rise, cam=(35, 30))


def m_no8(coll):
    """第八栋宿舍 (manual-21, E3): same old staff-residential series as old-res-* (official map labels 第十一~十三栋宿舍
    for those); grey 4-storey flat-roof block with stacked blue enclosed balconies (official zoom1), measured 11.5 m."""
    b = bld("manual-21")
    cx, cz, L, W, a = _min_rect([tuple(q) for q in b["pts"]])
    F = Frame(cx, cz, a)
    O = (cx, cz)
    mb = MB("manual-21", O)
    rect = F.rect(-L / 2, L / 2, -W / 2, W / 2)
    mb.col = (0.66, 0.67, 0.65)
    prism(mb, rect, 0, 10.8, "gen_dorm_t", bay=3.3, fh=2.7)
    mb.col = (0.86, 0.86, 0.84)
    floor_bands(mb, rect, [2.7 * k for k in range(1, 4)], "gen_trim_t", out=0.06, th=0.14)
    mb.col = (0.74, 0.74, 0.72)
    cap(mb, rect, 10.8, "gen_flat_t")
    mb.col = (0.7, 0.7, 0.68)
    parapet(mb, rect, 10.7, 11.5, 0.2, "gen_trim_t")
    mb.col = None
    for k in range(5):  # stacked glazed balconies on the south face
        u = -L / 2 + 4 + k * (L - 8) / 4
        box(mb, F, u - 1.5, u + 1.5, W / 2, W / 2 + 1.2, 2.7, 10.6, "glass_blue", top="white", bay=3, fh=2.7)
    return dict(objs=[mb.build(coll)], origin=O, replaces=["manual-21"], replaces_names=["第八栋宿舍"], height=11.5, cam=(30, 28))


def m_jzx(coll):
    """东苑集装箱美食街 (信藕空间·文创街区): two-storey container shop street on the 14 measured jzx-* footprints
    (extra_buildings.json, detail-correction session). Ground shops 6 m deep, upper shops only on the back (north)
    3 m with a walkway platform in front behind black-framed glass railings; orange container end blocks; two steel
    stairs. Shop fronts face south onto the walkway beside 硕园5栋. Sign texts are generic shop types."""
    raw = {e["id"]: e for e in json.loads((DATA / "manual" / "extra_buildings.json").read_text(encoding="utf-8"))["buildings"]
           if str(e.get("id", "")).startswith("jzx")}
    ids = ["jzx-w", "jzx-g1", "jzx-g2", "jzx-g3", "jzx-g4", "jzx-g5", "jzx-g6", "jzx-u1", "jzx-u2", "jzx-u3", "jzx-u4", "jzx-u5",
           "jzx-u6", "jzx-e"]
    allp = [p for i in ids for p in raw[i]["pts"]]
    O = (sum(p[0] for p in allp) / len(allp), sum(p[1] for p in allp) / len(allp))
    G = Frame(O[0], O[1], math.atan2(-704.4 + 687.12, 859.6 - 791.25))  # u along the street (east), v south (front)

    def uv_range(i):
        us = [(x - G.cx) * G.c + (z - G.cz) * G.s for x, z in raw[i]["pts"]]
        vs = [-(x - G.cx) * G.s + (z - G.cz) * G.c for x, z in raw[i]["pts"]]
        return min(us), max(us), min(vs), max(vs)

    mb = MB("东苑集装箱美食街", O)
    n = G.vec(0, 1)
    out_s = (n[0], 0, n[1])

    def sign(u0, u1, y0, y1, v, cell):
        cu, cv = cell % 2, cell // 2
        uv = [(cu / 2, 1 - (cv + 1) / 6), ((cu + 1) / 2, 1 - (cv + 1) / 6), ((cu + 1) / 2, 1 - cv / 6), (cu / 2, 1 - cv / 6)]
        mb.col = None
        mb.face([G.p3(u0, y0, v), G.p3(u1, y0, v), G.p3(u1, y1, v), G.p3(u0, y1, v)], uv, "jzx_signs", out=out_s)

    GROUND, SLAB = 3.6, 3.85
    for k, i in enumerate(["jzx-g1", "jzx-g2", "jzx-g3", "jzx-g4", "jzx-g5", "jzx-g6"]):
        u0, u1, v0, v1 = uv_range(i)
        mb.col = _hex(raw[i]["color"])
        box(mb, G, u0, u1, v0, v1, 0, GROUND, "container_t", bay=2.4, fh=2.6)
        mb.col = None
        gw = 1.3 if (u1 - u0) > 9 else 0.9  # leave coloured container panels either side of the glazing
        mb.face([G.p3(u0 + gw, 0.2, v1 + 0.03), G.p3(u1 - gw, 0.2, v1 + 0.03), G.p3(u1 - gw, 2.75, v1 + 0.03),
                 G.p3(u0 + gw, 2.75, v1 + 0.03)], [(0, 0), ((u1 - u0 - 2 * gw) / 2, 0), ((u1 - u0 - 2 * gw) / 2, 1), (0, 1)],
                "shopfront", out=out_s)
        sign(u0 + 0.4, u1 - 0.4, 2.9, 3.5, v1 + 0.04, k)
        box(mb, G, u0, u1, v0, v1 + 0.5, GROUND, SLAB, "concrete", top="brick_red", bot="concrete", bay=4, fh=0.25)  # brick deck
        if k == 0:  # 芒可: big yellow awning
            ring(mb, G.rect(u0 + 0.3, u1 - 0.3, v1 + 0.05, v1 + 1.9), 2.95, G.rect(u0 + 0.3, u1 - 0.3, v1 + 0.05, v1 + 0.06),
                 2.95, "awning_yellow")
            mb.face([G.p3(u0 + 0.3, 2.3, v1 + 1.9), G.p3(u1 - 0.3, 2.3, v1 + 1.9), G.p3(u1 - 0.3, 2.95, v1 + 1.9),
                     G.p3(u0 + 0.3, 2.95, v1 + 1.9)], None, "awning_yellow", out=out_s)
            mb.face([G.p3(u0 + 0.3, 2.95, v1 + 0.05), G.p3(u1 - 0.3, 2.95, v1 + 0.05), G.p3(u1 - 0.3, 2.3, v1 + 1.9),
                     G.p3(u0 + 0.3, 2.3, v1 + 1.9)], None, "awning_yellow", out=(n[0], 1, n[1]))
        if k == 2:  # 沪溪河桃酥: green kiosk standing forward into the street, green awning
            ka, kb = u0 + 1.0, u0 + 4.6
            mb.col = _hex("#2f6b4c")
            box(mb, G, ka, kb, v1, v1 + 3.2, 0, 3.0, "container_t", top="container_t", bay=2.4, fh=2.6)
            mb.col = None
            mb.face([G.p3(ka + 0.4, 0.3, v1 + 3.23), G.p3(kb - 0.4, 0.3, v1 + 3.23), G.p3(kb - 0.4, 2.3, v1 + 3.23),
                     G.p3(ka + 0.4, 2.3, v1 + 3.23)], [(0, 0), (1.4, 0), (1.4, 1), (0, 1)], "shopfront", out=out_s)
            sign(ka, kb, 2.35, 2.95, v1 + 3.24, 2)
            mb.face([G.p3(kb, 2.4, v1 + 0.5), G.p3(kb + 1.6, 2.0, v1 + 0.5), G.p3(kb + 1.6, 2.0, v1 + 3.0), G.p3(kb, 2.4, v1 + 3.0)],
                    None, "awning_green", out=(0.3, 1, 0))
        # glass balustrade with black frame along the platform edge
        vr = v1 + 0.35
        for sg, off in ((1, 0.01), (-1, -0.01)):
            mb.face([G.p3(u0, SLAB + 0.05, vr + off), G.p3(u1, SLAB + 0.05, vr + off), G.p3(u1, SLAB + 1.05, vr + off),
                     G.p3(u0, SLAB + 1.05, vr + off)], None, "glass_rail", out=(n[0] * sg, 0, n[1] * sg))
        beam(mb, G.p3(u0, SLAB + 1.1, vr), G.p3(u1, SLAB + 1.1, vr), 0.08, "bus_black")
        for uu in [u0 + 0.1 + t * 2.0 for t in range(int((u1 - u0) / 2.0) + 1)]:
            beam(mb, G.p3(uu, SLAB, vr), G.p3(uu, SLAB + 1.1, vr), 0.06, "bus_black")
    for k, i in enumerate(["jzx-u1", "jzx-u2", "jzx-u3", "jzx-u4", "jzx-u5", "jzx-u6"]):
        u0, u1, v0, v1 = uv_range(i)
        top = float(raw[i]["h"]) - 0.2
        mb.col = _hex(raw[i]["color"])
        box(mb, G, u0, u1, v0, v1, SLAB, top, "container_t", bay=2.4, fh=2.6)
        mb.col = tuple(v * 0.8 for v in _hex(raw[i]["color"]))
        box(mb, G, u0 - 0.05, u1 + 0.05, v0 - 0.05, v1 + 0.15, top, top + 0.2, "container_t", top="gen_flat_t", bay=2.4, fh=0.2)
        mb.col = None
        gw = 1.6
        mb.face([G.p3(u0 + gw, SLAB + 0.15, v1 + 0.03), G.p3(u1 - gw, SLAB + 0.15, v1 + 0.03), G.p3(u1 - gw, top - 0.65, v1 + 0.03),
                 G.p3(u0 + gw, top - 0.65, v1 + 0.03)], [(0, 0), ((u1 - u0 - 2 * gw) / 2, 0), ((u1 - u0 - 2 * gw) / 2, 1), (0, 1)],
                "shopfront", out=out_s)
        sign(u0 + 0.1, u1 - 0.1, top - 1.0, top - 0.05, v1 + 0.04, 6 + k)  # full-width upper fascia
    for i in ("jzx-w", "jzx-e"):  # orange end blocks: two stacked container storeys + a half-height top unit
        u0, u1, v0, v1 = uv_range(i)
        h = float(raw[i]["h"])
        west = i == "jzx-w"
        vf = v1 - 1.6 if west else v1  # west block: open stair strip along its south side (user photo)
        mb.col = _hex(raw[i]["color"])
        box(mb, G, u0, u1, v0, vf, 0, 3.7, "container_t", top="container_t", bay=2.4, fh=2.6)
        vu = vf if west else v1 - 0.3
        box(mb, G, u0 + 0.2, u1 - 0.2, v0, vu, 3.7, h - 0.2, "container_t", top="container_t", bay=2.4, fh=2.6)
        mb.col = None
        for (y0, y1, vv) in ((0.4, 2.9, vf + 0.03), (4.2, h - 1.6, vu + 0.03)):
            mb.face([G.p3(u0 + 0.6, y0, vv), G.p3(u1 - 0.6, y0, vv), G.p3(u1 - 0.6, y1, vv), G.p3(u0 + 0.6, y1, vv)],
                    [(0, 0), (2, 0), (2, 1), (0, 1)], "shopfront", out=out_s)
        if west:  # orange title fascia on the south and west faces, poster + timber slats on the west wall
            mb.face([G.p3(u0 + 0.15, h - 1.5, vu + 0.04), G.p3(u1 - 0.15, h - 1.5, vu + 0.04), G.p3(u1 - 0.15, h - 0.25, vu + 0.04),
                     G.p3(u0 + 0.15, h - 0.25, vu + 0.04)], [(0, 0), (1, 0), (1, 1), (0, 1)], "jzx_title", out=out_s)
            w_ = G.vec(-1, 0)
            # seen from the west (looking east) the viewer's right is south, so text runs north -> south
            mb.face([G.p3(u0 + 0.15, h - 1.5, v0 + 0.1), G.p3(u0 + 0.15, h - 1.5, vu - 0.1), G.p3(u0 + 0.15, h - 0.25, vu - 0.1),
                     G.p3(u0 + 0.15, h - 0.25, v0 + 0.1)], [(0, 0), (1, 0), (1, 1), (0, 1)], "jzx_title", out=(w_[0], 0, w_[1]))
            mb.face([G.p3(u0 + 0.17, 3.9, v0 + 0.3), G.p3(u0 + 0.17, 3.9, vu - 0.3), G.p3(u0 + 0.17, h - 1.7, vu - 0.3),
                     G.p3(u0 + 0.17, h - 1.7, v0 + 0.3)], [(0, 0), (1, 0), (1, 1), (0, 1)], "jzx_poster", out=(w_[0], 0, w_[1]))
            mb.face([G.p3(u0 - 0.03, 0.3, v0 + 0.3), G.p3(u0 - 0.03, 0.3, vf - 0.3), G.p3(u0 - 0.03, 3.4, vf - 0.3),
                     G.p3(u0 - 0.03, 3.4, v0 + 0.3)], None, "wood", out=(w_[0], 0, w_[1]))
            # yellow awning over the stair strip, hung from the upper block
            ring(mb, G.rect(u0 + 0.4, u1 - 0.4, vu, v1 - 0.1), 6.0, G.rect(u0 + 0.4, u1 - 0.4, vu, vu + 0.01), 6.0, "awning_yellow")
            mb.face([G.p3(u0 + 0.4, 6.0, vu), G.p3(u1 - 0.4, 6.0, vu), G.p3(u1 - 0.4, 5.5, v1 - 0.1), G.p3(u0 + 0.4, 5.5, v1 - 0.1)],
                    None, "awning_yellow", out=(n[0], 1, n[1]))
            # open steel stair in the strip, rising east from the street to the platform deck
            steps, run = 12, (u1 - u0 - 0.8) / 12
            for s_ in range(steps):
                ua = u0 + 0.4 + s_ * run
                box(mb, G, ua, ua + run, vf + 0.1, v1 - 0.2, (s_ + 1) * SLAB / steps - 0.08, (s_ + 1) * SLAB / steps, "concrete",
                    top="brick_red", bot="concrete", bay=1, fh=0.1)
            for vv in (vf + 0.1, v1 - 0.2):
                beam(mb, G.p3(u0 + 0.4, 0.0, vv), G.p3(u1 - 0.4, SLAB, vv), 0.12, "bus_black")
            beam(mb, G.p3(u0 + 0.4, 1.0, v1 - 0.2), G.p3(u1 - 0.4, SLAB + 1.0, v1 - 0.2), 0.05, "bus_black")
            for t_ in range(5):
                uu = u0 + 0.4 + t_ * (u1 - u0 - 0.8) / 4
                yy = t_ * SLAB / 4
                beam(mb, G.p3(uu, yy, v1 - 0.2), G.p3(uu, yy + 1.0, v1 - 0.2), 0.05, "bus_black")
    # east stair from the walkway up to the platform, in front of the last shop, rising west
    _, _, _, vfront = uv_range("jzx-g6")
    ustart, sgn, steps = uv_range("jzx-g6")[1] - 0.3, -1, 12
    for s_ in range(steps):
        ua = ustart + sgn * s_ * 0.55
        ub = ua + sgn * 0.55
        box(mb, G, min(ua, ub), max(ua, ub), vfront + 0.6, vfront + 1.8, (s_ + 1) * SLAB / steps - 0.08, (s_ + 1) * SLAB / steps,
            "concrete", top="concrete", bot="concrete", bay=1, fh=0.1)
    for vv in (vfront + 0.6, vfront + 1.8):
        beam(mb, G.p3(ustart, 0.0, vv), G.p3(ustart + sgn * steps * 0.55, SLAB, vv), 0.12, "bus_black")
        beam(mb, G.p3(ustart, 1.0, vv), G.p3(ustart + sgn * steps * 0.55, SLAB + 1.0, vv), 0.05, "bus_black")
    return dict(objs=[mb.build(coll)], origin=O, replaces=ids, replaces_names=["东苑集装箱美食街（信藕空间·文创街区）"],
                height=8.6, cam=(-62, 26), focus=(812.0, 4.0, -688.0, 24.0))


DORM_DEF = [(f"dorm_wenyuan_{z.lower()}", f"文园宿舍 {z}", m_wenyuan_zone(z)) for z in ("A2", "A3", "A4", "B2", "B3")]


# Models another session owns: never rebuilt by a full run (only with an explicit --only <key>, which then runs
# the owner's code). 东大门: tools/blender_dongdamen.py (v3); 东苑美食街街面: tools/blender_jzx_street.py -- both by the
# detail-correction session; their own main() is the usual way to rebuild them.
FROZEN = {"dongdamen", "jzx_street"}

VEHICLES_DEF = [("bus", "校园小公交", m_bus), ("bus_shelter", "公交候车亭", m_bus_shelter), ("ebike_7ma", "7ma共享电动车", m_ebike),
                ("gatehouse", "门卫岗亭", m_gatehouse)]


# ================================================================== batch 4 (official zoom1 crops)
def prism_edges(mb, pts, y0, y1, mat, pick=None, top=None, **kw):
    """Like prism, but pick(a, b) may return another material for an edge (glass corners etc.)."""
    pts = ccw(pts)
    n = len(pts)
    for i in range(n):
        a, b_ = pts[i], pts[(i + 1) % n]
        m = (pick(a, b_) if pick else None) or mat
        kk = dict(kw)
        if m != mat:
            kk.update(bay=3.0, fh=3.4, vspan=None)
        wall(mb, a, b_, y0, y1, m, **kk)
    if top:
        cap(mb, pts, y1, top)


def edge_box(mb, pts, near, w, d, y0, y1, mat, top="roof_flat", **kw):
    """Box (w along the facade, d out of it) attached outside the outline edge closest to point `near`."""
    pts = ccw(pts)
    best = None
    for i in range(len(pts)):
        a, b_ = pts[i], pts[(i + 1) % len(pts)]
        ex, ez = b_[0] - a[0], b_[1] - a[1]
        L = math.hypot(ex, ez)
        t = max(0.0, min(1.0, ((near[0] - a[0]) * ex + (near[1] - a[1]) * ez) / (L * L)))
        q = (a[0] + ex * t, a[1] + ez * t)
        dd = math.hypot(near[0] - q[0], near[1] - q[1])
        if best is None or dd < best[0]:
            best = (dd, q, math.atan2(ez, ex))
    _, q, ang = best
    Fb = Frame(q[0], q[1], ang)  # v = outward
    box(mb, Fb, -w / 2, w / 2, -0.5, d, y0, y1, mat, top=top, **kw)


def roof_pergola(mb, F, u0, u1, v0, v1, y0, h=2.4, mat="white"):
    for uu in (u0, u1):
        for vv in (v0, v1):
            box(mb, F, uu - 0.15, uu + 0.15, vv - 0.15, vv + 0.15, y0, y0 + h, mat, bay=0.3, fh=1)
    for vv in (v0, v1):
        box(mb, F, u0 - 0.2, u1 + 0.2, vv - 0.2, vv + 0.2, y0 + h, y0 + h + 0.35, mat, top=mat, bot=mat, bay=4, fh=0.35)
    k = max(2, int((u1 - u0) // 2.5))
    for i in range(k + 1):
        uu = u0 + (u1 - u0) * i / k
        box(mb, F, uu - 0.1, uu + 0.1, v0 - 0.2, v1 + 0.2, y0 + h + 0.35, y0 + h + 0.6, mat, top=mat, bot=mat, bay=4, fh=0.25)


def _std(bid, name, H, facade, bay, nf, height=None, cam=(32, 24), extra=None, pick=None, parapet_mat="white",
         roof="roof_flat", vspan=None):
    def fn(coll):
        b = bld(bid)
        pts = ccw(b["pts"])
        O = centroid(pts)
        mb = MB(name, O)
        kw = dict(bay=bay, fh=H / nf) if not vspan else dict(bay=bay, vspan=H)
        prism_edges(mb, pts, 0, H, facade, pick=pick, top=roof, **kw)
        if nf > 1 and facade not in ("theater",):
            floor_bands(mb, pts, [H * k / nf for k in range(1, nf)], "white")
        if parapet_mat:
            parapet(mb, pts, H - 0.2, H + 0.8, 0.25, parapet_mat)
        top = H + 0.8
        if extra:
            top = max(top, extra(mb, pts, O) or 0)
        return dict(objs=[mb.build(coll)], origin=O, replaces=[bid], replaces_names=[name], height=round(height or top, 1),
                    cam=cam)
    return fn


def _mingde(mb, pts, O):  # rounded glass east end done by pick(); tan external stair tower on the south facade
    edge_box(mb, pts, (600.0, -433.5), 4.6, 4.2, 0, 28.6, "of_facade", bay=2.3, fh=4.38)  # south facade (official crop)
    F = Frame(600.0, -441.0, -0.13)
    box(mb, F, -4, 4, -3, 3, 26.3, 29.0, "white", top="roof_flat", bay=4, fh=2.7)
    return 29.0


def _huodong(mb, pts, O):  # taller hall with dark roof (east part) + yellow steel pergola on the west roof
    F = Frame(O[0], O[1], -0.147)
    box(mb, F, 4, 30, -20, 6, 0, 17.0, "white_band", top="dark_roof", bay=4, fh=4.25)
    roof_pergola(mb, F, -28, -8, -10, 8, 12.9, h=3.0, mat="yellow")
    return 17.0


def _catmull(P, n=4):
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(0, i - 1)], P[i], P[i + 1], P[min(len(P) - 1, i + 2)]
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    out.append(tuple(P[-1]))
    return out


# 东苑食堂 east end from the 2024-12 drone photo (docs/questions/img/dongyuan_shitang_stairs_user_marked.webp), mapped onto
# the outline with an affine fit on its NW / SW / north-tip corners (2026-11-27). The glazed front is one smooth arc from
# the south wall (x ~719) to the north tip, ~5-8 m inside the outline's faceted east side.
DY_ARC = [(719.4, -618.0), (731.7, -623.3), (740.5, -629.5), (747.4, -637.7), (751.2, -645.3), (752.8, -656.4),
          (752.8, -667.2)]


def m_dongyuan_st(coll):
    """东苑食堂: 3 floors / 13.5 m (user; asset main roof 13.4, DSM 13.0-13.5), dark roof with plant units (drone 2024-12).
    User (2026-11-27): both stairs are inside the building, at the two places marked on the drone photo:
      - south: the protruding square red-brick stair block on the south wall where the glass arc starts (~1.7 m above
        the roof, DSM);
      - north: the pointed end of the arc, behind a white wall that slants out of the roof down to the plaza, with an
        orange-red beam across the arc above a red-brick pier.
    No outdoor stairs. The white slatted kiosk by the NE road is the gate's guard house, not part of this model."""
    b = bld(862952691)
    pts0 = [tuple(q) for q in b["pts"]]
    O = centroid(pts0)
    mb = MB("东苑食堂", O)
    arc = _catmull(DY_ARC, 4)
    pts = ccw([(673.5, -648.7), (679.9, -611.0)] + arc + [(745.0, -665.8)])
    arcset = set(arc)
    H = 13.5
    prism_edges(mb, pts, 0, H, "white_band", top="dark_roof", bay=4.0, fh=H / 3,
                pick=lambda a, b_: "glass_blue" if a in arcset and b_ in arcset else None)
    floor_bands(mb, pts, [4.5, 9.0], "white")
    parapet(mb, pts, H - 0.2, H + 0.8, 0.25, "white")
    F = Frame(O[0], O[1], 0.165)
    # south stair block: brick, flush with (0.8 m proud of) the south wall, just west of where the arc starts
    S = Frame(714.4, -617.6, 0.165 + math.pi)  # v points north (into the building)
    box(mb, S, -6.8, 6.8, -0.8, 6.0, 0, 15.2, "brick_red", top="dark_roof", bay=2.5, fh=3.8)
    # north end: red-brick pier under an orange-red beam across the arc, and the slanted white wall
    box(mb, Frame(761.6, -645.9, 0.165), -3.8, 3.8, -2.3, 2.3, 0, 12.6, "brick_red", top="brick_red", bay=2.5, fh=3.2)
    B = Frame(755.6, -648.4, math.atan2(-650.2 + 646.6, 767.5 - 743.7))
    box(mb, B, -12.0, 12.0, -0.9, 0.9, 12.6, 14.2, "terracotta", top="terracotta", bot="terracotta", bay=4, fh=1.6)
    a0, a1 = (749.5, -667.5), (761.9, -638.8)
    L = math.dist(a0, a1)
    W = Frame((a0[0] + a1[0]) / 2, (a0[1] + a1[1]) / 2, math.atan2(a1[1] - a0[1], a1[0] - a0[0]))
    prof = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, 2.5), (-L / 2, 17.0)]  # top edge 17 m at the tip -> 2.5 m at the plaza
    for vv, sgn in ((-0.4, -1), (0.4, 1)):
        ox, oz = W.vec(0, sgn)
        mb.face([W.p3(u, y, vv) for u, y in prof], None, "white", out=(ox, 0, oz))
    for k in range(3):
        u0, y0 = prof[k]
        u1, y1 = prof[k + 1]
        dx, dy = u1 - u0, y1 - y0
        ox, oz = W.vec(dy, 0)
        mb.face([W.p3(u0, y0, -0.4), W.p3(u1, y1, -0.4), W.p3(u1, y1, 0.4), W.p3(u0, y0, 0.4)], None, "white",
                out=(ox, -dx, oz))
    for u0, v0 in ((-24, -10), (-16, -10), (-8, -10), (-24, 2), (-16, 2), (-6, 6), (4, -4)):
        box(mb, F, u0, u0 + 4.5, v0, v0 + 2.2, H, H + 1.4, "steel_white", top="steel_white", bay=2.2, fh=1.4)
    box(mb, F, -26, 6, -5.5, -4.5, H, H + 0.7, "steel_white", top="steel_white", bay=4, fh=0.7)  # duct run
    return dict(objs=[mb.build(coll)], origin=O, replaces=[862952691], replaces_names=["东苑食堂"], height=17.0,
                cam=(60, 28))


def _zhongyuan(mb, pts, O):  # light-blue roof over the hall part
    # 2-storey link filling the wedge between 中苑美食城 (west) and this canteen, z -192..-158 (building audit:
    # asset + re-registered drone DSM both ~8.5 m there, our models had a gap)
    link = [(368.6, -192.0), (375.3, -192.0), (372.7, -185.5), (371.3, -161.4), (371.6, -158.0), (369.4, -158.0)]
    prism(mb, link, 0, 7.7, "red_brick", top="dark_roof", bay=3.6, fh=3.85)
    F = Frame(O[0], O[1], 1.547)
    box(mb, F, -22, 22, -10, 10, 7.7, 8.5, "white", top="sky_roof", bay=4, fh=0.8)
    return 8.5


def _qiming(mb, pts, O):  # red ground-floor band + blue glass stair tower at the west end
    prism(mb, inset(pts, -0.05), 0, 3.8, "brick_red", bay=2, fh=2, fit=False)
    edge_box(mb, pts, (363.0, -566.0), 5.0, 4.0, 0, 21.5, "glass_blue", top="white", bay=2.5, fh=3.4)
    return 21.5


def _changwang(mb, pts, O):  # yellow stair strip on the west facade + blue skylight/solar field on the roof
    edge_box(mb, pts, (431.0, -465.0), 2.4, 0.8, 0, 20.2, "yellow", top="yellow", bay=2.4, fh=3)
    F = Frame(452.0, -470.0, -0.168)
    box(mb, F, -8, 8, -10, 10, 18.8, 19.3, "glass_blue", top="glass_blue", bay=4, fh=0.5)
    return 20.2


def _fengyun(mb, pts, O):  # low hipped hall roof + gold entrance canopy + flat east block
    F = Frame(O[0], O[1], -0.1783)
    # outline from the 2024-12 orthophoto (detail session, 2026-11-27): u -24..23, v -16.5..19.
    # Re-registered DSM cross-sections (2026-11-27, ground ~-5.5): north strip v -16.5..-7 ~8.8 m, hall eaves ~10.7 m with a
    # shallow hip to ~12.2 m (ridge along u at v ~6, no fly tower), flat east block u 23..31 ~9.2 m (was hip to 17.6 m).
    box(mb, F, -23.5, 23.0, -7.0, 19.0, 0, 10.7, "theater", bay=4.0, fh=10.7)
    frustum(mb, F, -23.5, 23.0, -7.0, 19.0, 10.7, 12.2, 5.0, 12.5, "roof_gray", top="roof_gray", ov=0.6)
    box(mb, F, 22.5, 31.0, -8.0, 16.0, 0, 9.2, "theater", top="roof_flat", bay=4.0, fh=9.2)
    parapet(mb, F.rect(22.5, 31.0, -8.0, 16.0), 9.0, 9.7, 0.2, "white")
    box(mb, F, 12, 26, 15, 23, 4.0, 4.8, "yellow", top="yellow", bot="yellow", bay=4, fh=0.8)
    box(mb, F, 18, 20, 17, 22, 0, 4.0, "yellow", bay=2, fh=4)
    return 12.2


def _beichen(mb, pts, O):  # white rooftop pergola frames
    F = Frame(497.0, -575.3, -0.160)
    for uc in (-22, 0, 22):
        roof_pergola(mb, F, uc - 7, uc + 7, -5, 5, 15.9, h=2.4)
    return 18.9


m_mingde = _std(862952692, "明德楼", 26.3, "qx_wall", 3.4, 6, extra=_mingde, cam=(-20, 24),  # user: 6 floors; DSM 26.3
                pick=lambda a, b: "glass_blue" if min(a[0], b[0]) > 612 and max(a[1], b[1]) < -466 else None)
m_huodong = _std(862952689, "大学生活动中心", 12.9, "white_band", 4.0, 3, extra=_huodong, cam=(-35, 28))
m_zhongyuan_st = _std(1308936469, "中苑老食堂", 7.7, "red_brick", 3.6, 2, extra=_zhongyuan, cam=(-40, 28))  # 7.7 m: re-registered DSM (2026-11-27), was 10.8
m_qiming = _std(1114839563, "启明楼", 19.2, "qx_wall", 3.4, 5, extra=_qiming, cam=(-35, 24))
m_changwang = _std(1114839561, "长望楼", 18.8, "white_band", 4.0, 5, extra=_changwang, cam=(-50, 26))
m_fengyun = _std(862952697, "风云剧场", 8.8, "theater", 4.0, 1, extra=_fengyun, parapet_mat=None, cam=(30, 26), vspan=True)
m_beichen = _std(862959350, "北辰楼", 15.9, "gj_facade", 4.0, 4, extra=_beichen, cam=(25, 28))


# ================================================================== batch 5
def edge_frame(pts, near=None, facing=None):
    """Frame on an outline edge (u along it, v outward): the edge closest to `near`, or the longest edge whose
    outward normal points along `facing` (game x/z)."""
    pts = ccw(pts)
    best = None
    for i in range(len(pts)):
        a, b_ = pts[i], pts[(i + 1) % len(pts)]
        ex, ez = b_[0] - a[0], b_[1] - a[1]
        L = math.hypot(ex, ez)
        if near is not None:
            t = max(0.0, min(1.0, ((near[0] - a[0]) * ex + (near[1] - a[1]) * ez) / (L * L)))
            q = (a[0] + ex * t, a[1] + ez * t)
            score = -math.hypot(near[0] - q[0], near[1] - q[1])
        else:
            nx, nz = -ez / L, ex / L
            if nx * facing[0] + nz * facing[1] < 0.7:
                continue
            q, score = ((a[0] + b_[0]) / 2, (a[1] + b_[1]) / 2), L
        if best is None or score > best[0]:
            best = (score, q, math.atan2(ez, ex), L)
    _, q, ang, L = best
    F = Frame(q[0], q[1], ang)
    F.length = L
    return F


def classical_block(mb, rf, pts, cornice, top, facade, d=2.0):
    """逸夫楼 family: classical walls, white cornice, blue mansard with dormers along the whole outline."""
    prism(mb, pts, 0, cornice, facade, bay=3.8, vspan=cornice)
    prism(mb, inset(pts, -0.35), cornice - 0.6, cornice, "white", bay=3, fh=0.6)
    lo, hi = inset(pts, -0.35), inset(pts, d)
    ring(rf, lo, cornice, hi, top, "slate")
    cap(rf, hi, top, "slate_flat")
    dormers_poly(rf, lo, cornice, top - cornice, d + 0.35, 6.5, 3.5, wmat="white", hgt=min(2.0, top - cornice - 1.0))


def pavilion(mb, rf, F, u, w, cornice, roof_top, facade):
    """Square pavilion straddling the facade (frame from edge_frame), steep blue pyramid roof."""
    v0, v1 = -w + 1.5, 1.5
    box(mb, F, u - w / 2, u + w / 2, v0, v1, 0, cornice, facade, bay=3.8, vspan=cornice)
    box(mb, F, u - w / 2 - 0.3, u + w / 2 + 0.3, v0 - 0.3, v1 + 0.3, cornice - 0.6, cornice, "white", bay=3, fh=0.6)
    ring(rf, F.rect(u - w / 2 - 0.3, u + w / 2 + 0.3, v0 - 0.3, v1 + 0.3), cornice, [F.p(u, (v0 + v1) / 2)] * 4, roof_top,
         "slate")


def m_xueke(bid, name, cornice, top, facade, pav_us):
    def fn(coll):
        b = bld(bid)
        pts = ccw(b["pts"])
        O = centroid(pts)
        mb, rf = MB(name + "_主体", O), MB(name + "_屋顶", O)
        classical_block(mb, rf, pts, cornice, top, facade)
        F = edge_frame(pts, facing=(0, 1))  # longest south-facing facade
        for t in pav_us:
            pavilion(mb, rf, F, (t - 0.5) * F.length, 9.0, cornice + 1.5, top + 5.5, facade)
        return dict(objs=[mb.build(coll), rf.build(coll)], origin=O, replaces=[bid], replaces_names=[name],
                    height=round(top + 5.5, 1), cam=(-25, 28))
    return fn


def m_lanjiang(coll):
    b = bld(685183294)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], 1.043)  # u along the long side (towards SSE), v across
    mb = MB("揽江楼", O)
    # massing re-checked 2026-11-27 (building audit; building asset ray-cast height map, re-registered drone DSM):
    # end blocks 6 floors / 22.8 m, the middle with the two light wells one floor lower (19.1 m), penthouse 26.2 m
    # on the east (SSE) block; wells u -30..-12 / 12..30, v -12..7
    U, V, H, HM = 59.95, 26.35, 22.8, 19.1
    for u0, u1 in ((-U, -34), (34, U)):
        box(mb, F, u0, u1, -V, V, 0, H, "white_band", top="roof_flat", bay=4.0, fh=H / 6)
        parapet(mb, F.rect(u0, u1, -V, V), H - 0.2, H + 0.9, 0.25, "white")
    mids = [(-34, -30, -V, V), (-12, 12, -V, V), (30, 34, -V, V)]
    for u0, u1 in ((-30, -12), (12, 30)):
        mids += [(u0, u1, -V, -12), (u0, u1, 7, V)]
    for u0, u1, v0, v1 in mids:
        box(mb, F, u0, u1, v0, v1, 0, HM, "white_band", top="roof_flat", bay=4.0, fh=HM / 5)
    for u0, u1 in ((-34, 34),):
        for v0, v1 in ((-V, -V + 0.3), (V - 0.3, V)):
            box(mb, F, u0, u1, v0, v1, HM, HM + 0.9, "white", top="white", bay=4, fh=0.9)  # parapets of the lower middle
    floor_bands(mb, F.rect(-U, U, -V, V), [3.8 * k for k in range(1, 5)], "white")
    box(mb, F, U, U + 1.6, -8, 8, 0, H - 2.0, "glass_blue", top="white", bay=4, fh=H / 6)  # entrance, south-south-east end
    box(mb, F, 36, 44, -6, 6, H, 26.2, "white", top="roof_flat", bay=4, fh=3.4)       # penthouse (asset 26.2)
    for uc in (-50,):
        box(mb, F, uc - 4, uc + 4, -4, 4, H, H + 2.4, "white", top="roof_flat", bay=4, fh=2.4)
    return dict(objs=[mb.build(coll)], origin=O, replaces=[685183294], replaces_names=["揽江楼"], height=26.2, cam=(40, 26))


def m_yuejiang(coll):
    b = bld(1114843833)
    pts = ccw(b["pts"])
    O = centroid(pts)
    F = Frame(O[0], O[1], 1.053)
    mb = MB("阅江楼", O)
    H = 19.2
    prism(mb, pts, 0, H, "white_band", bay=4.0, fh=H / 5)
    floor_bands(mb, pts, [H * k / 5 for k in range(1, 5)], "white")
    inner = F.rect(-27, 27, -13, 13)
    for i in range(4):
        wall(mb, inner[(i + 1) % 4], inner[i], 0, H, "white_band", 4.0, H / 5)
    courtyard_roof(mb, pts, inner, H, "roof_flat")
    parapet(mb, pts, H - 0.2, H + 0.9, 0.25, "white")
    return dict(objs=[mb.build(coll)], origin=O, replaces=[1114843833], replaces_names=["阅江楼"], height=H + 0.9, cam=(40, 30))


def _meishicheng(mb, pts, O):  # glass pyramid skylight + glazed stair/bridge on the west side
    F = Frame(O[0], O[1], -0.1266)
    ring(mb, F.rect(-6, 6, -6, 6), 11.6, [F.p(0, 0)] * 4, 14.6, "glass_blue")
    Fe = edge_frame(pts, near=(317.0, -160.0))
    box(mb, Fe, -3.5, 3.5, -0.5, 3.0, 0, 12.4, "glass_blue", top="white", bay=3.5, fh=3.4)
    return 14.6


def _xinshitang(mb, pts, O):  # orange stair panel (west), glass entrance (south-east front), orange roof box
    Fo = edge_frame(pts, near=(145.0, 36.0))
    box(mb, Fo, -1.8, 1.8, -0.5, 0.8, 0, 15.2, "orange", top="orange", bay=3.6, fh=3.8)
    Fg = edge_frame(pts, near=(183.0, 39.0))
    box(mb, Fg, -8, 8, -0.5, 1.2, 0, 10.5, "glass_blue", top="white", bay=4, fh=3.5)
    box(mb, Frame(160.0, 30.0, -0.51), -3, 3, -1.5, 1.5, 14.3, 16.5, "orange", top="orange", bay=3, fh=2.2)
    return 16.5


m_xueke1 = m_xueke(1114843831, "学科1号楼", 13.7, 16.6, "yf4_wall", (0.5,))
m_xueke2 = m_xueke(1114843832, "学科2号楼", 16.0, 19.8, "yf_wall", (0.85,))
m_xueke3 = m_xueke(862959367, "学科3号楼", 15.5, 19.3, "yf_wall", (0.1, 0.9))
m_meishicheng = _std(1316305741, "中苑美食城", 11.6, "red_brick", 3.6, 3, extra=_meishicheng, cam=(-40, 28))
m_xinshitang = _std(862959361, "中苑新食堂", 14.3, "white_band", 4.0, 4, extra=_xinshitang, cam=(40, 26),
                    pick=lambda a, b: "glass_blue" if min(a[0], b[0]) > 208 else None)


def m_nanjie(coll):
    """南阶教室: 2 storeys (official crop). Sits on the OSM outline centre: aerial photo and official map both show
    the low grey-roofed block there; the DSM's 0.5 m is a reconstruction hole (the 6-9 m block ~15 m NE is
    another building). data/manual/model_overrides.json pins the same position."""
    O = (537.6, -381.5)
    F = Frame(O[0], O[1], -0.1834)
    mb = MB("南阶教室", O)
    box(mb, F, -13.5, 13.5, -7.5, 7.5, 0, 8.4, "white_band", top="roof_flat", bay=4.0, fh=4.2)
    parapet(mb, F.rect(-13.5, 13.5, -7.5, 7.5), 8.2, 9.1, 0.25, "white")
    box(mb, F, -16.0, -13.5, -2.0, 2.0, 0, 8.6, "white", top="roof_flat", bay=2, fh=2)  # external stair
    return dict(objs=[mb.build(coll)], origin=O, replaces=[862952688], replaces_names=["南阶教室"], height=9.1, cam=(-30, 30))


# ================================================================== batch 6
def _self_intersects(q):
    n = len(q)
    o = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            p1, p2, p3, p4 = q[i], q[(i + 1) % n], q[j], q[(j + 1) % n]
            if o(p1, p2, p3) * o(p1, p2, p4) < 0 and o(p3, p4, p1) * o(p3, p4, p2) < 0:
                return True
    return shoelace(q) >= 0  # inverted


def hip_on_outline(mb, pts, eave, ridge, mat, d_max=7.0):
    """Hip-like roof on any outline: slope from the eave line to the deepest valid inset, flat strip on top."""
    lo = inset(pts, -0.5)
    d = d_max
    while d > 1.0 and _self_intersects(inset(pts, d)):
        d -= 0.5
    hi = inset(pts, d)
    ring(mb, lo, eave, hi, ridge, mat)
    cap(mb, hi, ridge, mat)


def _kechuang(bid, name, eave, ridge, facade, nf):
    def fn(coll):
        b = bld(bid)
        pts = ccw(b["pts"])
        O = centroid(pts)
        mb = MB(name, O)
        prism(mb, pts, 0, eave, facade, bay=3.4, fh=eave / nf)
        floor_bands(mb, pts, [eave * k / nf for k in range(1, nf)] + [eave - 0.15], "white")
        hip_on_outline(mb, pts, eave, ridge, "tile_brown")
        return dict(objs=[mb.build(coll)], origin=O, replaces=[bid], replaces_names=[name], height=ridge, cam=(-25, 28))
    return fn


m_kc1 = _kechuang(862952684, "科创1号楼", 7.2, 10.5, "pink_facade", 2)
m_kc2 = _kechuang(862952683, "科创2号楼", 10.8, 14.2, "of_facade", 3)
m_kc3 = _kechuang(862952681, "科创3号楼", 10.8, 14.2, "pink_facade", 3)
m_kc4 = _kechuang(862952679, "科创4号楼", 4.5, 7.5, "of_facade", 1)


def m_jijia(coll):
    """基嘉楼, redone 2026-11-27: user confirmed ~3 floors / main roof ~10.3 m (DSM re-registered 10.3, asset 10.1);
    regular U around a small courtyard as on the official map (asset courtyard u -16..-8, v 0..8, its west-end fins
    are artefacts and not used); north-east block one storey higher (asset 12.8 m); light-blue barrel vault over the
    east part of the south wing (official map + drone 2024-12), dark flat roofs (drone)."""
    b = bld(862952700)
    pts = ccw(b["pts"])
    O = centroid(pts)
    F = Frame(526.71, -447.84, -0.1502)  # u ~ east along the south wing, v ~ south
    mb = MB("基嘉楼", O)
    H, NF = 10.3, 3
    prism(mb, pts, 0, H, "white_band", bay=4.0, fh=H / NF)
    inner = F.rect(-13.0, -3.5, -4.0, 5.0)
    for k in range(4):
        wall(mb, inner[(k + 1) % 4], inner[k], 0, H, "white_band", 4.0, H / NF)
    courtyard_roof(mb, pts, inner, H, "dark_roof")
    floor_bands(mb, pts, [H * k / NF for k in range(1, NF)], "white", out=0.08, th=0.18)
    parapet(mb, pts, H - 0.2, H + 0.7, 0.25, "white")
    # north-east block: one more storey (12.8 m)
    ne = F.rect(-8.0, 9.7, -14.3, -2.0)
    prism(mb, ne, H, 12.8, "white_band", top="dark_roof", bay=4.0, fh=H / NF)
    parapet(mb, ne, 12.6, 13.3, 0.25, "white")
    # light-blue barrel vault over the east part of the south wing (ridge along u)
    u0, u1, v0, v1, crown = -13.6, 24.9, 6.6, 19.5, 14.3
    n = 10
    prof = [(v0 + (v1 - v0) * k / n, H + (crown - H) * math.sin(math.pi * k / n)) for k in range(n + 1)]
    for (va, ya), (vb, yb) in zip(prof, prof[1:]):
        q = [F.p3(u0, ya, va), F.p3(u1, ya, va), F.p3(u1, yb, vb), F.p3(u0, yb, vb)]
        mb.face(q, [(u0 / 3, va / 3), (u1 / 3, va / 3), (u1 / 3, vb / 3), (u0 / 3, vb / 3)], "sky_roof",
                out=(F.vec(0, 1)[0] * -(yb - ya), 1, F.vec(0, 1)[1] * -(yb - ya)))
    for uu, su in ((u0, -1), (u1, 1)):  # gable ends of the vault
        ox, oz = F.vec(su, 0)
        mb.face([F.p3(uu, y, v) for v, y in prof], None, "white", out=(ox, 0, oz))
    objs = [mb.build(coll)]
    return dict(objs=objs, origin=O, replaces=[862952700], replaces_names=["基嘉楼"], height=14.3, cam=(-30, 30))


def m_jiaogong(coll):
    b = bld(862952690)
    O = centroid(b["pts"])
    mb = MB("教工活动中心", O)
    F = Frame(679.0, -369.4, -0.148)
    # re-registered DSM (2026-11-27): eaves ~7.0 m, shallow ridge ~9.0 m (was 8.0 / 13.0)
    gable(mb, F, -26.1, 26.1, -12.15, 12.15, 7.0, 7.0, 9.0, 0.5, "theater", "dark_roof", ov=0.8, bay=4.0, fh=7.0)
    annex = [(664.7, -354.9), (666.7, -341.9), (686.5, -344.9), (684.4, -358.1)]
    prism(mb, annex, 0, 4.8, "white_band", top="roof_flat", bay=4.0, fh=4.8)
    for k in range(9):  # round skylights along the south slope, as in the official crop
        x, z = F.p(-20 + 5 * k, -2.0)
        sphere(mb, (x, 8.8, z), 0.7, 8, 4, "white", ry=0.35)
    return dict(objs=[mb.build(coll)], origin=O, replaces=[862952690], replaces_names=["教工活动中心"], height=9.2, cam=(-30, 28))


def _nanqi(mb, pts, O):
    F = Frame(1065.0, -699.0, 0.145)  # outline moved 5 m south (position_audit 2026-11-27)
    roof_pergola(mb, F, -12, 4, -5, 5, 18.0, h=2.2)
    box(mb, F, 10, 18, -4, 4, 18.0, 21.0, "white", top="roof_flat", bay=4, fh=3)
    return 21.0


def clip_v(pts, F, v_cut, keep_greater):
    """Clip a map polygon by the line v = v_cut of frame F (Sutherland-Hodgman); keep the v > v_cut side or the other."""
    def side(q):
        dv = -(q[0] - F.cx) * math.sin(F.ang) + (q[1] - F.cz) * math.cos(F.ang) - v_cut
        return dv if keep_greater else -dv
    out = []
    for i in range(len(pts)):
        a, b_ = pts[i], pts[(i + 1) % len(pts)]
        sa, sb = side(a), side(b_)
        if sa >= 0:
            out.append(a)
        if (sa >= 0) != (sb >= 0):
            t = sa / (sa - sb)
            out.append((a[0] + (b_[0] - a[0]) * t, a[1] + (b_[1] - a[1]) * t))
    return out


def m_nanqi(coll):
    """南气宾馆: only the south ~17 m deep part is the tall block (5 floors, 19.9 m: re-registered DSM, campus h);
    the north ~10 m is a low podium / yard (detail session, 2024-12 orthophoto, 2026-11-27)."""
    b = bld(862952682)
    pts = ccw(b["pts"])
    O = centroid(pts)
    mb = MB("南气宾馆", O)
    F = Frame(1055.4, -699.0, 0.145)
    H = 19.9
    tall = ccw(clip_v(pts, F, -3.0, True))
    low = ccw(clip_v(pts, F, -3.0, False))
    prism(mb, tall, 0, H, "of_facade", top="roof_flat", bay=3.4, fh=H / 5)
    floor_bands(mb, tall, [H * k / 5 for k in range(1, 5)], "white")
    parapet(mb, tall, H - 0.2, H + 0.8, 0.25, "white")
    if len(low) >= 3:
        prism(mb, low, 0, 6.0, "of_facade", top="roof_flat", bay=3.4, fh=3.0)
        parapet(mb, low, 5.8, 6.6, 0.2, "white")
    Fr = Frame(1065.0, -699.0, 0.145)
    roof_pergola(mb, Fr, -12, 4, 0, 10, H, h=2.2)
    box(mb, Fr, 10, 18, 2, 10, H, H + 3.0, "white", top="roof_flat", bay=4, fh=3)
    return dict(objs=[mb.build(coll)], origin=O, replaces=[862952682], replaces_names=["南气宾馆"], height=H + 3.0,
                cam=(-30, 26))


def m_xiyuan(coll):
    b = bld(862959377)
    O = centroid(b["pts"])
    F = Frame(O[0], O[1], 0.0976)
    mb = MB("西苑新食堂", O)
    U, V, H = 34.85, 23.0, 11.0
    box(mb, F, -U, U, -V, V, 0, H, "white_band", bay=4.0, fh=H / 3)
    box(mb, F, -U - 1, U + 1, -V - 1, V + 4.5, H, H + 0.7, "white", top="roof_flat", bot="white", bay=4, fh=0.7)
    for u in range(-30, 31, 10):  # tall front colonnade under the canopy (south)
        cyl(mb, F.p(u, V + 3.8), 0.35, 0, H, 10, "white")
    for u0 in (-26, 6):
        roof_pergola(mb, F, u0, u0 + 20, -14, 14, H + 0.7, h=0.9)
    box(mb, F, U - 7, U, V, V + 0.5, 0, H, "glass_blue", top="white", bay=3.5, fh=3.67)
    return dict(objs=[mb.build(coll)], origin=O, replaces=[862959377], replaces_names=["西苑新食堂"], height=H + 2.2, cam=(25, 26))


# ================================================================== batch 7 (v0.5)
def m_zhongyuan_stand(coll):
    """中苑田径场西看台 + 主席台. Seats rise from the track (east, v<0) to the back wall (west, v>0); three sections
    split by two stair gaps; white two-storey grandstand building at the centre (official zoom1 + news photo)."""
    O = (-64.4, 13.75)
    F = Frame(O[0], O[1], math.pi / 2)  # u -> south, v -> west (back of the stand)
    mb = MB("中苑主席台", O)
    VF, VB, U = -8.1, 8.1, 71.25
    rows, y0, rise = 12, 1.2, 0.4
    depth = (VB - 1.6 - VF) / rows

    def seats(u0, u1, mat_t="seat_tread", mat_r="concrete"):
        prof = [(VF, 0.0), (VF, y0)]
        for k in range(rows):
            v = VF + k * depth
            prof += [(v + depth, y0 + k * rise), (v + depth, y0 + (k + 1) * rise)]
        prof += [(VB, y0 + rows * rise), (VB, 0.0)]
        top = y0 + rows * rise
        for (va, ya), (vb, yb) in zip(prof, prof[1:]):
            if va == vb and ya == yb:
                continue
            horiz = abs(ya - yb) < 1e-6
            pts = [F.p3(u0, ya, va), F.p3(u1, ya, va), F.p3(u1, yb, vb), F.p3(u0, yb, vb)]
            n = F.vec(0, -1)
            mb.face(pts, [(u0 / 2, va / 2), (u1 / 2, va / 2), (u1 / 2, vb / 2 + yb / 2), (u0 / 2, vb / 2 + yb / 2)],
                    mat_t if horiz else (mat_r if va != VB else "concrete"),
                    out=(0, 1, 0) if horiz else ((n[0], 0, n[1]) if va < VB - 0.01 else (-n[0], 0, -n[1])))
        for uu, sg in ((u0, -1), (u1, 1)):  # section end walls
            ox, oz = F.vec(sg, 0)
            mb.face([F.p3(uu, y, v) for v, y in prof], None, "white", out=(ox, 0, oz))
        box(mb, F, u0, u1, VF - 0.15, VF + 0.05, y0, y0 + 1.0, "white", top="white", bay=4, fh=1)          # front rail wall
        box(mb, F, u0, u1, VB - 0.3, VB, top, top + 1.1, "white", top="white", bay=4, fh=1.1)            # back parapet
        return top

    top = 0
    sections = [(-U, -26.0), (-22.0, -9.0), (9.0, 22.0), (26.0, U)]
    for u0, u1 in sections:
        top = seats(u0, u1)
    for gc in (-24.0, 24.0):  # stair gaps: steps up to the back walkway, white cheek walls, dark tunnel mouth
        seats(gc - 2.0, gc + 2.0, mat_t="stone", mat_r="stone")  # its sloped end walls are the stair cheeks
        ox, oz = F.vec(0, 1)
        mb.face([F.p3(gc - 1.6, 0.1, VB + 0.02), F.p3(gc + 1.6, 0.1, VB + 0.02), F.p3(gc + 1.6, 2.6, VB + 0.02),
                 F.p3(gc - 1.6, 2.6, VB + 0.02)], None, "dark_roof", out=(ox, 0, oz))
    # grandstand: VIP platform in front, white two-storey block, glazed upper floor, emblem, projecting roof slab
    box(mb, F, -9, 9, -6.6, -1.0, 0, 3.6, "white", top="stone", bay=4, fh=3.6)
    box(mb, F, -9, 9, -6.75, -6.45, 3.6, 4.7, "white", top="white", bay=4, fh=1.1)
    box(mb, F, -9, 9, -1.0, VB, 0, 9.6, "white", top="roof_flat", bay=4, fh=4.8)
    n = F.vec(0, -1)
    mb.face([F.p3(8.6, 5.6, -1.03), F.p3(-8.6, 5.6, -1.03), F.p3(-8.6, 8.5, -1.03), F.p3(8.6, 8.5, -1.03)],
            [(0, 0), (4, 0), (4, 1), (0, 1)], "glass_dark", out=(n[0], 0, n[1]))
    disc_pts = [F.p3(1.0 * math.cos(2 * math.pi * k / 20), 7.05 + 1.0 * math.sin(2 * math.pi * k / 20), -1.06) for k in range(20)]
    mb.face(disc_pts, [(0.5 - 0.5 * math.cos(2 * math.pi * k / 20), 0.5 + 0.5 * math.sin(2 * math.pi * k / 20)) for k in range(20)],
            "emblem", out=(n[0], 0, n[1]))
    box(mb, F, -11, 11, -4.6, VB + 0.3, 9.6, 10.1, "white", top="roof_flat", bot="white", bay=4, fh=0.5)
    return dict(objs=[mb.build(coll)], origin=O, replaces=["zhongyuan-stand"], replaces_names=["中苑田径场西看台+主席台"],
                height=10.1, cam=(70, 22), focus=(-60.0, 4.0, 13.75, 30.0))


def m_xiyuan_wenchuang(coll):
    """西苑文创街区 (5 small blocks; looks from the official zoom1 crop, assignment of looks to ids guessed)."""
    boxes = {b["id"]: b for b in CAMPUS["buildings"] if str(b["id"]).startswith("xywc")}
    allpts = [p for b in boxes.values() for p in b["pts"]]
    O = (sum(p[0] for p in allpts) / len(allpts), sum(p[1] for p in allpts) / len(allpts))
    mb = MB("西苑文创街区", O)

    def rect(bid):
        xs = [p[0] for p in boxes[bid]["pts"]]
        zs = [p[1] for p in boxes[bid]["pts"]]
        cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
        return Frame(cx, cz, 0.0), (max(xs) - min(xs)) / 2, (max(zs) - min(zs)) / 2

    # xywc-1: white two-storey block with two blue mono-pitch roofs + blue glass corner box
    F, hu, hv = rect("xywc-1")
    box(mb, F, -hu, hu, -hv, hv, 0, 6.2, "white_band", top="roof_flat", bay=3.0, fh=3.1)
    for u0, u1 in ((-hu - 0.3, 0.2), (0.2, hu + 0.3)):
        gable(mb, Frame(F.cx + (u0 + u1) / 2, F.cz, 0.0), -(u1 - u0) / 2, (u1 - u0) / 2, -hv - 0.3, hv + 0.3, 6.2, 6.2, 7.6,
              0.15, "white", "bus_blue", ov=0.4, bay=3, fh=3)
    box(mb, F, hu - 3.2, hu + 1.2, hv - 3.0, hv + 1.2, 0, 3.4, "glass_blue", top="white", bay=2.2, fh=3.4)
    # xywc-2: white house with flat roof and timber front
    F, hu, hv = rect("xywc-2")
    box(mb, F, -hu, hu, -hv, hv, 0, 4.2, "white_band", top="roof_flat", bay=3.0, fh=4.2)
    box(mb, F, hu, hu + 0.15, -hv + 1, hv - 1, 0.4, 3.6, "wood", top="wood", bay=2, fh=3.2)
    # xywc-3: glass pavilion (greenhouse look)
    F, hu, hv = rect("xywc-3")
    box(mb, F, -hu, hu, -hv, hv, 0, 3.2, "glass_blue", top="white", bay=2.25, fh=3.2)
    frustum(mb, F, -hu, hu, -hv, hv, 3.2, 3.6, 0.6, 0.6, "white", top="glass_blue")
    # xywc-4: yellow container shop with red sign band
    F, hu, hv = rect("xywc-4")
    box(mb, F, -hu, hu, -hv, hv, 0, 3.0, "container_yellow", top="roof_flat", bay=1.0, fh=3.0)
    box(mb, F, -hu - 0.05, hu + 0.05, -hv - 0.05, hv + 0.05, 3.0, 3.6, "sign_red", top="roof_flat", bay=4, fh=0.6)
    # xywc-5: white house with dark grey roof
    F, hu, hv = rect("xywc-5")
    box(mb, F, -hu, hu, -hv, hv, 0, 3.0, "white_band", bay=3.0, fh=3.0)
    frustum(mb, F, -hu, hu, -hv, hv, 3.0, 3.8, hu - 0.05, 0.6, "dark_roof", top=None, ov=0.4)
    return dict(objs=[mb.build(coll)], origin=O, replaces=["xywc-1", "xywc-2", "xywc-3", "xywc-4", "xywc-5"],
                replaces_names=["西苑文创街区 5 栋"], height=7.6, cam=(60, 30))


MODELS_DEF = [
    ("qixianglou", "气象楼", m_qixianglou),
    ("tushuguan", "图书馆", m_tushuguan),
    ("yifulou", "逸夫楼", m_yifulou),
    ("linjianglou", "临江楼（信息科技大楼）", m_linjianglou),
    ("dongyuan_tiyuguan", "东苑体育馆", m_tiyuguan),
    ("jianshanyuan", "见山园", m_jianshanyuan),
    ("laoxiaomen", "老校门", m_laoxiaomen),
    ("wendelou", "文德楼", m_wendelou),
    ("shangxianlou", "尚贤楼", m_shangxianlou),
    ("xingzhenglou", "行政楼", m_xingzhenglou),
    ("guojijiaoyu", "国际教育学院（培训楼）", m_guojijiaoyu),
    ("shengqi_guangchang", "升旗广场（旗阵）", m_shengqi),
    ("oufanglou", "藕舫楼", m_oufanglou),
    ("binjianglou", "滨江楼", m_binjianglou),
    ("dongdamen", "东大门", m_dongdamen),
    ("leidingxueyuan", "雷丁学院", m_leiding),
    ("shuiyunfang", "水云方（游泳馆）", m_shuiyunfang),
    ("qixianggu", "气象谷美食城", m_qixianggu),
    ("leidata", "雷达塔", m_leidata),
    ("mingdelou", "明德楼", m_mingde),
    ("huodongzhongxin", "大学生活动中心", m_huodong),
    ("dongyuan_shitang", "东苑食堂", m_dongyuan_st),
    ("zhongyuan_laoshitang", "中苑老食堂", m_zhongyuan_st),
    ("qiminglou", "启明楼", m_qiming),
    ("changwanglou", "长望楼", m_changwang),
    ("fengyun_juchang", "风云剧场", m_fengyun),
    ("beichenlou", "北辰楼", m_beichen),
    ("lanjianglou", "揽江楼", m_lanjiang),
    ("yuejianglou", "阅江楼", m_yuejiang),
    ("xueke1", "学科1号楼", m_xueke1),
    ("xueke2", "学科2号楼", m_xueke2),
    ("xueke3", "学科3号楼", m_xueke3),
    ("zhongyuan_meishicheng", "中苑美食城", m_meishicheng),
    ("zhongyuan_xinshitang", "中苑新食堂", m_xinshitang),
    ("nanjie_jiaoshi", "南阶教室", m_nanjie),
    ("kechuang1", "科创1号楼", m_kc1),
    ("kechuang2", "科创2号楼", m_kc2),
    ("kechuang3", "科创3号楼", m_kc3),
    ("kechuang4", "科创4号楼", m_kc4),
    ("jijialou", "基嘉楼", m_jijia),
    ("jiaogong_huodong", "教工活动中心", m_jiaogong),
    ("nanqi_binguan", "南气宾馆", m_nanqi),
    ("xiyuan_xinshitang", "西苑新食堂", m_xiyuan),
    ("zhongyuan_zhuxitai", "中苑主席台", m_zhongyuan_stand),
    ("xiyuan_wenchuang", "西苑文创街区", m_xiyuan_wenchuang),
]
MODELS_DEF += DORM_DEF
MODELS_DEF += DORM_DEF_QY
MODELS_DEF += DORM_DEF_DY
MODELS_DEF += [("dorm_qinyuan_g3", "沁园26栋", m_qinyuan26), ("dorm_e3_no8", "第八栋宿舍", m_no8)]
MODELS_DEF.append(("dongyuan_jzx", "东苑集装箱美食街", m_jzx))
MODELS_DEF.append(("jzx_street", "东苑美食街街面", m_jzx_street))  # owned by the detail-correction session (FROZEN)
MODELS_DEF.append(("e3_old_residential", "E3 老居民楼", m_e3_old_res))


# ------------------------------------------------------------------ scene / export
def setup_preview(objs, key, cam=(32, 24), focus=None, origin=(0.0, 0.0)):
    sc = bpy.context.scene
    pc = bpy.data.collections.new("_preview")
    sc.collection.children.link(pc)
    mn = Vector((1e9, 1e9, 1e9))
    mx = -mn
    for o in objs:
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    ctr = (mn + mx) / 2
    rad = (mx - mn).length / 2
    if focus:  # (x, y, z, radius) in game coordinates
        ctr = Vector((focus[0] - origin[0], -(focus[2] - origin[1]), focus[1]))
        rad = focus[3]
    # ground
    gm = bpy.data.meshes.new("ground")
    s = rad * 8
    gm.from_pydata([(-s, -s, -0.02), (s, -s, -0.02), (s, s, -0.02), (-s, s, -0.02)], [], [(0, 1, 2, 3)])
    gm.materials.append(M("ground"))
    g = bpy.data.objects.new("ground", gm)
    pc.objects.link(g)
    # world
    wd = bpy.data.worlds.new("sky")
    sc.world = wd
    if wd.node_tree is None:
        wd.use_nodes = True
    bg = next((n for n in wd.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs[0].default_value = (0.55, 0.7, 0.92, 1)
        bg.inputs[1].default_value = 0.55
    # sun from the south-east
    ld = bpy.data.lights.new("sun", "SUN")
    ld.energy = 3.0
    ld.angle = math.radians(2)
    lo = bpy.data.objects.new("sun", ld)
    lo.rotation_euler = Vector((-0.55, 0.75, -0.6)).to_track_quat("-Z", "Y").to_euler()
    pc.objects.link(lo)
    # camera: 3/4 view from south-south-east (all fronts face south = Blender -Y)
    cd = bpy.data.cameras.new("cam")
    cd.lens = 35
    co = bpy.data.objects.new("cam", cd)
    pc.objects.link(co)
    az, el = math.radians(cam[0]), math.radians(cam[1])
    aspect = 1000 / 680
    fov_v = 2 * math.atan(18 / 35 / aspect)
    dist = rad / math.sin(fov_v / 2) * 0.8
    co.location = ctr + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
    co.rotation_euler = (ctr - co.location).to_track_quat("-Z", "Y").to_euler()
    cd.clip_end = dist * 10
    sc.camera = co
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = 1000, 680, 100
    r.image_settings.file_format = "JPEG"
    r.image_settings.quality = 88
    r.filepath = str(PREV / f"{key}.jpg")
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        try:
            r.engine = eng
            break
        except TypeError:
            continue
    try:
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    return pc


def aim_camera(ctr, rad, cam):
    co = bpy.context.scene.camera
    aspect = 1000 / 680
    fov_v = 2 * math.atan(18 / 35 / aspect)
    dist = rad / math.sin(fov_v / 2) * 0.8
    az, el = math.radians(cam[0]), math.radians(cam[1])
    co.location = ctr + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
    co.rotation_euler = (ctr - co.location).to_track_quat("-Z", "Y").to_euler()


def export_glb(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True)


def tri_count(objs):
    return sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = None
    render = "--no-render" not in argv
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    if "--generic" in argv:
        build_generic(only, render)
        return
    for d in (BL, PREV, MODELS):
        d.mkdir(parents=True, exist_ok=True)
    out_json = BL / "models.json"
    entries = {e["file"]: e for e in (json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else [])}
    vjson = BL / "vehicles.json"
    ventries = {e["file"]: e for e in (json.loads(vjson.read_text(encoding="utf-8")) if vjson.exists() else [])}
    for key, title, fn in MODELS_DEF + VEHICLES_DEF:
        if only and key not in only:
            continue
        if key in FROZEN and not (only and key in only):
            print(f"[landmarks] {key}: skipped (owned by another session, see FROZEN)")
            continue
        bpy.ops.wm.read_homefile(use_empty=True)
        _MATS.clear()
        coll = bpy.data.collections.new(title)
        bpy.context.scene.collection.children.link(coll)
        info = fn(coll)
        objs = info["objs"]
        tris = tri_count(objs)
        glb = MODELS / f"{key}.glb"
        export_glb(objs, glb)
        if render:
            setup_preview(objs, key, info.get("cam", (32, 24)), info.get("focus"), info["origin"])
            bpy.ops.render.render(write_still=True)
            if info.get("cam2"):  # second view: same distance, other side
                sc = bpy.context.scene
                co = sc.camera
                ctr = sum((o.matrix_world @ v.co for o in objs for v in o.data.vertices), Vector()) / \
                    sum(len(o.data.vertices) for o in objs)
                dist = (co.location - ctr).length
                az, el = math.radians(info["cam2"][0]), math.radians(info["cam2"][1])
                co.location = ctr + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
                co.rotation_euler = (ctr - co.location).to_track_quat("-Z", "Y").to_euler()
                sc.render.filepath = str(PREV / f"{key}_2.jpg")
                bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(BL / f"{key}.blend"), compress=True, relative_remap=True)
        ox, oz = info["origin"]
        if info.get("vehicle"):
            ventries[f"models/{key}.glb"] = dict(name=title, file=f"models/{key}.glb", length=info["length"], width=info["width"],
                                                 height=info["height"], front="-z", origin="ground, centre of the body",
                                                 tris=tris, materials=len({m for o in objs for m in o.data.materials}))
            if info.get("note"):
                ventries[f"models/{key}.glb"].update(kind=info.get("kind"), note=info["note"])
            print(f"[landmarks] {key}: tris {tris}, glb {glb.stat().st_size / 1024:.0f} KB")
            continue
        e = dict(name=title, file=f"models/{key}.glb", x=round(ox, 2), z=round(oz, 2), rotY=0,
                 replaces=info["replaces"], replaces_names=info["replaces_names"], height=info["height"], tris=tris)
        if key == "yifulou":
            e["campus_name"] = "学科4号楼"
        if "replaces_poi" in info:
            e["replaces_poi"] = info["replaces_poi"]
        entries[e["file"]] = e
        print(f"[landmarks] {key}: tris {tris}, origin ({ox:.2f}, {oz:.2f}), glb {glb.stat().st_size / 1024:.0f} KB")
    order = [f"models/{k}.glb" for k, _, _ in MODELS_DEF]
    out = [entries[f] for f in order if f in entries]
    # keep entries written by other sessions' scripts (not in MODELS_DEF) -- never drop them
    out += [e for f, e in entries.items() if f not in order and f not in RETIRED]
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if ventries:
        vjson.write_text(json.dumps(list(ventries.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    print("[landmarks] wrote", out_json)
    for e in DORM_EAVE_LOG:
        print("[eave]", *e)


if __name__ == "__main__":
    main()
