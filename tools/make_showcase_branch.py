"""Build the `campus-showcase` branch: the campus 3D scene only (no gameplay), as a stand-alone Vite app at the repo root.

The branch is generated from the full project, never edited by hand. It holds:
  index.html            <- web/showcase.html
  src/*.js              <- web/src/showcase.js and the modules it imports (world / sports / life / textures / bounds)
  public/campus/*       <- web/public/campus/* (scene data, ortho, land cover, terrain)
  public/models/...     <- only the GLBs that campus.json places (landmarks + generic chunks)
  public/tex/*          <- web/public/tex/* (CC0 textures, sky)
  package.json, package-lock.json, vite.config.js, README.md, ASSET-LICENSES.md, .gitignore, .gitattributes
  nuist-campus-3d.html  <- vite build of the above packed into one HTML (tools/offline_html.py): double-click to open,
                           no Node.js, no network (built with web/node_modules; --no-offline skips it)
Game code (main.js, phone/, quest.js, tour.js, vehicles.js, avatar.js, start.js, route.js, stunt.js), photos and
game data (web/public/data) are left out; the script stops if the showcase ever imports one of them.

Nothing in the working tree, the index or the checked-out branch changes: blobs are read from a commit (default HEAD)
or, with --worktree, hashed from the files on disk; the tree is written through a temporary index and the commit goes
to refs/heads/<branch> with the previous showcase commit as parent (so pushes stay fast-forward).

Usage (project root):
  .venv\\Scripts\\python.exe tools\\make_showcase_branch.py              # from HEAD
  .venv\\Scripts\\python.exe tools\\make_showcase_branch.py --worktree   # from the files on disk (testing)
  .venv\\Scripts\\python.exe tools\\make_showcase_branch.py --dry-run    # list what would go in
  .venv\\Scripts\\python.exe tools\\make_showcase_branch.py --orphan     # fresh root commit that replaces the branch history
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME_ONLY = re.compile(r"^web/src/(main|quest|tour|vehicles|avatar|start|route|stunt)\.js$|^web/src/phone/")
IMPORT_RE = re.compile(r"""(?:import|export)\s[^'"]*?from\s*['"](\.{1,2}/[^'"]+)['"]|import\s*\(\s*['"](\.{1,2}/[^'"]+)['"]\s*\)|import\s*['"](\.{1,2}/[^'"]+)['"]""")


def git(*args: str, input: bytes | None = None, env: dict | None = None) -> bytes:
    r = subprocess.run(["git", *args], cwd=ROOT, input=input, capture_output=True, env=env)
    if r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.decode('utf-8', 'replace')}")
    return r.stdout


class Source:
    """Read project files either from a commit or from the working tree (non-ignored files only)."""

    def __init__(self, rev: str | None):
        self.rev = rev
        self.files: dict[str, str] = {}      # path -> blob sha (commit mode) or "" (working tree)
        if rev:
            self.commit: str | None = git("rev-parse", "--verify", f"{rev}^{{commit}}").decode().strip()
            for rec in git("ls-tree", "-r", "-z", self.commit).split(b"\0"):
                if rec:
                    meta, path = rec.split(b"\t", 1)
                    self.files[path.decode("utf-8")] = meta.decode().split()[2]
        else:
            self.commit = None
            out = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            self.files = {p: "" for p in out.decode("utf-8").split("\0") if p and (ROOT / p).is_file()}

    def has(self, path: str) -> bool:
        return path in self.files

    def read(self, path: str) -> bytes:
        if self.rev:
            return git("cat-file", "blob", self.files[path])
        return (ROOT / path).read_bytes()

    def blob(self, path: str) -> str:
        if self.rev:
            return self.files[path]
        return git("hash-object", "-w", "--", path).decode().strip()

    def under(self, prefix: str) -> list[str]:
        return sorted(p for p in self.files if p.startswith(prefix))


