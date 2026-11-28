"""Bring the school's official campus map data (map.nuist.edu.cn) into game coordinates.

Inputs : data/official/pois.json (downloaded POIs by category + bus route), data/official/transform.json
         (fit: [mapX, mapY] = [x, z, h, 1] @ A), web/public/campus/campus.json (current footprints and heights)
Output : data/official/local.json  {names: {building id: official name}, pois: [...], bus: {route, stops}}

Usage: .venv/Scripts/python.exe tools/official_import.py
"""
import json
import math
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
off = json.loads((OFF / "pois.json").read_text(encoding="utf-8"))
A = np.array(json.loads((OFF / "transform.json").read_text(encoding="utf-8"))["A"])
G_inv = np.linalg.inv(A[:2].T)
campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
W, D = campus["size"]

BUILDING_CATS = {"002001": "校内场馆", "002002": "教学科研", "002003": "学生宿舍", "002004": "行政办公",
                 "002005": "家属住宅", "002006": "文化风景", "002999": "其他楼宇"}
SERVICE_CATS = {"010001": "食堂餐厅", "010002": "商业服务", "010003": "校内医疗", "010004": "邮寄快递", "010006": "停车场",
                "010007": "出入口", "010008": "一卡通", "010009": "打字复印", "010010": "银行网点", "010011": "通信营业厅",
                "010012": "AED", "010016": "体育场馆", "010017": "便民服务", "007001": "师生服务", "011005": "百花"}


def to_local(X, Y, h=0.0):
    x, z = G_inv @ (np.array([X, Y]) - h * A[2] - A[3])
    return float(x), float(z)


def point_in(x, z, pts):
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        xi, zi = pts[i]
        xj, zj = pts[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def dist_to_poly(x, z, pts):
    if point_in(x, z, pts):
        return 0.0
    best = 1e18
    for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1]):
        ex, ez = x1 - x0, z1 - z0
        l2 = ex * ex + ez * ez or 1e-9
        t = max(0, min(1, ((x - x0) * ex + (z - z0) * ez) / l2))
        best = min(best, math.hypot(x - x0 - ex * t, z - z0 - ez * t))
    return best


def inside_map(x, z):
    return abs(x) < W / 2 and abs(z) < D / 2


def main():
    blds = [b for b in campus["buildings"] if b.get("kind") != "wall"]
    names, used, pois = {}, set(), []
    # building POIs: the label sits on the roof, so iterate with the candidate building's height
    for code, cat in BUILDING_CATS.items():
        for p in off.get(code, {}).get("pois", []):
            title = re.sub(r"\s+", "", p.get("title") or "")
            if not title:
                continue
            x, z = to_local(p["x"], p["y"], 0)
            best = None
            for _ in range(2):
                cands = sorted(((dist_to_poly(x, z, b["pts"]), b) for b in blds), key=lambda t: t[0])[:1]
                if not cands:
                    break
                d, b = cands[0]
                best = (d, b)
                x, z = to_local(p["x"], p["y"], b["h"])
            if not inside_map(x, z):
                continue
            d, b = best
            if d <= 12 and str(b["id"]) not in used and cat != "文化风景":
                names[str(b["id"])] = title
                used.add(str(b["id"]))
            else:
                pois.append(dict(name=title, cat=cat, x=round(x, 1), z=round(z, 1)))
    for code, cat in SERVICE_CATS.items():
        for p in off.get(code, {}).get("pois", []):
            x, z = to_local(p["x"], p["y"], 0)
            if inside_map(x, z) and p.get("title"):
                pois.append(dict(name=p["title"].strip(), cat=cat, x=round(x, 1), z=round(z, 1)))
    # bus: official route polyline (ground) and stops, stops ordered along the route
    route = [to_local(X, Y) for X, Y in off["_bus_route"]["pts"]]
    cum = [0.0]
    for (x0, z0), (x1, z1) in zip(route, route[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, z1 - z0))
    stops = []
    for p in off["010013"]["pois"]:
        x, z = to_local(p["x"], p["y"], 0)
        best = None
        for i, ((x0, z0), (x1, z1)) in enumerate(zip(route, route[1:])):
            ex, ez = x1 - x0, z1 - z0
            l2 = ex * ex + ez * ez or 1e-9
            t = max(0, min(1, ((x - x0) * ex + (z - z0) * ez) / l2))
            d = math.hypot(x - x0 - ex * t, z - z0 - ez * t)
            if best is None or d < best[0]:
                best = (d, cum[i] + t * math.sqrt(l2))
        stops.append(dict(name=p["title"], s=round(best[1], 1), off_route_m=round(best[0], 1), x=round(x, 1), z=round(z, 1)))
    stops.sort(key=lambda s: s["s"])
    out = dict(source="map.nuist.edu.cn (南京信息工程大学校园地图) japi/get_poi_by_sort_xq + drawRoute",
               names=names, pois=pois,
               bus=dict(route=[[round(x, 1), round(z, 1)] for x, z in route], stops=stops, length=round(cum[-1], 1)))
    (OFF / "local.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"named buildings {len(names)}, other POIs {len(pois)}, bus route {cum[-1]:.0f} m, stops:",
          [(s['name'], s['off_route_m']) for s in stops])
    from collections import Counter
    print(Counter(p["cat"] for p in pois))


if __name__ == "__main__":
    main()
