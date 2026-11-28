"""Measure building heights from our own drone photos.

COLMAP reconstruction (data/recon/ws) -> georeference with the photos' GPS -> 1 m DSM / DTM -> per-building height.
Also finds tall parts inside big footprints (e.g. a tower on a podium) and writes them as extra buildings.

Usage: .venv/Scripts/python.exe tools/recon_heights.py
Needs: data/recon/ws/sparse/0 (COLMAP), data/recon/ws/dense/0/fused.ply, data/recon/images (with EXIF GPS)
Output: data/manual/measured_heights.json, data/raw/dsm.npy (+ dsm_preview.jpg)
"""
import json
import math
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "data" / "recon"
WS = REC / "ws"
COLMAP = ROOT / "tools" / "colmap" / "bin" / "colmap.exe"
campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
W, D = campus["size"]
LAT0, LON0 = campus["origin"]["lat"], campus["origin"]["lon"]
phi = math.radians(LAT0)
M_LAT = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
M_LON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi) + 0.118 * math.cos(5 * phi)


def gps_local(path):
    im = Image.open(path)
    g = im.getexif().get_ifd(0x8825)
    dms = lambda v: float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
    lat, lon = dms(g[2]), dms(g[4])
    s = open(path, "rb").read(200000).decode("latin-1")
    m = re.search(r'RelativeAltitude="([-+\d.]+)"', s)
    alt = float(m.group(1)) if m else float(g.get(6, 0))
    return np.array([(lon - LON0) * M_LON, alt, -(lat - LAT0) * M_LAT])


def read_images_txt(path):
    out = {}
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    for l in lines[0::2]:
        p = l.split()
        qw, qx, qy, qz, tx, ty, tz = map(float, p[1:8])
        R = np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                      [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                      [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])
        out[p[-1]] = -R.T @ np.array([tx, ty, tz])
    return out


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(xd.T @ xs / len(src))
    E = np.eye(3)
    if np.linalg.det(U @ Vt) < 0:
        E[2, 2] = -1
    R = U @ E @ Vt
    s = np.trace(np.diag(S) @ E) / xs.var(0).sum()
    return s, R, mu_d - s * R @ mu_s


def read_ply(path):
    with open(path, "rb") as f:
        header = []
        while True:
            line = f.readline().decode("ascii").strip()
            header.append(line)
            if line == "end_header":
                break
        n = int(next(l for l in header if l.startswith("element vertex")).split()[-1])
        tmap = {"float": "<f4", "double": "<f8", "uchar": "u1", "int": "<i4", "uint": "<u4"}
        props = [(l.split()[2], tmap[l.split()[1]]) for l in header if l.startswith("property")]
        data = np.fromfile(f, dtype=np.dtype(props), count=n)
    return np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)


