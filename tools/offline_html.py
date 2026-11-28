"""Pack a Vite build (dist/) of the showcase into ONE self-contained HTML file that opens by double-click (file://).

Browsers block a local page from reading other local files, so every asset (campus data, GLB models, textures, sky) is
embedded as base64 (in a non-executed JSON script element) and served from memory: a small shim in front of the app
maps relative asset URLs to blob: URLs, made on first use, for window.fetch (JSON, GLB, HDR) and for <img>.src
(textures via THREE.TextureLoader). The app's JS bundle is inlined
as a module script. campus/ortho_4k.jpg is not embedded; requests for it get campus/ortho.jpg.

Usage: .venv\\Scripts\\python.exe tools\\offline_html.py <dist dir> <out.html>
Used by tools/make_showcase_branch.py, which puts the result in the campus-showcase branch.
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

MIME = {".json": "application/json", ".glb": "model/gltf-binary", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".hdr": "application/octet-stream", ".bin": "application/octet-stream"}
ALIAS = {"campus/ortho_4k.jpg": "campus/ortho.jpg"}

# 性能 (2026-11-27): the assets sit in a non-executed <script type="application/json"> that is parsed once and removed,
# and each asset becomes a Blob (blob: URL) on first use, its base64 dropped. Before, the base64 lived in an executed
# script (V8 keeps the source of a script whose functions are alive) and every asset was also kept as a data: URL
# string, so ~3 copies of the 45 MB stayed in the page's memory.
SHIM = r"""
(function () {
  var el = document.getElementById('offline-assets'), A = JSON.parse(el.textContent), ALIAS = %s, urls = {};
  el.parentNode.removeChild(el);
  var base = location.href.replace(/[?#].*$/, '').replace(/[^\/]*$/, '');
  function local(u) {
    if (typeof u !== 'string') return null;
    var abs; try { abs = new URL(u, location.href).href; } catch (e) { return null; }
    if (abs.indexOf(base) !== 0) return null;
    var p = decodeURIComponent(abs.slice(base.length).replace(/[?#].*$/, ''));
    p = ALIAS[p] || p;
    return A[p] || urls[p] ? p : null;
  }
  function blobURL(p) {
    if (urls[p]) return urls[p];
    var bin = atob(A[p][1]), n = bin.length, b = new Uint8Array(n);
    for (var i = 0; i < n; i++) b[i] = bin.charCodeAt(i);
    urls[p] = URL.createObjectURL(new Blob([b], { type: A[p][0] }));
    delete A[p];
    return urls[p];
  }
  window.__offlineURL = function (u) { var p = local(u); return p ? blobURL(p) : u; };
  var f0 = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var p = local(typeof input === 'string' ? input : input && input.url);
    return p ? f0(blobURL(p), init) : f0(input, init);
  };
  var d = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
  Object.defineProperty(HTMLImageElement.prototype, 'src', { configurable: true, enumerable: d.enumerable,
    get: function () { return d.get.call(this); }, set: function (v) { d.set.call(this, window.__offlineURL(v)); } });
})();
"""


def inline_dist(dist: Path) -> bytes:
    html = (dist / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="module"[^>]*\ssrc="\./(assets/[^"]+\.js)"[^>]*></script>', html)
    if not m:
        sys.exit("no module script in dist/index.html")
    js = (dist / m.group(1)).read_text(encoding="utf-8").replace("</script", "<\\/script")
    if re.search(r'<link[^>]+href="\./assets/', html):
        sys.exit("dist/index.html links other built assets; inline them first")
    assets = {}
    for p in sorted(dist.rglob("*")):
        rel = p.relative_to(dist).as_posix()
        if not p.is_file() or rel == "index.html" or rel.startswith("assets/") or rel in ALIAS:
            continue
        assets[rel] = [MIME.get(p.suffix.lower(), "application/octet-stream"), base64.b64encode(p.read_bytes()).decode("ascii")]
    data = json.dumps(assets, separators=(",", ":"))      # paths + base64 only: no "</script" inside
    tag = ("<script type=\"application/json\" id=\"offline-assets\">" + data + "</script>\n"
           "<script>" + (SHIM % json.dumps(ALIAS)) + "</script>\n"
           "<script type=\"module\">" + js + "</script>")
    return (html[:m.start()] + tag + html[m.end():]).encode("utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    b = inline_dist(Path(sys.argv[1]))
    Path(sys.argv[2]).write_bytes(b)
    print(f"{sys.argv[2]}: {len(b) / 1048576:.1f} MB")
