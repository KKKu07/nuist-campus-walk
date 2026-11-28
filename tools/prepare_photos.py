"""Resize the building photos listed in data/manual/building_overrides.json into web/public/photos/.

Usage: .venv/Scripts/python.exe tools/prepare_photos.py
Writes <slug>_<n>.jpg (long side 1280 px) and data/manual/photo_index.json {building name: [{file, caption}]}.
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "photos"
SLUG = {"气象楼": "qixianglou", "尚贤楼": "shangxianlou", "图书馆": "tushuguan", "文德楼": "wendelou",
        "滨江楼": "binjianglou", "藕舫楼": "oufanglou", "见山园": "jianshanyuan", "逸夫楼": "yifulou",
        "行政楼": "xingzhenglou", "东苑体育馆": "dongyuan_tiyuguan", "水云方": "shuiyunfang",
        "国际教育学院": "guoji_jiaoyu", "信息科技大楼": "xinxikeji", "气象谷美食城": "qixianggu",
        "老校门": "laoxiaomen", "东大门": "dongdamen", "升旗广场": "shengqi", "雷达塔": "leidata"}


def main():
    spec = json.loads((ROOT / "data" / "manual" / "building_overrides.json").read_text(encoding="utf-8"))
    src_root = Path(spec["photo_root"])
    if not src_root.is_absolute():
        src_root = ROOT / src_root
    pois_path = ROOT / "data" / "manual" / "pois.json"
    entries = dict(spec["buildings"])
    if pois_path.exists():
        for poi in json.loads(pois_path.read_text(encoding="utf-8"))["pois"]:
            entries[poi["name"]] = poi
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for name, o in entries.items():
        for n, fname in enumerate(o.get("photos", [])):
            slug = SLUG.get(name) or re.sub(r"[^a-z0-9]+", "_", name.encode("unicode_escape").decode().lower())
            out = OUT / f"{slug}_{n}.jpg"
            if not out.exists():
                im = Image.open(src_root / fname)
                if im.format == "JPEG":
                    im.draft("RGB", (2560, 2560))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                im.save(out, quality=80, optimize=True, progressive=True)
            cap = Path(fname).stem
            cap = name if cap.startswith(("DJI_", "3")) or cap.isdigit() else cap
            index.setdefault(name, []).append({"file": f"photos/{out.name}", "caption": cap})
    (ROOT / "data" / "manual" / "photo_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.glob("*.jpg")) / 1e6
    print(f"{sum(len(v) for v in index.values())} photos, {total:.1f} MB")


if __name__ == "__main__":
    main()
