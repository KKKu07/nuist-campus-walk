"""Per-building check (常识排查): game vs drone DSM vs the local building-model set (本机素材, never published).

For every building in docs/building-audit.csv:
  height   per 1 m cell: game top (Blender GLB, else the procedural outline height) vs 本机素材 top, both above the
           building's own ground; median difference over the shared cells, and the share of cells off by > 3 m (a
           wing / storey missing). 主屋面 = the commonest roof level (1 m bins) above 2.5 m. DSM (measured_heights.json).
  floors   本机素材 / game: roof (eaves for pitched roofs) / storey height (dorms 3.45 m calibrated on the official floor
           counts of 52 dorms, apartments 3.0, teaching 3.9, halls / canteens 4.5, others 3.6); official (dorms.csv).
  plan     centroid offset, area ratio, overlap; parts 本机素材 has and the game lacks (>= 25 m2 outside the game
           footprint + 2 m); such a part touching another game building = a link (连接体); one 本机素材 model covering
           several game buildings = joined.
  ground   scanModels result (sunk / floating) from the dev build.
plus 本机素材 buildings the game lacks and campus buildings 本机素材 does not have.

Usage: .venv/Scripts/python.exe -I -X utf8 tools/building_check.py <footprints.json> <scanmodels.json> [--img]
Writes: new columns in docs/building-audit.csv; docs/questions/buildings.md; data/source/scan2022_analysis/check_result.json;
with --img, overlays (aerial + game outline red + 本机素材 outline cyan) in data/source/scan2022_analysis/audit_img/ (local only).
"""
import csv
import json
import re
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "web" / "public"
LOCAL = ROOT / "data" / "source" / "scan2022_analysis"
NEW_COLS = ["旧实测高", "新实测高", "素材主屋面高", "实测核对", "素材层数估计", "平面偏移", "连接体", "问题等级", "建议", "负责会话"]
STOREY = {"dorm": 3.45, "apartment": 3.0, "teach": 3.9, "hall": 4.5, "canteen": 4.5, "other": 3.6}
ASSIGNED = {"东苑食堂", "国际教育学院", "培训楼", "雷丁学院"}       # already given to the Blender session (新主会话)
RENOVATED = {"尚贤楼", "明德楼", "基嘉楼"}                          # user: renovated in recent years
CONFIRMED = {"基嘉楼": "用户确认：约 3 层（已采用新实测）", "明德楼": "用户确认：6 层（采用新实测 26.3 m）"}                          # renovated, then answered by the user (2026-11-27)
# checked on photos by the Blender session (2026-11-27): the DSM top is a roof frame above the main roof, not a contradiction
VERIFIED = {n: "主屋面 17.0，屋顶构架 21.0，Blender 已按照片核对" for n in ("培训楼", "雷丁学院")}
LINKED = {n: "连接体已建入雷丁学院 GLB（用户确认 1–3 层连通）" for n in ("培训楼", "雷丁学院")}   # no joined / link flags
DZ = 1.9           # 本机素材 sits 1.9 m north of the game outlines on average (18 unmodelled OSM buildings): shift it back


def glb(path):
    b = path.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bl = struct.unpack("<I", b[off:off + 4])[0]
    bin_ = b[off + 8:off + 8 + bl]

    def acc(i):
        a = j["accessors"][i]
        v = j["bufferViews"][a["bufferView"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        comp = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]]
        size = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        stride = v.get("byteStride") or size * struct.calcsize(comp)
        return [struct.unpack_from("<" + comp * size, bin_, start + k * stride) for k in range(a["count"])]
    out = []
    for nd in j["nodes"]:
        if "mesh" not in nd:
            continue
        t = nd.get("translation", [0, 0, 0])
        tris = []
        for pr in j["meshes"][nd["mesh"]]["primitives"]:
            pos = acc(pr["attributes"]["POSITION"])
            idx = [i[0] for i in acc(pr["indices"])] if "indices" in pr else list(range(len(pos)))
            for k in range(0, len(idx) - 2, 3):
                tris.append(tuple((pos[idx[k + m]][0] + t[0], pos[idx[k + m]][1] + t[1], pos[idx[k + m]][2] + t[2]) for m in range(3)))
        out.append((nd.get("name", ""), tris))
    return out


def tops(tris, ox, oz):
    """1 m cells (game x, z) -> highest point of the triangles over the cell, and the lowest point overall"""
    cells, bot = {}, 1e9

    def put(x, z, y):
        k = (math.floor(x), math.floor(z))
        if cells.get(k, -1e9) < y:
            cells[k] = y
    for a, b, c in tris:
        ax, ay, az = a[0] + ox, a[1], a[2] + oz
        bx, by, bz = b[0] + ox, b[1], b[2] + oz
        cx, cy, cz = c[0] + ox, c[1], c[2] + oz
        bot = min(bot, ay, by, cy)
        area2 = (bx - ax) * (cz - az) - (cx - ax) * (bz - az)
        if abs(area2) < 0.02:
            ym = max(ay, by, cy)
            for (px, pz), (qx, qz) in (((ax, az), (bx, bz)), ((bx, bz), (cx, cz))):
                n = max(1, int(math.hypot(qx - px, qz - pz) / 0.5) + 1)
                for s in range(n + 1):
                    put(px + (qx - px) * s / n, pz + (qz - pz) * s / n, ym)
            continue
        for gx in range(math.floor(min(ax, bx, cx)), math.floor(max(ax, bx, cx)) + 1):
            for gz in range(math.floor(min(az, bz, cz)), math.floor(max(az, bz, cz)) + 1):
                px, pz = gx + 0.5, gz + 0.5
                w0 = ((bx - px) * (cz - pz) - (cx - px) * (bz - pz)) / area2
                w1 = ((cx - px) * (az - pz) - (ax - px) * (cz - pz)) / area2
                if w0 >= -0.25 and w1 >= -0.25 and w0 + w1 <= 1.25:
                    put(px, pz, ay * w0 + by * w1 + cy * (1 - w0 - w1))
    return cells, bot