def import_closure(src: Source, entry: str) -> list[str]:
    seen, todo = [], [entry]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        if not src.has(p):
            sys.exit(f"missing module {p}")
        seen.append(p)
        text = src.read(p).decode("utf-8")
        for m in IMPORT_RE.finditer(text):
            rel = next(g for g in m.groups() if g)
            todo.append(posixpath.normpath(posixpath.join(posixpath.dirname(p), rel)))
    return sorted(seen)


README = """# 南京信息工程大学 · 校园三维场景（展示版）

浏览器里的南京信息工程大学全校三维场景：建筑、道路、水系、运动场、绿化和地形的整体模型，打开就是高空俯瞰，可以自由平移、旋转、拉远拉近。这个分支**只有场景**，不含游戏玩法。

现有内容：{buildings} 栋建筑，其中 {models} 个 Blender 精修地标、{generic} 栋 Blender 普通楼模型；约 {trees} 棵树；{roads} 条道路；{sports} 处运动场。

## 最简单：下载一个文件，双击打开（给老师演示用这个）

1. 在本分支的文件列表里点 **`{offline}`**，再点右上角的 **下载按钮**（Download raw file，向下箭头图标）。文件约 {offline_mb} MB。
   也可以点绿色的 **Code → Download ZIP**，解压后找到 `{offline}`。
2. 双击这个文件，用 **Chrome 或 Edge** 打开（默认不是这两个浏览器的话：右键 → 打开方式 → 选 Chrome 或 Edge）。
3. 等 10～30 秒加载完，就是全校俯瞰画面。**不需要联网，也不需要安装任何软件。**

注意：不要点 GitHub 上的 “View raw” 或在网页里预览这个文件（只会显示一大段代码），一定要下载到电脑上再双击。建议用电脑，有独立显卡更流畅。

## 开发方式（需要 Node.js）

需要 [Node.js](https://nodejs.org/) 18 以上。

```sh
git clone -b campus-showcase https://github.com/KKKu07/nuist-campus-walk.git nuist-showcase
cd nuist-showcase
npm install
npm run dev
```

浏览器打开终端里显示的地址（默认 http://localhost:5173 ）。首次加载约 40 MB，需要几秒到十几秒。建议用电脑上的 Chrome / Edge，独立显卡更流畅。

打包成静态网页：`npm run build`，把生成的 `dist/` 整个放到任意静态网站（GitHub Pages、学校服务器等）。`dist/index.html` 不能直接双击打开（浏览器不允许本地网页读取数据文件），本机查看用 `npm run preview`；要双击打开就用上面的 `{offline}`（所有模型、贴图、数据都打包在这一个文件里）。

## 操作

| 操作 | 电脑 | 手机 / 平板 |
| --- | --- | --- |
| 平移 | 左键拖动，或 W A S D / 方向键 | 单指拖动 |
| 旋转 | 右键拖动，或 Q / E | 双指旋转 |
| 拉远拉近 | 滚轮，或 R / F | 双指缩放 |
| 回到全景 | H | 底部「全校全景」 |
| 自动环绕 | O | 底部「自动环绕」 |

底部按钮可以直接飞到图书馆、气象楼、钟楼、文德楼、临江楼等地标。按住 Shift 移动更快。

## 数据来源与说明

- 地面影像：校内为航拍拼图；周边为 Esri World Imagery。
- 建筑轮廓、道路、水系：© OpenStreetMap（ODbL）+ 人工补画和逐条核对。
- 楼高：航拍三维重建实测（部分楼按层数估算）。
- 地标和大部分楼宇：Blender 按官网三维地图、航拍和实拍照片建模。
- 贴图和天空：CC0 素材，见 `ASSET-LICENSES.md`。
- 模型还在逐栋核对中，个别楼的高度、外观和位置可能与实际有出入。

## 这个分支怎么来的

由完整项目（含玩法、数据工具和 Blender 工程，另行保存）自动生成：`tools/make_showcase_branch.py`（`{offline}` 由 `tools/offline_html.py` 打包），来源提交 `{source}`，生成日期 {today}。请不要直接在这个分支上改代码；要改场景，在完整项目里改好后重新生成。
"""
OFFLINE = "nuist-campus-3d.html"


