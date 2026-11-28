"""Run INSIDE the user's open Blender through the MCP bridge:

    .venv\\Scripts\\python.exe tools\\blender_bridge.py run tools\\blender_show_live.py

Appends every data/blender/<key>.blend landmark collection into a scene called "南信大地标"
(existing scenes are left alone), lays them out in a row and switches the window to that scene.
Re-running replaces the scene.
"""
import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
BL = ROOT / "data" / "blender"
SCENE = "南信大地标"

old = bpy.data.scenes.get(SCENE)
if old is not None:
    for coll in list(old.collection.children):
        for o in list(coll.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(coll)
    bpy.data.scenes.remove(old)
sc = bpy.data.scenes.new(SCENE)
sc.unit_settings.system = "METRIC"

entries = json.loads((BL / "models.json").read_text(encoding="utf-8"))
if (BL / "vehicles.json").exists():
    entries += json.loads((BL / "vehicles.json").read_text(encoding="utf-8"))
loaded, x = [], 0.0
for e in entries:
    key = Path(e["file"]).stem
    path = BL / f"{key}.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if not c.startswith("_")]
    for coll in dst.collections:
        sc.collection.children.link(coll)
        xs = [(o.matrix_world @ v.co).x for o in coll.all_objects if o.type == "MESH" for v in o.data.vertices]
        w = max(xs) - min(xs)
        for o in coll.all_objects:
            o.location.x += x - min(xs)
        loaded.append(dict(name=coll.name, objects=len(coll.all_objects), x=round(x, 1)))
        x += w + 25.0

TEX = BL / "textures"
for img in bpy.data.images:  # appended into an unsaved file: point textures at data/blender/textures
    if img.source == "FILE" and img.filepath:
        cand = TEX / img.filepath.replace("\\", "/").split("/")[-1]
        if cand.exists():
            img.filepath = str(cand)

wm = bpy.context.window_manager
win = wm.windows[0]
win.scene = sc
for area in win.screen.areas:
    if area.type == "VIEW_3D":
        sp = area.spaces.active
        sp.shading.type = "MATERIAL"
        sp.clip_end = 5000
        r3 = sp.region_3d
        r3.view_location = (x / 2, 0, 20)
        r3.view_distance = x * 0.75
        r3.view_perspective = "PERSP"
for i in bpy.data.images:
    if i.source == "FILE":
        i.reload()
missing = [i.name for i in bpy.data.images if i.source == "FILE" and i.size[0] == 0]
result["scene"] = SCENE
result["collections"] = loaded
result["missing_images"] = missing