def inside(x, z, pts):
    s, j = False, len(pts) - 1
    for i in range(len(pts)):
        (xi, zi), (xj, zj) = pts[i], pts[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            s = not s
        j = i
    return s


def poly_cells(pts):
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    return {(gx, gz) for gz in range(math.floor(min(zs)), math.floor(max(zs)) + 1)
            for gx in range(math.floor(min(xs)), math.floor(max(xs)) + 1) if inside(gx + 0.5, gz + 0.5, pts)}


def fill(cells):
    """the outline closed: cells enclosed by the drawn ones count too (courtyards of a closed ring excepted below)"""
    if not cells:
        return set()
    x0, x1 = min(c[0] for c in cells) - 1, max(c[0] for c in cells) + 1
    z0, z1 = min(c[1] for c in cells) - 1, max(c[1] for c in cells) + 1
    out, st = set(), [(x0, z0)]
    while st:
        p = st.pop()
        if p in out or p in cells or not (x0 <= p[0] <= x1 and z0 <= p[1] <= z1):
            continue
        out.add(p)
        st += [(p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)]
    return {(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1) if (x, z) not in out}


def dilate(cells, r):
    return {(x + dx, z + dz) for x, z in cells for dx in range(-r, r + 1) for dz in range(-r, r + 1)}


def comps(cells):
    seen, out = set(), []
    for c in cells:
        if c in seen:
            continue
        st, comp = [c], []
        while st:
            p = st.pop()
            if p in seen or p not in cells:
                continue
            seen.add(p)
            comp.append(p)
            st += [(p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)]
        out.append(comp)
    return out


def centroid(cells):
    n = len(cells) or 1
    return sum(c[0] for c in cells) / n + 0.5, sum(c[1] for c in cells) / n + 0.5


def roof_level(hs):
    """commonest roof level (1 m bins) above 2.5 m; None if nothing that high"""
    c = Counter(round(h) for h in hs if h > 2.5)
    if not c:
        return None
    lvl = c.most_common(1)[0][0]
    near = [h for h in hs if abs(h - lvl) <= 0.75]
    return sum(near) / len(near)


def main():
    fp_path, sm_path = Path(sys.argv[1]), Path(sys.argv[2])
    camp = json.loads((PUB / "campus" / "campus.json").read_text(encoding="utf-8"))
    B = {str(b["id"]): b for b in camp["buildings"] if b.get("kind") != "wall"}
    models = camp.get("models", [])
    measured_old = json.loads((ROOT / "data" / "manual" / "measured_heights.json").read_text(encoding="utf-8"))["buildings"]
    v2 = ROOT / "data" / "manual" / "measured_heights_v2.json"      # DSM re-registered (tools/dsm_register.py)
    measured = json.loads(v2.read_text(encoding="utf-8"))["buildings"] if v2.exists() else measured_old
    dorms = {r["id"]: r for r in csv.DictReader((ROOT / "data" / "dorms" / "dorms.csv").open(encoding="utf-8-sig"))}
    zones = json.loads((ROOT / "data" / "zones" / "grid.json").read_text(encoding="utf-8"))
    removed = json.loads((ROOT / "data" / "manual" / "building_overrides.json").read_text(encoding="utf-8")).get("remove_ids", {})
    # position check on the 2024-12 aerial photos by the detail-fixes session: verdict / detail per building id, and the
    # 本机素材-only buildings it looked at ("name (x,z)" -> status)
    pa_path = ROOT / "data" / "manual" / "position_audit.json"
    pa = json.loads(pa_path.read_text(encoding="utf-8")) if pa_path.exists() else {}
    pa_by, pa_lack = pa.get("by_id", {}), pa.get("lack", {})
    fps = json.loads(fp_path.read_text(encoding="utf-8"))
    scan = {r[0]: r for r in json.loads(sm_path.read_text(encoding="utf-8"))}
    boundary = camp.get("boundary", [])
    in_campus = lambda x, z: any(inside(x, z, rg) for rg in boundary)
    zone_of = lambda x, z: next((zn["id"] for zn in zones if zn["box"][0] <= x < zn["box"][2] and zn["box"][1] <= z < zn["box"][3]), "")

    # ---- game: per building 1 m cells -> top above the building's ground
    G = {}
    for bid, b in B.items():
        rise = b["roof"].get("rise", 0) if b.get("roof") else 0
        G[bid] = {"tops": {c: b["h"] + rise * 0.5 for c in poly_cells(b["pts"])}, "src": "程序生成", "pitched": bool(rise or b.get("hip"))}
    model_of = {}
    for md in models:
        p = PUB / md["file"]
        reps = [str(r) for r in md.get("replaces", []) if str(r) in B]
        for r in reps:
            model_of[r] = md["name"]
        if not p.exists() or not reps:
            continue
        per = defaultdict(list)
        for name, tris in glb(p):
            if name in reps:
                per[name] += tris
            elif len(reps) == 1:
                per[reps[0]] += tris
            else:                     # several buildings, nodes not named by id: each triangle to the nearest outline
                for t in tris:
                    cx, cz = sum(v[0] for v in t) / 3 + md["x"], sum(v[2] for v in t) / 3 + md["z"]
                    per[min(reps, key=lambda r: min((cx - x) ** 2 + (cz - z) ** 2 for x, z in B[r]["pts"]))].append(t)
        for bid, tris in per.items():
            cells, bot = tops(tris, md["x"], md["z"])
            G[bid] = {"tops": {c: y - bot for c, y in cells.items()}, "src": "精修模型 " + md["name"], "pitched": G[bid]["pitched"]}
    for ch in camp.get("generic", []):
        p = PUB / ch["file"]
        if not p.exists():
            continue
        for name, tris in glb(p):
            if name in B and B[name].get("generic"):
                cells, bot = tops(tris, ch["x"], ch["z"])
                G[name] = {"tops": {c: y - bot for c, y in cells.items()}, "src": "Blender 普通楼", "pitched": G[name]["pitched"]}
    for g in G.values():
        g["cells"] = fill(set(g["tops"]))
    # what the game draws anywhere: every building's cells (GLB extent for modelled ones, so a link or annex built into
    # a neighbour's GLB counts) plus the raised parts (> 2.5 m) of models that replace no building
    drawn = set().union(*(g["cells"] for g in G.values()))
    for md in models:
        p = PUB / md["file"]
        if p.exists() and not [r for r in md.get("replaces", []) if str(r) in B]:
            cells, bot = tops([t for _, tris in glb(p) for t in tris], md["x"], md["z"])
            drawn |= {c for c, y in cells.items() if y - bot > 2.5}
    drawn_near = dilate(drawn, 2)

    # game units: buildings replaced by one model whose cells touch (a building and its tower / annex) count as one
    unit = {bid: {bid} for bid in G}
    for md in models:
        reps = [str(r) for r in md.get("replaces", []) if str(r) in G]
        for a in reps:
            for b2 in reps:
                if a < b2 and (str(a).startswith("tower-") or str(b2).startswith("tower-") or len(reps) <= 3) \
                        and G[a]["cells"] & dilate(G[b2]["cells"], 1):
                    u = unit[a] | unit[b2]
                    for k in u:
                        unit[k] = u
    owner = defaultdict(set)
    for bid, g in G.items():
        for c in g["cells"]:
            owner[c].add(bid)

    # ---- 本机素材 objects (shifted by DZ), matched to game buildings by OSM id or by overlap
    S = []
    for folder, objs in fps.items():
        for oid, o in objs.items():
            tops_ = {(c[0], c[1] + round(DZ)): c[2] - o["ground"] for c in o["cells"]}
            S.append({"folder": folder, "oid": oid, "tops": tops_, "cells": fill(set(tops_)), "eave": (o["roof_p10"] - o["ground"]) if o.get("roof_p10") else None,
                      "fallback": o.get("roof_fallback", False) or not o.get("roof_p50")})
    targets = []
    match = defaultdict(list)
    for k, s in enumerate(S):
        ov = Counter(b for c in s["cells"] for b in owner.get(c, ()))
        tg = {s["oid"]} if s["oid"] in G else set()
        tg |= {b for b, n in ov.items() if n >= 0.25 * len(G[b]["cells"]) or n >= 0.3 * len(s["cells"])}
        targets.append(tg)
        for b in tg:
            match[b].append(k)

    rows = list(csv.DictReader((ROOT / "docs" / "building-audit.csv").open(encoding="utf-8-sig")))
    fields = list(rows[0].keys()) + [c for c in NEW_COLS if c not in rows[0]]
    questions, issues, zstat = [], [], defaultdict(lambda: [0, 0, 0])

    # pass 1: per building the shared measures
    P = {}
    for r in rows:
        bid = r["楼号"]
        if bid not in G:
            continue
        g, u = G[bid], unit[bid]
        ucells = set().union(*(G[x]["cells"] for x in u))
        utops = {}
        for x in u:
            for c, h in G[x]["tops"].items():
                utops[c] = max(utops.get(c, -1e9), h)
        e = {"u": u, "ucells": ucells, "utops": utops, "gmain": roof_level(list(g["tops"].values())), "ks": match.get(bid, [])}
        if e["ks"]:
            stops = {}
            for k in e["ks"]:
                for c, h in S[k]["tops"].items():
                    stops[c] = max(stops.get(c, -1e9), h)
            scells = set().union(*(S[k]["cells"] for k in e["ks"]))
            unear = dilate(ucells, 1)
            e.update(stops=stops, scells=scells, smain=roof_level([h for c, h in stops.items() if c in unear] or list(stops.values())),
                     fb=any(S[k]["fallback"] for k in e["ks"]))
            gx, gz = centroid(ucells)
            sx, sz = centroid(scells)
            e.update(dx=sx - gx, dz=sz - gz, ratio=len(scells) / max(1, len(ucells)), iou=len(scells & ucells) / max(1, len(scells | ucells)), cx=gx, cz=gz)
        P[bid] = e
    # local registration of 本机素材: median offset of the neighbours within 200 m (well overlapping ones only)
    good = [(b2, e) for b2, e in P.items() if "iou" in e and e["iou"] >= 0.45 and not str(b2).startswith("tower-")]
    for bid, e in P.items():
        if "iou" not in e:
            continue
        nb = [(e2["dx"], e2["dz"]) for b2, e2 in good if b2 != bid and math.hypot(e2["cx"] - e["cx"], e2["cz"] - e["cz"]) < 200]
        if len(nb) >= 3:
            e["ldx"], e["ldz"] = sorted(v[0] for v in nb)[len(nb) // 2], sorted(v[1] for v in nb)[len(nb) // 2]
        else:
            e["ldx"] = e["ldz"] = 0.0
    dsm_res = [P[b2]["smain"] - measured[b2]["h"] for b2 in P if P[b2].get("smain") and b2 in measured
               and measured[b2].get("cover", 0) >= 0.5 and measured[b2]["h"] > 3]
    obj_bias = sorted(dsm_res)[len(dsm_res) // 2] if dsm_res else 0.0
    print("本机素材 main roof - DSM: n", len(dsm_res), "median", round(obj_bias, 2))

    # pass 2: judgements
    for r in rows:
        for c in NEW_COLS:
            r[c] = ""
        bid = r["楼号"]
        if bid not in G:
            continue
        b, g, e = B[bid], G[bid], P[bid]
        name = r["显示名"] or r["官网名"] or r["OSM原名"] or bid
        z = zone_of(float(r["中心x"]), float(r["中心z"]))
        campus_ = r.get("校内") == "是"
        if campus_:
            zstat[z][0] += 1
        probs, sugg, owners, grade = [], [], set(), 0

        def flag(level, text, advice, who):
            nonlocal grade
            if name in VERIFIED and text.startswith(("高度", "层数")):
                return
            grade = max(grade, level)
            probs.append(text)
            if advice:
                sugg.append(advice)
            if who:
                owners.add(who)
        kind = b.get("kind", "other")
        modelled = g["src"] != "程序生成"
        own = "Blender 会话" if modelled else "主会话"
        meas = measured.get(bid)
        mh = meas["h"] if meas and meas.get("cover", 0) >= 0.5 and meas["h"] > 3 else None
        gmain, ks, ucells, u = e["gmain"], e["ks"], e["ucells"], e["u"]
        if mh and mh < 0.5 * max(gmain or 0, e.get("smain") or 0):
            mh = None                 # a hole in the DSM (a few metres over a whole building)
        pitched = g["pitched"] or bool(dorms.get(bid, {}).get("roof"))
        st = 3.45 if pitched or kind in ("dorm",) else STOREY.get(kind, 3.6)
        offl = int(dorms[bid]["official_floors"]) if dorms.get(bid, {}).get("official_floors") else None
        tower = str(bid).startswith("tower-")
        if tower:
            r["平面偏移"] = "塔楼部分，随主楼核对"
        elif ks:
            smain, fb, iou, ratio = e["smain"], e["fb"], e["iou"], e["ratio"]
            seave = min((S[k]["eave"] for k in ks if S[k]["eave"]), default=None) if pitched else None
            e["seave"] = seave
            r["素材主屋面高"] = (f"{smain:.1f}" if smain else "") + (f"（坡顶檐口 {seave:.1f}）" if seave else "") + ("（屋面按上表面估）" if fb else "")
            sfl = max(1, round((seave or smain) / st)) if smain else None
            r["素材层数估计"] = str(sfl or "")
            off = math.hypot(e["dx"], e["dz"])
            res = math.hypot(e["dx"] - e["ldx"], e["dz"] - e["ldz"])
            r["平面偏移"] = f"{off:.1f} m（扣除附近楼的整体偏差后 {res:.1f} m；面积比 {ratio:.2f}，重合 {iou:.0%}）"
            pv = pa_by.get(bid, {}).get("verdict", "")
            pos_ok = pv.startswith("游戏对") or "不改" in pv or pv.startswith("素材有")   # checked / placed on the photos: the game is right
            new_scan = str(bid).startswith("scan-") or pv.startswith("素材有")        # placed from the photos: a few m off the model is normal
            # 本机素材 lumps a block of several game buildings into one object (长望街区, 长望西街): not a mismatch
            lumped = len({t for k in ks for t in targets[k]} - u) >= 1 and len(ucells & e["scells"]) >= 0.6 * max(1, len(ucells))
            if lumped:
                r["平面偏移"] = "本机素材把这一片做成一个整体：" + r["平面偏移"]
            if pos_ok or lumped or (new_scan and min(off, res) < 10):
                pass
            elif iou < 0.3:
                flag(1, f"和本机素材对不上（重合 {iou:.0%}，面积比 {ratio:.2f}）", "核位置和轮廓（可能配错楼或现场变了）", "细节纠正会话")
                if campus_:
                    questions.append(("对不上", name, bid, z, f"游戏轮廓和本机素材只重合 {iou:.0%}、中心差 {off:.1f} m、面积比 {ratio:.2f}：是游戏位置错、配错楼，还是现场变了？"))
            else:
                if res > 4 and iou < 0.7 and not pos_ok and not lumped and not (new_scan and min(off, res) < 10):
                    flag(1, f"平面偏移 {res:.1f} m（已扣除附近楼的整体偏差，重合 {iou:.0%}；本机素材按 OSM 轮廓建，我们有些楼按航拍挪过，要对照正射照片看哪个对）", "对照正射照片核位置", "细节纠正会话")
                if (ratio < 0.65 or ratio > 1.5) and not new_scan and not lumped and "可细化" not in pv:
                    flag(1, f"平面面积比 {ratio:.2f}（本机素材 / 游戏）", "核轮廓", own)
                # height: the game is wrong only when two other sources agree against it
                refs = []
                if mh:
                    refs.append(("DSM", mh))
                if offl and (pitched or kind == "dorm"):
                    refs.append((f"官网 {offl} 层", offl * 3.45))
                if smain:
                    refs.append(("本机素材" + ("（估）" if fb else ""), seave if seave and (offl and pitched) else smain))
                if gmain and refs:
                    agree = [v for n_, v in refs if abs(v - gmain) <= (3.5 if n_.endswith("（估）") else 2.0)]
                    p30 = meas.get("p30", 0) if meas and meas.get("cover", 0) >= 0.5 else 0
                    if p30 > 3 and abs(p30 - gmain) <= 2.0:
                        agree.append(p30)      # mixed heights (气象楼): the DSM's lower level is the wings the game measures
                    others = [(n1, v1) for n1, v1 in refs]
                    cons = None
                    for i in range(len(others)):
                        for j in range(i + 1, len(others)):
                            if abs(others[i][1] - others[j][1]) <= 2.5:
                                cons = (others[i][1] + others[j][1]) / 2
                    txt = "，".join(f"{n1} {v1:.1f}" for n1, v1 in refs)
                    if not agree and cons is not None and abs(gmain - cons) > 1.5:
                        d = gmain - cons
                        lvl = 2 if abs(d) > 3 else 1
                        flag(lvl, f"高度：游戏{'高' if d > 0 else '低'} {abs(d):.1f} m（游戏 {gmain:.1f}；{txt}）", "按 DSM / 官网层数改高度", own)
                        gfl, cfl = max(1, round(gmain / st)), max(1, round(cons / st))
                        if gfl != cfl:
                            flag(lvl, f"层数：游戏约 {gfl}，应约 {cfl}" + (f"（官网 {offl}）" if offl else ""), "核层数（官网图 / 照片）", own)
                    elif not agree and cons is None and len(refs) == 1 and abs(gmain - refs[0][1]) > 3 and not refs[0][0].endswith("（估）"):
                        flag(1, f"高度待核：游戏 {gmain:.1f}，只有 {txt} 可比", "核高度", own)
                    elif not agree and cons is None and len(refs) >= 2 and campus_:
                        if name not in VERIFIED: questions.append(("高度", name, bid, z, f"各来源对不上：游戏 {gmain:.1f} m；{txt}" + ("（用户说近几年翻新过）" if name in RENOVATED else "")))
                        flag(1, f"高度：各来源对不上（游戏 {gmain:.1f}；{txt}）", "问用户 / 现场照片", "主会话")
                # a wing at another height (shared cells, outer ring of wall tops / eaves left out)
                dsm_confirms = bool(mh and gmain and abs(gmain - mh) <= 2.0)
                if iou >= 0.6 and not fb and not dsm_confirms and not any(p.startswith("高度") for p in probs):
                    core = {c for c in ucells & e["scells"] if all(n in ucells and n in e["scells"] for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)))}
                    diffs = [e["stops"][c] - e["utops"][c] for c in core if c in e["stops"] and c in e["utops"]]
                    if len(diffs) >= 40:
                        big = [dd for dd in diffs if abs(dd) > 3.5]
                        part = len(big) / len(diffs)
                        if part > 0.35:
                            mid_ = sorted(big)[len(big) // 2]
                            flag(1, f"高度：{part:.0%} 的面积游戏比本机素材{'低' if mid_ > 0 else '高'}约 {abs(mid_):.0f} m（某一翼的层数可能不对）", "逐翼核高度", own)
                # joined / link / annex: real blocks (>= 60 m2, >= 4 m wide on average, >= 2.5 m tall)
                others = sorted({t for k in ks for t in targets[k]} - u - {t for t in B if t.startswith("tower-")})
                others = [t for t in others if not (ucells & dilate(G[t]["cells"], 1))] if name not in LINKED else []   # joined in the game too
                if others:
                    nm = "、".join(B[t].get("name") or t for t in others)
                    r["连接体"] = f"本机素材里和 {nm} 是一个整体"
                    flag(2, f"本机素材把它和 {nm} 做成一个整体（连成一体）", "核对一层是否相连（连廊 / 裙楼）", "Blender 会话")
                extra = e["scells"] - drawn_near if name not in LINKED else set()     # drawn by any GLB / building = not missing
                annex = 0
                for cp in comps(extra):
                    xs_, zs_ = [c[0] for c in cp], [c[1] for c in cp]
                    hs = sorted(e["stops"].get(c, 0) for c in cp)
                    if len(cp) < 60 or len(cp) / max(max(xs_) - min(xs_) + 1, max(zs_) - min(zs_) + 1) < 4 or hs[len(hs) // 2] < 2.5:
                        continue
                    touch = sorted({t for c in dilate(set(cp), 5) for t in owner.get(c, ()) if t not in u and not t.startswith("tower-")})
                    if touch:
                        nm = "、".join(B[t].get("name") or t for t in touch)
                        r["连接体"] = (r["连接体"] + "；" if r["连接体"] else "") + f"连到 {nm}（{len(cp)} m²，高约 {hs[len(hs) // 2]:.0f} m）"
                        flag(2, f"连接体：本机素材有 {len(cp)} m² 连到 {nm}，游戏没有", "补连接体", "Blender 会话")
                    else:
                        annex += len(cp)
                if annex:
                    r["连接体"] = (r["连接体"] + "；" if r["连接体"] else "") + f"多出 {annex} m²"
                    flag(2 if annex >= 200 else 1, f"平面：本机素材多出 {annex} m²（附楼 / 裙楼）", "补附楼", own)
        elif campus_:
            r["平面偏移"] = "本机素材没有这栋"
        # sunk / floating with the new terrain (scanModels)
        sm = scan.get(model_of.get(bid))
        if sm and not tower:
            _, _, _, fmax, fat, _, bmax, bat, _ = sm
            for what, mx, at in (("悬空", fmax, fat), ("埋地", bmax, bat)):
                if at and mx >= 1.0 and (math.floor(at[0]), math.floor(at[1])) in dilate(ucells, 6):
                    flag(2 if mx >= 2 else 1, f"{what} {mx:.1f} m（{at[0]}, {at[1]}）",
                         "等航拍三维扫描重做地形后再看" if what == "埋地" else "模型底面对齐地形", "地表与植被会话" if what == "埋地" else "Blender 会话")
        # old / new DSM height next to the 本机素材 main roof: all three agreeing = usable
        mo, mn_ = measured_old.get(bid), measured.get(bid)
        fmt = lambda m: (f"{m['h']:.1f}" + (f"（覆盖 {m['cover']:.0%}）" if m.get("cover", 1) < 0.5 else "")) if m else ""
        r["旧实测高"], r["新实测高"] = fmt(mo), fmt(mn_)
        so = e.get("smain") if not tower else None
        ho = mo["h"] if mo and mo.get("cover", 0) >= 0.5 else None
        hn = mn_["h"] if mn_ and mn_.get("cover", 0) >= 0.5 else None
        hs = so - obj_bias if so else None              # 本机素材 main roof minus its median excess over the DSM
        T_ = 2.5
        if hn is not None and hs is not None:
            reno = "（用户说翻新过，要人工核）" if name in RENOVATED and name not in CONFIRMED else ""
            se = e.get("seave") if not tower else None
            # pitched: eaves or mid-roof; low buildings get a relative tolerance (4.2 m against a 7 m roof is not "the same")
            near = lambda h, tol: abs(h - hs) <= min(tol, max(1.5, 0.25 * hs)) or (se is not None and abs(h - (se - obj_bias)) <= min(tol, max(1.5, 0.25 * se)))
            if ho is not None and abs(ho - hn) <= T_:
                if near(hn, T_ + 0.5):
                    r["实测核对"] = f"可采用（新实测 {hn:.1f}）" if not reno else f"三者一致 {hn:.1f}{reno}"
                else:
                    r["实测核对"] = f"本机素材对不上（新旧实测都约 {hn:.1f}，本机素材 {so:.1f}）"
            elif near(hn, T_):
                r["实测核对"] = (f"可采用新实测 {hn:.1f}" if not reno else f"新实测和本机素材一致 {hn:.1f}{reno}") + (f"（旧实测 {ho:.1f} 混了地面）" if ho is not None else "")
            elif ho is not None and near(ho, T_):
                r["实测核对"] = f"新实测对不上（{hn:.1f}；旧 {ho:.1f} 和本机素材一致），配准后变差"
            else:
                r["实测核对"] = "三者对不上"
        elif hn is not None:
            r["实测核对"] = "没有本机素材，" + ("新旧实测一致" if ho is not None and abs(ho - hn) <= T_ else f"新实测 {hn:.1f}" + (f"，旧 {ho:.1f}" if ho is not None else ""))
        elif hs is not None:
            r["实测核对"] = "没有可靠实测（覆盖不足）"
        if name in RENOVATED and ks:
            questions.append(("翻新", name, bid, z, (f"{CONFIRMED[name]}。" if name in CONFIRMED else "") + "用户说近几年翻新过：本机素材可能是翻新前的样子，以无人机航拍 / 官网图 / 近照为准"
                              + (f"（本机素材主屋面 {e['smain']:.1f} m，DSM {mh:.1f} m，游戏 {gmain:.1f} m）" if e.get("smain") and mh and gmain else "")))
        if name in ASSIGNED or r.get("官网名") in ASSIGNED:
            owners = {"Blender 会话（已派）"}
        if name in VERIFIED:
            r["实测核对"] = VERIFIED[name]
        if name in LINKED:
            r["连接体"] = LINKED[name]
        r["问题等级"] = ["低", "中", "高"][grade] if probs else ""
        r["建议"] = "；".join(dict.fromkeys(sugg))
        r["负责会话"] = "、".join(sorted(owners))
        if probs:
            r["核对状态"] = "数据比对 2026-11-27：" + "；".join(probs)
        elif campus_:
            r["核对状态"] = "数据比对 2026-11-27：无明显问题" if ks else "数据比对 2026-11-27：本机素材没有这栋"
        if bid in pa_by:                 # the detail-fixes session's photo check, kept after the data comparison
            st_ = re.sub(r"；?位置核对 [^；]*.*$", "", r.get("核对状态") or "")
            r["核对状态"] = (st_ + "；" if st_ else "") + f"位置核对 2026-11-27：{pa_by[bid]['verdict']}（{pa_by[bid].get('detail', '')}）"
        if probs:
            if campus_:
                zstat[z][1 if grade == 2 else 2] += 1
            issues.append([grade, len(probs), name, bid, z, probs, r["负责会话"], g["src"], campus_])

    # 本机素材 buildings the game lacks / campus buildings it lacks
    lack = []
    for k, s in enumerate(S):
        if targets[k]:
            continue
        x, z_ = centroid(s["cells"])
        hs = list(s["tops"].values())
        lack.append([s["folder"], round(x), round(z_), len(s["cells"]), round(roof_level(hs) or max(hs), 1), zone_of(x, z_),
                     "校内" if in_campus(x, z_) else "校外", "已按用户说明删除" if s["oid"] in removed or any(str(v).startswith(s["folder"] + "：") for v in removed.values()) else ""])
    for l in lack:                      # 本机素材-only buildings the detail-fixes session already looked at on the photos
        for key, status in pa_lack.items():
            m_ = re.match(r"(.*?)\s*\((-?[\d.]+),\s*(-?[\d.]+)\)", key)
            if m_ and abs(float(m_.group(2)) - l[1]) <= 10 and abs(float(m_.group(3)) - l[2]) <= 10 and not l[7]:   # names differ ("未定名 ·020")
                l[7] = "位置核对：" + status
    nolocal = [[r["显示名"] or r["OSM原名"] or r["楼号"], r["楼号"], zone_of(float(r["中心x"]), float(r["中心z"])), r["类型"], r["高度m"]]
               for r in rows if r.get("校内") == "是" and r["楼号"] in G and not match.get(r["楼号"])]

    with (ROOT / "docs" / "building-audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    issues.sort(key=lambda t: (-t[0], -t[1]))
    verdict = Counter(re.sub(r"[\d.]+", "#", (r.get("实测核对") or "")).split("（")[0].replace(" #", "") for r in rows if r.get("校内") == "是")
    res = {"issues": issues, "lack": lack, "nolocal": nolocal, "questions": questions, "zones": {k: v for k, v in zstat.items()},
           "obj_bias": obj_bias, "verdict": dict(verdict),
           "game_h": {b_: round(e_["gmain"], 1) for b_, e_ in P.items() if e_.get("gmain")},   # main roof of what the game draws (GLB / block)
           # p70 of the drawn tops inside the building (same statistic as the DSM height; a pitched roof counts part of its rise)
           "game_p70": {b_: round(sorted(v for v in G[b_]["tops"].values() if v > 2.5)[int(0.7 * (sum(1 for v in G[b_]["tops"].values() if v > 2.5) - 1))], 1)
                        for b_ in P if any(v > 2.5 for v in G[b_]["tops"].values())}}
    (LOCAL / "check_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("issues", len(issues), "high", sum(1 for t in issues if t[0] == 2), "mid", sum(1 for t in issues if t[0] == 1),
          "lack", len(lack), "nolocal", len(nolocal), "questions", len(questions))
    if "--img" in sys.argv:
        overlays(res, B, G, S, match, targets)
    write_md(res, zones)


def write_md(res, zones):
    """docs/questions/buildings.md: summary, top 20, contradictions / questions for the user, missing buildings, per zone"""
    img = lambda bid: f"data/source/scan2022_analysis/audit_img/{bid}.jpg"
    crop = lambda nm: f"data/official/crops/{nm}.jpg" if (ROOT / "data" / "official" / "crops" / f"{nm}.jpg").exists() else ""
    camp = [t for t in res["issues"] if t[8]]
    reg = ROOT / "data" / "raw" / "dsm_register.json"
    DSM_NOTE = []
    if reg.exists():
        rg = json.loads(reg.read_text(encoding="utf-8"))
        ta, ch = rg.get("tile_affine", {}), rg.get("changes", {})
        tl = [t for t in rg.get("tiles", []) if t["score"] >= 0.75]
        DSM_NOTE = [
            f"- 整体平移：DSM 相对 campus.json 轮廓偏东 {rg['global_shift'][0]:.1f} m、偏北 {-rg['global_shift'][1]:.1f} m（轮廓格在 DSM 上“抬高”的比例 {rg['raised_share'][0]:.0%} → {rg['raised_share'][1]:.0%}），和 Blender 会话估的东 7、北 9 一致。",
            f"- 分区不一致：按 400 m 窗口（{len(tl)} 个）分别求，西侧（x < -400）只偏东约 -1 m，中东部偏东 5–10 m；北排偏北 13–17 m，南排 5–8 m。是 DSM 带了一点旋转 / 比例，用仿射场 dx = {ta['dx'][0]:+.1f} {ta['dx'][1]:+.1f}·x {ta['dx'][2]:+.1f}·z，dz = {ta['dz'][0]:+.1f} {ta['dz'][1]:+.1f}·x {ta['dz'][2]:+.1f}·z（x、z 以 km 计），窗口残差中位 {ta['residual']:.1f} m（只平移 {ta['residual_global']:.1f} m）。逐栋单独找偏移不可靠（宿舍成排，会对到隔壁一排）。",
            f"- 结果：比旧实测升高 2 m 以上 {ch.get('up2')} 栋、5 m 以上 {ch.get('up5')} 栋，降低 2 m 以上 {ch.get('down2')} 栋；混进地面（p30 < 3 m）的 {ch.get('p30_low', ['', ''])[0]} → {ch.get('p30_low', ['', ''])[1]} 栋。只平移和用仿射场，逐栋结果差别很小。",
            "- 已采用（主会话定，2026-11-27）：只把“实测核对”为“可采用”的楼换成新实测（名单 `data/manual/measured_adopt.json`，`tools/make_measured_adopt.py` 生成），尚贤楼、沁园22栋除外，基嘉楼（约 3 层）、明德楼（6 层）按用户确认加入；其余楼仍用旧实测。",
            "- 东苑（盘城新街以东）另外重量（`tools/dsm_register.py --east-only`）：在本机素材脚印上量、按局部偏移，地面取楼外 3–12 m 一圈 DSM 的 p20 和原地面模型里低的那个。原来 45 m 开运算的地面模型钻不进挨得很近的楼群（晖园11–14、东苑食堂），地面抬高了 3–8 m，楼高都偏低；偏移本身没问题。重量后晖园11–13 为 21–23 m、东苑食堂 12.9 m，和本机素材、官网层数（6 层 / 3 层）一致，已进可采用名单。",
            "- 2026-11-27 细节纠正会话挪完轮廓（26 栋）后全校重跑（`dsm_register.py --affine`，仿射比只平移好 0.75 m，正好在自动判断的门槛上，按上次一样用仿射场；再 `--east-only --write`），按同样规则重生成名单。核对时已接上 `data/manual/position_audit.json`：核为“游戏对 / 不改”的偏移不再报，新补的 scan-* 和本机素材差几米不报，本机素材把一片做成一个整体的（长望街区、长望西街）不算对不上。"]
    L = ["# 逐栋核对：各来源矛盾、需要问用户的楼", "", "> Blender 会话的逐栋问题和用户确认在 `docs/questions/buildings-blender.md`（那个文件由 Blender 会话维护，本工具不改它）。", "",
         "数据比对（常识排查会话，2026-11-27），只标问题、没改模型。工具 `tools/building_check.py`（本机素材部分 `tools/scan_footprints.py`，结果和叠加图只在本机：`data/source/scan2022_analysis/`）。逐栋结果见 `docs/building-audit.csv` 新加的 10 列（旧实测高、新实测高、素材主屋面高、实测核对、素材层数估计、平面偏移、连接体、问题等级、建议、负责会话）和“核对状态”。",
         "",
         "**比对方法**",
         f"- 高度：游戏（精修 / 普通楼 GLB 逐 1 m 格的顶高，否则程序楼高度）对比无人机 DSM（**重新配准后的 measured_heights_v2.json**，见下一节）、官网层数（宿舍，层高 3.45 m，用 52 栋有官网层数的宿舍标定）、本机素材主屋面。只有两个来源一致、而游戏和它们都差 1.5 m 以上时，才算游戏错（3 m 以上为高）。DSM 有空洞（整栋只有几米）时不用。配准后本机素材主屋面和 DSM 的中位差只有 {res['obj_bias']:+.2f} m。",
         "- 层数：按高度和层高估算（宿舍 3.45 m、公寓 3.0、教学 3.9、馆 / 食堂 4.5、其他 3.6），宿舍另和官网层数比。",
         "- 平面：本机素材脚印和游戏轮廓（模型顶视）比较中心偏移、面积比、重合度。偏移先扣掉附近 200 m 内楼的整体偏差（本机素材按 OSM 轮廓建，整体略有错位）。本机素材多出的块（≥60 m²、平均宽 ≥4 m、高 ≥2.5 m）：挨着另一栋游戏楼的算“连接体”，否则算附楼 / 裙楼。檐口、台阶、雨棚窄条不算。游戏这边按 GLB 实际范围算（包括做进相邻楼 GLB 的连接体 / 附楼），游戏里已经连在一起的不报“做成一个整体”。",
         "- 下沉 / 悬空：新地形下 `__campus.world.scanModels()` 的结果（悬空只看墙脚）。",
         "",
         f"**结果**：比对 {sum(v[0] for v in res['zones'].values())} 栋校内楼，有问题的 {len(camp)} 栋（高 {sum(1 for t in camp if t[0] == 2)}、中 {sum(1 for t in camp if t[0] == 1)}）。校外楼另有 {len(res['issues']) - len(camp)} 栋有问题（只记在 csv 里）。本机素材有、游戏没有的校内建筑 {sum(1 for l in res['lack'] if l[6] == '校内')} 处。游戏有、本机素材没有的校内楼 {len(res['nolocal'])} 栋。",
         "", "东苑食堂、国际教育学院（培训楼）、雷丁学院等 4 栋已派给 Blender 会话，表里负责会话写“Blender 会话（已派）”。", "",
         "## DSM 重新配准（tools/dsm_register.py → data/manual/measured_heights_v2.json，旧文件没动）", ""] + DSM_NOTE + ["",
         "csv 里并列三列“旧实测高 / 新实测高 / 素材主屋面高”，“实测核对”给结论（容差 2.5 m，矮楼取素材屋面的 25%、最少 1.5 m；本机素材先减去中位差；覆盖不足 50% 的实测不用）。校内楼：" +
         "、".join(f"{k or '无数据'} {v}" for k, v in sorted(res["verdict"].items(), key=lambda kv: -kv[1])) + "。", "",
         "## 问题最多的前 20 栋（校内）", "", "| # | 楼 | 区 | 等级 | 问题 | 负责会话 |", "|---|---|---|---|---|---|"]
    for i, t in enumerate(camp[:20], 1):
        L.append(f"| {i} | {t[2]} | {t[4]} | {'高' if t[0] == 2 else '中'} | {'；'.join(t[5])} | {t[6]} |")
    L += ["", "## 需要问用户 / 各来源矛盾的楼", ""]
    for kind, nm, bid, z, txt in res["questions"]:
        L.append(f"- **{nm}**（{bid}，{z} 区，{kind}）：{txt}")
        pics = [x for x in (img(bid) if (ROOT / img(bid)).exists() else "", crop(nm)) if x]
        if pics:
            L.append(f"  - 图：{'；'.join(pics)}（叠加图：红 = 游戏轮廓，青 = 本机素材，只在本机）")
    done_lack = [l for l in res["lack"] if l[6] == "校内" and l[7]]
    big = [l for l in res["lack"] if l[6] == "校内" and not l[7] and (l[3] >= 300 or l[4] >= 8)]
    if big:
        L += ["", "### 本机素材有、游戏里没有的较大建筑（校内，≥300 m² 或 ≥8 m）——现场还在吗？要不要补？", "",
              "| 本机素材名 | 位置 (x, z) | 区 | 占地 m² | 主屋面高 m |", "|---|---|---|---|---|"]
        for l in sorted(big, key=lambda l: -l[3]):
            L.append(f"| {l[0]} | ({l[1]}, {l[2]}) | {l[5]} | {l[3]} | {l[4]} |")
    small = [l for l in res["lack"] if l[6] == "校内" and not l[7] and not (l[3] >= 300 or l[4] >= 8)]
    if small:
        L += ["", "小的（棚、温室、亭）：" + "、".join(f"{l[0]}（{l[5]}）" for l in small) + "。"]
    if done_lack:
        L += ["", f"另有 {len(done_lack)} 处已由细节纠正会话按照片核过（已删 / 已没有 / 已补），不再列，见“位置核对结果”一节。"]
    L += ["", "## 按区汇总（docs/zones.md 的 42 区，校内楼）", "", "| 区 | 比对楼数 | 高 | 中 |", "|---|---|---|---|"]
    for zn in zones:
        v = res["zones"].get(zn["id"], [0, 0, 0])
        L.append(f"| {zn['id']} | {v[0]} | {v[1] or ''} | {v[2] or ''} |")
    out = ROOT / "docs" / "questions"
    out.mkdir(exist_ok=True)
    # sections other sessions wrote into this file (位置核对结果, Blender notes, ...) are kept, before the zone table
    MINE = ("## DSM 重新配准", "## 问题最多的前 20 栋", "## 需要问用户", "## 按区汇总")
    old = (out / "buildings.md").read_text(encoding="utf-8") if (out / "buildings.md").exists() else ""
    keep, cur = [], None
    for line in old.split(chr(10)):
        if line.startswith("## "):
            cur = None if line.startswith(MINE) else [line]
            if cur is not None:
                keep.append(cur)
        elif cur is not None:
            cur.append(line)
    if keep:
        at = L.index("## 按区汇总（docs/zones.md 的 42 区，校内楼）")
        extra_ = [ln for sec in keep for ln in (sec[:-1] if sec and sec[-1] == "" else sec) + [""]]
        L = L[:at] + extra_ + L[at:]
    (out / "buildings.md").write_text(chr(10).join(L) + chr(10), encoding="utf-8")


def overlays(res, B, G, S, match, targets):
    """aerial crop + game outline (red) + 本机素材 outline (cyan) for every building in the questions / high list"""
    from PIL import Image, ImageDraw
    Image.MAX_IMAGE_PIXELS = None
    camp = json.loads((PUB / "campus" / "campus.json").read_text(encoding="utf-8"))
    W, D = camp["size"]
    im = Image.open(PUB / "campus" / "ortho.jpg")
    iw, ih = im.size
    out = LOCAL / "audit_img"
    out.mkdir(exist_ok=True)
    ids = {q[2] for q in res["questions"]} | {t[3] for t in res["issues"] if t[0] == 2}
    for bid in ids:
        if bid not in G:
            continue
        cells = set(G[bid]["cells"])
        for k in match.get(bid, []):
            cells |= S[k]["cells"]
        xs, zs = [c[0] for c in cells], [c[1] for c in cells]
        x0, x1, z0, z1 = min(xs) - 25, max(xs) + 25, min(zs) - 25, max(zs) + 25
        f = lambda x, z: ((x + W / 2) / W * iw, (z + D / 2) / D * ih)
        a, b2 = f(x0, z0), f(x1, z1)
        cr = im.crop((int(a[0]), int(a[1]), int(b2[0]), int(b2[1]))).convert("RGB")
        sc = 600 / max(1, cr.size[0])
        cr = cr.resize((600, max(1, int(cr.size[1] * sc))))
        d = ImageDraw.Draw(cr)
        g = lambda x, z: (((x + W / 2) / W * iw - int(a[0])) * sc, ((z + D / 2) / D * ih - int(a[1])) * sc)
        def edge(cs, col):
            for (x, z) in cs:
                for dx, dz, seg in ((1, 0, ((x + 1, z), (x + 1, z + 1))), (-1, 0, ((x, z), (x, z + 1))), (0, 1, ((x, z + 1), (x + 1, z + 1))), (0, -1, ((x, z), (x + 1, z)))):
                    if (x + dx, z + dz) not in cs:
                        d.line([g(*seg[0]), g(*seg[1])], fill=col, width=2)
        edge(G[bid]["cells"], (255, 60, 40))
        for k in match.get(bid, []):
            edge(S[k]["cells"], (0, 230, 255))
        cr.save(out / f"{bid}.jpg", quality=85)


if __name__ == "__main__":
    main()
