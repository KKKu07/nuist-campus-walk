# 数据和建模流程

每一步：用什么数据 → 跑哪个脚本 → 产出什么。所有脚本在 `tools/`，Python 环境是项目里的 `.venv`（`uv` 建，Python 3.12）。

## 1. 底图

| 步骤 | 输入 | 脚本 | 产出 |
| --- | --- | --- | --- |
| OSM 数据 | Overpass API（南信大关系 13070911 周边） | 手动下载 | `data/raw/osm.json` |
| 卫星底图（备用） | Esri World Imagery z18 | `fetch_ortho.py` | `web/public/campus/ortho*.jpg`，原图备份 `data/raw/ortho_esri*.jpg` |
| 自己的航拍底图 | `data/source/航拍/全景航拍.jpg` | `align_pano.py` | SIFT 特征匹配 + 单应变换对齐到地图坐标，校园部分替换 Esri |
| 地形 | Terrarium / SRTM 高程瓦片 | `fetch_terrain.py` | `web/public/campus/terrain.json`（10 m 网格） |

## 2. 建筑

| 步骤 | 输入 | 脚本 / 文件 | 说明 |
| --- | --- | --- | --- |
| 补画缺失的楼 | 航拍底图 | `trace_aid.py` 出带网格的局部图，人工描 → `data/manual/extra_buildings.json` | 人才公寓、新楼、气象楼主楼 |
| 按楼名修正 | 实拍照片 | `data/manual/building_overrides.json` | 层数、外墙色、立面风格、显示名、照片 |
| 地标 | 你的说明 + 卫星图 | `data/manual/pois.json` | 老校门、东大门、升旗广场、雷达塔 |
| 照片 | `data/source/航拍` | `prepare_photos.py` | `web/public/photos/*.jpg` + `data/manual/photo_index.json` |
| 实测楼高 | `data/source/航拍/全校航拍拼图原图`（132 张，2024-12） | COLMAP + `recon_heights.py` | `data/manual/measured_heights.json`（每栋楼高度 + 自动找出的高塔） |
| 合成游戏数据 | 以上全部 | `build_campus.py` | `web/public/campus/campus.json`：楼、路、水、树、坡屋顶、围墙、公交线路、7ma 停放点 |

优先级：`building_overrides.json` 里写了层数的楼以它为准 > 实测楼高 > OSM 标注 > 按名称估算。

### 重新测楼高

COLMAP 不支持中文路径，所以先把重建目录映射成 X: 盘：

```powershell
subst X: "E:\Claude\三维南信大\data\recon"
& "E:\Claude\三维南信大\tools\colmap\bin\colmap.exe" automatic_reconstructor --workspace_path X:\ws --image_path X:\images --data_type individual --quality medium --dense 1 --use_gpu 1
E:\Claude\三维南信大\.venv\Scripts\python.exe E:\Claude\三维南信大\tools\recon_heights.py
subst X: /d
```

在 RTX 5090 上稀疏 + 稠密重建约 15 分钟。`data/raw/ndsm_preview.jpg` 是地物高度的伪彩色检查图。

### v0.4 数据重建顺序（改了任何人工数据后照这个顺序重跑）

```powershell
cd E:\Claude\三维南信大
.venv\Scripts\python.exe tools\official_mosaic.py        # 官网图贴到地面 → data/official/official_local.jpg（只需一次）
.venv\Scripts\python.exe tools\landcover.py              # 地表分类、路宽实测、单株树 → landcover.png, road_widths.json, trees_v2.json
.venv\Scripts\python.exe tools\landcover_fix.py          # 按官网图把冬季误判的裸土改回草地（landcover.py 之后必须跑）
.venv\Scripts\python.exe toolsuild_campus.py           # 合成 campus.json（读 road_audit.json、models.json 等）
```

- `data/manual/road_audit.json`：逐条核对过的路宽 / 人行道宽 / 中心线平移 / 官网路名位置，优先级高于 `road_widths.json`。
- `build_campus.py` 里：`apply_road_audit`（路宽、路名）、`snap_bus`（公交线吸附到车道）、`street_trees`（树移出路面、行道树、树冠补种）。
- 核对用的图都在 `data/raw/wp2/`：`sheet_*.jpg`（每格 70 m 航拍 + 模型路边线）、`ruler_*.jpg`（5 m 刻度）、`cmp_*.jpg`（上航拍、下官网）、`trees_avenue2.jpg`（行道树）、`bus_snap.jpg`（公交线）。

## 3. 游戏（`web/src/`）

- `textures.js`：用 Canvas 程序生成 7 种立面、路面、铺装、草地细节、水面法线、小公交车身贴图。
- `tour.js`：云游导览（Y 键，自动飞览打卡地标）。`quest.js`：云游打卡。`sports.js`：运动场。`life.js`：围栏、车辆、行人、草丛、绿篱。
- `world.js`：地面（航拍 + 地表分类材质）、道路（按车道数生成标线几何、路缘石、人行道、路口、路名牌）、水面、建筑（分风格立面、坡屋顶、女儿墙、屋顶设备、入口）、地标、树（团块 + 叶片卡）、路灯和庭院灯。
- `vehicles.js`：校园小公交（环线、靠站、可乘坐）和 7ma 共享电动车（可骑、可还）。
- `main.js`：角色、碰撞、视角、小地图、大地图传送、照片卡片、手机摇杆。

## 4. 下一步可以接的

- `data/recon/ws/dense/0/` 里的点云和网格可以导入 Blender，当作精修楼体的参照。
- 地标楼（气象楼、图书馆、逸夫楼）可以在 Blender 里精修成 GLB，替换程序生成的方盒子。
- 公交站点、7ma 停放点按实际位置修正 `build_campus.py` 里的站点列表。
