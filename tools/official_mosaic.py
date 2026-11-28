"""Warp the official illustrated campus map (map.nuist.edu.cn, zoom3 tiles) onto our local ground plane.

The official map is a 2.5D drawing; with the fitted transform ([mapX, mapY] = [x, z, h, 1] @ A, h = 0 for
the ground) every local ground point has a drawing pixel. Roofs and tall walls lean in the warped image, but
roads, lawns, water and sports fields sit at h = 0 and line up with our aerial ortho, which makes it the
reference for checking road widths, medians and sidewalks.

Usage: .venv/Scripts/python.exe tools/official_mosaic.py [m_per_px=0.5]
Output: data/official/tiles/zoom3/*.jpg (cache), data/official/official_local.jpg (+ _meta.json)
"""
import urllib.error
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
TILES = OFF / "tiles" / "zoom3"
UA = {"User-Agent": "Mozilla/5.0 (campus-3d-prototype)"}
A = np.array(json.loads((OFF / "transform.json").read_text(encoding="utf-8"))["A"])
UNITS_PER_TILE = 4 * 256


def fetch(t):
    tx, ty = t
    p = TILES / f"{tx}_{ty}.jpg"
    if p.exists():
        return
    for _ in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                f"https://map.nuist.edu.cn/mapdata/zoom3/{tx}_{ty}.jpg?v=20261101", headers=UA), timeout=30).read()
            p.write_bytes(b)
            return
        except urllib.error.HTTPError:
            p.write_bytes(b"")          # outside the drawing
            return
        except Exception:
            time.sleep(1)
    p.write_bytes(b"")


def main():
    mpp = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    allp = np.concatenate([np.array(p) for p in campus["boundary"]])
    x0, z0 = allp.min(0) - 40
    x1, z1 = allp.max(0) + 40
    W, H = int((x1 - x0) / mpp), int((z1 - z0) / mpp)
    xs = x0 + (np.arange(W) + 0.5) * mpp
    zs = z0 + (np.arange(H) + 0.5) * mpp
    X = xs[None, :] * A[0, 0] + zs[:, None] * A[1, 0] + A[3, 0]
    Y = xs[None, :] * A[0, 1] + zs[:, None] * A[1, 1] + A[3, 1]
    tx, ty = (X // UNITS_PER_TILE).astype(int), (Y // UNITS_PER_TILE).astype(int)
    need = sorted(set(zip(tx.ravel().tolist(), ty.ravel().tolist())))
    TILES.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(fetch, need))
    out = np.zeros((H, W, 3), np.uint8)
    got = 0
    for t in need:
        p = TILES / f"{t[0]}_{t[1]}.jpg"
        if p.stat().st_size < 3000:
            continue
        im = np.asarray(Image.open(p).convert("RGB"))
        m = (tx == t[0]) & (ty == t[1])
        px = ((X[m] - t[0] * UNITS_PER_TILE) / 4).astype(int).clip(0, 255)
        py = ((Y[m] - t[1] * UNITS_PER_TILE) / 4).astype(int).clip(0, 255)
        out[m] = im[py, px]
        got += 1
    Image.fromarray(out).save(OFF / "official_local.jpg", quality=90)
    (OFF / "official_local_meta.json").write_text(json.dumps(
        {"x0": float(x0), "z0": float(z0), "m_per_px": mpp, "size": [W, H],
         "note": "pixel (i, j) centre = (x0 + (i + .5) * m_per_px, z0 + (j + .5) * m_per_px), ground plane h = 0"}, indent=1))
    print(f"{W}x{H} px, tiles {got}/{len(need)}")


if __name__ == "__main__":
    main()
