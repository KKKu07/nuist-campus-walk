"""Campus terrain (地形, 2026-11-27): the 30 m SRTM (terrain_srtm.json, from tools/fetch_terrain.py) has metre-scale
fake bumps and pits inside the campus (the 尚贤楼-老校门 lawn dipped ~3 m, 晖园13 stood in a 7 m pit, 37 campus
buildings had > 4 m of ground difference under their footprint). The campus is flat ground in reality, 东苑 lower
than 中苑, with a ramp between them across the 盘城新街 corridor.

Per campus part (campus.json boundary rings: 0 = 西苑 + 中苑, 1 = 东苑, 2 = the outlying plot):
  1. prior: that part's SRTM smoothed at 250 m (normalised Gaussian): the regional level, no local bumps;
  2. local ground control points (data/source/ground_ctrl.json: building bases, [name, x, z, ground m], local only,
     not in git) pull it to the measured level: points > 2.5 m off the median of their neighbours within 150 m
     (basements, podiums) are dropped, the residuals are interpolated at 350 m then 110 m (Gaussian-weighted, the
     correction fading away from the points).
西苑 and 中苑 share ring 0 but sit at different levels (the control points: 西苑 ~16-20 m, 中苑 ~22-27 m); the
step is across the lake between them. Ring 0 is fitted as two surfaces, split along WEST_SPLIT (the lake's centre
line, x as a function of z), each from its own side's control points, blended over WEST_C +- WEST_L m;
WEST_DELTA shifts 西苑 as a whole (0 = as measured; the user has not yet confirmed that 西苑 is low).
Between 中苑 and 东苑 the two surfaces blend along the cross-corridor coordinate e = (d0 - d1) / 2 (0 on the corridor
midline) with a smoothstep centred at RAMP_C, +-RAMP_L m. Outside the campus the SRTM stays, blended in from 10 to
110 m beyond the boundary. Without the control file the prior alone is used (smoothed SRTM).
The drone DSM (data/raw/dsm.npy) is not used for levels: its large-scale shape bends (SfM doming / tilt).

Usage : .venv/Scripts/python.exe tools/campus_terrain.py
Input : data/raw/terrain_srtm.json (copied once from web/public/campus/terrain.json), campus.json, data/source/ground_ctrl.json
Output: web/public/campus/terrain.json (same format: nx, nz, size, base, h = decimetres above base, row-major north->south)
"""
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "terrain_srtm.json"
DST = ROOT / "web" / "public" / "campus" / "terrain.json"
CTRL = ROOT / "data" / "source" / "ground_ctrl.json"
PRIOR, SCALES, LAMBDA = 250.0, (350.0, 110.0), (0.15, 0.6)
OUTLIER, NEAR = 2.5, 150.0
RAMP_C, RAMP_L = 0.0, 60.0              # 中苑 -> 东苑 ramp: centre (m from the 盘城新街 corridor midline), half width
# 西苑 / 中苑 split: the centre line of the river between them (campus.json water[1]), north to south, (x, z)
WEST_SPLIT = [(-165, 320), (-165, 220), (-170, 140), (-180, 100), (-190, 40), (-205, -20), (-225, -80), (-215, -140),
              (-250, -180), (-270, -220), (-282, -300), (-290, -380), (-295, -700)]
