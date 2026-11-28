"""Re-register the drone DSM (data/raw/dsm.npy, tools/recon_heights.py) to the campus.json outlines and re-measure heights.

The DSM came out displaced against the outlines (Blender session: ~7 m east, 9 m north), so measured_heights.json
mixed ground cells into the building percentiles. This finds the shift:
  1. global: integer shifts in +-20 m maximising the share of outline cells that the DSM shows as raised (nDSM > 3 m),
     refined to 0.1 m with a parabola through the peak;
  2. per building (outlines >= 150 m2, well covered): the same search in a window around the building;
  3. consistency: per-zone medians (data/zones/grid.json) and an affine fit dx, dz = a + b x + c z (rotation / scale);
then measures every building as recon_heights.py does (p70 / p30 / p95 of nDSM inside the eroded outline), with the
chosen shift. recon_heights.py itself is not changed.

Usage: .venv/Scripts/python.exe -I -X utf8 tools/dsm_register.py [--affine]
Output: data/manual/measured_heights_v2.json (measured_heights.json is left as it is), data/raw/dsm_register.json (report)
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
W, D = campus["size"]
CELL = 1.0


def ndsm_of(dsm):
    """same ground model as recon_heights.py: grey opening over ~45 m, smoothed"""
    valid = ~np.isnan(dsm)
    hi = np.where(valid, dsm, 1e4).astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
    dtm = cv2.dilate(cv2.erode(hi, k), k)
    dtm[dtm > 5e3] = np.nan
    dtm_f = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm).astype(np.float32)
    dtm_f = cv2.GaussianBlur(dtm_f, (0, 0), 12)
    return dsm - dtm_f


def footprints():
    out = []
    for b in campus["buildings"]:
        if b.get("kind") == "wall" or len(b["pts"]) < 3:
            continue
        poly = np.array([[(x + W / 2) / CELL, (z + D / 2) / CELL] for x, z in b["pts"]], np.float32)
        out.append((str(b["id"]), b, poly))
    return out


def score_map(F, M, V, r):
    """share of outline cells shown raised, for every integer shift (dx, dz) in [-r, r]^2 (DSM sampled at cell + shift)"""
    H, Wd = F.shape
    S = np.full((2 * r + 1, 2 * r + 1), np.nan)
    for dz in range(-r, r + 1):
        for dx in range(-r, r + 1):
            fz0, fz1 = max(0, -dz), min(H, H - dz)
            fx0, fx1 = max(0, -dx), min(Wd, Wd - dx)
            f = F[fz0:fz1, fx0:fx1]
            m = M[fz0 + dz:fz1 + dz, fx0 + dx:fx1 + dx]
            v = V[fz0 + dz:fz1 + dz, fx0 + dx:fx1 + dx]
            n = np.count_nonzero(f & v)
            if n:
                S[dz + r, dx + r] = np.count_nonzero(f & m) / n
    return S


def peak(S, r):
    j = np.nanargmax(S)
    iz, ix = divmod(j, S.shape[1])

    def sub(a, b, c):
        den = a - 2 * b + c
        return 0.0 if not np.isfinite(den) or den >= 0 else 0.5 * (a - c) / den
    fx = sub(S[iz, ix - 1], S[iz, ix], S[iz, ix + 1]) if 0 < ix < S.shape[1] - 1 else 0
    fz = sub(S[iz - 1, ix], S[iz, ix], S[iz + 1, ix]) if 0 < iz < S.shape[0] - 1 else 0
    return float(ix - r + fx), float(iz - r + fz), float(S[iz, ix])


def measure(ndsm, shift_at):
    """per building: nDSM percentiles inside the eroded outline, the DSM sampled at outline cell + shift_at(x, z)"""
    nz, nx = ndsm.shape
    res = {}
    for bid, b, poly in footprints():
        cx, cz = poly.mean(0) * CELL - [W / 2, D / 2]
        dx, dz = shift_at(cx, cz)
        x0, z0 = np.floor(poly.min(0)).astype(int) - 1
        x1, z1 = np.ceil(poly.max(0)).astype(int) + 2
        mask = np.zeros((z1 - z0, x1 - x0), np.uint8)
        inner = cv2.erode(cv2.fillPoly(mask, [np.round(poly - [x0, z0]).astype(np.int32)], 1), np.ones((3, 3), np.uint8)).astype(bool)
        zz, xx = np.nonzero(inner)
        sx = np.round(xx + x0 + dx).astype(int)
        sz = np.round(zz + z0 + dz).astype(int)
        ok = (sx >= 0) & (sx < nx) & (sz >= 0) & (sz < nz)
        vals = ndsm[sz[ok], sx[ok]]
        vals = vals[~np.isnan(vals)]
        if len(vals) < 15 or inner.sum() < 20 or len(vals) < 0.3 * inner.sum():
            continue
        res[bid] = dict(name=b.get("name", ""), h=round(float(np.percentile(vals, 70)), 1), p30=round(float(np.percentile(vals, 30)), 1),
                        p95=round(float(np.percentile(vals, 95)), 1), est=b["h"], cover=round(len(vals) / inner.sum(), 2),
                        shift=[round(dx, 1), round(dz, 1)])
    return res


def east_side(x, z):
    """east of 盘城新街 (东苑): the side test against the street's centreline in campus.json"""
    best = None
    for r in campus["roads"]:
        if "盘城新街" not in (r.get("name") or ""):
            continue
        for (ax, az), (bx, bz) in zip(r["pts"], r["pts"][1:]):
            t = max(0.0, min(1.0, ((x - ax) * (bx - ax) + (z - az) * (bz - az)) / max((bx - ax) ** 2 + (bz - az) ** 2, 1e-9)))
            d = math.hypot(x - ax - t * (bx - ax), z - az - t * (bz - az))
            if best is None or d < best[0]:
                best = (d, (bx - ax) * (z - az) - (bz - az) * (x - ax))
    return best is not None and best[1] > 0       # the centreline is drawn south -> north: east = right-hand side


