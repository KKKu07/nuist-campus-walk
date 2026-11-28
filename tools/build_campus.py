"""Convert OpenStreetMap + orthophoto into the campus data the web game loads.

Usage: .venv/Scripts/python.exe tools/build_campus.py
Input : data/raw/osm.json, web/public/campus/ortho_4k.jpg, data/raw/ortho_meta.json
Output: web/public/campus/campus.json, data/raw/overlay.jpg (alignment check)

Local coordinates: metres, origin = bbox centre, x = east, z = south (three.js convention).
"""
import json
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "web" / "public" / "campus"
CAMPUS_REL = 13070911

meta = json.loads((RAW / "ortho_meta.json").read_text(encoding="utf-8"))
B = meta["bbox"]
LAT0 = (B["south"] + B["north"]) / 2
LON0 = (B["west"] + B["east"]) / 2
phi = math.radians(LAT0)
M_LAT = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
M_LON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi) + 0.118 * math.cos(5 * phi)
WIDTH = (B["east"] - B["west"]) * M_LON
DEPTH = (B["north"] - B["south"]) * M_LAT
FLOOR_H = 3.6


def to_local(lat, lon):
    return round((lon - LON0) * M_LON, 2), round(-(lat - LAT0) * M_LAT, 2)


def ring(geom):
    pts = [to_local(p["lat"], p["lon"]) for p in geom]
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, z1 = pts[i]
        x2, z2 = pts[(i + 1) % len(pts)]
        a += x1 * z2 - x2 * z1
    return abs(a) / 2


def guess_height(tags, pts):
    name = tags.get("name", "")
    if "height" in tags:
        try:
            return float(re.findall(r"[\d.]+", tags["height"])[0]), None
        except (IndexError, ValueError):
            pass
    if "building:levels" in tags:
        try:
            lv = int(float(tags["building:levels"]))
            return lv * FLOOR_H + 1.2, lv
        except ValueError:
            pass
    a = area(pts)
    if a < 80:
        lv = 1
    elif re.search(r"[园苑]\d+[栋号幢]", name):
        lv = 6
    elif "食堂" in name or "餐厅" in name:
        lv = 3
    elif "图书馆" in name:
        lv = 7
    elif "馆" in name or "剧场" in name or "体育" in name:
        return 18.0, None
    elif "楼" in name or tags.get("building") in ("university", "school", "college"):
        lv = 5
    elif tags.get("building") in ("dormitory", "apartments", "residential"):
        lv = 6
    elif a < 300:
        lv = 2
    else:
        lv = 4
    return lv * FLOOR_H + 1.2, lv


def kind_of(tags):
    name = tags.get("name", "")
    b = tags.get("building", "yes")
    if re.search(r"[园苑]\d+[栋号幢]", name) or b in ("dormitory", "apartments", "residential"):
        return "dorm"
    if "食堂" in name or "餐厅" in name:
        return "canteen"
    if "图书馆" in name or "馆" in name or "剧场" in name:
        return "hall"
    if "楼" in name or b in ("university", "school", "college"):
        return "teach"
    return "other"


ROAD_W = {
    "primary": 16, "secondary": 14, "tertiary": 11, "trunk": 18,
    "residential": 7, "unclassified": 7, "service": 5.5, "living_street": 6,
    "pedestrian": 6, "footway": 3, "path": 2.5, "cycleway": 3, "steps": 3, "track": 3.5,
}


