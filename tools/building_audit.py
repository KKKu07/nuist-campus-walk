"""WP5: per-building audit table for checking every building against the official map, the aerial data and photos.

Usage: .venv/Scripts/python.exe tools/building_audit.py   ->  docs/building-audit.csv (UTF-8 with BOM, opens in Excel)
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
c = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
measured = json.loads((ROOT / "data" / "manual" / "measured_heights.json").read_text(encoding="utf-8"))["buildings"]
# adopted re-registered DSM heights (tools/make_measured_adopt.py) replace the old measurement for those buildings
_ad, _v2 = ROOT / "data" / "manual" / "measured_adopt.json", ROOT / "data" / "manual" / "measured_heights_v2.json"
adopted = set(json.loads(_ad.read_text(encoding="utf-8"))["buildings"]) if _ad.exists() and _v2.exists() else set()
if adopted:
    _v2b = json.loads(_v2.read_text(encoding="utf-8"))["buildings"]
    measured = {**measured, **{k: _v2b[k] for k in adopted if k in _v2b}}
overrides = json.loads((ROOT / "data" / "manual" / "building_overrides.json").read_text(encoding="utf-8"))["buildings"]
official = json.loads((ROOT / "data" / "official" / "local.json").read_text(encoding="utf-8"))
models = json.loads((ROOT / "data" / "blender" / "models.json").read_text(encoding="utf-8")) if (ROOT / "data" / "blender" / "models.json").exists() else []
walls = json.loads((ROOT / "data" / "official" / "wall_colors.json").read_text(encoding="utf-8"))
off_names = official["names"]
model_of = {str(r): m["name"] for m in models for r in m.get("replaces", [])}


def inside(x, z, pts):
    s, j = False, len(pts) - 1
    for i in range(len(pts)):
        (xi, zi), (xj, zj) = pts[i], pts[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            s = not s
        j = i
    return s


def main():
    rows = []
    for b in c["buildings"]:
        if b.get("kind") == "wall":
            continue
        bid = str(b["id"])
        xs, zs = [p[0] for p in b["pts"]], [p[1] for p in b["pts"]]
        cx, cz = sum(xs) / len(xs), sum(zs) / len(zs)
        campus = b.get("campus", any(inside(cx, cz, r) for r in c["boundary"]))
        name = b.get("label") or b.get("name") or ""
        ov = overrides.get(b.get("osm_name") or b.get("name") or "", {})
        if b.get("fixed") or "lv" in ov or "h" in ov:
            hsrc = "照片/人工校正"
        elif b.get("measured"):
            hsrc = "航拍三维重建实测（配准后）" if bid in adopted else "航拍三维重建实测"
        elif b.get("src") == "measured":
            hsrc = "实测（自动识别的高塔）"
        elif b.get("lv") and b.get("src") != "manual" and not b.get("measured"):
            hsrc = "OSM 层数或按名称估算"
        else:
            hsrc = "估算"
        if ov.get("color"):
            csrc = "实拍照片"
        elif bid in walls and b.get("color"):
            csrc = "官网手绘地图取色"
        else:
            csrc = "按类型默认"
        m = measured.get(bid, {})
        rows.append({
            "楼号": bid, "显示名": name, "官网名": off_names.get(bid, ""), "OSM原名": b.get("osm_name", b.get("name", "") if b.get("src") != "manual" else ""),
            "来源": {"manual": "人工补画", "measured": "实测识别"}.get(b.get("src"), "OSM"), "校内": "是" if campus else "否",
            "类型": b.get("kind", ""), "立面风格": b.get("style", ""), "高度m": b.get("h"), "层数": b.get("lv") or round((b["h"] - 1.2) / 3.6),
            "高度来源": hsrc, "实测p70/p95": f'{m["h"]}/{m["p95"]}' if m else "", "颜色来源": csrc,
            "坡屋顶": "是" if b.get("roof") else "", "精修模型": model_of.get(bid, ""), "实拍照片": len(b.get("photos") or []),
            "中心x": round(cx, 1), "中心z": round(cz, 1), "核对状态": "",
        })
    rows.sort(key=lambda r: (r["校内"] != "是", r["显示名"] == "", r["显示名"]))
    out = ROOT / "docs" / "building-audit.csv"
    # keep what other sessions wrote at the end of 核对状态 (the detail-fixes session's "位置核对 …" photo check)
    if out.exists():
        prev = {r["楼号"]: r.get("核对状态", "") for r in csv.DictReader(out.open(encoding="utf-8-sig"))}
        for r in rows:
            i = prev.get(r["楼号"], "").find("位置核对")
            if i >= 0:
                r["核对状态"] = prev[r["楼号"]][i:]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} buildings ->", out)
    print("height source:", Counter(r["高度来源"] for r in rows))
    print("colour source:", Counter(r["颜色来源"] for r in rows))
    print("campus named:", sum(1 for r in rows if r["校内"] == "是" and r["显示名"]), "/ campus total:", sum(1 for r in rows if r["校内"] == "是"))


if __name__ == "__main__":
    main()
