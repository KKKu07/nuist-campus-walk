"""0.5 m ground-material map: the official map (registered to the aerial) for what each surface is, the aerial
land cover where the drawing is hidden (tree sprites, leaning buildings) or blank.

Classes (web/public/campus/ground.png, one byte per pixel; game shader GROUND_LC):
 0 unknown   1 lawn   2 under trees / planting   3 grey stone paving   4 asphalt   5 water   6 track rubber
 7 artificial turf   8 court   9 bare soil   10 building   11 light tiles (white)   12 red brick   13 coloured plaza
 14 dark granite (plaza bands / patterns)
The official drawing leans buildings to the north-west (a point h metres up is drawn ~(0.31 h, 0.63 h) m NW of
its ground position), so the swept footprint of every building is masked before reading the drawing.

Usage: .venv/Scripts/python.exe tools/ground_map.py
Input : data/official/official_aligned.jpg (tools/official_align.py), web/public/campus/landcover.png, campus.json
Output: web/public/campus/ground.png (+ ground_meta.json), data/raw/ground_preview.jpg
"""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = None
OFF = ROOT / "data" / "official"
UNK = 255                        # "fill from the nearest known class" marker (refine step 4)
LEAN = (-0.307, -0.625)          # ground offset per metre of height in the official drawing
PAL = np.array([[0, 0, 0], [110, 170, 80], [40, 95, 45], [178, 176, 170], [70, 70, 75], [60, 120, 200], [200, 80, 60],
                [60, 160, 70], [80, 140, 180], [150, 120, 80], [255, 0, 255], [232, 232, 226], [176, 86, 74], [235, 190, 60],
                [105, 106, 108]] + [[0, 0, 0]] * 241, np.uint8)