def east_refine(dsm, ndsm, write=False):
    """东苑: measure on the local building-model footprints (本机素材, data/source/scan2022_analysis/footprints.json) instead of
    the campus outlines, with a local DSM -> model shift, and a local ground.
    Why: the 45 m grey opening of ndsm_of() cannot get between closely packed blocks (晖园11-14, 东苑食堂), so the ground
    model sits up to ~8 m too high there and every height came out low; the shift was not the problem (checked against the
    models: 8 m east / 10 m north, within 2-3 m of the affine field).
    Ground = the lower of (that ground model under the building) and (p20 of the DSM in a 3-12 m ring outside the building,
    other buildings left out). Buildings without a model of the same id keep the affine-field value."""
    fpp = ROOT / "data" / "source" / "scan2022_analysis" / "footprints.json"
    if not fpp.exists():
        print("east_refine: no local model footprints, skipped")
        return {}
    fp = json.loads(fpp.read_text(encoding="utf-8"))
    objs = {}
    for d in fp.values():
        for oid, o in d.items():
            objs.setdefault(oid, o)
    H, Wd = dsm.shape
    valid = ~np.isnan(dsm)
    dtm = dsm - ndsm                                  # the ground model of ndsm_of()

    def raster(o):
        f = np.zeros((H, Wd), np.uint8)
        for x, z, t in o["cells"]:
            r, c = int(math.floor(z + D / 2)), int(math.floor(x + W / 2))
            if 0 <= r < H and 0 <= c < Wd and t - o["ground"] > 2.5:
                f[r, c] = 1
        return cv2.morphologyEx(f, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    byid = {str(b["id"]): b for b in campus["buildings"]}
    east = [k for k, b in byid.items() if k in objs and b.get("kind") != "wall"
            and east_side(sum(p[0] for p in b["pts"]) / len(b["pts"]), sum(p[1] for p in b["pts"]) / len(b["pts"]))]
    allF = np.zeros((H, Wd), np.uint8)
    for o in objs.values():
        allF |= raster(o)
    M = np.nan_to_num(ndsm, nan=0) > 3
    # one shift for the whole of 东苑 (DSM -> models), refined per building within +-4 m
    fz, fx = np.nonzero(allF)
    sel = np.zeros_like(allF, bool)
    for k in east:
        sel |= raster(objs[k]).astype(bool)
    rows, cols = np.nonzero(sel)
    r0, r1, c0, c1 = rows.min() - 30, rows.max() + 30, cols.min() - 30, cols.max() + 30
    f = sel[r0:r1, c0:c1]

    def iou(f, r0, c0, dx, dz):
        m = M[r0 + dz:r0 + dz + f.shape[0], c0 + dx:c0 + dx + f.shape[1]]
        v = valid[r0 + dz:r0 + dz + f.shape[0], c0 + dx:c0 + dx + f.shape[1]]
        return np.count_nonzero(f & m & v) / max(np.count_nonzero((f | m) & v), 1)
    S = np.array([[iou(f, r0, c0, dx, dz) for dx in range(-20, 21)] for dz in range(-20, 21)])
    edx, edz, _ = peak(S, 20)
    print(f"东苑: {len(east)} buildings with a local model; DSM -> model shift dx {edx:+.1f} dz {edz:+.1f}")
    out = {}
    for k in east:
        o, b = objs[k], byid[k]
        fb = raster(o)
        rr, cc = np.nonzero(fb)
        if len(rr) < 30:
            continue
        a0, a1, b0, b1 = rr.min() - 15, rr.max() + 16, cc.min() - 15, cc.max() + 16
        fw = fb[a0:a1, b0:b1].astype(bool)
        best = max(((iou(fw, a0, b0, int(round(edx)) + i, int(round(edz)) + j), int(round(edx)) + i, int(round(edz)) + j)
                    for i in range(-4, 5) for j in range(-4, 5)))
        _, dx, dz = best
        inner = cv2.erode(fb, np.ones((5, 5), np.uint8)).astype(bool)
        if inner.sum() < 20:
            inner = fb.astype(bool)
        ring = cv2.dilate(fb, np.ones((25, 25), np.uint8)).astype(bool) & ~cv2.dilate(allF, np.ones((7, 7), np.uint8)).astype(bool)
        zi, xi = np.nonzero(inner)
        vin = dsm[np.clip(zi + dz, 0, H - 1), np.clip(xi + dx, 0, Wd - 1)]
        vin = vin[~np.isnan(vin)]
        if len(vin) < 0.3 * inner.sum() or len(vin) < 15:
            continue
        zr, xr = np.nonzero(ring)
        vr = dsm[np.clip(zr + dz, 0, H - 1), np.clip(xr + dx, 0, Wd - 1)]
        vr = vr[~np.isnan(vr)]
        g_dtm = float(np.nanmedian(dtm[np.clip(zi + dz, 0, H - 1), np.clip(xi + dx, 0, Wd - 1)]))
        g_ring = float(np.percentile(vr, 20)) if len(vr) >= 200 else None
        g = min(g_dtm, g_ring) if g_ring is not None else g_dtm
        out[k] = dict(name=b.get("name", ""), h=round(float(np.percentile(vin, 70)) - g, 1), p30=round(float(np.percentile(vin, 30)) - g, 1),
                      p95=round(float(np.percentile(vin, 95)) - g, 1), est=b["h"], cover=round(len(vin) / inner.sum(), 2),
                      shift=[dx, dz], on="local model footprint", ground="ring" if g_ring is not None and g_ring < g_dtm else "dtm",
                      ground_lift=round(g_dtm - g, 1))
    return out


def main():
    if "--east-only" in sys.argv:       # 东苑 refinement on top of the existing measured_heights_v2.json
        dsm = np.load(ROOT / "data" / "raw" / "dsm.npy")
        ndsm = ndsm_of(dsm)
        res = east_refine(dsm, ndsm)
        p = ROOT / "data" / "manual" / "measured_heights_v2.json"
        v2 = json.loads(p.read_text(encoding="utf-8"))
        prev = {k: v for k, v in v2["buildings"].items() if k in res}
        for k, v in sorted(res.items(), key=lambda kv: -abs(kv[1]["h"] - prev.get(kv[0], {}).get("h", kv[1]["h"]))):
            print(f"  {v['name'] or k:12s} {k:>11s}  affine {prev.get(k, {}).get('h')}  ->  {v['h']}  (ground {v['ground']}, lift {v['ground_lift']}, "
                  f"shift {v['shift']}, cover {v['cover']})")
        if "--write" in sys.argv:
            for k, v in res.items():
                if k in v2["buildings"]:
                    v["h_affine"] = v2["buildings"][k]["h"]
                v2["buildings"][k] = v
            v2["east"] = ("东苑 (east of 盘城新街): measured on the local model footprints with a local shift and local ground "
                          "(tools/dsm_register.py --east-only); h_affine = the earlier value")
            p.write_text(json.dumps(v2, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"written: {len(res)} 东苑 buildings")
        return
    dsm = np.load(ROOT / "data" / "raw" / "dsm.npy")
    ndsm = ndsm_of(dsm)
    V = ~np.isnan(dsm)
    M = np.nan_to_num(ndsm, nan=0) > 3
    fps = footprints()
    F = np.zeros(dsm.shape, np.uint8)
    for _, _, poly in fps:
        cv2.fillPoly(F, [np.round(poly).astype(np.int32)], 1)
    F = F.astype(bool)
    ys, xs = np.nonzero(V)
    z0, z1, x0, x1 = ys.min() - 25, ys.max() + 25, xs.min() - 25, xs.max() + 25
    R = 20
    S = score_map(F[z0:z1, x0:x1], M[z0:z1, x0:x1], V[z0:z1, x0:x1], R)
    gdx, gdz, gscore = peak(S, R)
    s0 = float(S[R, R])
    print(f"global shift dx {gdx:+.1f} m (east), dz {gdz:+.1f} m (south); raised share {s0:.3f} -> {gscore:.3f}")

    # per building
    per = []
    for bid, b, poly in fps:
        area = cv2.contourArea(poly)
        if area < 150:
            continue
        bx0, bz0 = np.floor(poly.min(0)).astype(int) - R - 2
        bx1, bz1 = np.ceil(poly.max(0)).astype(int) + R + 3
        if bx0 < 0 or bz0 < 0 or bx1 > dsm.shape[1] or bz1 > dsm.shape[0]:
            continue
        f = np.zeros((bz1 - bz0, bx1 - bx0), np.uint8)
        cv2.fillPoly(f, [np.round(poly - [bx0, bz0]).astype(np.int32)], 1)
        f = f.astype(bool)
        v = V[bz0:bz1, bx0:bx1]
        if np.count_nonzero(f & v) < 0.6 * np.count_nonzero(f):
            continue
        Sb = score_map(f, M[bz0:bz1, bx0:bx1], v, R)
        if not np.isfinite(Sb).any():
            continue
        dx, dz, sc = peak(Sb, R)
        base = float(Sb[R, R]) if np.isfinite(Sb[R, R]) else 0
        sharp = sc - float(np.nanmedian(Sb))
        cx, cz = poly.mean(0) * CELL - [W / 2, D / 2]
        if sc >= 0.6 and sharp >= 0.25:
            per.append(dict(id=bid, name=b.get("name", ""), x=round(float(cx), 1), z=round(float(cz), 1), dx=round(dx, 1), dz=round(dz, 1),
                            score=round(sc, 2), score0=round(base, 2), area=round(float(area))))
    pdx = np.array([p["dx"] for p in per])
    pdz = np.array([p["dz"] for p in per])
    print(f"per building ({len(per)} well defined): median dx {np.median(pdx):+.1f} dz {np.median(pdz):+.1f}; "
          f"IQR dx {np.percentile(pdx, 25):+.1f}..{np.percentile(pdx, 75):+.1f}, dz {np.percentile(pdz, 25):+.1f}..{np.percentile(pdz, 75):+.1f}")
    # tiles: 400 m windows every 200 m, search +-12 m around the global shift (whole groups of buildings cannot alias
    # onto the next dorm row the way a single building can)
    tiles = []
    T, STEP, RT = 400, 200, 12
    for tz in range(z0, z1 - T // 2, STEP):
        for tx in range(x0, x1 - T // 2, STEP):
            fz0, fz1, fx0, fx1 = tz, min(tz + T, dsm.shape[0]), tx, min(tx + T, dsm.shape[1])
            f = F[fz0:fz1, fx0:fx1]
            if np.count_nonzero(f & V[fz0:fz1, fx0:fx1]) < 3000:
                continue
            gx_, gz_ = int(round(gdx)), int(round(gdz))
            pz0, pz1 = max(0, fz0 - RT + gz_), min(dsm.shape[0], fz1 + RT + gz_)
            px0, px1 = max(0, fx0 - RT + gx_), min(dsm.shape[1], fx1 + RT + gx_)
            # shift the DSM window by the rounded global shift first, then search +-RT
            Ms = np.zeros_like(f, bool)
            Vs = np.zeros_like(f, bool)
            Mw, Vw = M[pz0:pz1, px0:px1], V[pz0:pz1, px0:px1]
            Sb = np.full((2 * RT + 1, 2 * RT + 1), np.nan)
            for dz in range(-RT, RT + 1):
                for dx in range(-RT, RT + 1):
                    sz0, sx0 = fz0 + gz_ + dz - pz0, fx0 + gx_ + dx - px0
                    if sz0 < 0 or sx0 < 0 or sz0 + f.shape[0] > Mw.shape[0] or sx0 + f.shape[1] > Mw.shape[1]:
                        continue
                    m = Mw[sz0:sz0 + f.shape[0], sx0:sx0 + f.shape[1]]
                    v = Vw[sz0:sz0 + f.shape[0], sx0:sx0 + f.shape[1]]
                    n = np.count_nonzero(f & v)
                    if n:
                        Sb[dz + RT, dx + RT] = np.count_nonzero(f & m) / n
            if not np.isfinite(Sb).any():
                continue
            dx, dz, sc = peak(Sb, RT)
            prom = sc - float(np.nanpercentile(Sb, 50))
            tiles.append(dict(x=round((fx0 + fx1) / 2 * CELL - W / 2), z=round((fz0 + fz1) / 2 * CELL - D / 2), dx=round(gx_ + dx, 1), dz=round(gz_ + dz, 1),
                              score=round(sc, 3), prom=round(prom, 3), n=int(np.count_nonzero(f & V[fz0:fz1, fx0:fx1]))))
    # a usable tile: most of its outlines show up raised at the peak, and the peak is not on the search border
    tl = [t for t in tiles if t["score"] >= 0.75 and abs(t["dx"] - round(gdx)) < RT - 0.5 and abs(t["dz"] - round(gdz)) < RT - 0.5]
    print(f"tiles: {len(tl)}/{len(tiles)} with a clear peak; dx {min(t['dx'] for t in tl):+.1f}..{max(t['dx'] for t in tl):+.1f}, "
          f"dz {min(t['dz'] for t in tl):+.1f}..{max(t['dz'] for t in tl):+.1f}")
    TA = np.stack([np.ones(len(tl)), [t["x"] / 1000 for t in tl], [t["z"] / 1000 for t in tl]], 1)
    tdx, tdz = np.array([t["dx"] for t in tl]), np.array([t["dz"] for t in tl])
    wts = np.sqrt([t["n"] for t in tl])
    tcx, *_ = np.linalg.lstsq(TA * wts[:, None], tdx * wts, rcond=None)
    tcz, *_ = np.linalg.lstsq(TA * wts[:, None], tdz * wts, rcond=None)
    t_res_aff = float(np.median(np.hypot(TA @ tcx - tdx, TA @ tcz - tdz)))
    t_res_glob = float(np.median(np.hypot(tdx - gdx, tdz - gdz)))
    print(f"tile affine: dx = {tcx[0]:+.2f} {tcx[1]:+.2f}*x {tcx[2]:+.2f}*z ; dz = {tcz[0]:+.2f} {tcz[1]:+.2f}*x {tcz[2]:+.2f}*z ; "
          f"median residual {t_res_aff:.2f} m vs global {t_res_glob:.2f} m")
    # zones
    zones = json.loads((ROOT / "data" / "zones" / "grid.json").read_text(encoding="utf-8"))
    zrep = {}
    for zn in zones:
        x0_, z0_, x1_, z1_ = zn["box"]
        sel = [p for p in per if x0_ <= p["x"] < x1_ and z0_ <= p["z"] < z1_]
        if len(sel) >= 3:
            zrep[zn["id"]] = dict(n=len(sel), dx=round(float(np.median([p["dx"] for p in sel])), 1), dz=round(float(np.median([p["dz"] for p in sel])), 1))
    # robust affine fit dx, dz = a + b x + c z (x, z in km)
    A = np.stack([np.ones(len(per)), [p["x"] / 1000 for p in per], [p["z"] / 1000 for p in per]], 1)
    keep = np.ones(len(per), bool)
    for _ in range(4):
        cx_, *_ = np.linalg.lstsq(A[keep], pdx[keep], rcond=None)
        cz_, *_ = np.linalg.lstsq(A[keep], pdz[keep], rcond=None)
        r = np.hypot(A @ cx_ - pdx, A @ cz_ - pdz)
        keep = r < max(2.0, 2.5 * np.median(r))
    res_aff = float(np.median(np.hypot(A[keep] @ cx_ - pdx[keep], A[keep] @ cz_ - pdz[keep])))
    res_glob = float(np.median(np.hypot(pdx - gdx, pdz - gdz)))
    print(f"affine: dx = {cx_[0]:+.2f} {cx_[1]:+.2f}*x {cx_[2]:+.2f}*z ; dz = {cz_[0]:+.2f} {cz_[1]:+.2f}*x {cz_[2]:+.2f}*z (x, z in km); "
          f"median residual {res_aff:.2f} m vs global {res_glob:.2f} m; inliers {keep.sum()}/{len(per)}")
    # the shift field is decided on the tiles (the per-building search aliases onto neighbouring rows)
    use_aff = "--affine" in sys.argv or (t_res_glob - t_res_aff > 0.75)
    cx_, cz_ = tcx, tcz
    if use_aff:
        shift_at = lambda x, z: (float(cx_ @ [1, x / 1000, z / 1000]), float(cz_ @ [1, x / 1000, z / 1000]))
    else:
        shift_at = lambda x, z: (gdx, gdz)
    print("using", "affine shift field" if use_aff else "global shift")
    new = measure(ndsm, shift_at)
    old = json.loads((ROOT / "data" / "manual" / "measured_heights.json").read_text(encoding="utf-8"))["buildings"]
    up2 = sum(1 for k, v in new.items() if k in old and v["h"] - old[k]["h"] >= 2)
    up5 = sum(1 for k, v in new.items() if k in old and v["h"] - old[k]["h"] >= 5)
    down2 = sum(1 for k, v in new.items() if k in old and v["h"] - old[k]["h"] <= -2)
    lowp30_old = sum(1 for v in old.values() if v["p30"] < 3)
    lowp30_new = sum(1 for v in new.values() if v["p30"] < 3)
    print(f"measured {len(new)} buildings; vs v1: +2 m {up2}, +5 m {up5}, -2 m {down2}; p30 < 3 m (ground mixed in) {lowp30_old} -> {lowp30_new}")
    out = dict(source="data/raw/dsm.npy (COLMAP DSM 2024-12) re-registered to campus.json outlines by tools/dsm_register.py",
               cell_m=CELL, shift=("affine" if use_aff else "global"),
               global_shift=[round(gdx, 2), round(gdz, 2)], affine_dx=[round(float(v), 3) for v in cx_], affine_dz=[round(float(v), 3) for v in cz_],
               note="shift = (dx east, dz south) in metres: the DSM cell for outline cell (x, z) is (x + dx, z + dz)", buildings=new)
    (ROOT / "data" / "manual" / "measured_heights_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = dict(global_shift=[round(gdx, 2), round(gdz, 2)], raised_share=[round(s0, 3), round(gscore, 3)],
               per_building=per, zones=zrep, tiles=tiles, tile_affine=dict(dx=list(map(float, tcx)), dz=list(map(float, tcz)), residual=t_res_aff, residual_global=t_res_glob), affine=dict(dx=list(map(float, cx_)), dz=list(map(float, cz_)), residual=res_aff, residual_global=res_glob,
                                                        inliers=int(keep.sum())), used="affine" if use_aff else "global",
               changes=dict(up2=up2, up5=up5, down2=down2, p30_low=[lowp30_old, lowp30_new]))
    (ROOT / "data" / "raw" / "dsm_register.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