def rect_pts(cx, cz, length, width, angle_deg):
    a = math.radians(angle_deg)
    dx, dz = math.cos(a), -math.sin(a)   # long axis
    wx, wz = math.sin(a), math.cos(a)    # short axis
    hl, hw = length / 2, width / 2
    return [(round(cx + sx * dx * hl + sy * wx * hw, 2), round(cz + sx * dz * hl + sy * wz * hw, 2))
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def offset_hull(hull, margin):
    """Push a convex hull outwards by `margin` metres (approximate: move each vertex away from the centroid)."""
    cx = sum(p[0] for p in hull) / len(hull)
    cz = sum(p[1] for p in hull) / len(hull)
    out = []
    for x, z in hull:
        d = math.hypot(x - cx, z - cz) or 1
        out.append((round(x + (x - cx) / d * margin, 2), round(z + (z - cz) / d * margin, 2)))
    return out


def point_in(x, z, pts):
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        xi, zi = pts[i]
        xj, zj = pts[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def notch_ring(ring, poly):
    """Ring minus a convex polygon that crosses its boundary exactly twice (the ring follows the polygon's edges)."""
    def cross_seg(p, q, a, b):
        d = (q[0] - p[0]) * (b[1] - a[1]) - (q[1] - p[1]) * (b[0] - a[0])
        if abs(d) < 1e-9:
            return None
        t = ((a[0] - p[0]) * (b[1] - a[1]) - (a[1] - p[1]) * (b[0] - a[0])) / d
        u = ((a[0] - p[0]) * (q[1] - p[1]) - (a[1] - p[1]) * (q[0] - p[0])) / d
        return (t, (round(p[0] + t * (q[0] - p[0]), 2), round(p[1] + t * (q[1] - p[1]), 2))) if 0 <= t <= 1 and 0 <= u <= 1 else None
    n, m = len(ring), len(poly)
    hits = []
    for i in range(n):
        for j in range(m):
            c = cross_seg(ring[i], ring[(i + 1) % n], poly[j], poly[(j + 1) % m])
            if c:
                hits.append((i, c[0], c[1], j))
    if len(hits) != 2:
        print(f"  warning: zone notch skipped ({len(hits)} boundary crossings, need 2)")
        return ring
    (i1, t1, p1, j1), (i2, t2, p2, j2) = sorted(hits)

    def path(ja, jb):              # polygon vertices between the crossing edges, on the side inside the ring
        fwd = [poly[(ja + 1 + k) % m] for k in range((jb - ja) % m)]
        bwd = [poly[(ja - k) % m] for k in range((ja - jb) % m)]
        return fwd if all(point_in(x, z, ring) for x, z in fwd) else bwd
    probe = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2) if i1 == i2 else ring[(i1 + 1) % n]
    if point_in(probe[0], probe[1], poly):      # the ring stretch c1 -> c2 lies inside the polygon: replace it
        return ring[:i1 + 1] + [p1] + path(j1, j2) + [p2] + ring[i2 + 1:]
    return [p1] + ring[i1 + 1:i2 + 1] + [p2] + path(j2, j1)


def merge_manual(buildings):
    """Add hand-traced buildings (data/manual/extra_buildings.json) and build walled zones. Returns zones."""
    path = ROOT / "data" / "manual" / "extra_buildings.json"
    if not path.exists():
        return []
    spec = json.loads(path.read_text(encoding="utf-8"))
    osm_count = len(buildings)
    added = []
    for i, e in enumerate(spec.get("buildings", [])):
        lv = e.get("lv")
        h = e.get("h", (lv or 4) * FLOOR_H + 1.2)
        base = dict(id=e.get("id", f"manual-{i}"), name=e.get("name", ""), h=round(h, 1), lv=lv,
                    kind=e.get("kind", "apartment" if e.get("group") == "apartment" else "teach"),
                    group=e.get("group", ""), src="manual")
        if "campus" in e:
            base["campus"] = e["campus"]
        for k in ("color", "landmark", "style", "roofc", "hip"):
            if k in e:
                base[k] = e[k]
        if "rect" in e:
            added.append(dict(base, pts=rect_pts(*e["rect"])))
        elif "ring" in e:
            cx, cz, ro, ri, n = e["ring"]
            arc = e.get("arc")      # [deg0, deg1]: only the segments whose middle lies in this arc (x = cos, z = sin)
            for k in range(int(n)):
                a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
                if arc and not arc[0] <= math.degrees(a0 + a1) / 2 <= arc[1]:
                    continue
                pts = [(cx + ri * math.cos(a0), cz + ri * math.sin(a0)), (cx + ro * math.cos(a0), cz + ro * math.sin(a0)),
                       (cx + ro * math.cos(a1), cz + ro * math.sin(a1)), (cx + ri * math.cos(a1), cz + ri * math.sin(a1))]
                added.append(dict(base, id=f"manual-{i}-{k}", pts=[(round(x, 2), round(z, 2)) for x, z in pts]))
        elif "pts" in e:
            added.append(dict(base, pts=[tuple(p) for p in e["pts"]]))
    buildings.extend(added)

    zones = []
    for zspec in spec.get("zones", []):
        if "include_osm_box" in zspec:
            x0, z0, x1, z1 = zspec["include_osm_box"]
            for b in buildings[:osm_count]:
                cx = sum(p[0] for p in b["pts"]) / len(b["pts"])
                cz = sum(p[1] for p in b["pts"]) / len(b["pts"])
                if x0 <= cx <= x1 and z0 <= cz <= z1 and not b["name"]:
                    b.update(group=zspec["group"], campus=False, kind="apartment")
        pts = [p for b in buildings if b.get("group") == zspec["group"] for p in b["pts"]]
        ring_pts = offset_hull(convex_hull(pts), zspec.get("margin", 5))
        for ex in zspec.get("exclude", []):    # walled compounds the convex hull would swallow: cut a notch
            ring_pts = notch_ring(ring_pts, [tuple(p) for p in ex])
        for ox, oz, qx, qz in zspec.get("ring_move", []):   # hand-placed wall corners: vertex nearest (ox, oz), within 2 m
            k = min(range(len(ring_pts)), key=lambda i: math.hypot(ring_pts[i][0] - ox, ring_pts[i][1] - oz))
            if math.hypot(ring_pts[k][0] - ox, ring_pts[k][1] - oz) < 2:
                ring_pts[k] = (qx, qz)
            else:
                print(f"  warning: zone ring_move ({ox}, {oz}) matched no corner")
        zones.append(dict(name=zspec["name"], pts=ring_pts))
        for b in buildings[:osm_count]:
            if b.get("group") != zspec["group"] and any(point_in(x, z, ring_pts) for x, z in b["pts"]):
                print(f"  warning: OSM building {b['name'] or b['id']} touches zone {zspec['name']}")
        wall_h = zspec.get("wall_h", 0)
        if wall_h:
            t = 0.2
            for k in range(len(ring_pts)):
                (x0, z0), (x1, z1) = ring_pts[k], ring_pts[(k + 1) % len(ring_pts)]
                L = math.hypot(x1 - x0, z1 - z0) or 1
                nx, nz = (z1 - z0) / L * t, -(x1 - x0) / L * t
                buildings.append(dict(id=f"wall-{len(zones)}-{k}", name="", h=wall_h, lv=None, kind="wall",
                                      group="wall", src="manual", campus=False,
                                      pts=[(round(x0 + nx, 2), round(z0 + nz, 2)), (round(x1 + nx, 2), round(z1 + nz, 2)),
                                           (round(x1 - nx, 2), round(z1 - nz, 2)), (round(x0 - nx, 2), round(z0 - nz, 2))]))
    print(f"manual buildings +{len(added)}, zones {len(zones)}")
    return zones


def apply_overrides(buildings):
    """Per-name corrections from data/manual/building_overrides.json (+ photo_index.json from prepare_photos.py)."""
    path = ROOT / "data" / "manual" / "building_overrides.json"
    if not path.exists():
        return
    spec = json.loads(path.read_text(encoding="utf-8"))["buildings"]
    pidx_path = ROOT / "data" / "manual" / "photo_index.json"
    photos = json.loads(pidx_path.read_text(encoding="utf-8")) if pidx_path.exists() else {}
    hit = set()
    for b in buildings:
        o = spec.get(b["name"])
        if not o:
            continue
        hit.add(b["name"])
        if "lv" in o or "h" in o:
            b["fixed"] = True          # explicit user/photo correction: measured heights must not override it
        if "lv" in o:
            b["lv"] = o["lv"]
            b["h"] = round(o["lv"] * FLOOR_H + 1.2, 1)
        if "h" in o:
            b["h"] = o["h"]
        for k in ("color", "landmark", "label", "confidence", "style"):
            if k in o:
                b[k] = o[k]
        if "pts" in o:                 # corrected outline (OSM footprint in the wrong place)
            b["pts"] = [list(q) for q in o["pts"]]
        if b["name"] in photos:
            b["photos"] = photos[b["name"]]
    missing = set(spec) - hit
    print(f"overrides applied to {len(hit)} names" + (f"; not found: {sorted(missing)}" if missing else ""))
    # by building id (unnamed OSM buildings, or a name shared by several): pts / h / lv, same meaning as above
    by_id = json.loads(path.read_text(encoding="utf-8")).get("by_id", {})
    nid = 0
    for b in buildings:
        o = by_id.get(str(b["id"]))
        if not o:
            continue
        nid += 1
        if "lv" in o or "h" in o:
            b["fixed"] = True
        if "lv" in o:
            b["lv"] = o["lv"]
            b["h"] = round(o["lv"] * FLOOR_H + 1.2, 1)
        if "h" in o:
            b["h"] = o["h"]
        if "pts" in o:
            b["pts"] = [list(q) for q in o["pts"]]
    if by_id:
        print(f"overrides by id: {nid} of {len(by_id)}")


def load_pois():
    """Landmarks without a building (gates, flag plaza, radar tower) from data/manual/pois.json."""
    path = ROOT / "data" / "manual" / "pois.json"
    if not path.exists():
        return []
    pidx_path = ROOT / "data" / "manual" / "photo_index.json"
    photos = json.loads(pidx_path.read_text(encoding="utf-8")) if pidx_path.exists() else {}
    out = []
    for p in json.loads(path.read_text(encoding="utf-8"))["pois"]:
        q = {k: p[k] for k in ("name", "x", "z", "rot", "landmark", "field", "plots", "dish", "path", "shops",
                               "span", "pillars", "booth", "barrier") if k in p}
        if p["name"] in photos:
            q["photos"] = photos[p["name"]]
        out.append(q)
    return out


def main():
    osm = json.loads((RAW / "osm.json").read_text(encoding="utf-8"))
    buildings, roads, water, boundary, pitches = [], [], [], [], []
    NO_WATER = json.loads((ROOT / "data" / "manual" / "building_overrides.json").read_text(encoding="utf-8")).get("remove_water", {})
    for e in osm["elements"]:
        t = e.get("tags", {})
        if e["type"] == "relation" and e["id"] == CAMPUS_REL:
            for m in e.get("members", []):
                if m.get("role") == "outer" and "geometry" in m:
                    boundary.append(ring(m["geometry"]))
            continue
        polys = []
        if e["type"] == "way" and "geometry" in e:
            polys = [ring(e["geometry"])]
        elif e["type"] == "relation":
            polys = [ring(m["geometry"]) for m in e.get("members", []) if m.get("role") == "outer" and "geometry" in m]
        if "building" in t:
            for pts in polys:
                if len(pts) < 3:
                    continue
                h, lv = guess_height(t, pts)
                buildings.append(dict(id=e["id"], name=t.get("name", ""), h=round(h, 1), lv=lv,
                                      kind=kind_of(t), pts=pts))
        elif "highway" in t and e["type"] == "way":
            hw = t["highway"]
            if hw in ROAD_W:
                pts = [to_local(p["lat"], p["lon"]) for p in e["geometry"]]
                rd = dict(id=e["id"], kind=hw, w=ROAD_W[hw], name=t.get("name", ""), pts=pts)
                if t.get("oneway") in ("yes", "1", "-1") or t.get("junction") == "roundabout":
                    rd["oneway"] = True
                roads.append(rd)
        elif t.get("leisure") in ("pitch", "track", "stadium", "sports_centre") or t.get("landuse") == "construction":
            pitches.extend(p for p in polys if len(p) >= 3)
        elif t.get("natural") == "water" or t.get("water") or t.get("leisure") == "swimming_pool":
            if str(e["id"]) in NO_WATER:      # OSM water that is not there (building_overrides.json remove_water)
                continue
            for pts in polys:
                if len(pts) >= 3:
                    water.append(dict(name=t.get("name", ""), pts=pts))

    rw_path = ROOT / "data" / "manual" / "road_widths.json"
    if rw_path.exists():   # measured on our aerial photo by tools/landcover.py
        rw = json.loads(rw_path.read_text(encoding="utf-8"))
        for r in roads:
            m = rw.get(str(r.get("id")))
            if m:
                r["w"], r["measured"] = m["w"], True
    apply_road_audit(roads)
    zones = merge_manual(buildings)
    apply_overrides(buildings)
    apply_measured(buildings)
    pois = load_pois()
    official_bus, markers, flowers = apply_official(buildings, pois, roads)
    rm = json.loads((ROOT / "data" / "manual" / "building_overrides.json").read_text(encoding="utf-8")).get("remove_ids", {})
    gone = [b for b in buildings if str(b["id"]) in rm]
    for b in gone:
        buildings.remove(b)
    print(f"removed {len(gone)} buildings that do not exist: {[b['name'] or b['id'] for b in gone]}")
    apply_wall_colors(buildings)

    # Trees: sample the orthophoto for vegetation, skip anything under a building footprint.
    img = Image.open(OUT / "ortho_4k.jpg").convert("RGB")
    iw, ih = img.size
    small = img.resize((iw // 2, ih // 2))
    sw, sh = small.size
    px = small.load()
    mask = Image.new("L", (sw, sh), 0)
    md = ImageDraw.Draw(mask)

    def to_img(x, z, w, h):
        return (x + WIDTH / 2) / WIDTH * w, (z + DEPTH / 2) / DEPTH * h

    for b in buildings:
        md.polygon([to_img(x, z, sw, sh) for x, z in b["pts"]], fill=255)
    for wv in water:
        md.polygon([to_img(x, z, sw, sh) for x, z in wv["pts"]], fill=255)
    for pts in pitches:
        md.polygon([to_img(x, z, sw, sh) for x, z in pts], fill=255)
    for r in roads:
        if r["w"] >= 5:
            md.line([to_img(x, z, sw, sh) for x, z in r["pts"]], fill=255, width=max(1, int(r["w"] / WIDTH * sw)))
    mk = mask.load()
    campus = Image.new("L", (sw, sh), 0)
    cd = ImageDraw.Draw(campus)
    for bd in boundary:
        cd.polygon([to_img(x, z, sw, sh) for x, z in bd], fill=255)
    ck = campus.load()
    rnd = random.Random(7)
    inside, outside = [], []
    step = max(1, int(round(5.0 / (WIDTH / sw))))  # one sample roughly every 5 m
    # tree canopy = green AND rough texture; lawns and artificial turf are green but smooth
    import numpy as np
    import cv2
    arr = np.asarray(small, dtype=np.float32)
    gch = arr[..., 1]
    rough = np.sqrt(np.maximum(cv2.blur(gch * gch, (5, 5)) - cv2.blur(gch, (5, 5)) ** 2, 0))
    for j in range(0, sh, step):
        for i in range(0, sw, step):
            r_, g_, b_ = px[i, j]
            exg = 2 * g_ - r_ - b_
            if exg > 22 and g_ < 175 and rough[j, i] > 9 and mk[i, j] == 0:
                x = (i + rnd.random() * step) / sw * WIDTH - WIDTH / 2
                z = (j + rnd.random() * step) / sh * DEPTH - DEPTH / 2
                t = [round(x, 1), round(z, 1), round(0.8 + rnd.random() * 0.6, 2)]
                (inside if ck[i, j] else outside).append(t)
    assign_roofs(buildings, img)
    rnd.shuffle(outside)
    trees = inside[:16000] + outside[:14000]
    tv2 = ROOT / "data" / "manual" / "trees_v2.json"
    if tv2.exists():       # individual trees from the drone DSM (tools/landcover.py): [x, z, height, crown radius, species]
        trees = json.loads(tv2.read_text(encoding="utf-8"))
    if official_bus:
        official_bus = snap_bus(official_bus, roads)
    paving_colours(roads, img)
    roof_colours(buildings)
    junctions = road_junctions(osm, roads, boundary)
    trees = street_trees(trees, roads, buildings, water, boundary, junctions)
    trees = trees_off_paving(trees)
    for q in pois:              # open fields (observation field etc.) have no trees inside
        if "field" in q:
            fx0, fz0, fx1, fz1 = q["field"]
            trees = [t for t in trees if not (fx0 <= t[0] <= fx1 and fz0 <= t[1] <= fz1)]

    data = dict(
        origin=dict(lat=LAT0, lon=LON0), bbox=B, size=[round(WIDTH, 1), round(DEPTH, 1)],
        source="OpenStreetMap contributors (ODbL); imagery Esri World Imagery (prototype only)",
        buildings=buildings, roads=roads, water=water, boundary=boundary, trees=trees, zones=zones, pois=pois,
        bus=official_bus or bus_route(osm, buildings, pois, boundary), ebikes=ebike_stations(buildings, pois, roads),
        markers=markers, flowers=flowers,
        sports=export_sports(osm),
        junctions=junctions,
        models=apply_models(buildings, pois),
        generic=apply_generic(buildings),
        # grade-separated crossings (web/src/underpass.js): 中苑 <-> 东苑 only under 盘城新街
        underpasses=(json.loads((ROOT / "data" / "manual" / "underpasses.json").read_text(encoding="utf-8"))["underpasses"]
                     if (ROOT / "data" / "manual" / "underpasses.json").exists() else []),
    )
    (OUT / "campus.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Overlay for a visual alignment check.
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    for b in buildings:
        d.polygon([to_img(x, z, iw, ih) for x, z in b["pts"]], outline=(255, 60, 0), width=3)
    for r in roads:
        d.line([to_img(x, z, iw, ih) for x, z in r["pts"]], fill=(255, 230, 0), width=2)
    for bd in boundary:
        d.polygon([to_img(x, z, iw, ih) for x, z in bd], outline=(0, 200, 255), width=4)
    ov.resize((iw // 2, ih // 2)).save(RAW / "overlay.jpg", quality=82)
    print(f"size {WIDTH:.0f} x {DEPTH:.0f} m | buildings {len(buildings)} | roads {len(roads)} | "
          f"water {len(water)} | trees {len(trees)} | boundary rings {len(boundary)}")



# ---------------------------------------------------------------------------
# v0.2 additions: roof shapes, campus bus route, shared e-bike stations
# ---------------------------------------------------------------------------
def min_area_rect(pts):
    """Minimum-area oriented rectangle of a polygon: (cx, cz, length, width, angle_rad of long axis)."""
    hull = convex_hull([tuple(p) for p in pts])
    best = None
    for i in range(len(hull)):
        (x0, z0), (x1, z1) = hull[i], hull[(i + 1) % len(hull)]
        a = math.atan2(z1 - z0, x1 - x0)
        c, s = math.cos(a), math.sin(a)
        us = [x * c + z * s for x, z in hull]
        vs = [-x * s + z * c for x, z in hull]
        area_ = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area_ < best[0]:
            um, vm = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (area_, um * c - vm * s, um * s + vm * c, max(us) - min(us), max(vs) - min(vs), a)
    _, cx, cz, L, Wd, a = best
    if Wd > L:
        L, Wd, a = Wd, L, a + math.pi / 2
    return cx, cz, L, Wd, a


def assign_roofs(buildings, img):
    """Hip roofs for rectangular low-rise buildings whose real roof is tiled (red/blue-grey in the aerial photo)."""
    iw, ih = img.size
    px = img.load()
    n_hip = 0
    for b in buildings:
        if b.get("kind") == "wall" or len(b["pts"]) < 4:
            continue
        cx, cz, L, Wd, a = min_area_rect(b["pts"])
        rect_ratio = area(b["pts"]) / max(L * Wd, 1)
        rs = gs = bs = n = 0
        for du in (-0.25, 0, 0.25):
            for dv in (-0.2, 0, 0.2):
                x = cx + math.cos(a) * du * L - math.sin(a) * dv * Wd
                z = cz + math.sin(a) * du * L + math.cos(a) * dv * Wd
                i = int((x + WIDTH / 2) / WIDTH * iw)
                j = int((z + DEPTH / 2) / DEPTH * ih)
                if 0 <= i < iw and 0 <= j < ih:
                    r, g, bl = px[i, j]
                    rs += r; gs += g; bs += bl; n += 1
        if not n:
            continue
        r, g, bl = rs / n, gs / n, bs / n
        tiled = (r > g + 18 and r > bl + 25) or (bl > r + 8 and bl > g - 4 and r < 140)
        lv = b.get("lv") or round(b["h"] / FLOOR_H)
        if rect_ratio > 0.86 and lv <= 8 and Wd > 8 and L < 160 and (tiled or b.get("style") == "classical" or b.get("hip")):
            b["roof"] = dict(type="hip", obb=[round(cx, 2), round(cz, 2), round(L, 2), round(Wd, 2), round(a, 4)],
                             rise=round(min(Wd * 0.32, 7.0), 2))
            if b.get("measured"):   # the DSM height includes part of the pitched roof
                b["h"] = round(max(b["h"] - 0.5 * b["roof"]["rise"], 3.0), 1)
            n_hip += 1
    print(f"hip roofs: {n_hip}")


def bus_route(osm, buildings, pois, boundary):
    """Campus shuttle loop: shortest paths over the road graph between named stops (campus roads preferred)."""
    import heapq
    ok = {"primary": 1, "secondary": 1, "tertiary": 1, "residential": 1, "unclassified": 1, "service": 1,
          "living_street": 1, "pedestrian": 1.2, "footway": 1.6, "path": 2.5}
    inside = lambda x, z: any(point_in(x, z, r) for r in boundary)
    pos, adj = {}, {}
    for e in osm["elements"]:
        t = e.get("tags", {})
        if e["type"] != "way" or t.get("highway") not in ok or "nodes" not in e:
            continue
        pen = ok[t["highway"]]
        for nid, g in zip(e["nodes"], e["geometry"]):
            pos[nid] = to_local(g["lat"], g["lon"])
        for a, b in zip(e["nodes"], e["nodes"][1:]):
            (x0, z0), (x1, z1) = pos[a], pos[b]
            w = math.hypot(x1 - x0, z1 - z0) * pen * (1 if inside((x0 + x1) / 2, (z0 + z1) / 2) else 4)
            adj.setdefault(a, []).append((b, w))
            adj.setdefault(b, []).append((a, w))
    where = {b["name"]: (sum(p[0] for p in b["pts"]) / len(b["pts"]), sum(p[1] for p in b["pts"]) / len(b["pts"]))
             for b in buildings if b.get("name")}
    where.update({p["name"]: (p["x"], p["z"]) for p in pois})
    names = ["东大门", "国际教育学院", "气象楼", "文德楼", "大学生活动中心", "尚贤楼", "图书馆", "逸夫楼",
             "见山园", "信息科技大楼", "西苑新食堂", "文园11栋"]
    stops = [(n, where[n]) for n in names if n in where]
    campus_nodes = [n for n in adj if inside(*pos[n])]
    snap = lambda xy: min(campus_nodes, key=lambda n: (pos[n][0] - xy[0]) ** 2 + (pos[n][1] - xy[1]) ** 2)

    def path(a, b):
        dist, prev, pq = {a: 0}, {}, [(0, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w in adj[u]:
                if d + w < dist.get(v, 1e18):
                    dist[v] = d + w; prev[v] = u
                    heapq.heappush(pq, (d + w, v))
        if b not in dist:
            return None
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return out[::-1]

    route, stop_s, s = [], [], 0.0
    snapped = [(n, snap(xy)) for n, xy in stops]
    for k in range(len(snapped)):
        name, a = snapped[k]
        b = snapped[(k + 1) % len(snapped)][1]
        seg = path(a, b)
        if seg is None:
            print("  bus: no path after", name)
            continue
        if not route:
            route.append(pos[seg[0]])
        stop_s.append(dict(name=name, s=round(s, 1)))
        for n in seg[1:]:
            x, z = pos[n]
            s += math.hypot(x - route[-1][0], z - route[-1][1])
            route.append((x, z))
    print(f"bus loop {s:.0f} m, {len(stop_s)} stops")
    return dict(route=[[round(x, 2), round(z, 2)] for x, z in route], stops=stop_s, length=round(s, 1))


def ebike_stations(buildings, pois, roads):
    """4-6 shared e-bikes parked beside the road nearest to each popular place."""
    want = ["图书馆", "文德楼", "气象楼", "尚贤楼", "逸夫楼", "见山园", "东苑食堂", "中苑美食城", "西苑新食堂",
            "大学生活动中心", "藕舫楼", "东大门", "老校门", "行政楼", "信息科技大楼", "东苑体育馆"]
    # hand-placed rows in data/manual/ebike_spots.json instead (东大门: the auto spot fell on the 1.5 m strip between
    # the plaza and the north lane); skipped, not removed, so the other stations keep their bike counts (k % 3)
    hand = {"东大门"}
    where = {b["name"]: (sum(p[0] for p in b["pts"]) / len(b["pts"]), sum(p[1] for p in b["pts"]) / len(b["pts"]))
             for b in buildings if b.get("name")}
    where.update({p["name"]: (p["x"], p["z"]) for p in pois})
    out = []
    for k, name in enumerate(want):
        if name not in where or name in hand:
            continue
        cx, cz = where[name]
        best = None
        for r in roads:
            if r["w"] < 4:
                continue
            for (x0, z0), (x1, z1) in zip(r["pts"], r["pts"][1:]):
                ex, ez = x1 - x0, z1 - z0
                l2 = ex * ex + ez * ez or 1e-9
                t = max(0, min(1, ((cx - x0) * ex + (cz - z0) * ez) / l2))
                qx, qz = x0 + ex * t, z0 + ez * t
                d = math.hypot(cx - qx, cz - qz)
                if best is None or d < best[0]:
                    best = (d, qx, qz, ex, ez, r["w"])
        if not best or best[0] > 90:
            continue
        _, qx, qz, ex, ez, w = best
        L = math.hypot(ex, ez) or 1
        dx, dz = ex / L, ez / L
        nx, nz = -dz, dx
        side = 1 if (cx - qx) * nx + (cz - qz) * nz > 0 else -1
        off = w / 2 + 1.6
        for i in range(4 + k % 3):
            x = qx + nx * off * side + dx * (i - 2) * 0.9
            z = qz + nz * off * side + dz * (i - 2) * 0.9
            out.append([round(x, 2), round(z, 2), round(math.atan2(nx * side, nz * side), 3)])
    import importlib.util                          # hand-checked rows (data/manual/ebike_spots.json), e.g. 图书馆前广场两侧
    spec = importlib.util.spec_from_file_location("apply_ebike_spots", Path(__file__).with_name("apply_ebike_spots.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    manual = mod.manual_spots()
    out += manual
    print(f"e-bikes: {len(out)} ({len(manual)} manual)")
    return out


def apply_measured(buildings):
    """Heights measured from our drone photos (tools/recon_heights.py) replace estimates; tall parts become towers."""
    path = ROOT / "data" / "manual" / "measured_heights.json"
    if not path.exists():
        return
    m = json.loads(path.read_text(encoding="utf-8"))
    # buildings checked in docs/building-audit.csv ("实测核对" = 可采用, tools/make_measured_adopt.py): the re-registered
    # DSM height (measured_heights_v2.json, tools/dsm_register.py) agrees with the old one or the local model's main roof
    ad_path, v2_path = ROOT / "data" / "manual" / "measured_adopt.json", ROOT / "data" / "manual" / "measured_heights_v2.json"
    adopt = json.loads(ad_path.read_text(encoding="utf-8"))["buildings"] if ad_path.exists() and v2_path.exists() else {}
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))["buildings"] if adopt else {}
    n = n_v2 = 0
    for b in buildings:
        bid = str(b["id"])
        if bid in adopt and bid in v2 and not b.get("fixed") and b.get("kind") != "wall":
            b["h"] = round(max(v2[bid]["h"], 3.0), 1)      # the verified value itself, not the p95 fallback below
            b["lv"] = max(1, round((b["h"] - 1.2) / FLOOR_H))
            b["measured"] = True
            n += 1
            n_v2 += 1
            continue
        r = m["buildings"].get(bid)
        if not r or b.get("fixed") or b.get("kind") == "wall" or r["cover"] < 0.45 or not (2.5 <= r["h"] <= 130):
            continue
        h70, p95 = r["h"], r["p95"]
        if h70 >= 0.75 * p95:
            h = h70
        elif r["cover"] >= 0.6:
            h = max(h70, p95 - 3)        # courtyard or ground inside the outline pulls the 70th percentile down
        else:
            continue
        if h < 0.5 * b["h"] and r["cover"] < 0.75:
            continue                     # thin coverage and a big drop: keep the estimate
        b["h"] = round(max(h, 3.0), 1)
        b["lv"] = max(1, round((b["h"] - 1.2) / FLOOR_H))
        b["measured"] = True
        n += 1
    manual_pts = [b["pts"] for b in buildings if b.get("src") == "manual" and b.get("kind") != "wall"]
    added = 0
    for i, tw in enumerate(m.get("towers", [])):
        if any(point_in(tw["cx"], tw["cz"], pts) for pts in manual_pts):
            continue          # already modelled by hand (e.g. 气象楼 main tower)
        pts = rect_pts(tw["cx"], tw["cz"], tw["L"], tw["W"], -math.degrees(tw["angle_rad"]))
        th = round(tw["h"] - 4, 1)   # p95 includes rooftop plant; the main roof is a few metres lower
        parent = next((b for b in buildings if (b.get("name") or str(b["id"])) == tw["of"]), {})
        buildings.append(dict(id=f"tower-{i}", name="", h=th, lv=max(1, round((th - 1.2) / FLOOR_H)),
                              kind=parent.get("kind", "teach"), style=parent.get("style", "modern"), color=parent.get("color"),
                              group="tower", src="measured", pts=pts))
        added += 1
    print(f"measured heights applied to {n} buildings ({n_v2} from measured_heights_v2.json), towers added {added}")


def apply_official(buildings, pois, roads):
    """School campus map (map.nuist.edu.cn) data from tools/official_import.py: names, bus, gates, markers, flowers."""
    path = ROOT / "data" / "official" / "local.json"
    if not path.exists():
        return None, [], []
    d = json.loads(path.read_text(encoding="utf-8"))
    byid = {str(b["id"]): b for b in buildings}
    renamed = 0
    for bid, name in d["names"].items():
        b = byid.get(bid)
        if b and b.get("kind") != "wall" and not b.get("label") and b.get("name") != name:
            b["osm_name"] = b.get("name", "")
            b["name"] = name
            renamed += 1
    cent = lambda b: (sum(p[0] for p in b["pts"]) / len(b["pts"]), sum(p[1] for p in b["pts"]) / len(b["pts"]))
    named_now = {b["name"] for b in buildings if b.get("name")}
    building_cats = {"校内场馆", "教学科研", "学生宿舍", "行政办公", "家属住宅", "其他楼宇"}
    markers, flowers = [], []
    for p in d["pois"]:
        if p["cat"] in building_cats:
            if p["name"] in named_now:
                continue
            cands = [(math.hypot(cent(b)[0] - p["x"], cent(b)[1] - p["z"]), b) for b in buildings
                     if not b.get("name") and b.get("kind") != "wall"]
            if cands:
                dmin, b = min(cands, key=lambda t: t[0])
                if dmin < 28:
                    b["name"] = p["name"]
                    named_now.add(p["name"])
                    renamed += 1
                    continue
        if p["cat"] == "百花":
            flowers.append([p["x"], p["z"], p["name"]])
            continue
        if p["cat"] == "出入口" and not any(math.hypot(q["x"] - p["x"], q["z"] - p["z"]) < 40 for q in pois):
            best = None
            for r in roads:
                for (x0, z0), (x1, z1) in zip(r["pts"], r["pts"][1:]):
                    ex, ez = x1 - x0, z1 - z0
                    l2 = ex * ex + ez * ez or 1e-9
                    t = max(0, min(1, ((p["x"] - x0) * ex + (p["z"] - z0) * ez) / l2))
                    dd = math.hypot(p["x"] - x0 - ex * t, p["z"] - z0 - ez * t)
                    if best is None or dd < best[0]:
                        best = (dd, ex, ez, x0 + ex * t, z0 + ez * t)
            dd, ex, ez, qx, qz = best
            L = math.hypot(ex, ez) or 1
            nx, nz = -ez / L, ex / L                      # across the road
            gx, gz = (qx, qz) if dd < 25 else (p["x"], p["z"])
            pois.append(dict(name=p["name"], x=round(gx, 1), z=round(gz, 1), rot=round(math.degrees(math.atan2(-nz, nx)), 1),
                             landmark="gate_generic"))
            continue
        markers.append(p)
    bus = d.get("bus")
    if bus:
        bus = dict(route=bus["route"], stops=[dict(name=s["name"], s=s["s"]) for s in bus["stops"]], length=bus["length"])
    print(f"official: renamed/named {renamed} buildings, gates {sum(1 for q in pois if q.get('landmark') == 'gate_generic')}, "
          f"markers {len(markers)}, flowers {len(flowers)}, bus {'official' if bus else 'computed'}")
    return bus, markers, flowers


def apply_wall_colors(buildings):
    """Wall colours sampled from the official illustrated map (tools/official_colors.py); skip ones hidden by trees."""
    path = ROOT / "data" / "official" / "wall_colors.json"
    if not path.exists():
        return
    cols = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in buildings:
        c = cols.get(str(b["id"]))
        if not c or b.get("color") or b.get("kind") == "wall":
            continue
        r, g, bl = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * bl
        if (g > r + 8 and g > bl + 4) or lum < 95 or lum > 248:
            continue
        # lift the drawing's muted tones a little towards daylight values
        k = min(1.18, 225 / max(lum, 1))
        b["color"] = "#%02x%02x%02x" % tuple(min(255, int(v * k)) for v in (r, g, bl))
        n += 1
    print(f"wall colours from the official map: {n}")


def export_sports(osm):
    """OSM pitches / tracks as oriented rectangles for the 3D sports facilities (web/src/sports.js)."""
    out = []
    for e in osm["elements"]:
        t = e.get("tags", {})
        if t.get("leisure") not in ("pitch", "track") or e["type"] != "way" or "geometry" not in e:
            continue
        pts = [to_local(p["lat"], p["lon"]) for p in e["geometry"]]
        if len(pts) < 4:
            continue
        cx, cz, L, Wd, a = min_area_rect(pts)
        if L < 8 or Wd < 5:
            continue
        sport = t.get("sport", "")
        if t.get("leisure") == "track" or (sport == "athletics" and L > 120):
            kind = "track"
        elif "soccer" in sport:
            kind = "soccer"
        elif "basketball" in sport:
            kind = "basketball"
        elif "tennis" in sport:
            kind = "tennis"
        elif "volleyball" in sport:
            kind = "volleyball"
        elif sport == "athletics":
            kind = "track" if L > 90 else "court"
        else:
            kind = "court"
        out.append(dict(kind=kind, sport=sport, name=t.get("name", ""), obb=[round(cx, 2), round(cz, 2), round(L, 2), round(Wd, 2), round(a, 4)]))
    # running tracks: large red rubber rings in the land-cover map (OSM usually only has the inner pitch)
    lc_path = OUT / "landcover.png"
    if lc_path.exists():
        import cv2
        import numpy as np
        lc = np.asarray(Image.open(lc_path))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate((lc == 6).astype(np.uint8), np.ones((7, 7), np.uint8)))
        for j in range(1, n):
            if stats[j, cv2.CC_STAT_AREA] < 1500:
                continue
            ys, xs = np.nonzero(lab == j)
            (cx, cz), (rw, rh), ang = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
            L, Wd = max(rw, rh), min(rw, rh)
            if not (120 < L < 230 and 60 < Wd < 130):
                continue
            a = math.radians(ang if rw >= rh else ang + 90)
            out.append(dict(kind="oval", sport="athletics", name="", obb=[round(cx + 0.5 - WIDTH / 2, 2), round(cz + 0.5 - DEPTH / 2, 2),
                                                                           round(L, 2), round(Wd, 2), round(a, 4)]))
        # faded tracks next to the official map's 田径场 / 运动场 venues: looser red threshold in a window around them
        lp = ROOT / "data" / "official" / "local.json"
        rgb = np.asarray(Image.open(OUT / "ortho.jpg").convert("RGB").resize(lc.shape[::-1])).astype(np.int16)
        venues = [q for q in json.loads(lp.read_text(encoding="utf-8"))["pois"] if q["cat"] == "体育场馆" and re.search("田径|运动场", q["name"])] if lp.exists() else []
        for v in venues:
            if any(o["kind"] == "oval" and math.hypot(o["obb"][0] - v["x"], o["obb"][1] - v["z"]) < 60 for o in out):
                continue
            i0, j0 = int(v["x"] + WIDTH / 2), int(v["z"] + DEPTH / 2)
            win = rgb[max(0, j0 - 130):j0 + 130, max(0, i0 - 130):i0 + 130]
            faded = ((win[..., 0] - np.maximum(win[..., 1], win[..., 2])) > 14) & (win[..., 0] > 110)
            m = cv2.morphologyEx(faded.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            n2, lab2, st2, _ = cv2.connectedComponentsWithStats(m)
            if n2 < 2:
                continue
            j = 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA]))
            ys, xs = np.nonzero(lab2 == j)
            (cx, cz), (rw, rh), ang = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
            L, Wd = max(rw, rh), min(rw, rh)
            if 120 < L < 230 and 60 < Wd < 130:
                a2 = math.radians(ang if rw >= rh else ang + 90)
                out.append(dict(kind="oval", sport="athletics", name=v["name"], obb=[round(cx + max(0, i0 - 130) + 0.5 - WIDTH / 2, 2),
                           round(cz + max(0, j0 - 130) + 0.5 - DEPTH / 2, 2), round(L, 2), round(Wd, 2), round(a2, 4)]))
    # red courts are not tracks
    courts = [o for o in out if o["kind"] in ("basketball", "court", "tennis", "volleyball")]
    out = [o for o in out if o["kind"] != "oval" or not any(
        abs(o["obb"][0] - c["obb"][0]) < c["obb"][2] / 2 and abs(o["obb"][1] - c["obb"][1]) < c["obb"][2] / 2 for c in courts)]
    mp = ROOT / "data" / "manual" / "sports_manual.json"
    if mp.exists():
        for s in json.loads(mp.read_text(encoding="utf-8"))["sports"]:
            out.append({k: s[k] for k in ("kind", "sport", "name", "obb")})
    for s in [o for o in out if o["kind"] == "soccer" and o["obb"][2] >= 95]:
        if not any(o["kind"] == "oval" and math.hypot(o["obb"][0] - s["obb"][0], o["obb"][1] - s["obb"][1]) < 40 for o in out):
            out.append(dict(kind="oval", sport="athletics", name="", obb=[s["obb"][0], s["obb"][1], 176.4, 92.4, s["obb"][4]]))
    for o in out:                       # a track with a football pitch inside takes the pitch's centre and heading
        if o["kind"] != "oval":
            continue
        inner = [s for s in out if s["kind"] == "soccer" and math.hypot(s["obb"][0] - o["obb"][0], s["obb"][1] - o["obb"][1]) < 35]
        if inner:
            o["obb"][0], o["obb"][1], o["obb"][4] = inner[0]["obb"][0], inner[0]["obb"][1], inner[0]["obb"][4]
            o["has_pitch"] = True
    print(f"sports facilities: {len(out)}", sorted(set(o["kind"] for o in out)), "ovals:", [o["obb"][:4] for o in out if o["kind"] == "oval"])
    return out


def road_junctions(osm, roads, boundary):
    """Road intersections from shared OSM nodes, with crosswalk placements on each incoming road (w >= 6 m)."""
    byid = {r.get("id"): r for r in roads}
    inside = lambda x, z: any(point_in(x, z, ring) for ring in boundary)
    node_ways = {}
    for e in osm["elements"]:
        if e["type"] != "way" or e["id"] not in byid or "nodes" not in e:
            continue
        r = byid[e["id"]]
        if r["w"] < 5 or r["kind"] in ("footway", "path", "steps", "cycleway", "track"):
            continue
        ns, geo = e["nodes"], e["geometry"]
        for i, n in enumerate(ns):
            node_ways.setdefault(n, []).append((e["id"], i, ns, geo))
    junctions, seen = [], []
    for n, lst in node_ways.items():
        if len({w for w, *_ in lst}) < 2:
            continue
        wid, i, ns, geo = lst[0]
        cx, cz = MOVED.get(to_local(geo[i]["lat"], geo[i]["lon"]), to_local(geo[i]["lat"], geo[i]["lon"]))
        if not inside(cx, cz) or any(math.hypot(cx - sx, cz - sz) < 6 for sx, sz in seen):
            continue
        seen.append((cx, cz))
        arms = []
        for wid, i, ns, geo in lst:
            for j in (i - 1, i + 1):
                if 0 <= j < len(geo):
                    q = to_local(geo[j]["lat"], geo[j]["lon"])
                    x2, z2 = MOVED.get(q, q)
                    L = math.hypot(x2 - cx, z2 - cz) or 1
                    arms.append((byid[wid]["w"], (x2 - cx) / L, (z2 - cz) / L))
        if len(arms) < 3:
            continue
        rad = max(a[0] for a in arms) / 2 + 1.5
        cross = [[round(cx + dx * (rad + 1.8), 2), round(cz + dz * (rad + 1.8), 2), round(math.atan2(dz, dx), 4), round(w, 1)]
                 for w, dx, dz in arms if w >= 6]
        junctions.append(dict(x=round(cx, 2), z=round(cz, 2), r=round(rad, 2), cross=cross))
    print(f"junctions: {len(junctions)}, crosswalks: {sum(len(j['cross']) for j in junctions)}")
    return junctions


def trees_off_paving(trees):
    """No tree trunk on ground the official map shows as open paving, asphalt, courts / track or water
    (web/public/campus/ground.png; trees the drawing shows are tree sprites there, not paving). Fixes plazas
    such as the one in front of the library, where winter-aerial canopy detection had planted trees."""
    import numpy as np
    gp, mp = OUT / "ground.png", OUT / "ground_meta.json"
    if not gp.exists() or not mp.exists():
        return trees
    g = np.asarray(Image.open(gp))
    m = json.loads(mp.read_text(encoding="utf-8"))
    bad = np.zeros(256, bool)
    bad[[3, 4, 5, 6, 7, 8, 11, 12, 13]] = True
    out, removed = [], 0
    for t in trees:
        i, j = int((t[0] - m["x0"]) / m["m_per_px"]), int((t[1] - m["z0"]) / m["m_per_px"])
        if 0 <= j < g.shape[0] and 0 <= i < g.shape[1]:
            win = g[max(0, j - 1):j + 2, max(0, i - 1):i + 2]          # 1.5 m around the trunk, all paved
            if bad[win].all():
                removed += 1
                continue
        out.append(t)
    print(f"trees on paving / asphalt / courts / water (official ground map) removed: {removed}")
    return out


def apply_generic(buildings):
    """Ordinary buildings made in Blender (data/blender/generic.json, tools/blender_generic_prep.py): mark them so
    the game draws the chunk GLB instead of the procedural block. Buildings since replaced by a landmark model or
    removed from the data are skipped (their stale nodes are hidden by the game)."""
    path = ROOT / "data" / "blender" / "generic.json"
    if not path.exists():
        return []
    g = json.loads(path.read_text(encoding="utf-8"))
    byid = {str(b["id"]): b for b in buildings}
    out, n = [], 0
    for ch in g.get("chunks", []):
        ids = []
        for e in ch.get("buildings", []):
            b = byid.get(str(e["id"]))
            if b and not b.get("replaced"):
                b["generic"] = True
                ids.append(str(e["id"]))
        if ids:
            out.append(dict(file=ch["file"], x=ch["x"], z=ch["z"], ids=ids))
            n += len(ids)
    print(f"generic Blender buildings: {n} in {len(out)} chunks")
    return out


def apply_models(buildings, pois):
    """Refined landmark GLBs from the Blender session (data/blender/models.json): mark the buildings / POIs they replace."""
    path = ROOT / "data" / "blender" / "models.json"
    if not path.exists():
        return []
    models = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for m in models:
        rep = {str(r) for r in m.get("replaces", [])}
        for b in buildings:
            if str(b["id"]) in rep:
                b["replaced"] = True
                n += 1
        for q in pois:
            if q["name"] in rep or q["name"] == m["name"] or m["name"].startswith(q["name"] + "（"):
                q["replaced"] = True
                n += 1
    mo_path = ROOT / "data" / "manual" / "model_overrides.json"
    mo = json.loads(mo_path.read_text(encoding="utf-8")) if mo_path.exists() else {}
    for m in models:
        o = mo.get(m["name"])
        if isinstance(o, dict):
            m.update({k: o[k] for k in ("x", "z", "rotY") if k in o})
    print(f"landmark models: {len(models)}, replaced {n} buildings/POIs, position overrides {sum(1 for m in models if m['name'] in mo)}")
    # replaces: the game sets each model's ground level from the buildings it replaces (not from any replaced building nearby)
    return [{**{k: m[k] for k in ("name", "file", "x", "z", "rotY") if k in m}, "replaces": [str(r) for r in m.get("replaces", [])]}
            for m in models]

# ---------------------------------------------------------------------------
# v0.4 WP2/WP4: audited road widths / names / sidewalks, trees kept off roads, regular avenue rows
# ---------------------------------------------------------------------------
MOVED = {}          # original OSM vertex -> shifted position (roads re-centred on the aerial)
PUBLIC = ("motorway", "trunk", "primary", "secondary", "tertiary")


def _normals(pts):
    out = []
    for i in range(len(pts)):
        a, c = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        dx, dz = c[0] - a[0], c[1] - a[1]
        L = math.hypot(dx, dz) or 1
        out.append((-dz / L, dx / L))
    return out


def _repoint(old, new):
    """A road vertex was re-traced: roads joining there follow (MOVED maps original OSM vertices to final positions)."""
    old, new = tuple(old), tuple(new)
    hit = [o for o, q in MOVED.items() if tuple(q) == old]
    for o in hit:
        MOVED[o] = new
    if not hit:
        MOVED[old] = new


def apply_road_audit(roads):
    """data/manual/road_audit.json: verified width, sidewalk, centreline shift and official names (see the file's notes)."""
    path = ROOT / "data" / "manual" / "road_audit.json"
    audit = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"roads": {}, "labels": []}
    for a in audit.get("add", []):      # roads OSM does not have (e.g. the south gate lane at 东大门), final coordinates
        rd = dict(id=a["id"], kind=a.get("kind", "service"), w=a["w"], name=a.get("name", ""),
                  pts=[tuple(p) for p in a["pts"]], manual=True)
        if "sw" in a:
            rd["sw"] = a["sw"]
        if "pave" in a:                 # paving colour fixed by hand ("red" / "grey"), paving_colours leaves it
            rd["pave"], rd["pave_fixed"] = a["pave"], True
        if a.get("area"):               # paved area, not a route (street furniture may stand on it; sanity skips it)
            rd["area"] = True
        roads.append(rd)
    n = 0
    for r in roads:
        a = audit["roads"].get(str(r["id"]))
        if not a:
            continue
        n += 1
        r["w"], r["audited"] = a["w"], True
        if "sw" in a:
            r["sw"] = a["sw"]
        if "pave" in a:
            r["pave"], r["pave_fixed"] = a["pave"], True
        if a.get("area"):
            r["area"] = True
        if a.get("name"):
            r["name"] = a["name"]
        s = a.get("shift", 0)
        if s:
            new = [(round(x + nx * s, 2), round(z + nz * s, 2)) for (x, z), (nx, nz) in zip(r["pts"], _normals(r["pts"]))]
            for o, q in zip(r["pts"], new):
                MOVED[tuple(o)] = q
            r["pts"] = [list(q) for q in new]
        # re-traced geometry where the OSM line is wrong (e.g. cuts through a building): "move" = [[x, z, new x, new z]]
        # moves the vertex nearest (x, z) (within 2 m, after shift); "pts" replaces the whole centreline
        for ox, oz, qx, qz in a.get("move", []):
            k = min(range(len(r["pts"])), key=lambda i: math.hypot(r["pts"][i][0] - ox, r["pts"][i][1] - oz))
            if math.hypot(r["pts"][k][0] - ox, r["pts"][k][1] - oz) < 2:
                _repoint(r["pts"][k], (qx, qz))
                r["pts"][k] = [qx, qz]
        if "pts" in a:
            if not a.get("detach"):     # "detach": the old ends stay where they are for the roads that share them
                for k in (0, -1):
                    _repoint(r["pts"][k], tuple(a["pts"][k]))
            r["pts"] = [list(p) for p in a["pts"]]
    # side roads that end on a shifted road follow it
    for r in roads:
        r["pts"] = [list(MOVED.get(tuple(p), p)) for p in r["pts"]]
    for r in roads:            # sidewalks: public roads 3 m, campus roads >= 7 m 2.4 m, narrow ones none
        if "sw" not in r:
            r["sw"] = 3.0 if r["kind"] in PUBLIC and r["w"] >= 7 else 2.4 if r["w"] >= 7 else 0
    # official names: nearest road to each label, then carried along straight continuations
    named = 0
    seg = lambda p, a, b: _dseg(p, a, b)
    cand = [r for r in roads if r["w"] >= 5 and r["kind"] not in ("footway", "path", "steps", "cycleway", "track")]
    for name, x, z in audit.get("labels", []):
        best = min(cand, key=lambda r: min(seg((x, z), r["pts"][i], r["pts"][i + 1]) for i in range(len(r["pts"]) - 1)))
        if not best.get("name"):
            best["name"], best["official_name"] = name, True
            named += 1
    ends = {}
    for r in cand:
        for k in (0, -1):
            ends.setdefault((round(r["pts"][k][0]), round(r["pts"][k][1])), []).append((r, k))
    # a name does not continue across a public road (盘城新街 separates 万象路 from the 东苑 lanes)
    for key, lst in ends.items():
        if any(r["kind"] in PUBLIC for r, _ in lst):
            ends[key] = []
    pub_v = {(round(p[0]), round(p[1])) for r in roads if r["kind"] in PUBLIC for p in r["pts"]}
    for key in pub_v:
        ends.pop(key, None)
    pubs = [r for r in roads if r["kind"] in PUBLIC]

    def near_public(r2):          # touches or crosses a public road's carriageway
        for q in r2["pts"]:
            for pr in pubs:
                if any(_dseg(q, pr["pts"][i], pr["pts"][i + 1]) < pr["w"] / 2 + 2 for i in range(len(pr["pts"]) - 1)):
                    return True
        return False
    changed = True
    while changed:
        changed = False
        for r in cand:
            if not r.get("official_name"):
                continue
            for k in (0, -1):
                p = r["pts"][k]
                q = r["pts"][1 if k == 0 else -2]
                d0 = math.atan2(p[1] - q[1], p[0] - q[0])          # leaving direction
                for r2, k2 in ends.get((round(p[0]), round(p[1])), []):
                    if r2 is r or r2.get("name") or near_public(r2):
                        continue
                    a, b = r2["pts"][k2], r2["pts"][1 if k2 == 0 else -2]
                    d1 = math.atan2(b[1] - a[1], b[0] - a[0])
                    if abs((d1 - d0 + math.pi) % (2 * math.pi) - math.pi) < math.radians(30):
                        r2["name"], r2["official_name"] = r["name"], True
                        named += 1
                        changed = True
    print(f"road audit: {n} roads corrected, {len(MOVED)} vertices re-centred, {named} roads named from the official map")


def _dseg(p, a, b):
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0 if L2 == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - az) * dz) / L2))
    return math.hypot(ax + dx * t - p[0], az + dz * t - p[1])


