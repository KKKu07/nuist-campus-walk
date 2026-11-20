"""Bake ribbons, joined junctions and accessible bridge decks from revised geometry."""
from pathlib import Path
import json, math
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union

project=Path(__file__).resolve().parent.parent
data=json.loads((project/'osm-data.js').read_text().split('=',1)[1].strip(' ;\n'))
def area(items):
    return unary_union([Polygon(q['points'],q.get('holes',[])).buffer(0) for q in items])
decks=area(data['bridges'])
water=area(data['water']).difference(decks)
buildings=area([q for q in data['buildings'] if q['id']!='1114843846'])
def polys(q):
    if q.is_empty:return []
    if q.geom_type=='Polygon':return [q]
    return [p for sub in getattr(q,'geoms',[]) for p in polys(sub)]
def tiles(q):
    data=[];a,b,c,d=q.bounds
    for x in range(math.floor(a/24)*24,math.ceil(c/24)*24,24):
        for z in range(math.floor(b/24)*24,math.ceil(d/24)*24,24):
            for p in polys(q.intersection(box(x,z,x+24,z+24))):
                if p.area<.0005:continue
                def ring(c):return [[round(x,4),round(y,4)] for x,y in c.coords]
                data.append(dict(points=ring(p.exterior),holes=[ring(h) for h in p.interiors]))
    return data
layers={'paving':[],'road':[],'asphalt':[]}
for r in data['roads']:
    path=LineString(r['points']);w=r['width'];side=.36 if w>=1.4 else .12
    cap='flat' if r['id'].startswith('boundary-') and w>4.5 else 'round'
    layers['paving'].append(path.buffer(w/2+side,quad_segs=4,cap_style=cap))
    layers['road'].append(path.buffer(w/2,quad_segs=4,cap_style=cap))
    if w>=1.05:layers['asphalt'].append(path.buffer(w/2-.035,quad_segs=4,cap_style=cap))
layers['paving'].append(decks)
blocked=water.union(buildings)
for k,parts in layers.items():
    layers[k]=unary_union(parts).buffer(.09,quad_segs=3).buffer(-.09,quad_segs=3).difference(blocked).simplify(.018)
layers['curb']=layers['asphalt'].buffer(.04,quad_segs=3).difference(layers['asphalt']).difference(blocked).simplify(.012)
out={key:tiles(q) for key,q in layers.items()}
(project/'road-surfaces.js').write_text('export const surfaces='+json.dumps(out,separators=(',',':'))+';\n')
