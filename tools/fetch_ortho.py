"""Download satellite tiles for the campus bbox, stitch and crop to the exact bbox.

Usage: .venv/Scripts/python.exe tools/fetch_ortho.py
Output: web/public/campus/ortho.jpg (+ ortho_4k.jpg) and data/raw/ortho_meta.json
Imagery: Esri World Imagery (prototype only; replace with our own drone orthophoto before release).
"""
import json
import math
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BBOX = dict(south=32.1940, west=118.6895, north=32.2115, east=118.7245)
ZOOM = 18
URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
CACHE = ROOT / "data" / "raw" / "tiles" / str(ZOOM)
OUT = ROOT / "web" / "public" / "campus"


def lonlat_to_px(lon, lat, z):
    n = 256 * 2 ** z
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def fetch(tx, ty):
    path = CACHE / f"{ty}_{tx}.jpg"
    if path.exists() and path.stat().st_size > 0:
        return path
    req = urllib.request.Request(URL.format(z=ZOOM, x=tx, y=ty), headers={"User-Agent": "campus-3d-prototype/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                path.write_bytes(r.read())
            return path
        except Exception:
            time.sleep(1 + attempt)
    raise RuntimeError(f"tile failed {tx},{ty}")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    x0, y0 = lonlat_to_px(BBOX["west"], BBOX["north"], ZOOM)
    x1, y1 = lonlat_to_px(BBOX["east"], BBOX["south"], ZOOM)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    print(f"{len(tiles)} tiles")
    with ThreadPoolExecutor(4) as ex:
        paths = list(ex.map(lambda t: fetch(*t), tiles))
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for (tx, ty), p in zip(tiles, paths):
        mosaic.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    crop = mosaic.crop((round(x0 - tx0 * 256), round(y0 - ty0 * 256), round(x1 - tx0 * 256), round(y1 - ty0 * 256)))
    crop.save(OUT / "ortho.jpg", quality=86)
    w, h = crop.size
    s = 4096 / max(w, h)
    crop.resize((round(w * s), round(h * s)), Image.Resampling.LANCZOS).save(OUT / "ortho_4k.jpg", quality=86)
    meta = dict(bbox=BBOX, zoom=ZOOM, size=[w, h], source="Esri World Imagery (prototype only)")
    (ROOT / "data" / "raw" / "ortho_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("saved", crop.size)


if __name__ == "__main__":
    main()
