"""Designed campus planting and shoreline paths, clipped to surveyed footprints."""
import math,json,random
from pathlib import Path
from shapely.geometry import Point,LineString,Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
rng=random.Random(813)
data=json.loads(Path('osm-data.js').read_text().split('=',1)[1].strip().rstrip(';'))
def polygons(features):return unary_union([Polygon(f['points'],f.get('holes',[])).buffer(0) for f in features])
campus=polygons(data['campus']); buildings=polygons(data['buildings']);water=polygons(data['water']);sports=polygons(data['sports'])
streets=unary_union([LineString(r['points']).buffer(r['width']/2+.72) for r in data['roads']])
beds=[];trees=[];shore=[]
path=water.buffer(.86).difference(water.buffer(.42)).intersection(campus).difference(unary_union([streets,buildings,sports]))
existing=[(x,z) for x,z,_ in data['trees']]
free=prep(campus.difference(unary_union([buildings.buffer(.85),sports.buffer(.5),water.buffer(1.0),streets,path])))
for r in sorted(data['roads'],key=lambda r:-r['width']):
 if r['width']<1.4:continue
 line=LineString(r['points'])
 for side in [-1,1]:
  t=2.5+rng.random()*3
  while t<line.length-1:
   a=line.interpolate(t);b=line.interpolate(t+.2);angle=math.atan2(b.x-a.x,b.y-a.y)
   off=side*(r['width']/2+1.55);x=a.x+math.cos(angle)*off;z=a.y-math.sin(angle)*off
   if free.contains(Point(x,z).buffer(.65)) and all(math.hypot(x-i,z-j)>2.9 for i,j,*_ in beds):
    beds.append([x,z,angle,rng.randrange(4)])
    if len(trees)<320 and all(math.hypot(x-i,z-j)>2.6 for i,j in existing):
     trees.append([x,z,rng.uniform(.84,1.22)]);existing.append((x,z))
   t+=rng.uniform(4.5,7.5)
for f in data['water']:
 line=LineString(f['points'])
 for t in range(0,int(line.length),2):
  pt=line.interpolate(t);shore.append([pt.x,pt.y])
def rings(poly):return dict(points=list(poly.exterior.coords),holes=[list(h.coords) for h in poly.interiors])
paths=[rings(p) for p in getattr(path,'geoms',[path]) if p.geom_type=='Polygon' and p.area>.02]
def rounded(obj):
 if isinstance(obj,(list,tuple)):return [rounded(x) for x in obj]
 if isinstance(obj,dict):return {k:rounded(v) for k,v in obj.items()}
 return round(obj,4) if isinstance(obj,float) else obj
Path('landscape-data.js').write_text('export const landscape='+json.dumps(rounded(dict(beds=beds,trees=trees,shore=shore,paths=paths)),separators=(',',':'))+';')
print(len(beds),len(trees),len(shore),len(paths))
