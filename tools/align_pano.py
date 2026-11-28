"""Georeference our own campus orthomosaic by feature-matching it to the current (Esri) ortho, then blend it in.

Usage: .venv/Scripts/python.exe tools/align_pano.py "C:/path/全景航拍.jpg"
Output: web/public/campus/ortho.jpg + ortho_4k.jpg (our mosaic where it covers, Esri elsewhere),
        data/raw/ortho_esri*.jpg (backup of the originals, made once),
        data/raw/align_check.jpg (OSM outlines over the new ortho), data/raw/align_meta.json
"""
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
CAMPUS = ROOT / "web" / "public" / "campus"


def load_gray(path, max_w):
    im = Image.open(path)
    scale = min(1.0, max_w / im.width)
    if im.format == "JPEG" and scale < 1:
        im.draft("RGB", (int(im.width * scale), int(im.height * scale)))
    im = im.convert("RGB")
    full_w = Image.open(path).width
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.Resampling.LANCZOS)
    s = im.width / full_w
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY), s


def poly_terms(x, y, order):
    return np.stack([x ** i * y ** j for i in range(order + 1) for j in range(order + 1 - i)], axis=1)


def main():
    pano_path = Path(sys.argv[1])
    backup = ROOT / "data" / "raw"   # Esri originals live outside web/public so they never ship
    for n in ("ortho.jpg", "ortho_4k.jpg"):
        if not (backup / n.replace("ortho", "ortho_esri")).exists():
            shutil.copy(CAMPUS / n, backup / n.replace("ortho", "ortho_esri"))
    esri_full = np.asarray(Image.open(backup / "ortho_esri.jpg").convert("RGB"))
    EH, EW = esri_full.shape[:2]

    g_ref, s_ref = load_gray(backup / "ortho_esri.jpg", 4000)
    g_pan, s_pan = load_gray(pano_path, 4500)
    clahe = cv2.createCLAHE(2.0, (8, 8))
    g_ref, g_pan = clahe.apply(g_ref), clahe.apply(g_pan)
    sift = cv2.SIFT_create(nfeatures=40000)
    k1, d1 = sift.detectAndCompute(g_pan, None)
    k2, d2 = sift.detectAndCompute(g_ref, None)
    matches = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64}).knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    # pano px (full res) -> ortho px (full res)
    src = np.float32([k1[m.queryIdx].pt for m in good]) / s_pan
    dst = np.float32([k2[m.trainIdx].pt for m in good]) / s_ref
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 8.0, maxIters=20000, confidence=0.999)
    inl = mask.ravel().astype(bool)
    m_per_px = json.loads((CAMPUS / "campus.json").read_text(encoding="utf-8"))["size"][0] / EW
    proj = cv2.perspectiveTransform(src[inl].reshape(-1, 1, 2), H).reshape(-1, 2)
    rms_h = float(np.sqrt(((proj - dst[inl]) ** 2).sum(1).mean()) * m_per_px)
    print(f"matches {len(good)}, homography inliers {inl.sum()}, RMS {rms_h:.2f} m")

    # refine: polynomial map ortho px -> pano px on inliers, with outlier trimming
    X, Y = dst[inl, 0] / EW, dst[inl, 1] / EH
    U, V = src[inl, 0], src[inl, 1]
    keep = np.ones(len(X), bool)
    order = 3
    for _ in range(4):
        A = poly_terms(X[keep], Y[keep], order)
        cu, *_ = np.linalg.lstsq(A, U[keep], rcond=None)
        cv_, *_ = np.linalg.lstsq(A, V[keep], rcond=None)
        Af = poly_terms(X, Y, order)
        err = np.hypot(Af @ cu - U, Af @ cv_ - V)
        thr = max(3 * np.median(err[keep]), 4.0)
        keep = err < thr
    pano_mpp = m_per_px / np.sqrt(abs(np.linalg.det(H[:2, :2]))) if abs(np.linalg.det(H[:2, :2])) > 0 else 0
    rms_p = float(np.sqrt((err[keep] ** 2).mean()) * pano_mpp)
    print(f"poly order {order}: kept {keep.sum()}, RMS {rms_p:.2f} m (pano {pano_mpp:.3f} m/px)")

    # The homography is as accurate as the polynomial here and does not run away at the mosaic edges,
    # so it is what we warp with; the polynomial fit above is kept only as a diagnostic.
    pano = np.asarray(Image.open(pano_path).convert("RGB"))
    PH, PW = pano.shape[:2]
    warped = cv2.warpPerspective(pano, H, (EW, EH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    inside = cv2.warpPerspective(np.full((PH, PW), 255, np.uint8), H, (EW, EH), flags=cv2.INTER_NEAREST)
    inside = (inside > 0).astype(np.uint8)
    inside = cv2.erode(inside, np.ones((7, 7), np.uint8))
    # ignore pure white / black padding inside the mosaic
    lum = warped.mean(2)
    inside &= ((lum > 8) & (lum < 250)).astype(np.uint8)
    inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    feather = cv2.distanceTransform(inside, cv2.DIST_L2, 5)
    alpha = np.clip(feather / (15 / m_per_px), 0, 1)[..., None]   # 15 m blend band
    out = (warped * alpha + esri_full * (1 - alpha)).astype(np.uint8)
    img = Image.fromarray(out)
    img.save(CAMPUS / "ortho.jpg", quality=86)
    small = img.resize((4096, round(EH * 4096 / EW)), Image.Resampling.LANCZOS)
    small.save(CAMPUS / "ortho_4k.jpg", quality=86)

    campus = json.loads((CAMPUS / "campus.json").read_text(encoding="utf-8"))
    W, D = campus["size"]
    chk = small.copy()
    from PIL import ImageDraw
    d = ImageDraw.Draw(chk)
    sw, sh = chk.size
    for b in campus["buildings"]:
        d.polygon([((x + W / 2) / W * sw, (z + D / 2) / D * sh) for x, z in b["pts"]], outline=(255, 40, 0), width=2)
    chk.resize((sw // 2, sh // 2)).save(ROOT / "data" / "raw" / "align_check.jpg", quality=82)
    meta = dict(source=pano_path.name, matches=len(good), inliers=int(inl.sum()), rms_homography_m=round(rms_h, 2),
                rms_poly_m=round(rms_p, 2), coverage=round(float(inside.mean()), 3))
    (ROOT / "data" / "raw" / "align_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(meta)


if __name__ == "__main__":
    main()
