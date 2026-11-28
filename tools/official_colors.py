"""Sample each building's wall colour from the official illustrated campus map (map.nuist.edu.cn tiles).

The official map is a 2.5D drawing; with the fitted transform ([mapX, mapY] = [x, z, h, 1] @ A) we find the
facade that faces the drawing's viewer, sample the middle of that wall, and keep the mid-brightness pixels
(wall, not windows or shadow).

Usage: .venv/Scripts/python.exe tools/official_colors.py
Output: data/official/tiles/zoom3/*.jpg (cache), data/official/wall_colors.json {building id: "#rrggbb"}
"""
import io
import json
import math
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
TILES = OFF / "tiles" / "zoom3"
UA = {"User-Agent": "Mozilla/5.0 (campus-3d-prototype)"}
A = np.array(json.loads((OFF / "transform.json").read_text(encoding="utf-8"))["A"])
campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
UNITS_PER_PX = 4          # zoom3 pixel = 4 map units
TILE = 256
cache = {}


def tile(tx, ty):
    if (tx, ty) in cache:
        return cache[(tx, ty)]
    p = TILES / f"{tx}_{ty}.jpg"
    im = None
    if not p.exists():
        try:
            b = urllib.request.urlopen(urllib.request.Request(f"https://map.nuist.edu.cn/mapdata/zoom3/{tx}_{ty}.jpg?v=20261101", headers=UA), timeout=20).read()
            p.write_bytes(b)
            time.sleep(0.05)
        except Exception:
            p.write_bytes(b"")
    if p.stat().st_size > 3000:
        im = np.asarray(Image.open(p).convert("RGB"))
    cache[(tx, ty)] = im
    return im


def pixel(X, Y):
    px, py = X / UNITS_PER_PX, Y / UNITS_PER_PX
    tx, ty = int(px // TILE), int(py // TILE)
    im = tile(tx, ty)
    if im is None:
        return None
    return im[int(py - ty * TILE), int(px - tx * TILE)]


def main():
    TILES.mkdir(parents=True, exist_ok=True)
    G = A[:2].T
    g = np.linalg.solve(G, -A[2])          # ground direction that moves "down" on the drawing = towards its viewer
    g = g / np.linalg.norm(g)
    out = {}
    for b in campus["buildings"]:
        if b.get("kind") == "wall" or b.get("color"):
            continue
        pts = b["pts"]
        area = 0.0
        for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1]):
            area += x0 * z1 - x1 * z0
        sign = 1 if area > 0 else -1           # outward normal side depends on winding
        best = None
        for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1]):
            ex, ez = x1 - x0, z1 - z0
            L = math.hypot(ex, ez)
            if L < 4:
                continue
            n = np.array([ez, -ex]) / L * sign
            face = float(n @ g)
            if face > 0.25 and (best is None or L * face > best[0]):
                best = (L * face, x0, z0, ex, ez, n)
        if not best:
            continue
        _, x0, z0, ex, ez, n = best
        h = b["h"]
        samples = []
        for t in np.linspace(0.15, 0.85, 7):
            for f in (0.3, 0.45, 0.6, 0.75):
                x, z = x0 + ex * t + n[0] * 0.4, z0 + ez * t + n[1] * 0.4
                X, Y = np.array([x, z, h * f, 1.0]) @ A
                c = pixel(X, Y)
                if c is not None:
                    samples.append(c)
        if len(samples) < 12:
            continue
        s = np.array(samples, float)
        lum = s @ [0.299, 0.587, 0.114]
        lo, hi = np.percentile(lum, 45), np.percentile(lum, 85)
        keep = s[(lum >= lo) & (lum <= hi)]
        if not len(keep):
            continue
        r, gg, bb = np.median(keep, axis=0)
        out[str(b["id"])] = "#%02x%02x%02x" % (int(r), int(gg), int(bb))
    (OFF / "wall_colors.json").write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"wall colours for {len(out)} buildings, tiles cached {sum(1 for v in cache.values() if v is not None)}")


if __name__ == "__main__":
    main()
