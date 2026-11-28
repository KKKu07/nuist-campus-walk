"""WP1/WP2/WP4: land-cover map, measured road widths and individual trees from our own aerial data.

Inputs : web/public/campus/ortho.jpg (our mosaic + Esri outside), data/raw/ortho_esri.jpg (autumn colours),
         data/raw/dsm.npy (1 m DSM from the drone reconstruction), web/public/campus/campus.json, data/raw/osm.json
Outputs: data/manual/road_widths.json   {osm way id: {w, median, samples}}
         web/public/campus/landcover.png (1 m, one class per pixel; see CLASSES)
         data/manual/trees_v2.json       [[x, z, height, crown_radius, species], ...]
         data/raw/landcover_preview.jpg, data/raw/trees_preview.jpg

Usage: .venv/Scripts/python.exe tools/landcover.py   (then run tools/build_campus.py)
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_campus import to_local  # noqa: E402  (same local frame)

CLASSES = {0: "unknown", 1: "grass", 2: "canopy", 3: "paving", 4: "asphalt", 5: "water", 6: "track",
           7: "turf", 8: "court", 9: "soil", 10: "building"}
PREVIEW = {0: (0, 0, 0), 1: (120, 190, 90), 2: (30, 110, 40), 3: (200, 195, 185), 4: (70, 72, 78), 5: (60, 120, 200),
           6: (200, 70, 60), 7: (60, 170, 90), 8: (90, 140, 200), 9: (170, 130, 80), 10: (240, 240, 240)}
VEHICULAR = {"primary", "secondary", "tertiary", "trunk", "residential", "unclassified", "service", "living_street"}

campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
W, D = campus["size"]
NX, NZ = int(W), int(D)


def grid(x, z):
    return (x + W / 2), (z + D / 2)


def load_rgb(path):
    im = Image.open(path).convert("RGB").resize((NX, NZ), Image.Resampling.BILINEAR)
    return np.asarray(im).astype(np.float32)


def poly_mask(polys, value=1, shape=(NZ, NX), thick=None):
    m = np.zeros(shape, np.uint8)
    for pts in polys:
        arr = np.round(np.array([grid(x, z) for x, z in pts], np.float32)).astype(np.int32)
        if thick:
            cv2.polylines(m, [arr], False, value, thickness=thick)
        elif len(arr) >= 3:
            cv2.fillPoly(m, [arr], value)
    return m


def main():
    rgb = load_rgb(ROOT / "web" / "public" / "campus" / "ortho.jpg")
    autumn = load_rgb(ROOT / "data" / "raw" / "ortho_esri.jpg")
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(2), rgb.min(2)
    sat, lum = mx - mn, rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    exg = 2 * g - r - b
    dsm = np.load(ROOT / "data" / "raw" / "dsm.npy")[:NZ, :NX]
    have = ~np.isnan(dsm)
    hi = np.where(have, dsm, 1e4).astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
    dtm = cv2.dilate(cv2.erode(hi, k), k)
    dtm[dtm > 5e3] = np.nan
    dtm = cv2.GaussianBlur(np.where(np.isnan(dtm), np.nanmedian(dtm), dtm).astype(np.float32), (0, 0), 12)
    ndsm = np.where(have, dsm - dtm, np.nan)

    bmask = poly_mask([bd["pts"] for bd in campus["buildings"]])
    wmask = poly_mask([w["pts"] for w in campus["water"]])
    tall = np.nan_to_num(ndsm, nan=0) > 2.5

    # ---------------- WP2: measured road widths (cross-sections on the aerial photo)
    roadlike = ((sat < 22) & (lum > 60) & (lum < 170) & (exg < 6) & (bmask == 0) & ~(tall & (exg > 0))).astype(np.uint8)
    occluded = (tall & (exg > 10)).astype(np.uint8)          # tree canopy over the road: unknown, not "not road"
    widths = {}
    for rd in campus["roads"]:
        if rd["kind"] not in VEHICULAR and rd["kind"] != "pedestrian":
            continue
        samples, medians = [], []
        pts = rd["pts"]
        for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, z1 - z0)
            if L < 4:
                continue
            dx, dz = (x1 - x0) / L, (z1 - z0) / L
            nx, nz = -dz, dx
            for t in np.arange(2, L - 2, 8):
                cx, cz = x0 + dx * t, z0 + dz * t
                prof = []
                for o in np.arange(-30, 30.5, 1.0):
                    gx, gz = grid(cx + nx * o, cz + nz * o)
                    i, j = int(gx), int(gz)
                    if not (0 <= i < NX and 0 <= j < NZ):
                        prof.append(0); continue
                    prof.append(2 if occluded[j, i] else int(roadlike[j, i]))
                prof = np.array(prof)
                c = 30
                runs, cur = [], None          # road runs, letting occluded cells bridge gaps up to 6 m
                for idx, v in enumerate(prof):
                    if v == 1 or (v == 2 and cur is not None):
                        cur = [idx, idx] if cur is None else [cur[0], idx]
                    elif cur is not None:
                        runs.append(cur); cur = None
                if cur:
                    runs.append(cur)
                runs = [ru for ru in runs if ru[1] - ru[0] >= 2]
                if not runs:
                    continue
                center = [ru for ru in runs if ru[0] <= c <= ru[1]]
                if center:
                    lo, hi_ = center[0]
                    samples.append(hi_ - lo + 1)
                else:
                    left = [ru for ru in runs if ru[1] < c and c - ru[1] <= 9]
                    right = [ru for ru in runs if ru[0] > c and ru[0] - c <= 9]
                    if left and right:
                        lo, hi_ = left[-1][0], right[0][1]
                        gap = right[0][0] - left[-1][1] - 1
                        samples.append(hi_ - lo + 1)
                        medians.append(gap)
        if len(samples) >= 3:
            w = float(np.percentile(samples, 50))
            med = float(np.median(medians)) if len(medians) >= max(3, 0.4 * len(samples)) else 0.0
            w = max(0.6 * rd["w"], min(w, 2.2 * rd["w"], 40.0))
            if med > w * 0.5:
                med = 0.0
            widths[str(rd["id"])] = dict(w=round(w, 1), median=round(med, 1), samples=len(samples), osm=rd["w"])
    (ROOT / "data" / "manual" / "road_widths.json").write_text(json.dumps(widths, indent=0), encoding="utf-8")

    # ---------------- WP1: land cover
    cls = np.full((NZ, NX), 3, np.uint8)                       # default: paving / hard ground
    cls[(sat < 30) & (lum < 105) & (exg > -2)] = 1   # shadowed lawns
    cls[(r > g + 8) & (g > b + 4) & (sat >= 22) & (lum > 70)] = 9
    veg = (exg > 16) & (g > 45)
    rough_g = np.sqrt(np.maximum(cv2.blur(g * g, (5, 5)) - cv2.blur(g, (5, 5)) ** 2, 0))
    canopy = veg & (np.where(have, tall, rough_g > 10))
    cls[veg] = 1
    cls[canopy] = 2
    # roads drawn with their measured width (vehicular = asphalt, footways = paving)
    for rd in campus["roads"]:
        wv = widths.get(str(rd["id"]), {}).get("w", rd["w"])
        arr = np.round(np.array([grid(x, z) for x, z in rd["pts"]], np.float32)).astype(np.int32)
        cv2.polylines(cls, [arr], False, 4 if rd["kind"] in VEHICULAR else 3, thickness=max(1, int(round(wv))))
    # sports surfaces inside OSM pitch / track polygons
    osm = json.loads((ROOT / "data" / "raw" / "osm.json").read_text(encoding="utf-8"))
    sports = []
    for e in osm["elements"]:
        t = e.get("tags", {})
        if t.get("leisure") in ("pitch", "track") and e["type"] == "way" and "geometry" in e:
            sports.append((t.get("leisure"), t.get("sport", ""), [to_local(p["lat"], p["lon"]) for p in e["geometry"]]))
    red = (r - np.maximum(g, b) > 35) & (r > 120)
    sm = poly_mask([s[2] for s in sports])
    inside = sm > 0
    cls[inside & red] = 6
    cls[inside & veg] = 7
    beige = (r > g + 4) & (g > b + 4) & (sat < 70) & (lum > 120)
    cls[inside & ~red & ~veg & ~beige] = 8
    cls[inside & beige & ~red] = 9           # natural / sand infields
    cls[red & (sat > 60) & (lum > 80)] = 6                     # unlisted red rubber tracks
    cls[wmask > 0] = 5
    cls[bmask > 0] = 10
    cls = cv2.medianBlur(cv2.medianBlur(cls, 5), 3)
    Image.fromarray(cls, "L").save(ROOT / "web" / "public" / "campus" / "landcover.png", optimize=True)
    prev = np.zeros((NZ, NX, 3), np.uint8)
    for kk, col in PREVIEW.items():
        prev[cls == kk] = col
    Image.fromarray(prev).resize((NX // 2, NZ // 2)).save(ROOT / "data" / "raw" / "landcover_preview.jpg", quality=85)

    # ---------------- WP4: individual trees from DSM local maxima (fallback: texture sampling)
    road_mask = np.isin(cls, (4,)) & ~canopy
    h_s = cv2.GaussianBlur(np.nan_to_num(ndsm, nan=0).astype(np.float32), (0, 0), 1.2)
    peak = (h_s == cv2.dilate(h_s, np.ones((7, 7), np.uint8))) & (h_s > 3) & (h_s < 32) & canopy & (bmask == 0) & (wmask == 0)
    ys, xs = np.nonzero(peak)
    trees = []
    for j, i in zip(ys, xs):
        h = float(h_s[j, i])
        x, z = i + 0.5 - W / 2, j + 0.5 - D / 2
        ar, ag, ab = autumn[j, i]
        if ar > 140 and ag > 120 and ab < 95 and ar - ag < 45:
            sp = "ginkgo"
        elif ar > ag + 22 and ar > ab + 30:
            sp = "redleaf"
        elif h > 9 and rough_g[j, i] < 9:
            sp = "conifer"
        else:
            sp = "broad"
        trees.append([round(x, 1), round(z, 1), round(h, 1), round(min(7.0, max(1.8, 0.28 * h + 1.0)), 1), sp])
    # outside the reconstruction: green, rough texture, sampled every 6 m
    step = 6
    for j in range(0, NZ, step):
        for i in range(0, NX, step):
            if have[j, i] or not canopy[j, i] or road_mask[j, i] or bmask[j, i] or wmask[j, i]:
                continue
            trees.append([round(i - W / 2 + (j * 7 % step), 1), round(j - D / 2 + (i * 3 % step), 1), 9.0, 3.2,
                          "conifer" if (i + j) % 5 == 0 else "broad"])
    # trunks never stand on a carriageway: push them to the nearest road edge
    for tr in trees:
        i, j = int(tr[0] + W / 2), int(tr[1] + D / 2)
        if 0 <= i < NX and 0 <= j < NZ and cls[j, i] == 4:
            for rad in range(1, 16):
                hit = None
                for a in np.linspace(0, 2 * math.pi, 16, endpoint=False):
                    ii, jj = int(i + math.cos(a) * rad), int(j + math.sin(a) * rad)
                    if 0 <= ii < NX and 0 <= jj < NZ and cls[jj, ii] not in (4, 10, 5):
                        hit = (ii, jj); break
                if hit:
                    tr[0], tr[1] = round(hit[0] - W / 2 + 0.5, 1), round(hit[1] - D / 2 + 0.5, 1)
                    break
    (ROOT / "data" / "manual" / "trees_v2.json").write_text(json.dumps(trees), encoding="utf-8")
    tp = prev.copy()
    for x, z, h, rr, sp in trees:
        col = {"ginkgo": (255, 220, 0), "redleaf": (230, 90, 40), "conifer": (0, 80, 60), "broad": (40, 200, 60)}[sp]
        cv2.circle(tp, (int(x + W / 2), int(z + D / 2)), max(1, int(rr / 2)), col, -1)
    Image.fromarray(tp).resize((NX // 2, NZ // 2)).save(ROOT / "data" / "raw" / "trees_preview.jpg", quality=85)
    from collections import Counter
    print(f"road widths measured: {len(widths)} (with median: {sum(1 for v in widths.values() if v['median'] > 0)})")
    print("land cover share:", {CLASSES[kk]: round(float((cls == kk).mean()) * 100, 1) for kk in CLASSES if (cls == kk).any()})
    print(f"trees: {len(trees)}", Counter(t[4] for t in trees))
    big = sorted(widths.items(), key=lambda kv: -kv[1]["w"])[:8]
    names = {str(rd["id"]): rd.get("name") or rd["kind"] for rd in campus["roads"]}
    print("widest:", [(names[k], v["w"], v["median"]) for k, v in big])


if __name__ == "__main__":
    main()