def main():
    txt = REC / "sparse_txt"
    txt.mkdir(exist_ok=True)
    subprocess.run([str(COLMAP), "model_converter", "--input_path", str(WS / "sparse" / "0"), "--output_path", str(txt),
                    "--output_type", "TXT"], check=True, capture_output=True)
    centers = read_images_txt(txt / "images.txt")
    names = sorted(centers)
    src = np.array([centers[n] for n in names])
    dst = np.array([gps_local(REC / "images" / n) for n in names])
    rng = np.random.default_rng(1)
    best = None
    for _ in range(2000):
        idx = rng.choice(len(src), 4, replace=False)
        s, R, t = umeyama(src[idx], dst[idx])
        err = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
        inl = err < 4.0
        if best is None or inl.sum() > best[0].sum():
            best = (inl, s, R, t)
    inl = best[0]
    s, R, t = umeyama(src[inl], dst[inl])
    err = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
    print(f"georef: {inl.sum()}/{len(src)} cameras inliers, RMS {np.sqrt((err[inl] ** 2).mean()):.2f} m, scale {s:.3f}")

    pts = read_ply(WS / "dense" / "0" / "fused.ply")
    pts = (s * (R @ pts.T)).T + t
    print(f"points: {len(pts):,}")
    CELL = 1.0
    nx, nz = int(W / CELL), int(D / CELL)
    ix = ((pts[:, 0] + W / 2) / CELL).astype(int)
    iz = ((pts[:, 2] + D / 2) / CELL).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz)
    ix, iz, y = ix[ok], iz[ok], pts[ok, 1]
    flat = iz * nx + ix
    dsm = np.full(nx * nz, -1e9)
    np.maximum.at(dsm, flat, y)
    cnt = np.bincount(flat, minlength=nx * nz)
    dsm[cnt < 2] = np.nan
    dsm = dsm.reshape(nz, nx).astype(np.float32)
    valid = ~np.isnan(dsm)
    filled = np.where(valid, dsm, 0).astype(np.float32)
    med = cv2.medianBlur(filled, 5)
    dsm = np.where(valid, med, np.nan).astype(np.float32)
    # ground: grey opening (min then max) over ~45 m, smoothed
    hi = np.where(valid, dsm, 1e4).astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
    dtm = cv2.dilate(cv2.erode(hi, k), k)
    dtm[dtm > 5e3] = np.nan
    dtm_f = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm).astype(np.float32)
    dtm_f = cv2.GaussianBlur(dtm_f, (0, 0), 12)
    np.save(ROOT / "data" / "raw" / "dsm.npy", dsm)
    ndsm = dsm - dtm_f
    prev = np.clip(np.nan_to_num(ndsm, nan=0) / 60 * 255, 0, 255).astype(np.uint8)
    cv2.imwrite(str(ROOT / "data" / "raw" / "ndsm_preview.jpg"), cv2.applyColorMap(prev, cv2.COLORMAP_TURBO))

    results, towers = {}, []
    for b in campus["buildings"]:
        if b.get("kind") == "wall":
            continue
        poly = np.array([[(x + W / 2) / CELL, (z + D / 2) / CELL] for x, z in b["pts"]], np.float32)
        x0, z0 = np.floor(poly.min(0)).astype(int) - 1
        x1, z1 = np.ceil(poly.max(0)).astype(int) + 2
        x0, z0, x1, z1 = max(x0, 0), max(z0, 0), min(x1, nx), min(z1, nz)
        if x1 <= x0 or z1 <= z0:
            continue
        mask = np.zeros((z1 - z0, x1 - x0), np.uint8)
        inner = cv2.erode(cv2.fillPoly(mask.copy(), [np.round(poly - [x0, z0]).astype(np.int32)], 1), np.ones((3, 3), np.uint8))
        vals = ndsm[z0:z1, x0:x1][inner.astype(bool)]
        vals = vals[~np.isnan(vals)]
        if len(vals) < 15 or inner.sum() < 20 or len(vals) < 0.3 * inner.sum():
            continue
        h = float(np.percentile(vals, 70))
        key = str(b["id"])
        results[key] = dict(name=b.get("name", ""), h=round(h, 1), p30=round(float(np.percentile(vals, 30)), 1),
                            p95=round(float(np.percentile(vals, 95)), 1), est=b["h"], cover=round(len(vals) / inner.sum(), 2))
        # tower inside a big footprint: cells well above the 70th percentile, forming a compact block
        p95 = float(np.percentile(vals, 95))
        if inner.sum() > 1200 and p95 - float(np.percentile(vals, 40)) > 15:
            sub = np.nan_to_num(ndsm[z0:z1, x0:x1], nan=0)
            tall = ((sub > p95 - 9) & inner.astype(bool)).astype(np.uint8)
            tall = cv2.morphologyEx(tall, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            n, lab, stats, _ = cv2.connectedComponentsWithStats(tall)
            if n > 1:
                j = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
                if stats[j, cv2.CC_STAT_AREA] >= 150:
                    ys, xs = np.nonzero(lab == j)
                    rect = cv2.minAreaRect(np.stack([xs + x0, ys + z0], 1).astype(np.float32))
                    (cx, cz), (rw, rh), ang = rect
                    L, Wd = max(rw, rh) * CELL, min(rw, rh) * CELL
                    a = math.radians(ang if rw >= rh else ang + 90)
                    towers.append(dict(of=b.get("name") or key, cx=round(cx * CELL - W / 2, 1), cz=round(cz * CELL - D / 2, 1),
                                       L=round(L, 1), W=round(Wd, 1), angle_rad=round(a, 4), h=round(p95, 1)))
    out = dict(source="COLMAP dense reconstruction of data/source/航拍/全校航拍拼图原图 (2024-12)", cell_m=CELL,
               georef_rms_m=round(float(np.sqrt((err[inl] ** 2).mean())), 2), buildings=results, towers=towers)
    (ROOT / "data" / "manual" / "measured_heights.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"measured {len(results)} buildings, {len(towers)} towers")
    for tw in towers:
        print("  tower", tw)
    for key, r in sorted(results.items(), key=lambda kv: -kv[1]["h"])[:12]:
        print(f"  {r['name'] or key}: {r['h']} m (est {r['est']}, cover {r['cover']})")


if __name__ == "__main__":
    main()
