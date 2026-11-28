# Blender 地标模型

| 文件 | 说明 |
|---|---|
| `models.json` | 游戏摆放表：`name, file, x, z, rotY, replaces[], height, tris` |
| `<key>.blend` | 可编辑工程（每个地标一个集合，`_preview` 集合是渲染用的地面/相机/灯） |
| `previews/<key>.jpg` | 预览渲染 |
| `textures/` | 程序生成的立面/屋顶贴图（`tools/blender_textures.py`） |
| `../../web/public/models/<key>.glb` | 游戏用模型 |

## 坐标

GLB 顶点 = 游戏坐标 (x − X, y, z − Z)，X/Z 取自 `models.json`，`rotY` 恒为 0，节点上没有任何变换。
建模时直接用游戏坐标（x 向东、z 向南、y 向上），写入 Blender 时转成 (x, −z, y)，glTF 导出 +Y up 再转回来。

## 重新生成

```powershell
.venv\Scripts\python.exe tools\blender_textures.py
G:\Blender\blender.exe --background --factory-startup --python-use-system-env --python tools\blender_landmarks.py
```

只做某几个：末尾加 `-- --only qixianglou,yifulou`；不渲染预览：`-- --no-render`。
`--python-use-system-env` 让 Blender 读到 `PYTHONDONTWRITEBYTECODE=1`，不会往 G 盘写 `__pycache__`。

## 连接正在运行的 Blender

用户装的是 Blender Lab 官方 “MCP” 扩展（`%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\mcp`），
它在 `localhost:9876` 收 `{"type":"execute","code":"<python>","strict_json":false}` + `\0`，
代码在主线程执行，`result` 字典原样返回。客户端：

```powershell
.venv\Scripts\python.exe tools\blender_bridge.py info
.venv\Scripts\python.exe tools\blender_bridge.py run tools\blender_show_live.py
```

`blender_show_live.py` 把所有 `.blend` 里的地标追加到打开的 Blender 的新场景「南信大地标」（不动原有场景）。

## 已做的模型（2026-11-27）

| 批次 | key（GLB 文件名） |
|---|---|
| 1 | qixianglou, tushuguan, yifulou, linjianglou, dongyuan_tiyuguan, jianshanyuan, laoxiaomen |
| 2 | wendelou, shangxianlou, xingzhenglou, guojijiaoyu, shengqi_guangchang, oufanglou, binjianglou, dongdamen, leidingxueyuan |
| 3 | shuiyunfang, qixianggu, leidata |
| 4 | mingdelou, huodongzhongxin, dongyuan_shitang, zhongyuan_laoshitang, qiminglou, changwanglou, fengyun_juchang, beichenlou |
| 5 | lanjianglou, yuejianglou, xueke1, xueke2, xueke3, zhongyuan_meishicheng, zhongyuan_xinshitang, nanjie_jiaoshi |
| 6 | kechuang1–4, jijialou, jiaogong_huodong, nanqi_binguan, xiyuan_xinshitang |
| 7 | zhongyuan_zhuxitai（替换 zhongyuan-stand）, xiyuan_wenchuang（替换 xywc-1…5） |
| 宿舍 | dorm_wenyuan_a2/a3/a4/b2/b3（文园 21 栋）、dorm_qinyuan_d4/d5/e4/e5/f3/f4（沁园 21 栋 + tower-3/4）、dorm_dongyuan_g1/h1/h2/i1/i2（东苑 21 栋）、dorm_qinyuan_g3（沁园26）、dorm_e3_no8（第八栋宿舍），按区一个 GLB |
| E3 | e3_old_residential（老居民楼 old-res-1…4 + 平房 old-res-2a + res-p1） |
| 车辆/道具（`vehicles.json`，不进 models.json） | bus, bus_shelter, ebike_7ma |

预览拼图：`previews/_all.jpg`（第 1 批）、`_batch2.jpg`、`_batch3.jpg`（含车辆）、`_batch4.jpg`。

第 4 批外观照官网 zoom1 裁图（`data/official/crops/`），楼体高度都用 campus.json 的 h，没有改层数；只有屋顶附加物高出 h：
大学生活动中心东北侧大厅 17 m（官网图比其余部分高一层），风云剧场四坡屋顶屋脊 17.6 m，明德楼外挂楼梯 26 m，启明楼玻璃楼梯间 21.5 m。各楼哪些地方是推测的，见 `tools/blender_landmarks.py` 里每个 `m_*` 函数的注释。

