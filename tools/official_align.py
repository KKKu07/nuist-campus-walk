"""Register the official illustrated map (warped to the ground, data/official/official_local.jpg) to our aerial.

The fitted transform puts the official drawing's ground ~10-20 m off (it was fitted on label positions, which
float above the ground). For windows of 200 m on a 100 m lattice over the campus we search the shift
(dx, dz) that maximises mutual information between colour classes (brightness x greenness) of the aerial
and of the official map — robust across the two very different image types. Low-confidence windows (z-score
of the peak < 2.5) are replaced by the median of their neighbours. Then the official map is re-sampled with
the smooth shift field.

Usage: .venv/Scripts/python.exe tools/official_align.py
Output: data/official/align_shift.json (lattice of shifts + scores), data/official/official_aligned.jpg (+ _meta.json)
Check: data/raw/v05/align_check_*.jpg (official edges over the aerial before / after)
"""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = None
OFF = ROOT / "data" / "official"


def feat(a):
    a = a.astype(np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    lum = (R + G + B) // 3
    exg = 2 * G - R - B
    return (np.clip(lum // 32, 0, 7) * 4 + np.digitize(exg, [0, 15, 35])).astype(np.int32)


def mi(a, b, bins=32):
    h, _, _ = np.histogram2d(a.ravel(), b.ravel(), bins=bins, range=[[0, bins], [0, bins]])
    p = h / h.sum()
    px, py = p.sum(1, keepdims=True), p.sum(0, keepdims=True)
    nz = p > 0
    return float((p[nz] * np.log(p[nz] / (px @ py)[nz])).sum())


def main():
    c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, H = c["size"]
    orth = np.asarray(Image.open(ROOT / "web" / "public" / "campus" / "ortho.jpg").convert("RGB"))
    sx = orth.shape[1] / W
    offi = np.asarray(Image.open(OFF / "official_local.jpg").convert("RGB"))
    m = json.loads((OFF / "official_local_meta.json").read_text(encoding="utf-8"))
    q = 1 / m["m_per_px"]

    def crop(img, x0, z0, x1, z1, ox, oz, s):
        a = img[int((z0 - oz) * s):int((z1 - oz) * s), int((x0 - ox) * s):int((x1 - ox) * s)]
        return cv2.resize(a, (int(x1 - x0), int(z1 - z0)), interpolation=cv2.INTER_AREA)

    allp = np.concatenate([np.array(p) for p in c["boundary"]])
    (bx0, bz0), (bx1, bz1) = allp.min(0), allp.max(0)
    xs = np.arange(np.floor(bx0 / 100) * 100, bx1 + 100, 100)
    zs = np.arange(np.floor(bz0 / 100) * 100, bz1 + 100, 100)
    S, HW = 26, 100
    grid = np.full((len(zs), len(xs), 3), np.nan)
    from PIL import ImageDraw
    cm = Image.new("L", (int(W), int(H) + 1), 0)
    for ring in c["boundary"]:
        ImageDraw.Draw(cm).polygon([(x + W / 2, z + H / 2) for x, z in ring], fill=1)
    cm = np.asarray(cm)
    for j, zc in enumerate(zs):
        for i, xc in enumerate(xs):
            x0, z0, x1, z1 = xc - HW, zc - HW, xc + HW, zc + HW
            sub = cm[max(0, int(z0 + H / 2)):max(0, int(z1 + H / 2)), max(0, int(x0 + W / 2)):max(0, int(x1 + W / 2))]
            if sub.size == 0 or sub.mean() < 0.1:
                continue                                   # only windows that cover the campus
            if x0 - S < m["x0"] or z0 - S < m["z0"] or (x1 + S - m["x0"]) * q > offi.shape[1] or (z1 + S - m["z0"]) * q > offi.shape[0]:
                continue
            A = feat(crop(orth, x0, z0, x1, z1, -W / 2, -H / 2, sx))
            if (A % 4 >= 2).mean() < 0.05 and A.std() < 2:
                continue
            res = []
            for dz in range(-S, S + 1, 2):
                for dx in range(-S, S + 1, 2):
                    res.append((mi(A, feat(crop(offi, x0 + dx, z0 + dz, x1 + dx, z1 + dz, m["x0"], m["z0"], q))), dx, dz))
            res.sort(reverse=True)
            v, dx, dz = res[0]
            for ddz in (-1, 0, 1):              # refine to 1 m
                for ddx in (-1, 0, 1):
                    vv = mi(A, feat(crop(offi, x0 + dx + ddx, z0 + dz + ddz, x1 + dx + ddx, z1 + dz + ddz, m["x0"], m["z0"], q)))
                    if vv > v:
                        v, bdx, bdz = vv, dx + ddx, dz + ddz
                        dx, dz = bdx, bdz
            vals = np.array([r[0] for r in res])
            z = (v - vals.mean()) / (vals.std() + 1e-9)
            grid[j, i] = (dx, dz, z)
            print(f"({xc:.0f},{zc:.0f}) shift {dx:+.0f},{dz:+.0f} z={z:.1f}", flush=True)
    # reject weak peaks and outliers, fill from neighbours
    good = (grid[..., 2] >= 2.5)
    med = np.nanmedian(np.where(good[..., None], grid[..., :2], np.nan).reshape(-1, 2), axis=0)
    sh = np.where(good[..., None], grid[..., :2], np.nan)
    for _ in range(6):
        filled = sh.copy()
        for j in range(len(zs)):
            for i in range(len(xs)):
                nb = sh[max(0, j - 1):j + 2, max(0, i - 1):i + 2].reshape(-1, 2)
                nb = nb[~np.isnan(nb[:, 0])]
                if np.isnan(sh[j, i, 0]):
                    if len(nb):
                        filled[j, i] = np.median(nb, axis=0)
                elif len(nb) >= 3 and np.abs(sh[j, i] - np.median(nb, axis=0)).max() > 6:
                    filled[j, i] = np.median(nb, axis=0)     # outlier vs neighbours
        sh = filled
    sh[np.isnan(sh)] = np.nan
    for k in range(2):
        sh[..., k] = np.where(np.isnan(sh[..., k]), med[k], sh[..., k])
    (OFF / "align_shift.json").write_text(json.dumps({
        "note": "official_local pixel for ground point (x, z) is at (x + dx, z + dz); lattice 100 m, windows 200 m, MI registration",
        "xs": xs.tolist(), "zs": zs.tolist(), "dx": sh[..., 0].round(1).tolist(), "dz": sh[..., 1].round(1).tolist(),
        "raw": np.nan_to_num(grid, nan=-99).round(1).tolist(), "median": med.round(1).tolist()}, indent=0), encoding="utf-8")
    print("median shift", med, "good windows", int(good.sum()), "/", int((~np.isnan(grid[..., 0])).sum()))

    # resample the whole official map with the smooth shift field (bilinear over the lattice)
    Hh, Ww = offi.shape[:2]
    gx = m["x0"] + (np.arange(Ww) + 0.5) * m["m_per_px"]
    gz = m["z0"] + (np.arange(Hh) + 0.5) * m["m_per_px"]
    fi = np.clip((gx - xs[0]) / 100, 0, len(xs) - 1)
    fj = np.clip((gz - zs[0]) / 100, 0, len(zs) - 1)
    small_dx = cv2.resize(sh[..., 0].astype(np.float32), (len(xs), len(zs)))
    small_dz = cv2.resize(sh[..., 1].astype(np.float32), (len(xs), len(zs)))
    mapx = cv2.remap(small_dx, np.tile(fi, (Hh, 1)).astype(np.float32), np.repeat(fj[:, None], Ww, 1).astype(np.float32), cv2.INTER_LINEAR)
    mapz = cv2.remap(small_dz, np.tile(fi, (Hh, 1)).astype(np.float32), np.repeat(fj[:, None], Ww, 1).astype(np.float32), cv2.INTER_LINEAR)
    srcx = (np.tile(np.arange(Ww), (Hh, 1)) + mapx * q).astype(np.float32)
    srcz = (np.repeat(np.arange(Hh)[:, None], Ww, 1) + mapz * q).astype(np.float32)
    aligned = cv2.remap(offi, srcx, srcz, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(240, 240, 240))
    Image.fromarray(aligned).save(OFF / "official_aligned.jpg", quality=90)
    (OFF / "official_aligned_meta.json").write_text(json.dumps(dict(m, note="official map re-sampled with align_shift.json: pixel = ground point (x, z) directly")), encoding="utf-8")
    print("wrote official_aligned.jpg")


if __name__ == "__main__":
    main()
