"""Correct the land-cover map with the official illustrated map (run after tools/landcover.py).

Our aerial survey was flown in late autumn / winter, so dormant lawns are brown and tools/landcover.py
classed many of them as bare soil (class 9). Where the official map (warped onto the ground by
tools/official_mosaic.py) draws lawn or planting at that spot, the pixel becomes grass (class 1).
Pitches, construction sites and other soil the official map does not draw green stay soil.

Usage: .venv/Scripts/python.exe tools/landcover_fix.py
Input : web/public/campus/landcover.png (backed up once to data/raw/landcover_raw.png),
        data/official/official_local.jpg + _meta.json, web/public/campus/campus.json
Output: web/public/campus/landcover.png, data/raw/landcover_fix_preview.jpg
"""
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LC = ROOT / "web" / "public" / "campus" / "landcover.png"
RAW = ROOT / "data" / "raw" / "landcover_raw.png"


def main():
    if not RAW.exists():
        shutil.copy(LC, RAW)
    lc = np.asarray(Image.open(RAW)).copy()
    H, W = lc.shape
    campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    SW, SD = campus["size"]
    off = np.asarray(Image.open(ROOT / "data" / "official" / "official_local.jpg").convert("RGB")).astype(np.int16)
    m = json.loads((ROOT / "data" / "official" / "official_local_meta.json").read_text(encoding="utf-8"))
    # official pixel for each land-cover pixel centre
    xs = np.arange(W) + 0.5 - SW / 2
    zs = np.arange(H) + 0.5 - SD / 2
    oi = ((xs - m["x0"]) / m["m_per_px"]).astype(int)
    oj = ((zs - m["z0"]) / m["m_per_px"]).astype(int)
    vi = (oi >= 0) & (oi < off.shape[1])
    vj = (oj >= 0) & (oj < off.shape[0])
    green = np.zeros((H, W), bool)
    sub = off[np.clip(oj, 0, off.shape[0] - 1)][:, np.clip(oi, 0, off.shape[1] - 1)]
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    green = (g > r + 12) & (g > b + 8) & (g > 60)
    green &= vj[:, None] & vi[None, :]
    # the drawing's 4.5 m registration error: require green in a 3x3 m neighbourhood majority
    import cv2
    gm = cv2.blur(green.astype(np.float32), (3, 3)) > 0.6
    fix = (lc == 9) & gm
    lc[fix] = 1
    Image.fromarray(lc, "L").save(LC, optimize=True)
    print(f"soil -> grass: {int(fix.sum())} m2 ({fix.sum() / max(1, (RAW_soil := int((np.asarray(Image.open(RAW)) == 9).sum()))) * 100:.0f}% of {RAW_soil} m2 soil)")
    pal = np.array([[0, 0, 0], [110, 170, 80], [30, 90, 40], [190, 185, 170], [70, 70, 75], [60, 120, 200], [200, 80, 60],
                    [60, 160, 70], [80, 140, 180], [150, 120, 80], [230, 230, 230]] + [[255, 0, 255]] * 245, np.uint8)
    Image.fromarray(pal[lc]).resize((W // 2, H // 2)).save(ROOT / "data" / "raw" / "landcover_fix_preview.jpg", quality=85)


if __name__ == "__main__":
    main()
