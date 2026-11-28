# 宿舍群逐栋核对（v0.5 阶段 B）

`dorms.csv`：校内 67 栋宿舍（不含人才公寓（校外）和第十一~十三栋老居民楼（细节会话在改））。
列：id、名字、所在区、中心、最小外接矩形长宽、现在的高度/层数、坡屋顶、屋顶色（官网）、外墙色、是否已有精修模型、高度来源（measured=航拍三维重建实测 / fixed=人工 / est=估算），
以及待填：official_floors（官网 zoom1 图数层数）、roof_check（屋顶形式：红瓦坡顶/端部楼梯塔/平顶…）、facade_check（立面颜色、窗带、阳台、空调）、photo（网上照片链接）、status（核对结论）。

核对依据：
- 官网 zoom1 图：`.venv\Scripts\python.exe tools\official_crop.py <楼id或楼名>`（已按 `data/official/align_shift.json` 校正偏移，裁图框住整栋楼）。
- 航拍：`web/public/campus/ortho.jpg`；带 5 m 刻度放大图 `data/raw/wp2/ruler.py <名> x0 z0 x1 z1 [px/m]`。
- 区核对图：`tools/zone_ref.py <区> x0 z0 x1 z1`（B2、B3、E4、H1 已生成在 `data/zones/`）。
- 楼高：hsrc=measured 的以实测为准（檐口）；est 的按官网层数 × 约 3.0–3.3 m（宿舍层高）。

已知楼型（官网图）：
- 西苑文园：白色长条板楼约 6–7 层，中段红瓦坡屋顶，两端楼梯间塔楼高出一截（一端塔顶红色四坡小帽 + 栏杆，另一端平顶）。
