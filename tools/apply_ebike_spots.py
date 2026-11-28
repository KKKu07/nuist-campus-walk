"""Add the hand-checked 7ma rows (data/manual/ebike_spots.json) to web/public/campus/campus.json without a full rebuild.

Manual bikes carry a 4th value 1 ([x, z, a, 1]) so re-running replaces them instead of adding duplicates.
build_campus.py appends the same rows on a full rebuild (see ebike_stations).
Usage: .venv/Scripts/python.exe tools/apply_ebike_spots.py
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manual_spots():
    path = ROOT / "data" / "manual" / "ebike_spots.json"
    if not path.exists():
        return []
    out = []
    for r in json.loads(path.read_text(encoding="utf-8"))["rows"]:
        (x0, z0), (x1, z1), n = r["from"], r["to"], max(1, r["n"])
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0
            out.append([round(x0 + (x1 - x0) * t, 2), round(z0 + (z1 - z0) * t, 2), round(r["a"], 3), 1])
    return out


def main():
    p = ROOT / "web" / "public" / "campus" / "campus.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    keep = [e for e in data.get("ebikes", []) if len(e) < 4]
    add = manual_spots()
    data["ebikes"] = keep + add
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"e-bikes: {len(keep)} generated + {len(add)} manual")


if __name__ == "__main__":
    main()