WEST_C, WEST_L, WEST_DELTA = 0.0, 20.0, 0.0  # 西苑 -> 中苑 transition: centre, half width (m); 西苑 level shift (m)
OUT_IN, OUT_OUT = 10.0, 110.0
# lakes inside the campus (用户: 高差放在湖和湖岸两侧的绿地上, 跨湖的路和桥要缓, 水位按最低的岸, 走过去感觉不到高差): the
# shore band (BANK_FLAT m) of each lake is set to its low bank level (10th percentile of the ground 4-14 m out), so
# main.js's water level (mean shore height - 0.6) sits just under every bank; away from the shore the ground may rise
# at most BANK_SLOPE per metre (a natural grass bank; the drone DSM shows the 中苑 shore of the 西苑/中苑 lake rising
# ~3 m over 40-60 m), ROAD_SLOPE within ROAD_PAD m of a road or path that crosses or reaches the lake (measured from
# the shore, i.e. along such a road). Lakes: campus.json water polygons with every vertex inside the terrain grid.
BANK_FLAT, BANK_SLOPE, ROAD_SLOPE, ROAD_PAD, LAKE_REACH = 6.0, 0.07, 0.045, 12.0, 300.0
BLDG_PAD = 0.0                     # > 0: lakeside buildings keep their ground (+ margin) right to the water (steep bank)
# a building within LAKE_REACH whose footprint now spans more than PAD_SPREAD m of ground (it stands on the new bank
# slope) gets a level pad at the PAD_Q percentile of that ground, + PAD_IN m around it, blended back to the slope over
# PAD_OUT m: a ~1-1.5 m quay in front, the building cut into the slope behind (the game puts a model at its lowest
# footprint corner, so a tilted pad buries the uphill side)
PAD_SPREAD, PAD_Q, PAD_IN, PAD_OUT, PAD_NEAR = 1.5, 40, 3.0, 18.0, 80.0   # only buildings within PAD_NEAR m of the lake


def model_rects(c):
    """building id -> plan rectangle of the Blender model that replaces it (GLB position bounds, rotY 0): a pad
    follows the built part, not an outline that also holds a courtyard (见山园)"""
    import struct
    out = {}
    for md in c.get("models", []):
        f = ROOT / "web" / "public" / md["file"]
        if not f.exists() or md.get("rotY") or len(md.get("replaces", [])) != 1:
            continue
        b = f.read_bytes()
        js = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
        mn, mx = [1e9, 1e9], [-1e9, -1e9]
        for m in js["meshes"]:
            for pr in m["primitives"]:
                a = js["accessors"][pr["attributes"]["POSITION"]]
                mn = [min(mn[0], a["min"][0]), min(mn[1], a["min"][2])]; mx = [max(mx[0], a["max"][0]), max(mx[1], a["max"][2])]
        x0, z0, x1, z1 = md["x"] + mn[0], md["z"] + mn[1], md["x"] + mx[0], md["z"] + mx[1]
        out[str(md["replaces"][0])] = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    return out


def seg_dist(X, Z, pts, closed):
    """distance (m) from every grid node to a polyline / polygon outline"""
    d = np.full(X.shape, np.inf, np.float32)
    n = len(pts)
    for i in range(n if closed else n - 1):
        (ax, az), (bx, bz) = pts[i], pts[(i + 1) % n]
        ex, ez = bx - ax, bz - az
        L2 = ex * ex + ez * ez or 1e-9
        t = np.clip(((X - ax) * ex + (Z - az) * ez) / L2, 0, 1)
        d = np.minimum(d, np.hypot(ax + ex * t - X, az + ez * t - Z))
    return d


def inside_poly(X, Z, pts):
    m = np.zeros(X.shape, bool)
    n = len(pts)
    for i in range(n):
        (xi, zi), (xj, zj) = pts[i], pts[i - 1]
        cross = ((zi > Z) != (zj > Z)) & (X < (xj - xi) * (Z - zi) / ((zj - zi) or 1e-9) + xi)
        m ^= cross
    return m