第 5 批高度（官网 zoom1 裁图数层数复核）：
- 南阶教室：官网图 2 层，用 8.4 m（+0.7 m 女儿墙），不是 campus.json 的 19.2 m。位置就在 OSM 轮廓中心 (537.6, -381.5)（航拍和官网图都在那；DSM 0.5 m 是重建漏洞，东北 15 m 处 6–9 m 的楼块是另一栋）。
- 揽江楼 6 层 22.8 m、阅江楼 5 层 19.2 m（官网内院立面约 5–6 排窗）、中苑美食城 3 层 11.6 m、中苑新食堂 4 层 14.3 m：与 campus.json 一致。
- 学科 1/2/3 号楼（逸夫楼同款蓝色孟莎顶）：檐口 13.7 / 16.0 / 15.5 m，屋顶到 16.6 / 19.8 / 19.3 m（与实测 h 一致），角楼尖顶再高 5.5 m。

第 6 批高度（官网 zoom1 数层数；campus.json 的 19.2 m 是按名称估的）：
- 科创1号楼 2 层：檐口 7.2 m、屋脊 10.5 m（DSM 轮廓内 6–9 m，与之吻合）。
- 科创2号楼 3 层：10.8 / 14.2 m（官网图米黄色 3–4 层，DSM 在此只有 3–9 m，采用官网层数）。
- 科创3号楼 3 层：10.8 / 14.2 m（官网粉色 3 层）。
- 科创4号楼 1 层：4.5 / 7.5 m（官网是两座单层坡顶小楼，这里合成一栋）。
- 南气宾馆 5 层 18.0 m（campus.json 16.5 m；官网 5 层，DSM 轮廓内 p70 约 19.7 m）。
- 西苑新食堂 3 层 11.0 m + 屋面板 0.7 m（campus.json 7.9 m；官网 3 排窗 + 通高柱廊）。
- 基嘉楼：3 层 11 m 主体 + 西北 5 层 18 m 楼块 + 南翼蓝色拱顶（顶 14.2 m）；教工活动中心：檐口 8 m、双坡屋脊 13 m，南侧 4.8 m 白色附楼。
- 轮廓核对：8 栋的 OSM 轮廓与正射图都对得上，不需要改。科创 3/4 号楼 DSM 几乎测不到高度，是因为航拍重建在校园北缘覆盖差，不是轮廓错位。

## 细化（2026-11-27）与普通楼

- **所有贴图都有法线贴图**（`textures/*_n.jpg`，由贴图明暗推算：玻璃凹、窗框和线脚凸），GLB 里是 glTF normalTexture；材质默认单面（doubleSided=false），旗子除外。
- **地标加了几何细节**：楼层挑檐线（每层 0.1 m 外挑的楼板线）、女儿墙压顶，已在第 4–6 批通用函数和文德楼、滨江楼、阅江楼、揽江楼、行政楼、尚贤楼、藕舫楼、气象楼主楼上生效。
- **普通楼（非地标 247 栋，不含围墙）也用 Blender 生成**：`tools/blender_generic_prep.py` 先从 campus.json、`data/official/wall_colors.json` 和官网 zoom3 瓦片（按屋顶高度取样屋面色）生成 `generic_input.json`，再
  `G:\Blender\blender.exe --background --factory-startup --python-use-system-env --python tools\blender_landmarks.py -- --generic`
  按 640 m 网格分 14 块导出 `web/public/models/generic/<块>.glb` 和 `data/blender/generic.json`。
  每栋：按官网墙色着色（顶点色 × 中性贴图，三种立面：宿舍单窗 / 办公双窗 / 大厅）、0.7 m 深色勒脚、每层楼板线、平顶女儿墙 + 楼梯间 + 空调机组，或按 campus.json roof.obb 做四坡顶（屋面色取自官网图）、南向主立面入口雨棚。约 250 三角面/栋，共约 6.1 万面、7 MB。
  官网墙色偏饱和，生成时往浅灰拉了 45%。

