# 协作说明 · 云游南信大

浏览器里 1:1 复原南京信息工程大学全校的 3D 网页游戏（Three.js + Vite）。这份说明给一起开发的同学：怎么跑起来、文件在哪、哪些是手改的、哪些是脚本生成的、分支怎么用。

## 1. 先跑起来（只看游戏，5 分钟）

只需要 Node.js 18 以上（作者用 24）。Python、Blender 都不用装。

```powershell
git clone <仓库地址>
cd <仓库目录>\web
npm install
npm run dev
```

打开 http://localhost:5173 。键位见 `README.md`。打包：`npm run build`，产物在 `web/dist/`（不进仓库），整个文件夹放到任意静态网站即可（`vite.config.js` 里 `base: './'`）。

游戏要用的数据和素材都在 `web/public/` 里，已经提交，拉下来就能跑：

| 路径 | 内容 | 由谁生成 |
| --- | --- | --- |
| `web/public/campus/campus.json` | 楼、路、水、树、公交线路、7ma 停放点 | `tools/build_campus.py` |
| `web/public/campus/ortho*.jpg` | 地面航拍底图（校园部分是项目航拍，周边是 Esri 卫星图） | `tools/fetch_ortho.py` + `tools/align_pano.py` |
| `web/public/campus/landcover.png`、`ground.png`、`paving.json`、`terrain.json` | 地表分类、地面图、铺装、地形 | `landcover.py` / `landcover_fix.py`、`ground_map.py`、`paving.py`、`fetch_terrain.py` |
| `web/public/models/*.glb`、`models/generic/*.glb` | Blender 精修地标、宿舍、普通楼、小公交、7ma | `tools/blender_landmarks.py`（在 Blender 里跑） |
| `web/public/tex/` | CC0 贴图和 HDR 天空 | `tools/fetch_assets.py` |
| `web/public/photos/` | 实拍照片（已缩到 1280 px，无 GPS 信息） | `tools/prepare_photos.py` |
| `web/public/data/*.json` | 手机玩法的菜单、任务、路线 | 手写 |

### 展示版（只有场景、没有玩法）

`web/showcase.html` + `web/src/showcase.js`：同一套场景（复用 `world.js`、`sports.js`、`life.js`、`textures.js`、`bounds.js`），打开就是高空 45° 俯瞰，只能平移 / 旋转 / 缩放和切预设视角，没有角色、手机、打卡、公交乘坐。开发时访问 http://localhost:5173/showcase.html 。

给老师看的 `campus-showcase` 分支由脚本从完整项目生成（入口改名为 `index.html`，只带场景代码和 `campus.json` 用到的模型），不要手改：

```powershell
.venv\Scripts\python.exe tools\make_showcase_branch.py    # 从当前提交生成本地 campus-showcase 分支（--dry-run 只列文件）
```

## 2. 目录

| 路径 | 内容 |
| --- | --- |
| `web/src/` | 游戏代码：`main.js`（角色、视角、界面、交互入口）、`world.js`（地面、道路、建筑、树、地标）、`vehicles.js`（小公交、7ma）、`textures.js`（程序贴图）、`sports.js`、`life.js`、`tour.js`（云游导览）、`quest.js`（打卡）、`phone/`（手机玩法）、`avatar.js`、`start.js`、`route.js`、`stunt.js` |
| `tools/` | Python 数据脚本（每个文件开头的注释写了用法、输入、输出） |
| `data/manual/` | **人工核对数据**，大部分是手改的（见第 4 节） |
| `data/official/` | 学校官网三维地图（map.nuist.edu.cn）的点位、坐标换算、对齐结果 |
| `data/blender/` | Blender 工程 `*.blend`、摆放表 `models.json` / `generic.json` / `vehicles.json`、预览图，说明见 `data/blender/README.md` |
| `data/dorms/` | 宿舍逐栋核对表 |
| `data/zones/` | 逐区精修的参考图（航拍、斜视、官网），进度见 `docs/zones.md` |
| `data/raw/` | 下载的原始数据（`osm.json`、`dsm.npy` 等）和各种检查图 |
| `data/review/` | 核对用的拼图 |
| `docs/` | 流程 `pipeline.md`、计划和进度 `plan-*.md` / `progress-*.md`、手机玩法 `gameplay-phone.md`、逐栋核对表 `building-audit.csv`、截图 `screens/` |

坐标：单位米，x 向东、z 向南、y 向上，原点是校园外包框中心。

## 3. 改数据（需要 Python）