def build_offline(out: dict[str, bytes | str]) -> bytes:
    """vite build of the generated tree (using the project's web/node_modules), packed into one double-clickable HTML."""
    sys.path.insert(0, str(ROOT / "tools"))
    from offline_html import inline_dist  # pyright: ignore[reportMissingImports]  (tools/ is put on sys.path above)
    nm = ROOT / "web" / "node_modules"
    if not (nm / "vite" / "bin" / "vite.js").is_file():
        sys.exit("web/node_modules is missing: run npm install in web/ first")
    td = Path(tempfile.mkdtemp(prefix="showcase-build-"))
    link = td / "node_modules"
    try:
        for p, v in out.items():
            if p in ("index.html", "vite.config.js", "package.json") or p.startswith(("src/", "public/")):
                f = td / p
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(v if isinstance(v, bytes) else git("cat-file", "blob", v))
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(nm), str(link))
        else:
            link.symlink_to(nm, target_is_directory=True)
        r = subprocess.run(["node", str(nm / "vite" / "bin" / "vite.js"), "build", "--logLevel", "error"], cwd=td, capture_output=True)
        if r.returncode:
            sys.exit("vite build failed:\n" + r.stderr.decode("utf-8", "replace"))
        return inline_dist(td / "dist")
    finally:
        # drop the link itself first, so the clean-up can never walk into web/node_modules
        if link.is_symlink() or link.exists():
            os.rmdir(link) if os.name == "nt" else link.unlink()
        if not link.exists():
            shutil.rmtree(td, ignore_errors=True)
        else:
            print(f"warning: left {td} (could not remove the node_modules link)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="HEAD", help="commit to build from (default HEAD)")
    ap.add_argument("--worktree", action="store_true", help="read files from disk instead of a commit")
    ap.add_argument("--branch", default="campus-showcase")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-offline", action="store_true", help=f"skip building {OFFLINE} (the double-click version)")
    ap.add_argument("--orphan", action="store_true",
                    help="new root commit with no parent (to replace the published branch, e.g. after removing text; push with --force-with-lease)")
    a = ap.parse_args()
    src = Source(None if a.worktree else a.source)

    out: dict[str, bytes | str] = {}      # repo path -> bytes (new content) or blob sha (copied)
    # code: the showcase entry and everything it imports, nothing from the game
    mods = import_closure(src, "web/src/showcase.js")
    bad = [m for m in mods if GAME_ONLY.search(m)]
    if bad:
        sys.exit(f"showcase imports game-only modules: {bad}")
    for m in mods:
        out[m[len("web/"):]] = src.blob(m)
    out["index.html"] = src.blob("web/showcase.html")
    out["vite.config.js"] = src.blob("web/vite.config.js")

    # data: scene files, textures, and only the GLBs campus.json places
    C = json.loads(src.read("web/public/campus/campus.json").decode("utf-8"))
    for p in src.under("web/public/campus/") + src.under("web/public/tex/"):
        out[p[len("web/"):]] = src.blob(p)
    glbs = sorted({m["file"] for m in C.get("models", [])} | {g["file"] for g in C.get("generic", [])})
    missing = [g for g in glbs if not src.has(f"web/public/{g}")]
    if missing:
        sys.exit(f"campus.json places models that are not in the source: {missing}")
    for g in glbs:
        out[f"public/{g}"] = src.blob(f"web/public/{g}")

    # package files, renamed for the showcase
    pkg = json.loads(src.read("web/package.json"))
    pkg["name"] = "nuist-campus-showcase"
    pkg["description"] = "南京信息工程大学校园三维场景（展示版）"
    out["package.json"] = (json.dumps(pkg, ensure_ascii=False, indent=2) + "\n").encode()
    lock = json.loads(src.read("web/package-lock.json"))
    lock["name"] = pkg["name"]
    if "" in lock.get("packages", {}):
        lock["packages"][""]["name"] = pkg["name"]
    out["package-lock.json"] = (json.dumps(lock, ensure_ascii=False, indent=2) + "\n").encode()

    # one self-contained HTML (all data inside) that opens by double-click, for people without Node.js
    offline_mb = 0.0
    if not a.no_offline and not a.dry_run:
        out[OFFLINE] = build_offline(out)
        offline_mb = len(out[OFFLINE]) / 1048576
        if offline_mb > 95:
            sys.exit(f"{OFFLINE} is {offline_mb:.0f} MB, over GitHub's 100 MB file limit")

    n_buildings = sum(1 for b in C["buildings"] if b.get("kind") != "wall")
    n_generic = sum(len(g.get("ids", [])) for g in C.get("generic", []))
    short = src.commit[:12] if src.commit else git("rev-parse", "--short=12", "HEAD").decode().strip() + "（加未提交改动）"
    out["README.md"] = README.format(buildings=n_buildings, models=len(C.get("models", [])), generic=n_generic,
                                     trees=f"{round(len(C.get('trees', [])), -3):,}", roads=len(C.get("roads", [])),
                                     sports=len(C.get("sports", [])), source=short, today=date.today().isoformat(),
                                     offline=OFFLINE, offline_mb=round(offline_mb)).encode()
    out["ASSET-LICENSES.md"] = src.blob("data/assets/LICENSES.md")
    out[".gitignore"] = b"node_modules/\ndist/\n.DS_Store\nThumbs.db\n"
    out[".gitattributes"] = f"*.glb binary\n*.jpg binary\n*.png binary\n*.hdr binary\n{OFFLINE} binary\n".encode()

    if a.dry_run:
        for p in sorted(out):
            print(p)
        print(f"{len(out)} files; modules: {', '.join(mods)}")
        return

    lines = []
    for p, v in sorted(out.items()):
        sha = git("hash-object", "-w", "--stdin", input=v).decode().strip() if isinstance(v, bytes) else v
        lines.append(f"100644 {sha}\t{p}")
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(td) / "index")}
        git("read-tree", "--empty", env=env)
        git("update-index", "--add", "--index-info", input=("\n".join(lines) + "\n").encode("utf-8"), env=env)
        tree = git("write-tree", env=env).decode().strip()

    ref = f"refs/heads/{a.branch}"

    def resolve(name: str) -> str | None:
        r = subprocess.run(["git", "rev-parse", "--verify", "-q", name], cwd=ROOT, capture_output=True)
        return r.stdout.decode().strip() if r.returncode == 0 else None

    local = resolve(ref)
    parent = None if a.orphan else local or resolve(f"refs/remotes/classmate/{a.branch}")
    if parent and git("rev-parse", f"{parent}^{{tree}}").decode().strip() == tree:
        print(f"{a.branch} unchanged ({parent[:7]}), {len(out)} files")
        return
    msg = (f"校园三维场景展示版：由完整项目 {short} 生成\n\n"
           f"只含场景（{n_buildings} 栋建筑、{len(C.get('models', []))} 个精修地标、{len(glbs)} 个 GLB），不含游戏玩法。\n"
           f"生成脚本：tools/make_showcase_branch.py\n\n"
           f"Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
    commit = git("commit-tree", tree, *(["-p", parent] if parent else []), input=msg.encode("utf-8")).decode().strip()
    git("update-ref", ref, commit, local or "0" * 40)     # fails if the branch moved meanwhile
    print(f"{a.branch} -> {commit[:7]} (parent {parent[:7] if parent else 'none'}), {len(out)} files, tree {tree[:7]}")


if __name__ == "__main__":
    main()
