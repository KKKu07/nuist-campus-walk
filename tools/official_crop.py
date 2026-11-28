"""Cut a high-resolution reference picture of one building out of the official illustrated campus map.

map.nuist.edu.cn serves its 2.5D drawing at several zoom levels; zoom1 is 1 map unit per pixel, about
7 px per metre, enough to read facades, window bands, roof equipment, sidewalks and railings. With the
fitted transform ([mapX, mapY] = [x, z, h, 1] @ A) the footprint at ground and at roof height gives the
crop box. Used as modelling reference for the Blender landmarks.

Usage: .venv/Scripts/python.exe tools/official_crop.py 明德楼 大学生活动中心 ...   (names or building ids)
Output: data/official/tiles/zoom1/*.jpg (cache), data/official/crops/<name>.jpg
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
TILES = OFF / "tiles" / "zoom1"
OUT = OFF / "crops"
UA = {"User-Agent": "Mozilla/5.0 (campus-3d-prototype)"}
A = np.array(json.loads((OFF / "transform.json").read_text(encoding="utf-8"))["A"])
T = 256          # zoom1: 1 map unit per pixel, 256-unit tiles


def tile(tx, ty):
    p = TILES / f"{tx}_{ty}.jpg"
    if not p.exists():
        try:
            p.write_bytes(urllib.request.urlopen(urllib.request.Request(
                f"https://map.nuist.edu.cn/mapdata/zoom1/{tx}_{ty}.jpg?v=20261101", headers=UA), timeout=30).read())
            time.sleep(0.05)
        except (urllib.error.URLError, TimeoutError):
            p.write_bytes(b"")
    return Image.open(p).convert("RGB") if p.stat().st_size > 2000 else None


def local_shift(x, z):
    """ground offset of the official drawing at (x, z) from tools/official_align.py (0, 0 if not measured)"""
    p = OFF / "align_shift.json"
    if not p.exists():
        return 0.0, 0.0
    d = json.loads(p.read_text(encoding="utf-8"))
    xs, zs = np.array(d["xs"]), np.array(d["zs"])
    i = int(np.clip(np.round((x - xs[0]) / (xs[1] - xs[0])), 0, len(xs) - 1))
    j = int(np.clip(np.round((z - zs[0]) / (zs[1] - zs[0])), 0, len(zs) - 1))
    return float(d["dx"][j][i]), float(d["dz"][j][i])


def crop(b, margin=60):
    pts = np.array(b["pts"], float)
    sdx, sdz = local_shift(pts[:, 0].mean(), pts[:, 1].mean())
    pts = pts + [sdx, sdz]                       # where the official drawing actually puts this building
    ground = np.c_[pts, np.zeros(len(pts)), np.ones(len(pts))] @ A
    roof = np.c_[pts, np.full(len(pts), b["h"]), np.ones(len(pts))] @ A
    allp = np.vstack([ground, roof])
    x0, y0 = allp.min(0) - margin
    x1, y1 = allp.max(0) + margin
    out = Image.new("RGB", (int(x1 - x0), int(y1 - y0)), (240, 240, 240))
    for tx in range(int(x0 // T), int(x1 // T) + 1):
        for ty in range(int(y0 // T), int(y1 // T) + 1):
            im = tile(tx, ty)
            if im is not None:
                out.paste(im, (int(tx * T - x0), int(ty * T - y0)))
    d = ImageDraw.Draw(out)
    d.line([tuple(q - (x0, y0)) for q in ground] + [tuple(ground[0] - (x0, y0))], fill=(255, 0, 0), width=1)   # footprint at ground
    return out


def main():
    TILES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    for q in sys.argv[1:]:
        b = next((b for b in campus["buildings"] if str(b["id"]) == q or b.get("name") == q), None)
        if not b:
            print("not found:", q)
            continue
        im = crop(b)
        path = OUT / f"{b.get('name') or b['id']}.jpg"
        im.save(path, quality=90)
        print(f"{path.relative_to(ROOT)}  {im.size[0]}x{im.size[1]} px  (h {b['h']} m, id {b['id']})")


if __name__ == "__main__":
    main()