def level_lakes(H, c, X, Z, gx, gz, area):
    W, D = c["size"]
    H = H.copy()
    for k, w in enumerate(c["water"]):
        pts = w["pts"]
        if len(pts) < 3 or not all(abs(x) < W / 2 and abs(z) < D / 2 for x, z in pts):
            continue
        xs, zs = [p[0] for p in pts], [p[1] for p in pts]
        box = (X > min(xs) - LAKE_REACH) & (X < max(xs) + LAKE_REACH) & (Z > min(zs) - LAKE_REACH) & (Z < max(zs) + LAKE_REACH)
        ins = inside_poly(X, Z, pts)
        d = np.where(ins, 0.0, seg_dist(X, Z, pts, True))
        bank = H[(d >= 4) & (d <= 14) & ~ins]
        if bank.size < 5:
            continue
        L = float(np.percentile(bank, 10))
        def soft_away(mask, reach=20.0, dead=0.0):   # 0 on the mask (and within `dead` m), 1 from `reach` m on
            dm = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5) * gx
            return smoothstep(dead, reach, dm)
        road = np.zeros(X.shape, bool)       # corridors of the roads that cross or reach this lake: ROAD_SLOPE
        road_any = np.zeros(X.shape, bool)   # every road / path near it: the bank slope and pads leave them alone
        road_core = np.zeros(X.shape, bool)  # the paved surface itself (+1 m) of every road near it: pads stay off
        for r in c["roads"]:
            rx, rz = [p[0] for p in r["pts"]], [p[1] for p in r["pts"]]
            if max(rx) < min(xs) - LAKE_REACH or min(rx) > max(xs) + LAKE_REACH or max(rz) < min(zs) - LAKE_REACH or min(rz) > max(zs) + LAKE_REACH:
                continue
            rd = seg_dist(X, Z, r["pts"], False)
            hw = r["w"] / 2 + (r.get("sw") or 0)
            rp = np.array(r["pts"], np.float32)
            sx = np.concatenate([np.linspace(a[0], b[0], 8) for a, b in zip(rp[:-1], rp[1:])])
            sz = np.concatenate([np.linspace(a[1], b[1], 8) for a, b in zip(rp[:-1], rp[1:])])
            if inside_poly(sx, sz, pts).any() or seg_dist(sx, sz, pts, True).min() < 15:
                road |= rd < hw + ROAD_PAD
                road_core |= rd < hw + 1
            else:
                road_any |= rd < hw + 2
                road_core |= rd < hw + 1
        keep = np.zeros(X.shape, bool)
        for b in (c["buildings"] if BLDG_PAD > 0 else []):
            bx, bz = [p[0] for p in b["pts"]], [p[1] for p in b["pts"]]
            if max(bx) < min(xs) - LAKE_REACH or min(bx) > max(xs) + LAKE_REACH or max(bz) < min(zs) - LAKE_REACH or min(bz) > max(zs) + LAKE_REACH:
                continue
            keep |= inside_poly(X, Z, b["pts"]) | (seg_dist(X, Z, b["pts"], True) < BLDG_PAD)
        keep &= ~ins                      # a lakeside building keeps its ground right to the water (an embankment)
        cone = L + np.where(road, ROAD_SLOPE, BANK_SLOPE) * np.maximum(0, d - BANK_FLAT)
        wpass = soft_away(road_any & ~road)  # a road running past the lake keeps its own grade (no tilt, no dip)
        new = np.where(keep, H, np.where(d <= BANK_FLAT, L, H + (np.minimum(H, cone) - H) * wpass))
        new = np.where(d < BANK_FLAT + 10, np.maximum(new, L - 0.3), new)          # no bank below the water
        # soften the road / grass slope seams (a 10 m grid cannot hold a cut), only where the lake changed things
        changed = (np.abs(new - H) > 0.05) & box
        if changed.any():
            soft = cv2.GaussianBlur(new.astype(np.float32), (0, 0), 0.8)
            wgt = cv2.GaussianBlur(changed.astype(np.float32), (0, 0), 1.5)
            new = np.where(d <= BANK_FLAT, new, new * (1 - wgt) + soft * wgt)
            new = np.where(keep, H, np.where(d <= BANK_FLAT, L, new))
        # level pads for the buildings now standing on the bank slope (never reaching into a sports ground + 15 m,
        # which main.js levels on its own and whose stands / fences sit on it)
        sport = np.zeros(X.shape, bool)
        for sp in c.get("sports", []):
            cx, cz, Ls, Ws, ang = sp["obb"]
            u = (X - cx) * np.cos(ang) + (Z - cz) * np.sin(ang)
            v = -(X - cx) * np.sin(ang) + (Z - cz) * np.cos(ang)
            sport |= (np.abs(u) < Ls / 2 + 15) & (np.abs(v) < Ws / 2 + 15)
        near_b = [b for b in c["buildings"] if not (max(q[0] for q in b["pts"]) < min(xs) - LAKE_REACH or min(q[0] for q in b["pts"]) > max(xs) + LAKE_REACH
                                                    or max(q[1] for q in b["pts"]) < min(zs) - LAKE_REACH or min(q[1] for q in b["pts"]) > max(zs) + LAKE_REACH)]
        foot = {id(b): inside_poly(X, Z, b["pts"]) for b in near_b}
        npad = 0
        rects = model_rects(c)
        for b in near_b:
            bpts = rects.get(str(b["id"]), b["pts"])
            bx, bz = [q[0] for q in bpts], [q[1] for q in bpts]
            gxs, gzs = np.meshgrid(np.linspace(min(bx), max(bx), 10), np.linspace(min(bz), max(bz), 10))
            fin = inside_poly(gxs, gzs, bpts)
            if fin.sum() < 4 or seg_dist(gxs[fin], gzs[fin], pts, True).min() > PAD_NEAR:
                continue
            fi = ((gxs + W / 2) / gx).astype(np.float32); fk = ((gzs + D / 2) / gz).astype(np.float32)
            hv = cv2.remap(new.astype(np.float32), fi, fk, cv2.INTER_LINEAR)[fin]
            if hv.max() - hv.min() <= PAD_SPREAD:
                continue
            P = float(np.percentile(hv, PAD_Q))
            db = np.where(inside_poly(X, Z, bpts), 0.0, seg_dist(X, Z, bpts, True))
            others = sport.copy()
            for ob in near_b:
                if ob is not b:
                    others |= foot[id(ob)]
            wpad = (1 - smoothstep(PAD_IN, PAD_IN + PAD_OUT, db)) * soft_away(others) * soft_away(road_core, 25.0, 8.0)   # roads keep their grade; a building touching one sits cut into the slope
            onb = inside_poly(X, Z, bpts) & ~ins    # under the building the pad wins over the shore band (waterfront quay)
            new = np.where((d <= BANK_FLAT) & ~onb, new, new + wpad * (P - new))
            npad += 1
        dz = np.where(box, (new - H) * area, 0)
        H = H + dz
        if npad:
            print(f"lake {k}: {npad} building pads levelled on the bank slope")
        print(f"lake {k}: bank level {L:.1f} m (water {L - 0.6:.1f}); ground lowered up to {-dz.min():.1f} m, raised up to {dz.max():.1f} m")
    return H


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    if not SRC.exists():                 # keep the untouched SRTM grid as the input of every later run
        shutil.copyfile(DST, SRC)
    t = json.loads(SRC.read_text(encoding="utf-8"))
    c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, D = c["size"]
    nx, nz, base = t["nx"], t["nz"], t["base"]
    srtm = np.array(t["h"], np.float32).reshape(nz, nx) / 10 + base
    gx, gz = W / (nx - 1), D / (nz - 1)
    X, Z = np.meshgrid(np.arange(nx) * gx - W / 2, np.arange(nz) * gz - D / 2)
    masks = []
    for ring in c["boundary"]:
        im = Image.new("L", (nx, nz), 0)
        ImageDraw.Draw(im).polygon([((x + W / 2) / gx, (z + D / 2) / gz) for x, z in ring], fill=1)
        masks.append(np.asarray(im).astype(np.float32))

    def sample(a, x, z):
        return float(cv2.remap(a.astype(np.float32), np.array([[(x + W / 2) / gx]], np.float32),
                               np.array([[(z + D / 2) / gz]], np.float32), cv2.INTER_LINEAR)[0, 0])

    def part_of(x, z):
        i, k = int(round((x + W / 2) / gx)), int(round((z + D / 2) / gz))
        for p, m in enumerate(masks):
            if 0 <= i < nx and 0 <= k < nz and m[k, i]:
                return p
        return -1

    # signed distance (m, + east) from the 西苑 / 中苑 split line, measured along x
    wz = np.array([q[1] for q in WEST_SPLIT]); wx = np.array([q[0] for q in WEST_SPLIT])
    split_x = lambda z: np.interp(z, wz[::-1], wx[::-1])
    east_of_split = lambda x, z: x - split_x(z)
    side_of = lambda x, z, p: (1 if east_of_split(x, z) > 0 else -1) if p == 0 else 0

    pts = []
    if CTRL.exists():
        raw = [(x, z, g, part_of(x, z)) for _, x, z, g in json.loads(CTRL.read_text(encoding="utf-8"))["points"]]
        for i, (x, z, g, p) in enumerate(raw):
            if p < 0:
                continue
            nb = [q[2] for j, q in enumerate(raw) if j != i and q[3] == p and side_of(q[0], q[1], p) == side_of(x, z, p)
                  and np.hypot(q[0] - x, q[1] - z) < NEAR]
            if len(nb) >= 3 and abs(g - np.median(nb)) > OUTLIER:
                continue
            pts.append((x, z, g, p))
        print(f"control points: {len(raw)}, used {len(pts)}")
    else:
        print("no control points: smoothed SRTM only")

    def surface(p, side=0):
        m = masks[p]
        s = PRIOR / gx
        num, den = cv2.GaussianBlur(srtm * m, (0, 0), s), cv2.GaussianBlur(m, (0, 0), s)
        far = cv2.GaussianBlur(srtm * m, (0, 0), 3 * s) / np.maximum(cv2.GaussianBlur(m, (0, 0), 3 * s), 1e-6)
        H = np.where(den > 0.02, num / np.maximum(den, 1e-6), far)
        sel = [q for q in pts if q[3] == p and (side == 0 or side * east_of_split(q[0], q[1]) > 0)]
        for sig, lam in zip(SCALES, LAMBDA):
            if not sel:
                break
            num, den = np.zeros_like(H), np.zeros_like(H)
            for x, z, g, _ in sel:
                w = np.exp(-((X - x) ** 2 + (Z - z) ** 2) / (2 * sig * sig))
                num += w * (g - sample(H, x, z))
                den += w
            H = H + num / (den + lam)
        return H

    S = [surface(p) for p in range(len(masks))]
    if pts:                              # ring 0 = 西苑 (west of the split) + 中苑 (east), blended across the lake
        ww = smoothstep(WEST_C - WEST_L, WEST_C + WEST_L, X - split_x(Z))
        S[0] = (1 - ww) * (surface(0, -1) + WEST_DELTA) + ww * surface(0, +1)
    dist = [cv2.distanceTransform((1 - m).astype(np.uint8), cv2.DIST_L2, 5) * gx for m in masks]       # 0 inside
    sd = [np.where(m > 0, -cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5) * gx, d) for m, d in zip(masks, dist)]
    w1 = smoothstep(RAMP_C - RAMP_L, RAMP_C + RAMP_L, (sd[0] - sd[1]) / 2)
    C = (1 - w1) * S[0] + w1 * S[1]
    for k in range(2, len(masks)):       # outlying plots on their own surface
        C = np.where(dist[k] < np.minimum(dist[0], dist[1]), S[k], C)
    wo = smoothstep(OUT_IN, OUT_OUT, np.minimum.reduce(dist))
    H = (1 - wo) * C + wo * srtm
    # lake shores: only inside the campus (feathered over ~30 m past the boundary), the SRTM outside stays
    area = np.clip(1 - smoothstep(0, 30, np.minimum.reduce(dist)), 0, 1)
    H = level_lakes(H, c, X, Z, gx, gz, area)
    out = dict(t)
    out["h"] = [int(v) for v in np.round((H - base) * 10).astype(int).ravel()]
    out["source"] = "SRTM (Terrarium tiles, tools/fetch_terrain.py); campus re-levelled by tools/campus_terrain.py"
    DST.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    camp = sum(masks) > 0
    gy0, gx0 = np.gradient(srtm, gz, gx)
    gy1, gx1 = np.gradient(H, gz, gx)
    sl0, sl1 = np.hypot(gx0, gy0)[camp] * 100, np.hypot(gx1, gy1)[camp] * 100
    print(f"campus slope % p50/p95/max: SRTM {np.percentile(sl0, 50):.1f}/{np.percentile(sl0, 95):.1f}/{sl0.max():.1f}"
          f" -> {np.percentile(sl1, 50):.1f}/{np.percentile(sl1, 95):.1f}/{sl1.max():.1f}")
    if pts:
        res = np.array([g - sample(H, x, z) for x, z, g, _ in pts])
        print(f"control residual p5/p50/p95 {np.percentile(res, 5):+.2f}/{np.median(res):+.2f}/{np.percentile(res, 95):+.2f} m")


if __name__ == "__main__":
    main()
