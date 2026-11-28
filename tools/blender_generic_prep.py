"""Prepare the input for the generic (non-landmark) Blender buildings.

Run with the project venv:  .venv\\Scripts\\python.exe tools\\blender_generic_prep.py
Reads campus.json, data/blender/models.json (landmarks already modelled), data/official/wall_colors.json and the
cached official map tiles (zoom3) to sample each roof colour. Writes data/blender/generic_input.json:
    {"chunk_m": 320, "buildings": [{id, name, pts, h, lv, kind, roof, wall, roofcol, chunk}]}
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
CHUNK = 640.0
A = np.array(json.loads((OFF / "transform.json").read_text(encoding="utf-8"))["A"])
_tiles: dict = {}


# Heights the Blender session has checked against photos where campus.json is still off (tell the main session so the
# campus value follows): id -> (h, floors)
H_OVERRIDE = {
    "862959351": (7.0, 2),  # 明远楼: two low blocks with blue fascias by the pylon (2024-12 drone); asset main roof 7.0 m
}

def tile(tx, ty):
    if (tx, ty) not in _tiles:
        p = OFF / "tiles" / "zoom3" / f"{tx}_{ty}.jpg"
        _tiles[(tx, ty)] = np.asarray(Image.open(p).convert("RGB")) if p.exists() and p.stat().st_size > 3000 else None
    return _tiles[(tx, ty)]


def sample(x, z, h, r=6):
    """Median colour of a (2r+1)^2 block of the official illustrated map at local (x, z, height h),
    ignoring vegetation-green pixels (trees drawn over roofs)."""
    X, Y = np.array([x, z, h, 1.0]) @ A / 4.0
    vals = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            px, py = int(X) + dx, int(Y) + dy
            t = tile(px // 256, py // 256)
            if t is not None:
                c = t[py % 256, px % 256].astype(int)
                if not (c[1] > max(c[0], c[2]) + 10):
                    vals.append(c)
    if len(vals) < 10:
        return None
    m = np.median(np.array(vals), axis=0)
    return "#{:02x}{:02x}{:02x}".format(*[int(v) for v in m])


def centroid(p):
    a = cx = cz = 0.0
    n = len(p)
    for i in range(n):
        x0, z0 = p[i]
        x1, z1 = p[(i + 1) % n]
        c = x0 * z1 - x1 * z0
        a += c
        cx += (x0 + x1) * c
        cz += (z0 + z1) * c
    return (cx / (3 * a), cz / (3 * a)) if abs(a) > 1e-9 else (sum(q[0] for q in p) / n, sum(q[1] for q in p) / n)


def main():
    campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    models = json.loads((ROOT / "data" / "blender" / "models.json").read_text(encoding="utf-8"))
    done = {str(r) for e in models for r in e["replaces"]}
    walls = json.loads((OFF / "wall_colors.json").read_text(encoding="utf-8"))
    out, sampled = [], 0
    for b in campus["buildings"]:
        if str(b["id"]) in done or b.get("kind") == "wall" or len(b["pts"]) < 3:
            continue
        cx, cz = centroid(b["pts"])
        roof = b.get("roof")
        rh = b["h"] + (roof["rise"] * 0.5 if roof else 0.0)
        rc = sample(cx, cz, rh)
        sampled += rc is not None
        hv, lvv = H_OVERRIDE.get(str(b["id"]), (b["h"], b.get("lv")))
        out.append(dict(id=b["id"], name=b.get("name") or "", pts=b["pts"], h=hv, lv=lvv, kind=b.get("kind"),
                        roof=roof, campus=b.get("campus", True),
                        wall=b.get("color") or walls.get(str(b["id"])) or "#e6e6e2",
                        roofcol=rc or ("#8c7a6b" if roof else "#c9cbc8"),
                        chunk=f"{math.floor((cx + 1650) / CHUNK)}_{math.floor((cz + 970) / CHUNK)}"))
    dst = ROOT / "data" / "blender" / "generic_input.json"
    dst.write_text(json.dumps(dict(chunk_m=CHUNK, buildings=out), ensure_ascii=False), encoding="utf-8")
    chunks = sorted({o["chunk"] for o in out})
    print(f"{len(out)} generic buildings, roof colour sampled for {sampled}, {len(chunks)} chunks -> {dst}")


if __name__ == "__main__":
    main()
