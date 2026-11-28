"""Per-building measures from the local building-model set (本机素材, OBJ per building; never published):
ground, main roof height, top, and a 1 m top-view footprint raster, per OSM object inside each OBJ, in game coordinates.

Usage: .venv/Scripts/python.exe -I tools/scan_footprints.py <obj root> <out.json>
  obj root: data/source/南信大校园建筑单体（按楼名）   out: data/source/scan2022_analysis/footprints.json
Alignment (data/source/scan2022_analysis/README.md): game x = X - 134.9975, game z = -(Y - 303.9464), elevation = Z + 126.3256.
Group names carry the OSM id (osm-w<id>_... walls, roof_osm-w<id>_... roof parts); faces are attributed by it.
Main roof = area-weighted z of the "roof_planes" faces (the roof skin, not parapets / equipment / housings);
for pitched roofs p10 ~ eaves, p50 mid-slope, max ridge.
"""
import json
import math
import os
import re
import sys

OX, OY, OZ = 134.9975, 303.9464, 126.3256
ID = re.compile(r"osm-w(\d+)")


def scan(path):
    vx, vy, vz = [], [], []
    objs = {}                      # osm id -> dict
    cur_id, cur_kind, cur_up, obj_id, obj_name = None, None, False, None, ""

    def rec(i):
        r = objs.get(i)
        if r is None:
            r = objs[i] = {"name": "", "zmin": 1e9, "roof": [], "up": [], "cells": {}, "walls": 0.0}
        return r

    def put(r, x, y, z):              # cell (1 m, game coords) -> highest model point seen over it
        k = (math.floor(x - OX), math.floor(-(y - OY)))
        if r["cells"].get(k, -1e9) < z:
            r["cells"][k] = z
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            c = line[:2]
            if c == "v ":
                a = line.split()
                vx.append(float(a[1])); vy.append(float(a[2])); vz.append(float(a[3]))
            elif c == "f ":
                if cur_kind is None or cur_id is None:
                    continue
                idx = []
                for tok in line.split()[1:]:
                    k = int(tok.split("/")[0])
                    idx.append(k - 1 if k > 0 else len(vx) + k)
                r = rec(cur_id)
                p0 = idx[0]
                for t in range(1, len(idx) - 1):
                    a, b, d = p0, idx[t], idx[t + 1]
                    ax, ay, az = vx[a], vy[a], vz[a]
                    bx, by, bz = vx[b], vy[b], vz[b]
                    dx, dy, dz = vx[d], vy[d], vz[d]
                    zmn = min(az, bz, dz)
                    if zmn < r["zmin"]:
                        r["zmin"] = zmn
                    # top-view footprint cells (1 m, game coords)
                    area2 = (bx - ax) * (dy - ay) - (dx - ax) * (by - ay)
                    if abs(area2) < 0.02:          # vertical face: its edges
                        zmx = max(az, bz, dz)
                        for (px, py), (qx, qy) in (((ax, ay), (bx, by)), ((bx, by), (dx, dy))):
                            n = max(1, int(math.hypot(qx - px, qy - py) / 0.5) + 1)
                            for s in range(n + 1):
                                put(r, px + (qx - px) * s / n, py + (qy - py) * s / n, zmx)
                        if cur_kind == "wall":
                            r["walls"] += math.hypot(bx - ax, by - ay) * abs(max(az, bz, dz) - zmn)
                        continue
                    x0, x1 = min(ax, bx, dx), max(ax, bx, dx)
                    y0, y1 = min(ay, by, dy), max(ay, by, dy)
                    for gx in range(math.floor(x0), math.floor(x1) + 1):
                        for gy in range(math.floor(y0), math.floor(y1) + 1):
                            px, py = gx + 0.5, gy + 0.5
                            w0 = ((bx - px) * (dy - py) - (dx - px) * (by - py)) / area2
                            w1 = ((dx - px) * (ay - py) - (ax - px) * (dy - py)) / area2
                            if w0 >= -0.25 and w1 >= -0.25 and w0 + w1 <= 1.25:
                                put(r, px, py, az * w0 + bz * w1 + dz * (1 - w0 - w1))
                    ux, uy, uz = bx - ax, by - ay, bz - az
                    wx, wy, wz = dx - ax, dy - ay, dz - az
                    cx_, cy_, cz_ = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
                    A = 0.5 * math.sqrt(cx_ * cx_ + cy_ * cy_ + cz_ * cz_)
                    if cur_kind == "roof":
                        # true face area and mean height of the roof skin
                        if A > 1e-4:
                            r["roof"].append(((az + bz + dz) / 3, A, max(az, bz, dz)))
                    elif cur_up and A > 1e-4 and abs(cz_) > 0.7 * 2 * A:
                        # fallback roof candidates (models without a "roof_planes" group): faces facing up / down
                        r["up"].append(((az + bz + dz) / 3, A, max(az, bz, dz)))
            elif c == "o ":
                m = ID.search(line)
                raw = line[2:].strip()
                obj_id = m.group(1) if m else "o:" + raw          # models named without an OSM id (survey-hNN, library_...)
                obj_name = raw.split("_", 1)[-1]
                rec(obj_id)["name"] = obj_name
            elif c == "g ":
                g = line[2:].strip()
                m = ID.search(g)
                cur_id = m.group(1) if m else obj_id
                low = g.lower()
                cur_kind = ("roof" if "roof_planes" in low else "wall" if "exterior_walls" in low
                            else "other" if (low.startswith("roof_") or "parapet" in low or "coping" in low or "roof" in low or "eave" in low)
                            else "misc" if not m else None)        # non-standard models: every part counts
                cur_up = cur_kind in ("other", "misc") and not any(s in low for s in ("interior", "room_", "floor", "ceiling", "ground"))
    out = {}
    for i, r in objs.items():
        if r["zmin"] > 1e8:
            continue
        roof = sorted(r["roof"])
        fallback = not roof
        if fallback:        # up-facing faces at least 2.5 m above the ground: the largest roof areas decide
            roof = sorted(t for t in r["up"] if t[0] > r["zmin"] + 2.5)
        tot = sum(a for _, a, _ in roof)

        def q(p):
            acc = 0.0
            for z, a, _ in roof:
                acc += a
                if acc >= p * tot:
                    return z
            return roof[-1][0] if roof else None
        out[i] = {"name": r["name"], "ground": round(r["zmin"] + OZ, 2),
                  "roof_p10": round(q(0.1) + OZ, 2) if roof else None, "roof_p50": round(q(0.5) + OZ, 2) if roof else None,
                  "roof_max": round(max(m for _, _, m in roof) + OZ, 2) if roof else None,
                  "roof_area": round(tot, 1), "wall_area": round(r["walls"], 1), "roof_fallback": fallback,
                  "cells": [[i_, k_, round(z_ + OZ, 1)] for (i_, k_), z_ in sorted(r["cells"].items())]}   # [x, z, top elevation]
    return out


def main():
    root, outp = sys.argv[1], sys.argv[2]
    res = json.load(open(outp, encoding="utf-8")) if os.path.exists(outp) else {}
    for n in sorted(os.listdir(root)):
        d = os.path.join(root, n)
        if not os.path.isdir(d) or n in res:
            continue
        objs = [f for f in os.listdir(d) if f.endswith(".obj")]
        if not objs:
            continue
        res[n] = scan(os.path.join(d, objs[0]))
        print(n, len(res[n]), flush=True)
        json.dump(res, open(outp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
