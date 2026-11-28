"""Download open (CC0) assets: PBR ground textures (ambientCG), sky HDRI (Poly Haven), low-poly nature kit (Kenney).

Usage: .venv/Scripts/python.exe tools/fetch_assets.py
Output: data/assets/<source>/... (originals), web/public/tex/*.jpg (web-sized copies), data/assets/LICENSES.md
"""
import io
import json
import re
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data" / "assets"
WEBTEX = ROOT / "web" / "public" / "tex"
UA = {"User-Agent": "Mozilla/5.0 (campus-3d-prototype)"}
log = []


def get(url, binary=True):
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    return data if binary else data.decode("utf-8", "replace")


def ambientcg(query, role):
    api = "https://ambientcg.com/api/v2/full_json?" + urllib.parse.urlencode(
        {"type": "Material", "q": query, "limit": 8, "sort": "Popular", "include": "downloadData"})
    for asset in json.loads(get(api, False)).get("foundAssets", []):
        aid = asset["assetId"]
        dl = None
        for cat in asset.get("downloadFolders", {}).values():
            for d in cat.get("downloadFiletypeCategories", {}).get("zip", {}).get("downloads", []):
                if d.get("attribute") == "1K-JPG":
                    dl = d["downloadLink"]
        if not dl:
            continue
        folder = ASSETS / "ambientcg" / aid
        if not folder.exists():
            folder.mkdir(parents=True)
            zipfile.ZipFile(io.BytesIO(get(dl))).extractall(folder)
            time.sleep(0.5)
        files = {f.name: f for f in folder.iterdir()}
        col = next((f for n, f in files.items() if n.endswith("_Color.jpg")), None)
        nrm = next((f for n, f in files.items() if n.endswith("_NormalGL.jpg")), None)
        if col:
            Image.open(col).convert("RGB").resize((1024, 1024)).save(WEBTEX / f"{role}.jpg", quality=86)
        if nrm:
            Image.open(nrm).convert("RGB").resize((1024, 1024)).save(WEBTEX / f"{role}_n.jpg", quality=90)
        log.append(f"| `{role}` | ambientCG {aid} (1K JPG) | CC0 | https://ambientcg.com/view?id={aid} |")
        return aid
    return None


def polyhaven_hdri(asset, res="2k"):
    files = json.loads(get(f"https://api.polyhaven.com/files/{asset}", False))
    url = files["hdri"][res]["hdr"]["url"]
    out = ASSETS / "polyhaven" / f"{asset}_{res}.hdr"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_bytes(get(url))
    (WEBTEX / "sky.hdr").write_bytes(out.read_bytes())
    log.append(f"| `sky.hdr` | Poly Haven {asset} ({res}) | CC0 | https://polyhaven.com/a/{asset} |")


def kenney(slug):
    page = get(f"https://kenney.nl/assets/{slug}", False)
    m = re.search(r'href="([^"]+\.zip)"', page)
    if not m:
        return None
    url = urllib.parse.urljoin("https://kenney.nl", m.group(1))
    folder = ASSETS / "kenney" / slug
    if not folder.exists():
        folder.mkdir(parents=True)
        zipfile.ZipFile(io.BytesIO(get(url))).extractall(folder)
    log.append(f"| `{slug}` | Kenney {slug} | CC0 | https://kenney.nl/assets/{slug} |")
    return folder


def main():
    WEBTEX.mkdir(parents=True, exist_ok=True)
    for q, role in (("grass", "grass"), ("asphalt", "asphalt"), ("paving stones", "paving"), ("ground", "dirt"),
                    ("roofing tiles", "rooftiles"), ("bricks", "bricks"), ("concrete", "concrete")):
        try:
            print(role, ambientcg(q, role))
        except Exception as e:
            print(role, "ERR", e)
    try:
        polyhaven_hdri("kloofendal_48d_partly_cloudy_puresky")
        print("hdri ok")
    except Exception as e:
        print("hdri ERR", e)
    try:
        print("kenney", kenney("nature-kit"))
    except Exception as e:
        print("kenney ERR", e)
    lic = ASSETS / "LICENSES.md"
    head = "# 素材来源与许可\n\n| 文件 | 来源 | 许可 | 链接 |\n| --- | --- | --- | --- |\n"
    old = lic.read_text(encoding="utf-8").splitlines()[4:] if lic.exists() else []
    rows = sorted(set(old + log))
    lic.write_text(head + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"done, {len(log)} assets logged")


if __name__ == "__main__":
    main()
