"""Render a crop of the orthophoto with OSM/extra buildings shaded and a metre grid, to help trace missing buildings.

Usage: .venv/Scripts/python.exe tools/trace_aid.py NAME X0 Z0 X1 Z1 [MPP] [GRID]
  X/Z in local metres (x east, z south, origin = bbox centre); MPP metres per output pixel (default 1.0);
  GRID grid spacing in metres (default 20, labels every 5th line).
Output: data/raw/aid_NAME.jpg
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
campus = json.loads((ROOT / "web" / "public" / "campus" / "campus.json").read_text(encoding="utf-8"))
W, D = campus["size"]


def main():
    name = sys.argv[1]
    x0, z0, x1, z1 = map(float, sys.argv[2:6])
    mpp = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
    step = float(sys.argv[7]) if len(sys.argv) > 7 else 20.0
    img = Image.open(ROOT / "web" / "public" / "campus" / "ortho.jpg").convert("RGB")
    iw, ih = img.size
    to_src = lambda x, z: ((x + W / 2) / W * iw, (z + D / 2) / D * ih)
    sx0, sz0 = to_src(x0, z0)
    sx1, sz1 = to_src(x1, z1)
    out_w, out_h = round((x1 - x0) / mpp), round((z1 - z0) / mpp)
    crop = img.crop((round(sx0), round(sz0), round(sx1), round(sz1))).resize((out_w, out_h), Image.Resampling.LANCZOS)
    to_px = lambda x, z: ((x - x0) / mpp, (z - z0) / mpp)
    shade = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for b in campus["buildings"]:
        if b.get("src") == "manual":
            sd.polygon([to_px(x, z) for x, z in b["pts"]], fill=(0, 160, 255, 90), outline=(0, 200, 255, 255))
        else:
            sd.polygon([to_px(x, z) for x, z in b["pts"]], fill=(255, 40, 0, 90), outline=(255, 60, 0, 255))
    for zn in campus.get("zones", []):
        pts = [to_px(x, z) for x, z in zn["pts"]]
        sd.line(pts + pts[:1], fill=(255, 0, 255, 255), width=3)
    out = Image.alpha_composite(crop.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    gx = (int(x0 // step) + 1) * step
    while gx < x1:
        major = round(gx / step) % 5 == 0
        px = (gx - x0) / mpp
        d.line([(px, 0), (px, out_h)], fill=(255, 255, 0) if major else (255, 255, 255), width=1)
        if major:
            d.text((px + 2, 2), f"x{gx:.0f}", fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        gx += step
    gz = (int(z0 // step) + 1) * step
    while gz < z1:
        major = round(gz / step) % 5 == 0
        pz = (gz - z0) / mpp
        d.line([(0, pz), (out_w, pz)], fill=(255, 255, 0) if major else (255, 255, 255), width=1)
        if major:
            d.text((2, pz + 2), f"z{gz:.0f}", fill=(255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        gz += step
    out.save(ROOT / "data" / "raw" / f"aid_{name}.jpg", quality=88)
    print(out.size)


if __name__ == "__main__":
    main()
