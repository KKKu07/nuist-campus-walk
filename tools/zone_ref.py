"""Reference sheet for one zone of the campus: what we model vs what the sources show.

For a box [x0, z0, x1, z1] (local metres) it writes data/zones/<name>/:
  aerial.jpg     our drone/Esri ortho (0.25 m/px) with our buildings (yellow), roads (red edges), water (blue)
  official.jpg   the official illustrated map warped to the ground (same frame), same overlay
  oblique.jpg    the official map's zoom1 drawing (2.5D, ~7 px/m) of the box, unwarped: facades, roofs, paving
  info.json      buildings / roads / sports / markers inside the box (ids, names, heights, sources)

Usage: .venv/Scripts/python.exe tools/zone_ref.py <name> x0 z0 x1 z1
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from official_crop import A, T, tile  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def main():
    name = sys.argv[1]
    x0, z0, x1, z1 = map(float, sys.argv[2:6])
    out = ROOT / "data" / "zones" / name
    out.mkdir(parents=True, exist_ok=True)
    c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, H = c["size"]
    k = 4.0                                                     # output px per metre
    size = (int((x1 - x0) * k), int((z1 - z0) * k))
    P = lambda x, z: ((x - x0) * k, (z - z0) * k)

    orth = Image.open(ROOT / "web" / "public" / "campus" / "ortho.jpg")
    sx = orth.size[0] / W
    aer = orth.crop((int((x0 + W / 2) * sx), int((z0 + H / 2) * sx), int((x1 + W / 2) * sx), int((z1 + H / 2) * sx))).resize(size, Image.LANCZOS)
    off = Image.open(ROOT / "data" / "official" / "official_local.jpg")
    m = json.loads((ROOT / "data" / "official" / "official_local_meta.json").read_text(encoding="utf-8"))
    q = 1 / m["m_per_px"]
    ofl = off.crop((int((x0 - m["x0"]) * q), int((z0 - m["z0"]) * q), int((x1 - m["x0"]) * q), int((z1 - m["z0"]) * q))).resize(size, Image.LANCZOS)

    def inside(pts, pad=0):
        xs, zs = [p[0] for p in pts], [p[1] for p in pts]
        return max(xs) >= x0 - pad and min(xs) <= x1 + pad and max(zs) >= z0 - pad and min(zs) <= z1 + pad

    info = {"box": [x0, z0, x1, z1], "buildings": [], "roads": [], "sports": [], "markers": [], "models": []}
    for im in (aer, ofl):
        d = ImageDraw.Draw(im, "RGBA")
        for w in c["water"]:
            if inside(w["pts"]):
                d.polygon([P(*p) for p in w["pts"]], outline=(60, 140, 255, 255))
        for r in c["roads"]:
            if not inside(r["pts"], 20):
                continue
            hw = r["w"] / 2
            for (ax, az), (bx, bz) in zip(r["pts"], r["pts"][1:]):
                L = math.hypot(bx - ax, bz - az) or 1
                nx, nz = -(bz - az) / L, (bx - ax) / L
                for s in (-1, 1):
                    d.line([P(ax + nx * hw * s, az + nz * hw * s), P(bx + nx * hw * s, bz + nz * hw * s)], fill=(255, 40, 40, 220), width=1)
        for b in c["buildings"]:
            if inside(b["pts"]):
                col = (0, 255, 255, 255) if b.get("replaced") else (255, 230, 0, 255)
                d.polygon([P(*p) for p in b["pts"]], outline=col)
                cx = sum(p[0] for p in b["pts"]) / len(b["pts"])
                cz = sum(p[1] for p in b["pts"]) / len(b["pts"])
                d.text(P(cx, cz), f"{b.get('name') or ''} {b['h']}m", fill=col)
        for s in c["sports"]:
            cx, cz, L, Wd, a = s["obb"]
            if x0 - L < cx < x1 + L and z0 - L < cz < z1 + L:
                ca, sa = math.cos(a), math.sin(a)
                cs = [(cx + u * ca - v * sa, cz + u * sa + v * ca) for u, v in ((-L / 2, -Wd / 2), (L / 2, -Wd / 2), (L / 2, Wd / 2), (-L / 2, Wd / 2))]
                d.polygon([P(*p) for p in cs], outline=(255, 120, 255, 255))
    for b in c["buildings"]:
        if inside(b["pts"]):
            info["buildings"].append({k2: b.get(k2) for k2 in ("id", "name", "h", "lv", "kind", "style", "color", "replaced", "fixed")})
    for r in c["roads"]:
        if inside(r["pts"], 5):
            info["roads"].append({k2: r.get(k2) for k2 in ("id", "name", "kind", "w", "sw", "pave", "audited")})
    for s in c["sports"]:
        if x0 <= s["obb"][0] <= x1 and z0 <= s["obb"][1] <= z1:
            info["sports"].append({"kind": s["kind"], "name": s.get("name"), "obb": s["obb"]})
    info["markers"] = [mk for mk in c["markers"] if x0 <= mk["x"] <= x1 and z0 <= mk["z"] <= z1]
    info["models"] = [md for md in c["models"] if x0 <= md["x"] <= x1 and z0 <= md["z"] <= z1]
    aer.save(out / "aerial.jpg", quality=88)
    ofl.save(out / "official.jpg", quality=88)

    # oblique high-res official drawing (unwarped); ground box corners at h = 0 and 20 m
    cs = np.array([[x, z, h, 1] for x in (x0, x1) for z in (z0, z1) for h in (0, 20)]) @ A
    X0, Y0 = cs.min(0)
    X1, Y1 = cs.max(0)
    ob = Image.new("RGB", (int(X1 - X0), int(Y1 - Y0)), (240, 240, 240))
    for tx in range(int(X0 // T), int(X1 // T) + 1):
        for ty in range(int(Y0 // T), int(Y1 // T) + 1):
            t = tile(tx, ty)
            if t is not None:
                ob.paste(t, (int(tx * T - X0), int(ty * T - Y0)))
    if ob.size[0] > 2400:
        ob = ob.resize((2400, int(ob.size[1] * 2400 / ob.size[0])), Image.LANCZOS)
    ob.save(out / "oblique.jpg", quality=88)
    (out / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out.relative_to(ROOT)}: aerial/official {size[0]}x{size[1]}, oblique {ob.size[0]}x{ob.size[1]}, "
          f"{len(info['buildings'])} buildings, {len(info['roads'])} roads, {len(info['markers'])} markers")


if __name__ == "__main__":
    main()