第 7 批（v0.5）：
- 中苑主席台（西看台）：轮廓 x -72.5…-56.3、z -57.5…85（143 × 16.2 m）。12 排看台，每排深 1.2 m、高 0.4 m，从跑道边 1.2 m 升到 6.0 m，后墙女儿墙到 7.1 m（照片里约 10–12 排、后墙 6–8 m）。分 3 段，段间（u = ±24 m）是楼梯口，后墙有通道口。正中是 18 m 宽的白色主席台楼：前面 3.6 m 高的贵宾台、二层玻璃带、校徽，挑檐屋面板到 10.1 m（官网 zoom1 和新闻照片里是两层白楼、正面有校徽）。校徽是示意图案，不是真校徽。
- 西苑文创街区：5 栋合成一个 GLB。xywc-1 白墙两层 + 两块蓝色单坡顶 + 蓝玻璃角房（7.6 m），xywc-2 白色平顶房 + 木饰面，xywc-3 玻璃小馆，xywc-4 黄色集装箱商铺 + 红色招牌带，xywc-5 白墙深灰坡顶小房。哪种外观对应哪个 id 是按官网图位置推测的。

宿舍群（v0.5 阶段 B）—— 西苑文园 21 栋（逐栋记录在 `data/dorms/dorms.csv` 的 official_floors / roof_check / facade_check / status 列）：
- 依据：官网 zoom1 裁图（只读本地缓存瓦片，按 align_shift 校正），21 栋全部看过；文园2栋的官网瓦片缺上半部，按同组推定。
- 参数化「文园型」（`tools/blender_landmarks.py` 的 `wenyuan_building`）：最小外接矩形（+u 朝东），6 层浅色板楼（官网墙色）+ 深灰首层 + 楼层线；中段红瓦四坡顶（屋面色取官网，坡度约 0.3×进深；文园20、21 是两段坡顶、中间平顶）；两端楼梯塔比檐口高 3.4 m，凸出两侧 0.6 m，一端红色四坡小帽 + 立柱，另一端平顶 + 栏杆（哪端是红帽逐栋看官网图，见 csv）。
- 檐口高：实测值在 17–22.5 m 之间就用实测（15 栋）；文园10（11.9）、12（14.5）、17（估算 6.0）、20（15.9）、21（14.6）的数值和官网图上与邻楼同为 6 层不符，统一按 6 × 3.1 = 18.6 m。
- 按区出 5 个 GLB，replaces 填该区全部 id；普通楼块 `generic/*.glb` 已重新生成，不再包含这 21 栋（现 226 栋）。

E3 老居民楼（细节纠正会话提供位置，`extra_buildings.json` 的 rect，角度从正东往北转）：
- 4 栋 5 层 × 3 m 砖混楼，墙顶 15 m + 女儿墙到 h（16 / 16.5 m）；灰色脏旧外墙贴图（水渍、铝窗、防盗栏，`old_res.jpg` + 法线贴图），楼层线，外凸楼梯间（每 15 m 一个单元，深色门洞 + 每层小窗；old-res-1 朝南面正气路，其余朝北），两侧随机空调外机。没有门厅雨棚和名牌。
- 屋顶：old-res-2 北沿一排楼梯间小凸起 + 几块深色补丁（旧屋面），old-res-3/4 北沿一排朝南倾斜的太阳能热水器（集热板 + 水箱）。北侧那栋按 2024-12 照片做平顶（官网图画成坡顶）。
- old-res-2a：一层平房 3.2 m，深灰屋面，南面一排卷帘门洞。
- res-p1（old-res-1 北边围墙院里，较新、非废弃）：5 层灰墙，檐口 15.5 m + 白色檐口线，红褐瓦四坡顶（"平改坡"）屋脊 20 m，北坡 6 个老虎窗，南面 3 个楼梯口。
- 一个 GLB，每栋一个节点（按 id 命名），约 2.6k 三角面。generic.json 已重新生成，去掉作废的 manual-17…20。

中苑沁园 21 栋（D4/D5/E4/E5/F3/F4，逐栋记录在 dorms.csv；`qinyuan_building`）：
- 官网 zoom1 看出 6 种楼型：A 灰玫红瓦四坡顶 + 浅绿白墙 + 两端叠层阳台（**屋面偏粉是官网原色，不是取样错误**，只是比 zoom3 取样略深）；B 鲜红瓦 + 橙色檐口带 + 浅蓝灰墙（27/28/40）；C 米黄墙 + 红瓦（29、青教公寓 6 幢、30 两段坡顶）；D 褐灰瓦 + 成排阳台（38/39/25）；E 沁园41 红砖 + 蓝玻璃 + 玻璃中庭；F 外廊式白墙 + 红砖立柱 + 浅蓝平屋面（F3 三栋）。36/37/39 东端加圆形塔。
- 檐口：实测值（15–22 m）直接用作檐口，层数 = 檐口/3.25；沁园42（manual-33，估算）按 6×3.1 m，官网裁图对不准，低把握；沁园22 官网瓦片缺，按同组推定。
- E4、F4 的 GLB 同时替换 tower-3、tower-4（沁园40/30 的实测高起部分）。generic 已重新生成。