class SegGrid:
    """Road segments hashed on a 20 m grid: nearest road, signed side and band test."""
    def __init__(self, roads, minw=3.0):
        self.cell, self.g = 20.0, {}
        for r in roads:
            if r["w"] < minw or r["kind"] in ("footway", "path", "steps", "cycleway", "track"):
                continue
            for i in range(len(r["pts"]) - 1):
                a, b = r["pts"][i], r["pts"][i + 1]
                pad = r["w"] / 2 + r.get("sw", 0) + 6
                for cx in range(int((min(a[0], b[0]) - pad) // 20), int((max(a[0], b[0]) + pad) // 20) + 1):
                    for cz in range(int((min(a[1], b[1]) - pad) // 20), int((max(a[1], b[1]) + pad) // 20) + 1):
                        self.g.setdefault((cx, cz), []).append((r, a, b))

    def near(self, x, z):
        return self.g.get((int(x // 20), int(z // 20)), [])

    def band(self, x, z, extra=0.0, skip=None):
        """the road whose carriageway + sidewalk (+extra) contains (x, z), with the distance to its centreline"""
        for r, a, b in self.near(x, z):
            if r is skip:
                continue
            d = _dseg((x, z), a, b)
            if d < r["w"] / 2 + r.get("sw", 0) + extra:
                return r, a, b, d
        return None


def roof_colours(buildings):
    """Roof colour and solar panels from the official map registered to the aerial (official_aligned.jpg).
    The drawing shows a roof h metres up shifted ~(-0.31 h, -0.63 h) m from its footprint; sample the shrunk,
    shifted footprint, keep the dominant colour (median of the mid-brightness pixels) and the share of
    blue-black panel pixels."""
    import numpy as np
    p = ROOT / "data" / "official" / "official_aligned.jpg"
    if not p.exists():
        return
    o = np.asarray(Image.open(p).convert("RGB")).astype(np.int16)
    m = json.loads((ROOT / "data" / "official" / "official_aligned_meta.json").read_text(encoding="utf-8"))
    mpp, X0, Z0 = m["m_per_px"], m["x0"], m["z0"]
    Hh, Ww = o.shape[:2]
    n_col = n_pv = 0
    for b in buildings:
        if b.get("kind") == "wall" or b["h"] < 3 or b.get("roofc"):   # roofc set by hand (extra_buildings.json) wins
            continue
        pts = b["pts"]
        cx = sum(q[0] for q in pts) / len(pts)
        cz = sum(q[1] for q in pts) / len(pts)
        sh = (-0.307 * b["h"], -0.625 * b["h"])
        poly = [((cx + (x - cx) * 0.7 + sh[0] - X0) / mpp, (cz + (z - cz) * 0.7 + sh[1] - Z0) / mpp) for x, z in pts]
        i0, j0 = max(0, int(min(q[0] for q in poly))), max(0, int(min(q[1] for q in poly)))
        i1, j1 = min(Ww, int(max(q[0] for q in poly)) + 2), min(Hh, int(max(q[1] for q in poly)) + 2)
        if i1 - i0 < 3 or j1 - j0 < 3:
            continue
        mask = Image.new("L", (i1 - i0, j1 - j0), 0)
        ImageDraw.Draw(mask).polygon([(u - i0, v - j0) for u, v in poly], fill=1)
        mk = np.asarray(mask).astype(bool)
        if mk.sum() < 12:
            continue
        px = o[j0:j1, i0:i1][mk]
        R, G, B = px[:, 0], px[:, 1], px[:, 2]
        lum = (R + G + B) / 3
        pv = ((B > R + 25) & (B > G + 5) & (lum < 150)).mean()           # blue solar modules
        green = ((2 * G - R - B) > 30).mean()                            # tree sprites over the roof: unreliable
        if green > 0.5 or (lum > 236).mean() > 0.5:
            continue
        hipr = b.get("roof", {}).get("type") == "hip"
        # pitched roofs: the dominant tile colour (red or blue-grey tiles) if the drawing shows one, ignoring the
        # white facade that the sample window can catch; flat roofs: the mid-tones
        reddish = (R - G > 40) & (R > 120)
        bluish = (B - R > 18) & (lum < 170)
        if hipr and reddish.mean() > 0.12:
            sel = px[reddish]
        elif hipr and bluish.mean() > 0.12:
            sel = px[bluish]
        else:
            sel = px[(lum > np.percentile(lum, 20)) & (lum < np.percentile(lum, 80))]
        if len(sel) < 6:
            continue
        r, g, bb = np.median(sel, axis=0)
        b["roofc"] = "#%02x%02x%02x" % (int(r), int(g), int(bb))
        n_col += 1
        if 0.18 < pv < 0.7 and not (bb > r + 12):      # a blue roof colour is a blue roof, not panels
            b["solar"] = round(float(pv), 2)
            n_pv += 1
    print(f"roof colours from the official map: {n_col}, with solar panels: {n_pv}")


def paving_colours(roads, img):
    """Sidewalk / footpath colour. The winter aerial cannot tell red brick from brown ground, so read it off the
    official illustrated map (warped to the ground, data/official/official_local.jpg), which draws campus walks
    in red permeable brick or light-grey stone. Vote over windows along the walk (the drawing is ~4.5 m off)."""
    import numpy as np
    offp = ROOT / "data" / "official" / "official_local.jpg"
    if not offp.exists():
        return
    o = np.asarray(Image.open(offp).convert("RGB")).astype(np.int16)
    m = json.loads((ROOT / "data" / "official" / "official_local_meta.json").read_text(encoding="utf-8"))
    R, G, B = o[..., 0], o[..., 1], o[..., 2]
    lum = (R + G + B) / 3
    red = (R - G > 40) & (R > 140) & (np.abs(G - B) < 35)
    grey = (np.abs(R - G) < 12) & (np.abs(G - B) < 12) & (lum > 150) & (lum < 228)
    H, Wo = R.shape
    k = 1 / m["m_per_px"]
    stats = {"red": 0, "grey": 0}
    for r in roads:
        if r.get("pave_fixed"):
            continue
        walk = r["kind"] in ("footway", "path", "pedestrian", "cycleway")
        sw = r.get("sw", 0)
        if not walk and sw <= 0:
            continue
        offs = [0.0] if walk else [r["w"] / 2 + sw / 2, -(r["w"] / 2 + sw / 2)]
        nr = ng = 0
        for (x0, z0), (x1, z1) in zip(r["pts"], r["pts"][1:]):
            L = math.hypot(x1 - x0, z1 - z0)
            if L < 1:
                continue
            nx, nz = -(z1 - z0) / L, (x1 - x0) / L
            for t in np.arange(2, L, 6):
                for of in offs:
                    x, z = x0 + (x1 - x0) * t / L + nx * of, z0 + (z1 - z0) * t / L + nz * of
                    i, j = int((x - m["x0"]) * k), int((z - m["z0"]) * k)
                    if not (6 <= i < Wo - 6 and 6 <= j < H - 6):
                        continue
                    nr += int(red[j - 6:j + 7, i - 6:i + 7].sum())
                    ng += int(grey[j - 6:j + 7, i - 6:i + 7].sum())
        if nr + ng >= 30:
            c = "red" if nr / (nr + ng) > 0.35 else "grey"
            r["pave"] = c
            stats[c] += 1
    print(f"paving colour from the official map: {stats}")


def snap_bus(bus, roads):
    """Official bus loop (drawn on the map) -> drive on our road centrelines, in the right-hand lane."""
    route = bus["route"] + [bus["route"][0]]
    cum = [0.0]
    for a, b in zip(route, route[1:]):
        cum.append(cum[-1] + math.dist(a, b))

    def at(s):
        s %= cum[-1]
        for i in range(len(cum) - 1):
            if cum[i + 1] >= s:
                f = (s - cum[i]) / max(1e-9, cum[i + 1] - cum[i])
                return (route[i][0] + (route[i + 1][0] - route[i][0]) * f, route[i][1] + (route[i + 1][1] - route[i][1]) * f)
        return tuple(route[-1])

    stops_xy = [at(st["s"]) for st in bus["stops"]]
    grid = SegGrid([r for r in roads if r["w"] >= 5])
    pts, snapped, flags, prev = [], 0, [], None
    n = int(cum[-1] / 2)
    for k in range(n):
        x, z = at(k * 2)
        x2, z2 = at(k * 2 + 2)
        dx, dz = x2 - x, z2 - z
        L = math.hypot(dx, dz) or 1
        dx, dz = dx / L, dz / L
        best = keep = None
        for r, a, b in grid.near(x, z):
            sx, sz = b[0] - a[0], b[1] - a[1]
            sl = math.hypot(sx, sz) or 1
            if abs((sx * dx + sz * dz) / sl) < 0.7:        # road must run along the route here
                continue
            d = _dseg((x, z), a, b)
            if d < 18 and (best is None or d < best[0]):
                best = (d, r, a, b)
            if d < 18 and r is prev and (keep is None or d < keep[0]):
                keep = (d, r, a, b)
        if keep and best and keep[0] < best[0] + 5:        # hysteresis: stay on the same road
            best = keep
        prev = best[1] if best else None
        if best:
            d, r, a, b = best
            sx, sz = b[0] - a[0], b[1] - a[1]
            L2 = sx * sx + sz * sz or 1
            t = max(0, min(1, ((x - a[0]) * sx + (z - a[1]) * sz) / L2))
            cx, cz = a[0] + sx * t, a[1] + sz * t
            off = (r["w"] / 2 - 1.8) if r.get("oneway") else min(r["w"] / 4, 3.0)
            x, z = cx - dz * off, cz + dx * off          # right of travel = (-dz, dx)
            snapped += 1
        flags.append(bool(best))
        pts.append((x, z))
    # gaps (no parallel road within 18 m): follow the road graph between the snapped ends when a short path exists
    import heapq
    node, adj = {}, {}
    key = lambda q: (round(q[0]), round(q[1]))
    for r in roads:
        if r["w"] < 5 or r["kind"] in ("footway", "path", "steps", "cycleway", "track"):
            continue
        for a, b in zip(r["pts"], r["pts"][1:]):
            ka, kb = key(a), key(b)
            node[ka], node[kb] = a, b
            w = math.dist(a, b)
            adj.setdefault(ka, []).append((kb, w))
            adj.setdefault(kb, []).append((ka, w))
    segs = [(key(a), key(b)) for k0 in list(adj) for (k1, _) in adj[k0] for a, b in [(node[k0], node[k1])] if k0 < k1]

    def nearest(q, tag):
        # temporary node at the foot of the perpendicular on the nearest road segment
        best = None
        for ka, kb in segs:
            a, b = node[ka], node[kb]
            d = _dseg(q, a, b)
            if best is None or d < best[0]:
                best = (d, ka, kb)
        d, ka, kb = best
        a, b = node[ka], node[kb]
        sx, sz = b[0] - a[0], b[1] - a[1]
        L2 = sx * sx + sz * sz or 1
        t = max(0, min(1, ((q[0] - a[0]) * sx + (q[1] - a[1]) * sz) / L2))
        f = (a[0] + sx * t, a[1] + sz * t)
        node[tag] = f
        adj[tag] = [(ka, math.dist(f, a)), (kb, math.dist(f, b))]
        adj.setdefault(ka, []).append((tag, math.dist(f, a)))
        adj.setdefault(kb, []).append((tag, math.dist(f, b)))
        return tag

    def shortest(ka, kb):
        dist, prv, pq = {ka: 0.0}, {}, [(0.0, ka)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == kb:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w in adj.get(u, []):
                if d + w < dist.get(v, 1e18):
                    dist[v] = d + w
                    prv[v] = u
                    heapq.heappush(pq, (d + w, v))
        if kb not in dist:
            return None, 0
        out = [kb]
        while out[-1] != ka:
            out.append(prv[out[-1]])
        return [node[k] for k in out[::-1]], dist[kb]

    new_pts, new_flags, i, rerouted = [], [], 0, 0
    while i < len(pts):
        if flags[i] or i == 0:
            new_pts.append(pts[i]); new_flags.append(flags[i]); i += 1
            continue
        j = i
        while j < len(pts) and not flags[j]:
            j += 1
        if j < len(pts) and j - i >= 3:
            run_len = 2 * (j - i)
            na, nb = nearest(pts[i - 1], ('tmp', i, 0)), nearest(pts[j], ('tmp', i, 1))
            path, plen = shortest(na, nb)
            if path and plen <= 2.5 * run_len + 40 and math.dist(node[na], pts[i - 1]) < 12 and math.dist(node[nb], pts[j]) < 12:
                for a, b in zip(path, path[1:]):
                    L = math.dist(a, b)
                    for t in [k * 2.0 for k in range(int(L / 2.0) + 1)]:
                        if t < L:
                            new_pts.append((a[0] + (b[0] - a[0]) * t / L, a[1] + (b[1] - a[1]) * t / L)); new_flags.append(True)
                rerouted += 1
                i = j
                continue
        new_pts.extend(pts[i:j]); new_flags.extend(flags[i:j]); i = j
    pts, flags = new_pts, new_flags
    print(f"bus: {rerouted} gaps rerouted over the road graph")
    # smooth the joins at junctions (moving average over ~14 m), then iron out remaining kinks
    sm = []
    for i in range(len(pts)):
        win = [pts[(i + j) % len(pts)] for j in range(-3, 4)]
        sm.append((sum(p[0] for p in win) / 7, sum(p[1] for p in win) / 7))
    N = len(sm)
    for _ in range(6):
        out = list(sm)
        for i in range(N):
            a, b, c = sm[i - 1], sm[i], sm[(i + 1) % N]
            v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*v1) or 1, math.hypot(*v2) or 1
            if (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2) < math.cos(math.radians(35)):
                win = [sm[(i + j) % N] for j in range(-4, 5)]
                out[i] = (sum(p[0] for p in win) / 9, sum(p[1] for p in win) / 9)
        sm = out
    c2 = [0.0]
    for a, b in zip(sm, sm[1:]):
        c2.append(c2[-1] + math.dist(a, b))
    stops = []
    for st, (sx, sz) in zip(bus["stops"], stops_xy):
        i = min(range(len(sm)), key=lambda i: (sm[i][0] - sx) ** 2 + (sm[i][1] - sz) ** 2)
        stops.append(dict(name=st["name"], s=round(c2[i], 1)))
    length = c2[-1] + math.dist(sm[-1], sm[0])
    # stretches with no road in OSM: the official bus drives there, so there is a lane; add it (6 m service road)
    added, i = 0, 0
    while i < len(pts):
        if flags[i]:
            i += 1
            continue
        j = i
        while j < len(pts) and not flags[j]:
            j += 1
        if j - i >= 10:
            run = sm[max(0, i - 2):min(len(sm), j + 2)]
            roads.append(dict(id=f"bus-{added}", kind="service", w=6.0, sw=0, name="", synthetic=True,
                              pts=[[round(x, 2), round(z, 2)] for x, z in run[::2]]))
            added += 1
        i = j
    print(f"bus: {snapped}/{len(pts)} route points snapped to road lanes, {added} missing lanes added, loop {length:.0f} m")
    return dict(route=[[round(x, 2), round(z, 2)] for x, z in sm], stops=stops, length=round(length, 1))


def street_trees(trees, roads, buildings, water, boundary, junctions):
    """1) DSM trees whose trunk stands on a carriageway or sidewalk are moved to the verge (or dropped);
    2) where the aerial land cover shows a continuous canopy strip along a campus road, plant a regular row
       (6 m spacing, the real street-tree pattern) and drop the DSM trees it replaces; size/species from those."""
    import numpy as np
    lc = np.asarray(Image.open(OUT / "landcover.png"))
    LH, LW = lc.shape

    def lcat(x, z):
        i, j = int(x + WIDTH / 2), int(z + DEPTH / 2)
        return lc[j, i] if 0 <= i < LW and 0 <= j < LH else 0

    def canopy_frac(x, z, r=2):
        n = c = 0
        for dx in range(-r, r + 1):
            for dz in range(-r, r + 1):
                n += 1
                c += lcat(x + dx, z + dz) == 2
        return c / n

    grid = SegGrid(roads)
    inside = lambda x, z: any(point_in(x, z, ring) for ring in boundary)
    # building / water lookup on a 2 m raster
    occ = Image.new("L", (int(WIDTH / 2) + 1, int(DEPTH / 2) + 1), 0)
    od = ImageDraw.Draw(occ)
    for b in buildings:
        od.polygon([((x + WIDTH / 2) / 2, (z + DEPTH / 2) / 2) for x, z in b["pts"]], fill=1)
    for w in water:
        od.polygon([((x + WIDTH / 2) / 2, (z + DEPTH / 2) / 2) for x, z in w["pts"]], fill=2)
    occ = np.asarray(occ)
    blocked = lambda x, z: occ[min(occ.shape[0] - 1, max(0, int((z + DEPTH / 2) / 2))), min(occ.shape[1] - 1, max(0, int((x + WIDTH / 2) / 2)))] > 0

    # 1) off the roads
    out, moved, dropped = [], 0, 0
    for t in trees:
        x, z = t[0], t[1]
        hit = grid.band(x, z, 0.4)
        if hit:
            r, a, b, d = hit
            dx, dz = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dz) or 1
            nx, nz = -dz / L, dx / L
            side = 1 if (x - a[0]) * nx + (z - a[1]) * nz >= 0 else -1
            # foot of the perpendicular, then out to the verge
            tt = max(0, min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / (L * L)))
            fx, fz = a[0] + dx * tt, a[1] + dz * tt
            o = r["w"] / 2 + r.get("sw", 0) + 1.0
            x2, z2 = fx + nx * o * side, fz + nz * o * side
            if grid.band(x2, z2, 0.4) or blocked(x2, z2):
                dropped += 1
                continue
            t = [round(x2, 1), round(z2, 1)] + list(t[2:])
            moved += 1
        out.append(t)
    trees = out

    # 2) regular avenue rows
    cell = {}
    for k, t in enumerate(trees):
        cell.setdefault((int(t[0] // 10), int(t[1] // 10)), []).append(k)

    def near_trees(x, z, rad):
        res = []
        for cx in range(int((x - rad) // 10), int((x + rad) // 10) + 1):
            for cz in range(int((z - rad) // 10), int((z + rad) // 10) + 1):
                for k in cell.get((cx, cz), []):
                    if math.hypot(trees[k][0] - x, trees[k][1] - z) < rad:
                        res.append(k)
        return res

    jpts = [(j["x"], j["z"], j["r"]) for j in junctions]
    remove, planted, rows = set(), [], 0
    SP = 6.0
    for r in roads:
        if r["w"] < 6 or r["kind"] in ("footway", "path", "steps", "cycleway", "track"):
            continue
        pts = r["pts"]
        # stations every SP metres along the road
        st, acc = [], SP / 2
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 0.1:
                continue
            ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            s = acc
            while s < L:
                st.append((a[0] + ux * s, a[1] + uz * s, -uz, ux))
                s += SP
            acc = s - L
        for side in (1, -1):
            o = r["w"] / 2 + r.get("sw", 0) + 1.8
            cand, free = [], []
            for x, z, nx, nz in st:
                tx, tz = x + nx * o * side, z + nz * o * side
                hard = (inside(tx, tz) and not blocked(tx, tz) and not grid.band(tx, tz, 0.6)
                        and all(math.hypot(tx - jx, tz - jz) > jr + 5 for jx, jz, jr in jpts))
                # evidence of a tree row: canopy in the aerial land cover, or a DSM-detected tree right there
                ev = canopy_frac(tx, tz) >= 0.35 or bool(near_trees(tx, tz, 3.5))
                free.append(hard)
                cand.append((tx, tz) if hard and ev else None)
            for i in range(1, len(cand) - 1):        # close single gaps inside a row
                if cand[i] is None and free[i] and cand[i - 1] and cand[i + 1]:
                    x, z, nx, nz = st[i]
                    cand[i] = (x + nx * o * side, z + nz * o * side)
            # keep runs of >= 5 consecutive stations (>= 24 m of continuous canopy)
            i = 0
            while i < len(cand):
                if cand[i] is None:
                    i += 1
                    continue
                j = i
                while j < len(cand) and cand[j] is not None:
                    j += 1
                if j - i >= 5:
                    run = cand[i:j]
                    ks = set()
                    for tx, tz in run:
                        ks.update(near_trees(tx, tz, 4.5))
                    hs = sorted(trees[k][2] for k in ks) or [9.0]
                    rs = sorted(trees[k][3] for k in ks) or [3.0]
                    sp = [trees[k][4] for k in ks] or ["broad"]
                    h = min(20, max(6, hs[len(hs) // 2]))
                    cr = min(4.2, max(2.2, rs[len(rs) // 2]))
                    species = max(set(sp), key=sp.count)
                    rnd = random.Random(int(abs(run[0][0] * 7 + run[0][1] * 13)))
                    for tx, tz in run:
                        planted.append([round(tx, 1), round(tz, 1), round(h * (0.92 + rnd.random() * 0.16), 1),
                                        round(cr * (0.9 + rnd.random() * 0.2), 1), species])
                    remove |= ks
                    rows += 1
                i = j
    kept = [t for k, t in enumerate(trees) if k not in remove] + planted

    # 3) canopy fill inside the campus: DSM peaks miss trees inside a continuous canopy, so where the aerial
    #    land cover is tree canopy but no crown covers it, add trees ~5 m apart sized like their neighbours
    cm = Image.new("L", (LW, LH), 0)
    cd = ImageDraw.Draw(cm)
    for ring in boundary:
        cd.polygon([(x + WIDTH / 2, z + DEPTH / 2) for x, z in ring], fill=1)
    camp = np.asarray(cm).astype(bool)
    cov = Image.new("L", (LW, LH), 0)
    vd = ImageDraw.Draw(cov)
    for t in kept:
        i, j, rr = t[0] + WIDTH / 2, t[1] + DEPTH / 2, t[3] * 0.85
        vd.ellipse([i - rr, j - rr, i + rr, j + rr], fill=1)
    cov = np.asarray(cov).copy()
    need = (lc == 2) & camp & (cov == 0)
    js, is_ = np.nonzero(need)
    order = random.Random(11).sample(range(len(js)), len(js))
    kc = {}
    for t in kept:
        kc.setdefault((int(t[0] // 15), int(t[1] // 15)), []).append(t)
    fill = []
    for o in order:
        j, i = js[o], is_[o]
        if cov[j, i]:
            continue
        x, z = i + 0.5 - WIDTH / 2, j + 0.5 - DEPTH / 2
        if blocked(x, z) or grid.band(x, z, 0.8):
            continue
        # needs a canopy patch, not a stray pixel: >= 60 % canopy in the 5 x 5 m around it
        if canopy_frac(x, z) < 0.6:
            continue
        nb = [t for cx in (-1, 0, 1) for cz in (-1, 0, 1) for t in kc.get((int(x // 15) + cx, int(z // 15) + cz), [])]
        hs = sorted(t[2] for t in nb) or [8.0]
        sp = [t[4] for t in nb] or ["broad"]
        h = min(18, max(5, hs[len(hs) // 2])) * (0.85 + ((i * 7 + j * 13) % 10) / 33)
        rr = min(4.0, max(2.2, 0.28 * h + 1.0))
        fill.append([round(x, 1), round(z, 1), round(h, 1), round(rr, 1), max(set(sp), key=sp.count)])
        y0, y1, x0, x1 = max(0, int(j - rr * 1.5)), min(LH, int(j + rr * 1.5) + 1), max(0, int(i - rr * 1.5)), min(LW, int(i + rr * 1.5) + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        cov[y0:y1, x0:x1] |= ((yy - j) ** 2 + (xx - i) ** 2 <= (rr * 1.5) ** 2).astype(np.uint8)
    kept += fill
    print(f"trees: {moved} moved off roads, {dropped} dropped; {rows} avenue rows, {len(planted)} street trees "
          f"replace {len(remove)} DSM trees; canopy fill +{len(fill)}; total {len(kept)}")
    return kept


if __name__ == "__main__":
    main()
