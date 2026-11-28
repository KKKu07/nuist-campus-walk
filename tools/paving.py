"""Trace footpaths, plazas and other paved ground from the 0.5 m aerial ortho into polygons.

The winter aerial shows paving clearly where it is not under trees: grey / white stone and tiles (low
saturation), red permeable brick (red hue, low green-blue difference). Dormant brown lawn and bare soil are
yellowish (green well above blue) and are left out; building, road (carriageway + sidewalk), water and
sports areas are masked because they are modelled separately. Shadowed paving (dark, neutral) counts as
paving. The mask is cleaned (open/close, small blobs and holes removed), vectorised and simplified to 0.5 m.

Usage: .venv/Scripts/python.exe tools/paving.py [x0 z0 x1 z1]      (default: whole campus boundary box)
Output: web/public/campus/paving.json  {"polys": [{"c": "grey"|"red", "pts": [[x,z]...], "holes": [[[x,z]...]]}]}
        data/raw/paving_preview.jpg (aerial with traced outlines; for a box: data/raw/paving_preview_box.jpg)
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = None
MPP = 0.5


def main():
    c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, H = c["size"]
    if len(sys.argv) == 5:
        x0, z0, x1, z1 = map(float, sys.argv[1:5])
    else:
        allp = np.concatenate([np.array(p) for p in c["boundary"]])
        (x0, z0), (x1, z1) = allp.min(0) - 10, allp.max(0) + 10
    nx, nz = int((x1 - x0) / MPP), int((z1 - z0) / MPP)
    orth = Image.open(ROOT / "web" / "public" / "campus" / "ortho.jpg")
    sx = orth.size[0] / W
    rgb = np.asarray(orth.crop((int((x0 + W / 2) * sx), int((z0 + H / 2) * sx), int((x1 + W / 2) * sx), int((z1 + H / 2) * sx)))
                     .resize((nx, nz), Image.BILINEAR).convert("RGB")).astype(np.int16)
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(2), rgb.min(2)
    lum = (R + G + B) / 3
    exg = 2 * G - R - B
    grey = ((mx - mn) < 30) & (lum > 100) & (lum < 240) & (exg < 8) & ~((G - B) > 14)
    shadow = ((mx - mn) < 22) & (lum >= 45) & (lum <= 100) & (exg < 6)
    red = ((R - G) > 18) & ((G - B) < 16) & (R > 105) & (exg < 0)

    # masks of everything modelled elsewhere
    def P(x, z):
        return ((x - x0) / MPP, (z - z0) / MPP)
    other = Image.new("L", (nx, nz), 0)
    d = ImageDraw.Draw(other)
    for b in c["buildings"]:
        d.polygon([P(*p) for p in b["pts"]], fill=255)
    for w in c["water"]:
        d.polygon([P(*p) for p in w["pts"]], fill=255)
    for r in c["roads"]:
        if r["kind"] in ("footway", "path", "steps", "cycleway", "pedestrian", "track") or r["w"] < 3.5:
            continue
        hw = r["w"] / 2 + r.get("sw", 0) + 0.3
        for (ax, az), (bx, bz) in zip(r["pts"], r["pts"][1:]):
            L = math.hypot(bx - ax, bz - az) or 1
            ux, uz = -(bz - az) / L * hw, (bx - ax) / L * hw
            d.polygon([P(ax + ux, az + uz), P(bx + ux, bz + uz), P(bx - ux, bz - uz), P(ax - ux, az - uz)], fill=255)
            d.ellipse([P(ax - hw, az - hw), P(ax + hw, az + hw)], fill=255)
    for s in c["sports"]:
        cx, cz, L, Wd, a = s["obb"]
        ca, sa = math.cos(a), math.sin(a)
        cs = [(cx + u * ca - v * sa, cz + u * sa + v * ca) for u, v in ((-L / 2, -Wd / 2), (L / 2, -Wd / 2), (L / 2, Wd / 2), (-L / 2, Wd / 2))]
        d.polygon([P(*p) for p in cs], fill=255)
    other = np.asarray(other) > 0
    inside = Image.new("L", (nx, nz), 0)
    di = ImageDraw.Draw(inside)
    for ring in c["boundary"]:
        di.polygon([P(*p) for p in ring], fill=255)
    inside = np.asarray(inside) > 0

    pave = (grey | shadow | red) & ~other & inside
    k3 = np.ones((3, 3), np.uint8)
    m = cv2.morphologyEx(pave.astype(np.uint8), cv2.MORPH_OPEN, k3)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m[other] = 0
    # drop specks (< 8 m2) and fill small holes (< 6 m2)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 8 / (MPP * MPP)
    m = keep[lab].astype(np.uint8)
    inv = (1 - m).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inv, 4)
    small = np.zeros(n, bool)
    small[1:] = st[1:, cv2.CC_STAT_AREA] < 6 / (MPP * MPP)
    m[small[lab] & ~other] = 1

    redm = cv2.morphologyEx((red & (m > 0)).astype(np.uint8), cv2.MORPH_CLOSE, k3)
    contours, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    polys = []
    to_local = lambda q: [round(x0 + (q[0] + 0.5) * MPP, 2), round(z0 + (q[1] + 0.5) * MPP, 2)]
    if hier is not None:
        hier = hier[0]
        for i, cnt in enumerate(contours):
            if hier[i][3] != -1:
                continue                                   # holes are attached to their parent below
            ap = cv2.approxPolyDP(cnt, 1.0, True).reshape(-1, 2)
            if len(ap) < 3 or cv2.contourArea(cnt) < 8 / (MPP * MPP):
                continue
            holes = []
            j = hier[i][2]
            while j != -1:
                hp = cv2.approxPolyDP(contours[j], 1.0, True).reshape(-1, 2)
                if len(hp) >= 3 and cv2.contourArea(contours[j]) >= 6 / (MPP * MPP):
                    holes.append([to_local(q) for q in hp])
                j = hier[j][0]
            mask1 = np.zeros_like(m)
            cv2.drawContours(mask1, [cnt], -1, 1, -1)
            area = mask1.sum()
            col = "red" if redm[mask1 > 0].sum() > 0.45 * area else "grey"
            polys.append({"c": col, "pts": [to_local(q) for q in ap], "holes": holes})
    full = len(sys.argv) != 5
    out = {"source": "tools/paving.py from the 0.5 m aerial", "polys": polys}
    if full:
        (ROOT / "web" / "public" / "campus" / "paving.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    # preview
    prev = Image.fromarray(rgb.astype(np.uint8)).convert("RGB")
    dp = ImageDraw.Draw(prev)
    for p in polys:
        q = [((x - x0) / MPP, (z - z0) / MPP) for x, z in p["pts"]]
        dp.line(q + [q[0]], fill=(255, 0, 0) if p["c"] == "red" else (0, 255, 255), width=1)
        for h in p["holes"]:
            qh = [((x - x0) / MPP, (z - z0) / MPP) for x, z in h]
            dp.line(qh + [qh[0]], fill=(255, 255, 0), width=1)
    name = "paving_preview.jpg" if full else "paving_preview_box.jpg"
    if full:
        prev = prev.resize((prev.size[0] // 2, prev.size[1] // 2))
    prev.save(ROOT / "data" / "raw" / name, quality=85)
    area_m2 = sum(cv2.contourArea(np.array([[(x - x0) / MPP, (z - z0) / MPP] for x, z in p["pts"]], np.float32)) for p in polys) * MPP * MPP
    print(f"{len(polys)} paved polygons ({sum(1 for p in polys if p['c'] == 'red')} red), ~{area_m2 / 1e4:.1f} ha, "
          f"{sum(len(p['pts']) + sum(len(h) for h in p['holes']) for p in polys)} vertices")


if __name__ == "__main__":
    main()