东苑硕园/晖园 21 栋（G1/H1/H2/I1/I2；`dongyuan_building`）：
- H 型（晖园 11–14、硕园 1/2/3/6）：白墙，南立面每 7.5 m 一列竖向弧形飘窗（半圆柱），两端叠层阳台，暗紫红瓦四坡顶（硕园1 为灰褐瓦）。
- S 型（硕园4、硕园5-云中信大）：米黄墙、灰褐瓦四坡顶；硕园5 首层玻璃商铺。
- O 型（G1/H1/I1 里 11 栋无名楼，id 1425305xxx/1425504xxx）：官网插画图没画（那里是普通街道地图，标“15幢/16幢”，校外住宅小区），按正射图做 6 层 18 m 平顶板楼 + 北沿一排太阳能热水器，轮廓照原样（含凸凹）。
- 檐口：实测 15–23 m 的直接用；晖园11（10.3）、晖园13（10.8）、硕园6（10.4）与官网同排 6 层不符，按 18.6 m。晖园11–13 官网瓦片大半缺失，按同组推定。

最后 2 栋：
- 沁园26栋（G3）：官网 5 层白墙蓝窗带、褐灰瓦坡顶（U 形，东翼山花），正射图轮廓吻合；檐口用实测 18.1 m，坡顶用沿轮廓内缩的四坡（`hip_on_outline`）到 22.6 m。
- 第八栋宿舍（manual-21，E3）：官网画成 4 层灰墙平顶、南面一列列蓝色封闭阳台、自带围墙院，和 old-res（官网标第十一~十三栋宿舍）是同一系列的老式教工宿舍/居民楼，不是学生宿舍；实测 11.5 m（4 层 × 2.7 m + 女儿墙）。单独一个 GLB，没并进 e3_old_residential。

文园17栋（862959378）轮廓修正：细节纠正会话用 2024-12 的 480 m 无人机正射照片（17 个同名点配准，误差 0.6 m）量出北墙在 z≈-530，原 OSM 轮廓向北多出约 7 m（那是长望西街商铺南侧的人行带）。`WENYUAN_NORTH_Z` 把模型北墙（含两端楼梯塔）收到 z -530，南墙不动，进深 20.9 → 14.3 m。campus.json 的轮廓（碰撞）由游戏会话改。

东大门重做（细节纠正会话按实测位置，用户全景照片 + `data/zones/fix_dongdamen/` 航拍/官网 4 px/m）：原点 = 门前圆形广场中心 (1405.0, -520.75)，部件各按实测坐标摆放：
- 广场：半径 11 m 灰砖环 + 白色卵石面 + 14 折木条（7 个外角各一块大石头）。
- 中央岛：5 根雕花石柱一行，南端 (1381,-512) → 北端 (1387,-530)（北端偏东约 18°），柱高 15.8 m（中间 3 根铜球、两端石狮简化），东侧（朝广场）14 m 长、约 3.3 m 高刻字景石 + 矮花坛，下面绿化台。
- 门卫室：北 (1387.5,-553)、南 (1374.4,-500.6)，中心距 54 m；12×7×6 m 米黄石材两层，屋檐线脚，两侧各一根 8.5 m 素石柱，路侧柱旁一根红白升降杆（6 m），东侧一排蓝黄防撞柱横过车道。
- 注意：campus.json 里两条门路（590302085 / 404874362）的中线比航拍更靠近中央岛，按数据宽度加人行道算，岛在石柱处只剩约 8 m；模型按实测位置做，门路几何请细节会话按航拍调。

