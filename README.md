# 南京信息工程大学 · 校园三维场景（展示版）

浏览器里的南京信息工程大学全校三维场景：建筑、道路、水系、运动场、绿化和地形的整体模型，打开就是高空俯瞰，可以自由平移、旋转、拉远拉近。这个分支**只有场景**，不含游戏玩法。

现有内容：338 栋建筑，其中 70 个 Blender 精修地标、193 栋 Blender 普通楼模型；约 33,000 棵树；305 条道路；29 处运动场。

## 最简单：下载一个文件，双击打开（给老师演示用这个）

1. 在本分支的文件列表里点 **`nuist-campus-3d.html`**，再点右上角的 **下载按钮**（Download raw file，向下箭头图标）。文件约 49 MB。
   也可以点绿色的 **Code → Download ZIP**，解压后找到 `nuist-campus-3d.html`。
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

打包成静态网页：`npm run build`，把生成的 `dist/` 整个放到任意静态网站（GitHub Pages、学校服务器等）。`dist/index.html` 不能直接双击打开（浏览器不允许本地网页读取数据文件），本机查看用 `npm run preview`；要双击打开就用上面的 `nuist-campus-3d.html`（所有模型、贴图、数据都打包在这一个文件里）。

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

由完整项目（含玩法、数据工具和 Blender 工程，另行保存）自动生成：`tools/make_showcase_branch.py`（`nuist-campus-3d.html` 由 `tools/offline_html.py` 打包），来源提交 `d95cdf37d5a3`，生成日期 2026-11-28。请不要直接在这个分支上改代码；要改场景，在完整项目里改好后重新生成。
