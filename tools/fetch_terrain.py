"""Download public elevation tiles (Terrarium / SRTM-based) and resample to a 10 m grid over the campus bbox.

Usage: .venv/Scripts/python.exe tools/fetch_terrain.py
Output: web/public/campus/terrain.json  {nx, nz, cell, size, base, h: [decimetres, row-major north->south]}
"""
import json
import math
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "public" / "campus"
Z = 14
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CELL = 10.0

meta = json.loads((RAW / "ortho_meta.json").read_text(encoding="utf-8"))
B = meta["bbox"]


def lonlat_to_px(lon, lat, z):
    n = 256 * 2 ** z
    s = math.sin(math.radians(lat))
    return (lon + 180) / 360 * n, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n


def main():
    cache = RAW / "terrain" / str(Z)
    cache.mkdir(parents=True, exist_ok=True)
    x0, y0 = lonlat_to_px(B["west"], B["north"], Z)
    x1, y1 = lonlat_to_px(B["east"], B["south"], Z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            p = cache / f"{ty}_{tx}.png"
            if not p.exists():
                req = urllib.request.Request(URL.format(z=Z, x=tx, y=ty), headers={"User-Agent": "campus-3d-prototype/0.1"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    p.write_bytes(r.read())
            mosaic.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    W, H = mosaic.size
    elev = Image.new("F", (W, H))
    src, dst = mosaic.load(), elev.load()
    for j in range(H):
        for i in range(W):
            r, g, b = src[i, j]
            dst[i, j] = (r * 256 + g + b / 256) - 32768

    phi = math.radians((B["south"] + B["north"]) / 2)
    width = (B["east"] - B["west"]) * (111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi))
    depth = (B["north"] - B["south"]) * (111132.92 - 559.82 * math.cos(2 * phi))
    nx, nz = int(width // CELL) + 1, int(depth // CELL) + 1
    ep = elev.load()

    def sample(px, py):
        px = min(max(px, 0), W - 1.001)
        py = min(max(py, 0), H - 1.001)
        i, j = int(px), int(py)
        fx, fy = px - i, py - j
        a, b_ = ep[i, j], ep[i + 1, j]
        c, d = ep[i, j + 1], ep[i + 1, j + 1]
        return (a * (1 - fx) + b_ * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy

    hs = []
    for k in range(nz):
        lat = B["north"] - (B["north"] - B["south"]) * k / (nz - 1)
        for i in range(nx):
            lon = B["west"] + (B["east"] - B["west"]) * i / (nx - 1)
            px, py = lonlat_to_px(lon, lat, Z)
            hs.append(sample(px - tx0 * 256, py - ty0 * 256))
    for _ in range(2):  # light smoothing: SRTM-type data carries building/tree noise
        sm = hs[:]
        for k in range(nz):
            for i in range(nx):
                acc, n = 0.0, 0
                for dk in (-1, 0, 1):
                    for di in (-1, 0, 1):
                        kk, ii = k + dk, i + di
                        if 0 <= kk < nz and 0 <= ii < nx:
                            acc += hs[kk * nx + ii]
                            n += 1
                sm[k * nx + i] = acc / n
        hs = sm
    base = sorted(hs)[len(hs) // 10]
    data = dict(nx=nx, nz=nz, size=[round(width, 1), round(depth, 1)], base=round(base, 1),
                h=[int(round((v - base) * 10)) for v in hs])
    (OUT / "terrain.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"grid {nx}x{nz}, base {base:.1f} m, range {min(hs) - base:.1f}..{max(hs) - base:.1f} m")


if __name__ == "__main__":
    main()