Python 一律用 [uv](https://docs.astral.sh/uv/) 在项目里建 `.venv`，不要装到全局：

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r tools\requirements.txt
```

完整流程和每一步的输入输出见 **`docs/pipeline.md`**。最常用的：只改了 `data/manual/` 里的文件，重新合成游戏数据：

```powershell
.venv\Scripts\python.exe tools\build_campus.py
```

改地表 / 路宽 / 树时按顺序跑：`landcover.py` → `landcover_fix.py` → `build_campus.py`。

Blender 模型（Blender 5.1）：

```powershell
.venv\Scripts\python.exe tools\blender_textures.py
<Blender 路径>\blender.exe --background --factory-startup --python tools\blender_landmarks.py -- --only qixianglou
```

## 4. 哪些手改、哪些生成

- **手改（以它为准，改完提交）**：`data/manual/building_overrides.json`、`extra_buildings.json`、`model_overrides.json`、`pois.json`、`road_audit.json`、`sports_manual.json`；`data/dorms/dorms.csv`；`web/public/data/*.json`；`web/src/`；`tools/`；`docs/`。
- **脚本生成（不要手改，改了会被下次生成覆盖）**：`web/public/campus/*`、`web/public/models/*.glb`、`data/blender/models.json` / `vehicles.json` / `generic*.json`、`data/manual/road_widths.json`、`data/manual/trees_v2.json`、`data/official/local.json`、`wall_colors.json`、`official_*.jpg`、`docs/building-audit.csv`。
- **生成但当成固定输入（需要仓库外的原始素材才能重新生成）**：`data/manual/measured_heights.json` 和 `data/raw/dsm.npy`（来自航拍三维重建）、`data/manual/photo_index.json` 和 `web/public/photos/`（来自原始照片）、`data/raw/ortho_esri*.jpg`（对齐前的卫星图备份，`landcover.py` 要读）。

生成的文件也提交，这样不跑脚本也能玩。提交前跑一遍生成脚本，确认产物和代码对得上。

## 5. 不在仓库里的东西

`.gitignore` 里排除了这些，需要时这样拿：

| 内容 | 体积 | 怎么拿 |
| --- | --- | --- |
| `web/node_modules/` | 54 MB | `npm install` |
| `web/dist/` | 43 MB | `npm run build` |
| `.venv/` | 186 MB | 见第 3 节 |
| `data/official/tiles/` | 101 MB | 官网地图瓦片缓存，`official_mosaic.py` / `official_colors.py` / `official_crop.py` 会自动下载；`blender_generic_prep.py` 要先有 zoom3 缓存 |
| `data/raw/tiles/`、`data/raw/terrain/` | 7 MB | `fetch_ortho.py`、`fetch_terrain.py` 的下载缓存（注意 `fetch_ortho.py` 会用纯卫星图覆盖 `ortho.jpg`，之后要再跑 `align_pano.py`） |
| `data/assets/ambientcg/`、`polyhaven/` | 51 MB | `fetch_assets.py`（CC0，来源见 `data/assets/LICENSES.md`） |
| `tools/colmap/` | 765 MB | COLMAP 4.2.1 CUDA 版，只有重测楼高才需要，从 COLMAP 官方 GitHub Releases 下载解压到这里 |
| `data/source/航拍/` | 2.7 GB | 航拍原片和照片（本机素材），**不公开**，需要时找项目负责人要 |
| `data/recon/` | 4.7 GB | 三维重建工作区（COLMAP 工程、点云），由原始航拍重建，步骤见 `docs/pipeline.md`「重新测楼高」 |
| `*.blend1` | — | Blender 自动备份 |
| `.claude/` | — | 本机 Claude Code 配置 |

## 6. 分支和提交

- `main`（在同学的仓库里是 `yunyou-nuist` 分支）：能跑的稳定版本。不要往上强推（`--force`）。
- 新功能、新模型各开一个分支：`<名字>/<内容>`，例如 `kkku/library-interior`、`du/dorm-roofs`。做完开 Pull Request，别人看过再合。
- 一个人负责一组文件，避免两个人同时改同一个大文件（尤其 `web/src/main.js`、`world.js`、`tools/build_campus.py`、`data/manual/*.json`）。要改别人负责的文件，先说一声，只加小钩子。
- 提交前：`npm run build` 能通过；游戏里看一眼改动的地方；生成的文件和脚本一起提交。
- 提交信息写清楚改了什么、依据是什么（照片、官网图、实测），例如「藕舫楼：按官网 zoom1 图把南翼改成 4 级退台」。

## 7. 大文件和隐私

- GitHub 单文件上限 100 MB，超过 50 MB 会警告。GLB 尽量控制在几 MB 以内，贴图 ≤ 2048 px。
- 原始航拍、带 GPS 的照片、宿舍内部照片不要提交。往 `web/public/photos/` 放照片前用 `tools/prepare_photos.py` 缩图（会去掉 EXIF）。
- 不提交密钥、令牌、个人邮箱、手机号。
- 数据来源：建筑轮廓和道路来自 OpenStreetMap（ODbL，需署名）；周边卫星图是 Esri World Imagery（公开发布前建议换成项目航拍）；官网地图只作核对参考。