东苑集装箱美食街（信藕空间·文创街区，`dongyuan_jzx`，replaces jzx-w / g1…g6 / u1…u6 / jzx-e 共 14 块；细节纠正会话量的位置）：
- 一层 6 块商铺进深 6 m、高 3.6 m，集装箱波纹板（`container.jpg`，按 extra_buildings 的店色顶点着色），中间黑框玻璃门面，上方彩色店招（`jzx_signs.jpg`：便利超市/特色小吃/奶茶果饮/咖啡简餐/麻辣烫/炸鸡汉堡/文创小店/鲜果水吧——通用店名）。
- 楼板 3.85 m，前面 3 m 是二层平台走廊，沿边黑框玻璃栏杆；二层 6 个集装箱商铺只占靠北（围墙）3 m，顶到 7.2–7.4 m。
- 两端橙色端头（西 8 m、东 8.6 m，上层退进），西端头挂“信藕空间·文创街区”牌；两端各一部钢楼梯从步行街上到平台。门面朝南（硕园5栋一侧的步行街）。
- 按用户实拍 `data/zones/fix_dongyuan_jzx/user_photo.jpg`（西端高处往东看）对过：一层从西往东“芒可24h 鲜饮市集”（黄色大遮阳篷）、“购好超市”（深灰店招在平台下）、绿色小亭“沪溪河桃酥”（凸出到街上、绿遮阳篷）；二层整宽店招“不如麻辣烫”“李堡长”“禾香楼”；平台地面棕红砖；西端头南、西两面橙色“信藕空间 文创街区”招牌，西墙大海报 + 下部木条，上层黄遮阳篷。其余几家店名照片看不清，用通用名（鲜果水吧/特色小吃/便利店/奶茶咖啡/文创小店/简餐）。预览图按照片视角（西端高处朝东）渲染。二次核对：西楼梯改到西端头南侧 1.6 m 的开敞楼梯带里（照片里在黄遮阳篷下、从街面向东上平台），不再挡在芒可门前；东端楼梯仍在最后一家店前的街上；芒可店招改成浅蓝底深蓝字。generic 已重生成（去掉旧 1316175152）。

东大门第二版（`data/zones/fix_dongdamen/spec_v2.md`，细节纠正会话按 480 m 正射配准，rms 0.7 m）：原点 = 广场中心 (1405.5, -520.8)。
- 梭形绿岛（spec 轮廓，0.2 m 路缘 + 草坪，西半部 r 5 m 环形小路，东边弧形 1.5 m 黄红花带）。
- 5 根九龙柱按 spec 柱基排成向西凹的缓弧，浮雕柱身（`relief_column.jpg` + 法线贴图），顶高约 14 m，C2–C4 铜球、C1/C5 石狮简化。方座 1.6 m（C5 1.5 m），C5 比 spec 北移 0.4 m（在配准误差内），否则柱身会伸进南车道 0.15 m。
- 大石刻：(1388.0,-530.5)–(1385.6,-519.0)，约 11.7 m 长、顶高 3.25 m，刻字面朝东南东（广场），下面一圈矮花坛。
- 门卫室位置不变，两端各一根浮雕柱（约 10 m，鼓形柱帽）；道闸做成抬起状态（约 83°），底座在车道外。
- 广场：外圈浅棕砖 + 24 个小石墩，内圈灰蓝方砖，偏南的椭圆卵石地；北斗七星 7 块砂岩景石用锈红条连成，斗口朝北、斗柄朝南，约 12 m；r 2 m 铜盘在 (1401.4,-521.4)。隔离桩只沿广场西侧弧线摆。
- 车道核对：北车道（中线 ± 4.25 m）和南车道（± 3.5 m）范围内，0.4–2.2 m 高度没有任何实体，最小净距 0.11 m。只有 spec 岛轮廓自己的路缘（≤ 0.2 m）在西尖处和车道相接。

东大门第三版起归细节纠正会话：`tools/blender_dongdamen.py`（贴图 `tools/ddm_textures.py`），用它自己的 main() 重建。`blender_landmarks.py` 里 `FROZEN = {"dongdamen"}`，整体重建会跳过；注册表里的 m_dongdamen 只是转调它（把本模块注册成 `blender_landmarks`，共用材质缓存），只有显式 `--only dongdamen` 才会走到。第二版的代码已删，relief_column 等材质留着没影响。

东苑美食街街面（`jzx_street`，细节纠正会话 `tools/blender_jzx_street.py`）同东大门：在 FROZEN 里，整体重建跳过；注册表里用 `_delegate` 转调它的 m_street。另外 `blender_landmarks.py` 的 main() 现在会保留 models.json 里不在 MODELS_DEF 中的条目（别的会话脚本写的），整体重建不会再删掉它们。