def refine(out, c, P, courtcol=None):
    """Clean-up where the geometry is known (细节纠正 2026-11-27): ponds take their exact outline and the blue paint
    the drawing spills around them becomes bank; sport colours outside the 3D pitches / tracks (misregistered paint)
    and track rubber / turf far from any facility go; colour specks under 8 m2 are absorbed by their surroundings;
    class boundaries are smoothed (one-hot blur, argmax) so edges are not 0.5 m staircases."""
    Hh, Ww = out.shape
    UNK = 255

    def poly_mask(polys):
        im = Image.new("L", (Ww, Hh), 0)
        d = ImageDraw.Draw(im)
        for pts in polys:
            d.polygon([P(*p) for p in pts], fill=255)
        return np.asarray(im) > 0

    def ring(mask, px):
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
        return cv2.dilate(mask.astype(np.uint8), k) > 0

    keep = np.isin(out, (0, 10))                 # outside the drawing / building footprints stay as they are
    # 1. water: exact pond / river outlines; blue paint within 12 m of them is bank (filled from the surroundings)
    wat = poly_mask([w["pts"] for w in c["water"]])
    out[np.isin(out, (5,)) & ~wat] = UNK
    out[ring(wat, 24) & ~wat & (out == 8)] = UNK
    out[wat] = 5
    # 2. sports: the 3D facility (sports.js) covers its oriented box; sport paint just outside it is misregistered
    boxes, ovals = [], []
    for s in c["sports"]:
        cx, cz, L, Wd, a = s["obb"]
        ca, sa = math.cos(a), math.sin(a)
        corner = lambda u, v: (cx + u * ca - v * sa, cz + u * sa + v * ca)
        if s["kind"] == "oval":           # IAAF stadium shape (84.39 m straights, outer radius ~46.9 m)
            r, hs = 46.9, 84.39 / 2
            pts = [corner(hs + r * math.cos(t), r * math.sin(t)) for t in np.linspace(-math.pi / 2, math.pi / 2, 24)]
            pts += [corner(-hs + r * math.cos(t), r * math.sin(t)) for t in np.linspace(math.pi / 2, 1.5 * math.pi, 24)]
            ovals.append(pts)
        boxes.append([corner(u, v) for u, v in ((-L / 2 - 1, -Wd / 2 - 1), (L / 2 + 1, -Wd / 2 - 1), (L / 2 + 1, Wd / 2 + 1), (-L / 2 - 1, Wd / 2 + 1))])
    fac = poly_mask(boxes)
    oval = poly_mask(ovals)
    sport = np.isin(out, (6, 7, 8))
    out[sport & ring(fac, 12) & ~fac] = UNK                          # 6 m fringe
    out[np.isin(out, (6, 7)) & ~ring(fac, 60)] = UNK                 # rubber / turf 30 m+ from any facility
    out[oval] = 6                                                    # under the 3D track: rubber (only shows at the very edge)
    # 2b. (地表观感) paint that belongs to buildings, not the ground: the drawing's glass (blue -> "court"), white walls
    #     (-> light tiles) and red stair-tower caps (-> brick) spill just past the leaning-building mask. Pieces of
    #     those classes lying mostly within 8 m of a footprint go; court paint away from every 3D facility goes too.
    bld = out == 10
    nearb = ring(bld, 16) & ~bld
    dbld = cv2.distanceTransform((~bld).astype(np.uint8), cv2.DIST_L2, 3)
    away = ~ring(fac, 8)
    for k in (8, 11, 12):
        n, lab, st, _ = cv2.connectedComponentsWithStats((out == k).astype(np.uint8), connectivity=8)
        if n <= 1:
            continue
        tot = st[:, cv2.CC_STAT_AREA]
        inn = np.bincount(lab[nearb], minlength=n)
        bad = (inn > 0.6 * tot) & (tot < 2400)                      # < 600 m2, mostly hugging a building
        # compact blobs (a stair-tower cap / roof leaning 10-20 m off its footprint, often with dark detailing holes),
        # not strips: within 20 m of a building, < 150 m2, a 5-20 m box they fill; paths are narrower or longer
        sel = lab > 0
        dmin = np.full(n, 1e9, np.float32)
        np.minimum.at(dmin, lab[sel], dbld[sel])
        bw, bh = st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT]
        fill = tot / np.maximum(1, bw * bh)
        bad |= (dmin < 40) & (tot < 600) & (np.minimum(bw, bh) >= 10) & (np.maximum(bw, bh) <= 40) & (fill > 0.45)
        if k == 8:
            far = np.bincount(lab[away], minlength=n)
            bad |= (far > 0.5 * tot) & (tot < 1600)                  # small court paint with no court there
            if courtcol is not None:                                 # (地表观感) court paint away from every 3D facility
                cc = np.bincount(lab[courtcol], minlength=n)         # where the orthophoto shows no court colour (blue /
                bad |= (far > 0.5 * tot) & (cc < 0.2 * tot)          # teal / green / red): glass-facade reflections,
                                                                     # dust nets, a dark ditch (气象谷, 西苑 south) -> ground
        bad[0] = False
        out[bad[lab] & ~fac] = UNK
    # 2c. (地表观感) asphalt away from the carriageways is the drawing's shade on paving, dark granite bands or yard
    #     concrete, not road: small pieces inside paving -> dark granite (14), the rest -> grey paving (3). Parking
    #     lots (official 停车场 markers) and big yards (> 1500 m2) stay asphalt.
    cor = Image.new("L", (Ww, Hh), 0)
    dcor = ImageDraw.Draw(cor)
    NONCAR = {"footway", "path", "steps", "cycleway", "track", "pedestrian"}
    for r in c["roads"]:
        if r.get("kind") in NONCAR or r["w"] < 3.5:
            continue
        sw = r.get("sw", 2.4 if r["w"] >= 7 else 0) or 0
        dcor.line([P(*p) for p in r["pts"]], fill=255, width=max(3, int((r["w"] + 2 * sw + 3) / 0.5)), joint="curve")
    cor = np.asarray(cor) > 0
    off = (out == 4) & ~cor
    n, lab, st, _ = cv2.connectedComponentsWithStats(off.astype(np.uint8), connectivity=8)
    if n > 1:
        tot = st[:, cv2.CC_STAT_AREA]
        keep4 = tot > 6000
        for mk in c.get("markers", []):
            if mk.get("cat") == "停车场":
                px, pz = P(mk["x"], mk["z"])
                y0, x0 = int(pz) - 20, int(px) - 20
                ids = np.unique(lab[max(0, y0):y0 + 41, max(0, x0):x0 + 41])
                keep4[ids] = True
        paved = np.isin(out, (3, 11, 12, 13)).astype(np.uint8)
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        rim = cv2.dilate(off.astype(np.uint8), k3) > 0
        rim &= ~off
        # rim pixels take the (max) label of a component within 3 px: approximate, good enough for a vote
        rl =cv2.dilate(lab.astype(np.float32), k3).astype(np.int32)
        rim_tot = np.bincount(rl[rim], minlength=n)
        rim_pav = np.bincount(rl[rim & (paved > 0)], minlength=n)
        dark = (tot < 400) & (rim_pav > 0.6 * np.maximum(rim_tot, 1))
        conv = np.where(keep4, 0, np.where(dark, 14, 3)).astype(np.uint8)
        conv[0] = 0
        sel = (lab > 0) & (conv[lab] > 0)
        out[sel] = conv[lab][sel]
    # 2d. (地表观感) paving islands: a paved piece under 60 m2 that lawn / planting surrounds on > 85 % of its rim
    #     is a fragment of a path the tree sprites hide (or stray grey paint); a lone grey blob in a lawn reads wrong,
    #     so it becomes the surrounding green. Pieces joined to other paving keep (they lead somewhere).
    pav = np.isin(out, (3, 11, 12, 13, 14))
    green = np.isin(out, (1, 2))
    n, lab, st, _ = cv2.connectedComponentsWithStats(pav.astype(np.uint8), connectivity=8)
    if n > 1:
        k3 = np.ones((3, 3), np.uint8)
        rl = cv2.dilate(lab.astype(np.float32), k3).astype(np.int32)
        rim = (rl > 0) & ~pav
        rt = np.bincount(rl[rim], minlength=n)
        rg = np.bincount(rl[rim & green], minlength=n)
        isl = (st[:, cv2.CC_STAT_AREA] < 240) & (rg > 0.85 * np.maximum(rt, 1))
        isl[0] = False
        out[isl[lab]] = UNK
    # 3. specks: components under 8 m2 (32 px) of the paved / planted classes
    for k in (1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14):
        n, lab, st, _ = cv2.connectedComponentsWithStats((out == k).astype(np.uint8), connectivity=8)
        small = np.where(st[:, cv2.CC_STAT_AREA] < 32)[0]
        small = small[small > 0]
        if len(small):
            out[np.isin(lab, small)] = UNK
    # 4. fill the unknowns with the nearest known class
    unk = out == UNK
    if unk.any():
        _, lab = cv2.distanceTransformWithLabels(unk.astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
        known = ~unk
        lut = np.zeros(lab.max() + 1, np.uint8)
        lut[lab[known]] = out[known]
        out[unk] = lut[lab[unk]]
    # 5. smooth boundaries between the open-ground classes (buildings, water, blank stay exact)
    fixed = keep | wat | (out == 0)
    best = np.full(out.shape, -1.0, np.float32)
    sm = out.copy()
    for k in np.unique(out[~fixed]):
        f = cv2.GaussianBlur((out == k).astype(np.float32), (0, 0), 0.9)
        upd = f > best
        best[upd] = f[upd]
        sm[upd] = k
    out[~fixed] = sm[~fixed]
    return out


def main():
    c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, H = c["size"]
    o = np.asarray(Image.open(OFF / "official_aligned.jpg").convert("RGB")).astype(np.int16)
    m = json.loads((OFF / "official_aligned_meta.json").read_text(encoding="utf-8"))
    mpp, X0, Z0 = m["m_per_px"], m["x0"], m["z0"]
    Hh, Ww = o.shape[:2]
    R, G, B = o[..., 0], o[..., 1], o[..., 2]
    mx, mn = o.max(2), o.min(2)
    lum = (R + G + B) / 3
    sat = mx - mn
    exg = 2 * G - R - B

    cls = np.zeros((Hh, Ww), np.uint8)
    blank = (lum > 236) & (sat < 10)                                     # paper outside the drawing
    lawn = (exg > 45) & (G > 120) & (lum > 95) & (lum < 190)
    tree = (exg > 18) & ~lawn                                            # darker / shaded greens: tree sprites
    autumn = (R > 170) & (B < 80) & (R - B > 110)                        # orange / red tree sprites
    light = (sat < 18) & (lum >= 196) & ~blank
    stone = (sat < 22) & (lum >= 128) & (lum < 196)
    asph = (sat < 20) & (lum >= 40) & (lum < 128)
    brick = (R - G > 45) & (np.abs(G - B) < 30) & (R > 120) & (R < 215) & (B > 55) & ~autumn
    water = (B > R + 30) & (B > G + 2) & (lum < 175)
    teal = (G > R + 25) & (B > R + 25) & (np.abs(G - B) < 45)            # courts / blue rubber
    plaza = (R > 200) & (G > 150) & (B < 110) & ~autumn                  # yellow plaza paint
    cls[lawn] = 1
    cls[tree | autumn] = 2
    cls[stone] = 3
    cls[light] = 11
    cls[asph] = 4
    cls[brick] = 12
    cls[water] = 5
    cls[teal] = 8
    cls[plaza] = 13
    cls[blank] = 0

    # mask the official drawing where buildings stand or lean over the ground
    def P(x, z):
        return ((x - X0) / mpp, (z - Z0) / mpp)
    lean = Image.new("L", (Ww, Hh), 0)
    dl = ImageDraw.Draw(lean)
    foot = Image.new("L", (Ww, Hh), 0)
    df = ImageDraw.Draw(foot)
    for b in c["buildings"]:
        h = b["h"] * 1.25 + 2
        pts = b["pts"]
        df.polygon([P(*p) for p in pts], fill=255)
        for t in np.linspace(0, 1, 6):
            dl.polygon([P(x + LEAN[0] * h * t, z + LEAN[1] * h * t) for x, z in pts], fill=255)
    lean = np.asarray(lean) > 0
    foot = np.asarray(foot) > 0

    # aerial land cover (1 m) resampled to this grid as the fallback
    lc = np.asarray(Image.open(ROOT / "web" / "public" / "campus" / "landcover.png"))
    gx = X0 + (np.arange(Ww) + 0.5) * mpp
    gz = Z0 + (np.arange(Hh) + 0.5) * mpp
    li = np.clip((gx + W / 2).astype(int), 0, lc.shape[1] - 1)
    lj = np.clip((gz + H / 2).astype(int), 0, lc.shape[0] - 1)
    lcg = lc[lj][:, li]
    hidden = lean | (cls == 2) | (cls == 0)
    out = cls.copy()
    # hidden ground (behind leaning buildings, under tree sprites, blank paper) is filled from the nearest
    # VISIBLE official surface in refine() step 4 (lawn / path / plaza continue under the obstruction),
    # not from the winter aerial, which turned every building's surroundings into grey patches.
    # The aerial still decides two things there: real tree canopy (-> under trees) and asphalt.
    # under tree sprites (not behind a building): lawn, canopy where the aerial shows canopy, paving / asphalt if
    # the aerial sees paving there
    tr = (cls == 2) & ~lean
    out[tr] = 1
    out[tr & (lcg == 2)] = 2
    ap = tr & np.isin(lcg, (3, 4))
    # (地表观感) aerial "paving" under a tree sprite is a path only where it continues a visible official path or
    # plaza; isolated pieces inside a lawn are the winter aerial's dormant grass and stay lawn
    vis = np.isin(cls, (3, 4, 11, 12, 13)) & ~tr & ~lean
    n, lab, _, _ = cv2.connectedComponentsWithStats(ap.astype(np.uint8), connectivity=8)
    if n > 1:
        touch = np.zeros(n, bool)
        touch[np.unique(lab[cv2.dilate(vis.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0])] = True
        touch[0] = False
        ap &= touch[lab]
    out[ap] = lcg[ap]
    # behind leaning buildings and on blank paper: nearest visible surface (refine step 4); asphalt from the aerial
    hb = lean | (cls == 0)
    out[hb] = UNK
    out[hb & (lcg == 4)] = 4
    out[foot] = 10
    # the official drawing only covers the campus: outside (beyond 15 m) fall back to the aerial land cover;
    # blue paint is water only inside real water bodies, otherwise it is a court / rubber surface
    camp = Image.new("L", (Ww, Hh), 0)
    dc = ImageDraw.Draw(camp)
    for ring in c["boundary"]:
        dc.polygon([P(*p) for p in ring], fill=255)
    camp = cv2.dilate(np.asarray(camp), np.ones((61, 61), np.uint8)) > 0
    wat = Image.new("L", (Ww, Hh), 0)
    dw = ImageDraw.Draw(wat)
    for w in c["water"]:
        dw.polygon([P(*p) for p in w["pts"]], fill=255)
    wat = cv2.dilate(np.asarray(wat), np.ones((9, 9), np.uint8)) > 0
    out[(out == 5) & ~wat] = 8
    out[~camp] = 0
    # tidy: majority filter 3x3 on the paved classes to remove speckle
    out = cv2.medianBlur(out, 3)
    # manual patches (data/manual/ground_overrides.json), e.g. a construction site the drawing paints as a pond
    gov = ROOT / "data" / "manual" / "ground_overrides.json"
    if gov.exists():
        for pa in json.loads(gov.read_text(encoding="utf-8")).get("patches", []):
            pm = Image.new("L", (Ww, Hh), 0)
            ImageDraw.Draw(pm).polygon([P(*p) for p in pa["pts"]], fill=255)
            out[(np.asarray(pm) > 0) & ~foot] = pa["cls"]
    # orthophoto court colours on this grid (blue / teal / green / red sports surfaces), for refine's court check
    o = np.asarray(Image.open(ROOT / "web" / "public" / "campus" / "ortho.jpg").convert("RGB")).astype(np.float32)   # PIL: non-ASCII path
    osx, osz = o.shape[1] / W, o.shape[0] / H
    MX, MZ = np.meshgrid(((gx + W / 2) * osx).astype(np.float32), ((gz + H / 2) * osz).astype(np.float32))
    oc = cv2.remap(o, MX, MZ, cv2.INTER_LINEAR)
    oR, oG, oB = oc[..., 0], oc[..., 1], oc[..., 2]
    courtcol = (((oB - oR > 25) & (oB > oG - 15)) | ((oG - oR > 25) & (oG - oB > 5) & (oG > 110))
                | ((oR - oG > 40) & (oR - oB > 30) & (oR > 150)))
    del o, oc, MX, MZ
    out = refine(out, c, P, courtcol)
    Image.fromarray(out, "L").save(ROOT / "web" / "public" / "campus" / "ground.png", optimize=True)
    (ROOT / "web" / "public" / "campus" / "ground_meta.json").write_text(json.dumps(
        {"x0": X0, "z0": Z0, "m_per_px": mpp, "size": [Ww, Hh], "classes": __doc__.split("Classes")[1].split("The official")[0].strip()}, ensure_ascii=False), encoding="utf-8")
    prev = PAL[out]
    Image.fromarray(prev).resize((Ww // 3, Hh // 3), Image.NEAREST).save(ROOT / "data" / "raw" / "ground_preview.jpg", quality=85)
    tot = (out > 0).sum()
    print({k: round(float((out == k).sum() / tot * 100), 1) for k in range(15) if (out == k).any()})


if __name__ == "__main__":
    main()
