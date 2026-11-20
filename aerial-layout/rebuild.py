"""Bake the user-supplied aerial plan into the game's existing metre-based frame."""
import argparse, json, math, subprocess, sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import minimize
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union, nearest_points
from shapely.strtree import STRtree
from traces import blocks, bridges, fits, names, roads

project = Path(__file__).resolve().parent.parent
default_base = Path(__file__).resolve().parent/'inputs'
parser = argparse.ArgumentParser()
parser.add_argument('--image',type=Path,default=default_base/'NUIST-2D-Campus-Map.png')
parser.add_argument('--base',type=Path,default=default_base)
parser.add_argument('--proof',type=Path)
args=parser.parse_args()
image=Image.open(args.image).convert('RGB')
if image.size != (8997,5061):
    raise ValueError('Expected the original 8997 × 5061 campus plan.')
grid=(4256,2394)
analysis=np.asarray(image.resize(grid,Image.Resampling.LANCZOS))
def read(name):
    return json.loads((args.base/name).read_text().split('=',1)[1].strip(' ;\n'))
def write(name,variable,data):
    (project/name).write_text('export const '+variable+' = '+json.dumps(data,separators=(',',':'),ensure_ascii=False)+';\n')
d=read('osm-data.js')
base_buildings=read('osm-data.js')['buildings']
layouts=read('sports-layout.js')
# Three separate 400 m tracks provide an east-west and a north-south baseline.
controls=[('r20451657',(940,1444)),('r20452213',(1420,1573)),('r20452366',(3120,693))]
M=np.linalg.solve([[*layouts[k][1:3],1] for k,p in controls], [p for k,p in controls])
inverse=np.linalg.inv(M[:2])
def project_to_pixel(pts):
    return np.asarray(pts)@M[:2]+M[2]
def world(pts):
    return ((np.asarray(pts)-M[2])@inverse).round(4).tolist()
def ring(coords):
    return world(list(coords))
def pixel_shape(f):
    return Polygon(project_to_pixel(f['points']),[project_to_pixel(h) for h in f.get('holes',[])])
def store_shape(poly):
    return {'points':ring(poly.exterior.coords),'holes':[ring(h.coords) for h in poly.interiors]}
def rect(x,y,length,width,angle):
    return affinity.rotate(box(x-length/2,y-width/2,x+length/2,y+width/2),angle,(x,y))
def geometry(b,poly):
    b.update(store_shape(poly))
    fp=Polygon(b['points'],b['holes'])
    rectangle=fp.minimum_rotated_rectangle
    corners=np.array(rectangle.exterior.coords)
    sides=np.diff(corners,axis=0)
    ix=np.argmax(np.linalg.norm(sides,axis=1));dx,dz=sides[ix]
    center=list(rectangle.centroid.coords[0])
    b.update(rect=corners.round(4).tolist(),center=center,width=float(np.hypot(dx,dz)),depth=float(np.linalg.norm(sides[(ix+1)%4])),
             angle=math.atan2(-dz,dx))
    ox,oz=d['origin']
    b['lon']=round(ox+center[0]/(111320*math.cos(math.radians(oz))*d['unitsPerMeter']),8)
    b['lat']=round(oz-center[1]/(111320*d['unitsPerMeter']),8)

# Match existing roof outlines using bright roofs and red tiles. Blue cartographic
# labels are ignored. A constrained fit keeps partially occluded roofs stable.
rgb=analysis.astype(np.int16)
r,g,b=rgb.transpose(2,0,1)
white=(np.minimum(np.minimum(r,g),b)>137)&((np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b))<58)
red=(r>70)&(r>g*1.28)&(r>b*1.27)&(r<225)
roof=(white|red).astype('uint8')
label=(b>g+21)&(g>r+25)&(r<110)
roof=cv2.morphologyEx(roof,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
field=cv2.GaussianBlur(roof.astype('float32'),(0,0),1.5)
def fit_existing(f):
    poly=pixel_shape(f)
    spec=fits.get(f['id'])
    bounds=poly.minimum_rotated_rectangle
    points=np.array(bounds.exterior.coords); sides=np.diff(points,axis=0)
    axis=sides[np.argmax(np.linalg.norm(sides,axis=1))];axis/=np.linalg.norm(axis)
    if axis[0]<0:axis*=-1
    rot=np.array([axis,[-axis[1],axis[0]]])
    origin=np.array(bounds.centroid.coords[0])
    def transform(v):
        dx,dy,sx,sy=v
        axes=rot.T@np.diag([sx,sy])@rot
        offset=origin+np.array([dx,dy])-axes@origin
        return affinity.affine_transform(poly,[*axes[0],*axes[1],*offset])
    if spec:
        x,y,long,short,bearing=spec
        local=affinity.rotate(poly,-math.degrees(math.atan2(axis[1],axis[0])),tuple(origin))
        lx,ly,rx,ry=local.bounds
        shape=affinity.scale(local,long/(rx-lx),short/(ry-ly),origin=tuple(origin))
        shape=affinity.rotate(shape,bearing,tuple(origin))
        return affinity.translate(shape,x-origin[0],y-origin[1])
    if f['id']=='1114843846':return poly
    edge=poly.exterior
    pts=np.array([edge.interpolate(t).coords[0] for t in np.arange(.25,edge.length,2.5)])
    # On either side of every boundary sample, compare roof and surroundings.
    follow=np.array([edge.interpolate((t+.6)%edge.length).coords[0] for t in np.arange(.25,edge.length,2.5)])
    tangent=follow-pts
    tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],.001)
    normal=tangent[:,::-1]*[-1,1]
    if not edge.is_ccw:normal*=-1
    inside=(pts+normal*3-origin)@rot.T
    outside=(pts-normal*3-origin)@rot.T
    def sample(q):
        xx,yy=q.T
        return cv2.remap(field,xx.astype('float32').reshape(-1,1),yy.astype('float32').reshape(-1,1),cv2.INTER_LINEAR).ravel()
    def cost(v):
        offs=origin+v[:2];scale=np.asarray(v[2:])
        a=(inside*scale)@rot+offs;c=(outside*scale)@rot+offs
        idx=np.rint((a+c)/2).astype(int)
        ok=~label[idx[:,1],idx[:,0]]
        score=(sample(a)-sample(c))[ok]
        return -score.mean()+.0008*np.dot(v[:2],v[:2])+.8*np.sum((scale-1)**2) if len(score)>10 else 1.
    start=min(([dx,dy,1.,1.] for dx in [-7.,0.,7.] for dy in [-6.,0.,6.,12.]),key=cost)
    res=minimize(cost,start,method='Powell',bounds=[(-13,13),(-13,13),(.82,1.28),(.81,1.32)],options={'maxiter':8,'xtol':.025})
    return transform(res.x) if cost(res.x)<cost(np.array([0,0,1.,1.]))-.045 else poly

profiles=read('building-profiles.js')
for f in d['buildings']:
    poly=fit_existing(f)
    # Preserve known facade orientation and original local centre on untouched geometry.
    if not poly.equals_exact(pixel_shape(f),.005):
        geometry(f,poly)
    if f['id'] in names:
        f['name']=names[f['id']]
        f['tags']['name']=f['name']
# The old footprint of 学科3号楼 combined two separate buildings and their yard.
for key,spec in [('862959357',(1547,1491,86,26,-7)),('862959358',(1555,1541,85,26,-7))]:
    geometry(next(f for f in d['buildings'] if f['id']==key),rect(*spec))
main=next(f for f in d['buildings'] if f['id']=='862959367')
geometry(main,rect(1284,1228,85,32,-7))
# Raster plan shows a narrow ceremonial tower in a planted circular forecourt.
tower=Point(1884,843).buffer(5.7,quad_segs=6)
for key,name,spec,roof_kind,floors in [*blocks,('changwang','长望塔',None,'sand',4)]:
    feature={'id':'plan-'+key,'name':name,'tags':{'building':'yes','name':name},'heightSource':'鸟瞰轮廓，楼层估计','height':floors*.68}
    geometry(feature,rect(*spec) if spec else tower)
    profiles[feature['id']]={'kind':('campusTower' if not spec else 'planBlock'),'roof':roof_kind,'floors':floors,'status':'用户鸟瞰图轮廓','note':name+'的位置与平面尺寸按校园鸟瞰图重建，外立面待实拍核对。'}
    d['buildings'].append(feature)
# Survey plot: a ground feature. Include the agricultural observation fields north
# of the instrumentation strip without turning them into a building collider.
plot=next(f for f in d['buildings'] if f['id']=='1114843846')
geometry(plot,Polygon([(1034,825),(1152,812),(1170,1000),(1212,997),(1219,1116),(1059,1120),(1041,1023)]))

# Trace exposed water from the original RGB pixels. Restrict the segmentation to
# individually inspected basins, so blue roofs, map labels and courts are excluded.
basins={
 'west':[(970,881),(1035,887),(1065,1098),(1090,1153),(1177,1169),(1225,1133),(1225,1054),(1316,1044),(1321,1095),(1274,1143),(1278,1201),(1224,1288),(1215,1364),(1181,1490),(1200,1640),(1205,1835),(1226,1915),(1155,1933),(1112,1791),(1083,1601),(1079,1540),(1041,1539),(1027,1438),(1067,1353),(1022,1296),(986,1171),(976,1084)],
 'pond':[(1486,927),(1550,929),(1570,1061),(1492,1061)],
 'lotus':[(2050,862),(2118,845),(2133,915),(2060,926)],
 'east':[(2688,570),(2727,565),(2797,841),(2869,1093),(2893,1123),(3237,1213),(3236,1250),(2852,1157),(2826,1130),(2770,930),(2722,736)]}
def polygons(shape):
    if shape.is_empty:return []
    if shape.geom_type=='Polygon':return [shape]
    return [a for q in getattr(shape,'geoms',[]) for a in polygons(q)]
def trace_water(vertices):
    region=Polygon(vertices)
    x0,y0,x1,y1=region.bounds
    scale=np.array(image.size)/grid
    offset=np.floor(np.array([x0,y0])*scale).astype(int)
    end=np.ceil(np.array([x1,y1])*scale).astype(int)+1
    crop=np.array(image.crop((*offset,*end))).astype('int16')
    rr,gg,bb=crop.transpose(2,0,1)
    colour=((rr<94)&(gg-rr>36)&(bb>99)&(bb<170)&(bb-gg>6)&(bb-gg<40)).astype('uint8')
    mask=np.zeros(colour.shape,np.uint8)
    cv2.fillPoly(mask,[np.rint(np.asarray(vertices)*scale-offset).astype('int32')],1)
    ink=cv2.morphologyEx(colour*mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    contours,hier=cv2.findContours(ink,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    found=[]
    def coords(c):return (c.reshape(-1,2)+offset)/scale
    for i,c in enumerate(contours):
        if hier[0,i,3]>=0 or cv2.contourArea(c)<145*scale.prod():continue
        holes=[];child=hier[0,i,2]
        while child!=-1:
            if cv2.contourArea(contours[child])>14*scale.prod():holes.append(coords(contours[child]))
            child=hier[0,child,0]
        found.extend(polygons(Polygon(coords(c),holes).buffer(0).simplify(.9,preserve_topology=True)))
    return found
segments={key:trace_water(q) for key,q in basins.items()}
# Continuous channels pass below the mapped bridge decks. Local ties only span the
# recorded openings; dry islands and unconnected ornamental ponds retain dry land.
def underneath(parts,key):
    exposed=unary_union(parts)
    inferred=[]
    for name,width,points in bridges:
        if not name.startswith(key+'-'):continue
        line=LineString(points);a=np.array(points[0]);delta=np.array(points[-1])-a
        along=delta/np.linalg.norm(delta);normal=along[::-1]*[-1,1]
        # Estimate the submerged banks only where the mapped channel continues on
        # both sides of the same deck. Islands and paths remain dry.
        for t in np.arange(0,line.length,1):
            at=a+along*t
            reach=width*.5+10
            across=LineString([at-normal*reach,at+normal*reach])
            slices=lines_under(exposed.intersection(across))
            sides=[]
            for q in slices:
                interval=sorted(np.dot(np.array(q.coords)-at,normal))
                sides.append((interval[0],interval[-1]))
            left=[v[1] for v in sides if v[1]<=.8]
            right=[v[0] for v in sides if v[0]>=-.8]
            if left and right and min(right)>max(left):
                v=at+normal*(max(left)-.65);w=at+normal*(min(right)+.65)
                inferred.append(Polygon([v-along*.56,v+along*.56,w+along*.56,w-along*.56]))
    return unary_union([exposed,*inferred]).buffer(.3).buffer(-.3).simplify(.42)
def lines_under(g):
    if g.is_empty:return []
    if g.geom_type=='LineString':return [g]
    return [v for q in getattr(g,'geoms',[]) for v in lines_under(q)]
surface_ids={'west':'1114848802','pond':'682188172','lotus':'682188142','east':'plan-east-canal'}
d['water']=[]
for key,parts in segments.items():
    merged=underneath(parts,key)
    for i,poly in enumerate(sorted(polygons(merged),key=lambda p:-p.area)):
        d['water'].append(dict(id=surface_ids[key]+(f'-{i}' if i else ''),name={'west':'西苑水系','pond':'人才公寓旁池塘','lotus':'藕舫园','east':'东苑河道'}[key],**store_shape(poly)))
water_shape=unary_union([pixel_shape(f) for f in d['water']])

obstacles=unary_union([pixel_shape(f) for f in d['buildings'] if f['id']!='1114843846'])
sport_outline=unary_union([pixel_shape(f) for f in d['sports']])
deck_shapes=[LineString(p).buffer(w/2,cap_style='flat') for _,w,p in bridges]
deck_union=unary_union(deck_shapes)
# Avoid planting slivers on the deck approaches.
d['bridges']=[dict(id='bridge-'+k,**store_shape(poly)) for (k,w,pts),poly in zip(bridges,deck_shapes)]
forbidden=obstacles.buffer(1.2).union(water_shape.difference(deck_union.buffer(1)))
chroma=rgb.max(axis=2)-rgb.min(axis=2)
road_likelihood=((chroma<22)&(g>39)&(g<157)).astype('float32')
road_likelihood+=.36*((chroma<18)&(g>=157)&(g<202))
road_likelihood=cv2.GaussianBlur(road_likelihood,(0,0),1.7)
obs_mask=np.zeros(road_likelihood.shape,np.uint8)
for item in polygons(obstacles.union(sport_outline)):
    cv2.fillPoly(obs_mask,[np.rint(item.exterior.coords).astype('int32')],1)
    for h in item.interiors:cv2.fillPoly(obs_mask,[np.rint(h.coords).astype('int32')],0)
road_likelihood-=obs_mask*1.2
def samples(line,step):
    n=max(2,int(np.ceil(line.length/step))+1)
    return np.array([line.interpolate(i,normalized=True).coords[0] for i in np.linspace(0,1,n)])
def snap(line,width,limit):
    pts=samples(line,8)
    tangent=np.gradient(pts,axis=0); tangent/=np.maximum(.001,np.linalg.norm(tangent,axis=1)[:,None])
    normal=tangent[:,::-1]*[-1,1]
    offsets=np.arange(-limit,limit+1,1.5)
    def likelihood(delta):
        q=np.rint(pts[:,None,:]+normal[:,None,:]*(offsets+delta)[None,:,None]).astype(int)
        return road_likelihood[q[:,:,1].clip(0,grid[1]-1),q[:,:,0].clip(0,grid[0]-1)]
    score=.38*likelihood(0)+.31*(likelihood(width*.3)+likelihood(-width*.3))
    score-=.10*(likelihood(width*.75)+likelihood(-width*.75))
    score-=.0013*(offsets**2)[None,:]
    transition=.085*np.abs(offsets[:,None]-offsets[None,:])**1.5
    cumulative=score[0].copy(); back=[]
    for row in score[1:]:
        options=cumulative[:,None]-transition
        pick=options.argmax(axis=0);back.append(pick)
        cumulative=options[pick,np.arange(len(pick))]+row
    path=[cumulative.argmax()]
    for opts in reversed(back):path.append(opts[path[-1]])
    shifted=pts+normal*offsets[list(reversed(path)),None]
    return LineString(shifted).simplify(.8)
def lines(geom):
    if geom.is_empty:return []
    if geom.geom_type=='LineString':return [geom]
    return [v for s in getattr(geom,'geoms',[]) for v in lines(s)]
def road_width(line,prior):
    pts=samples(line,10); direction=np.gradient(pts,axis=0);direction/=np.maximum(.001,np.linalg.norm(direction,axis=1)[:,None])
    n=direction[:,::-1]*[-1,1]; offsets=np.arange(-23,24)
    q=np.rint(pts[:,None,:]+n[:,None,:]*offsets[None,:,None]).astype(int)
    mask=road_likelihood[q[:,:,1].clip(0,grid[1]-1),q[:,:,0].clip(0,grid[0]-1)]>.42
    widths=[]
    for row in mask[1:-1]:
        if not row[23]:continue
        neg=np.flatnonzero(~row[23::-1]);pos=np.flatnonzero(~row[23:])
        if len(neg) and len(pos):
            w=neg[0]+pos[0]-1
            if 3<=w<=prior*1.9:widths.append(w)
    value=np.median(widths) if len(widths)>=3 else prior
    return round(float(np.clip(.72*value+.28*prior,max(3,prior*.73),prior*1.35)),2)
manual=[]
for name,width,pts in roads:
    ln=snap(LineString(pts),width,22)
    for part in lines(ln.difference(forbidden)):
        if part.length>=11:manual.append((name,road_width(part,width),part))
for (key,width,pts),geom in zip(bridges,deck_shapes):
    ln=LineString(pts)
    if not any(ln.difference(line.buffer(max(4,w*.7))).length<8 for _,w,line in manual):
        manual.append(('桥面',width,ln))

# Preserve OSM intersections shared by multiple streets. Short remaining stubs snap
# to the newly traced main line; parallel copies of that line are removed.
all_manual=[p for _,_,p in manual]; tree=STRtree(all_manual)
def near_main(pt):
    ix=tree.nearest(pt); road=all_manual[ix]
    return road.interpolate(road.project(pt))
base_roads=d['roads']
candidates=[];nodes={}
for rr in base_roads:
    line=LineString(project_to_pixel(rr['points']))
    width=rr['width']*6.685
    for a in [line.coords[0],line.coords[-1]]:nodes.setdefault(tuple(np.round(a,3)),[])
    if line.length<2:continue
    moved=snap(line,width,9)
    candidates.append((rr,line,moved,road_width(moved,width)))
    for i in [0,-1]:nodes[tuple(np.round(line.coords[i],3))].append(moved.coords[i])
def merged_node(pt):
    items=nodes[tuple(np.round(pt,3))]
    return np.mean(items,axis=0) if items else pt
all_roads=[]
def add_road(ident,name,w,line):
    all_roads.append(dict(id=ident,name=name,width=round(w/6.685,4),points=world(line.coords)))
for i,(name,w,line) in enumerate(manual): add_road('plan-road-'+str(i),name,w,line)
for rr,before,moved,width in candidates:
    cs=list(moved.coords);cs[0]=merged_node(before.coords[0]);cs[-1]=merged_node(before.coords[-1]);moved=LineString(cs)
    trim=[]
    for ix in tree.query(moved.buffer(20)):
        main=all_manual[ix]; close=moved.intersection(main.buffer(max(7,manual[ix][1]*.72)))
        # Keep perpendicular branches long enough to actually meet the main road.
        for seg in lines(close):
            a,b=seg.boundary.geoms if not seg.is_ring else (None,None)
            if a is None:continue
            run=abs(main.project(a)-main.project(b))
            if run>seg.length*.76 and run>4:trim.append(main.buffer(max(8,manual[ix][1]*.80)))
    remainder=moved.difference(unary_union(trim)) if trim else moved
    for k,part in enumerate(lines(remainder)):
        if part.length<3:continue
        coords=list(part.coords)
        for i in (0,-1):
            point=Point(coords[i]);match=near_main(point)
            if point.distance(match)<13:
                coords[i]=match.coords[0]
        for j,p in enumerate(lines(LineString(coords).difference(forbidden))):
            if p.length>2.5:add_road(rr['id']+'-'+str(k)+'-'+str(j),rr.get('name',''),width,p)
# The campus boundary roads are visually broader, with separate approaches to the gates.
perimeter=[
 ('万家坝路',51,[(444,736),(612,753),(847,774),(994,777),(1130,769),(1281,744),(1455,711),(1590,704),(1744,709),(1888,715),(2003,706),(2138,676),(2211,659),(2423,604),(2647,548),(2783,514),(2958,487),(3166,469),(3404,467)]),
 ('龙山北路',39,[(903,2103),(1100,1991),(1287,1888),(1473,1785),(1615,1711),(1812,1625),(1986,1556),(2208,1467),(2450,1364),(2579,1312),(2669,1284),(2748,1281),(2828,1286),(2936,1304),(3043,1321),(3190,1344)]),
 ('江北大道快速路',66,[(3515,249),(3449,470),(3397,680),(3344,896),(3291,1113),(3246,1319),(3197,1518)]),
 ('西苑南门',17,[(1077,2001),(1066,1961),(1065,1939)]),
 ('中苑南门',17,[(1864,1597),(1850,1559),(1837,1516)]),
 ('东苑南门',20,[(2936,1304),(2940,1246),(2938,1192)]),
 ('东苑北门',15,[(2422,604),(2432,636),(2440,666)]),
 ('西苑北门',13,[(847,774),(843,803),(838,844)]),
]
for i,(name,width,coordinates) in enumerate(perimeter):
    add_road('boundary-'+str(i),name,width,LineString(coordinates))
d['roads']=all_roads
# Fill the previously absent landscape between the east athletics track, east gate
# and river. The two old campus polygons excluded the main dividing avenue.
boundary=[(611,790),(852,816),(1062,819),(1247,800),(1434,772),(1647,746),(1839,756),(1973,750),(2128,712),(2240,681),(2472,614),(2716,553),(2916,526),(3187,502),(3397,498),(3411,529),(3377,678),(3312,967),(3244,1241),(3198,1318),(3007,1291),(2848,1275),(2743,1265),(2666,1266),(2607,1284),(2444,1348),(2194,1447),(1973,1539),(1795,1614),(1606,1691),(1469,1760),(1271,1860),(1107,1976),(925,2072),(792,1837),(652,1590),(578,1452),(541,1348),(524,1235),(529,1121),(552,975),(582,854)]
d['campus']=[store_shape(Polygon(boundary))]
road_area=unary_union([LineString(project_to_pixel(v['points'])).buffer(v['width']*6.685/2+.9) for v in all_roads])
dry=Polygon(boundary).difference(unary_union([road_area.buffer(2),obstacles.buffer(2.5),water_shape.buffer(1),sport_outline]))
d['trees']=[t for t in d['trees'] if dry.contains(Point(project_to_pixel([t[:2]])[0]))]
# Sample mapped green canopy patches, with a deterministic spacing. This restores the
# wooded east edge without planting into the newly mapped residences or driveways.
rng=np.random.default_rng(44)
tree_pts=[Point(project_to_pixel([t[:2]])[0]) for t in d['trees']]
old_trees=STRtree(tree_pts)
new=[]
for x in np.arange(540,3400,22):
    for y in np.arange(525,2040,24):
        xx,yy=np.array([x,y])+rng.uniform(-5,5,2); pt=Point(xx,yy)
        if not dry.contains(pt):continue
        red_px,green_px,blue_px=rgb[int(yy),int(xx)]
        if not (green_px>red_px*1.16 and blue_px<green_px*.77):continue
        if tree_pts and old_trees.query(pt,predicate='dwithin',distance=13).size:continue
        if rng.random()>.32:continue
        new.append([*world([[xx,yy]])[0],round(rng.uniform(.73,1.14),3)])
d['trees']+=new

# Re-route both bus directions on the same noded road centrelines as the rendered
# lanes. Waypoints keep the original loop around campus and its ten stop names.
import heapq
from collections import defaultdict
network=[LineString(q['points']) for q in all_roads if q['width']>=.68 and not q['id'].startswith('boundary-')]
roads_union=unary_union(network)
graph=defaultdict(dict)
def connect(a,b):
    a=tuple(np.round(a,3));b=tuple(np.round(b,3))
    if a!=b:graph[a][b]=graph[b][a]=math.dist(a,b)
for line in lines(roads_union):
    points=samples(line,1.05)
    for a,c in zip(points,points[1:]):connect(a,c)
nodes0=list(graph)
from scipy.spatial import cKDTree
kd=cKDTree(nodes0)
blocked_world=unary_union([Polygon(q['points'],q['holes']).buffer(.07) for q in d['buildings'] if q['id']!='1114843846'])
wet_world=unary_union([Polygon(q['points'],q['holes']) for q in d['water']]).difference(unary_union([Polygon(q['points']) for q in d['bridges']]))
road_buffer=unary_union(network).buffer(.55)
for i,a in enumerate(nodes0):
    if len(graph[a])>1:continue
    for j in kd.query_ball_point(a,1.25):
        if i==j:continue
        link=LineString((a,nodes0[j]))
        if road_buffer.covers(link) and not link.intersects(blocked_world) and not link.intersects(wet_world):connect(a,nodes0[j])
anchor_legs=read('shuttle-route.js')
components=[];remaining=set(graph)
while remaining:
    start=next(iter(remaining));seen={start};queue=[start]
    for a in queue:
        for c in graph[a]:
            if c not in seen:seen.add(c);queue.append(c)
    remaining-=seen;components.append(queue)
main=max(components,key=len); kdt=cKDTree(main)
def closest(q):return main[kdt.query(q)[1]]
def route(a,b):
    if a==b:return [a]
    prev={};best={a:0};heap=[(0,a)]
    while heap:
        cost,node=heapq.heappop(heap)
        if node==b:break
        if cost!=best[node]:continue
        for n,edge in graph[node].items():
            d2=cost+edge
            if d2<best.get(n,math.inf):best[n]=d2;prev[n]=node;heapq.heappush(heap,(d2,n))
    result=[b]
    while result[-1]!=a:result.append(prev[result[-1]])
    return result[::-1]
shuttle=[]
for leg in anchor_legs:
    original=LineString(leg['points']);samples0=samples(original,12)
    way=[closest(p) for p in samples0]
    path=[way[0]]
    for a,b0 in zip(way,way[1:]):path.extend(route(a,b0)[1:])
    # A waypoint just inside a side street can introduce an out-and-back spur.
    # Keep the simple path through the ordered stops.
    ix={};unique=[]
    for node in path:
        if node in ix:
            while unique[-1]!=node:del ix[unique.pop()]
        else:ix[node]=len(unique);unique.append(node)
    ln=LineString(unique).simplify(.02)
    shuttle.append({'stop':leg['stop'],'points':list(ln.coords)})
write('shuttle-route.js','shuttleLegs',shuttle)
write('osm-data.js','osm',d)
write('building-profiles.js','profiles',profiles)
# The weather tower is a separately modelled upper body; apply the same affine
# change to it as to its podium so the two remain aligned.
original=next(q for q in base_buildings if q['id']=='478390591')
updated=next(q for q in d['buildings'] if q['id']=='478390591')
src=np.column_stack((original['points'],np.ones(len(original['points']))))
warp=np.linalg.lstsq(src,updated['points'],rcond=None)[0]
part=read('building-parts.js')
q=part[original['id']];q['points']=(np.column_stack((q['points'],np.ones(len(q['points']))))@warp).round(4).tolist()
write('building-parts.js','parts',part)

print('Buildings',len(d['buildings']),'water pieces',[(k,len(v)) for k,v in segments.items()],'road sections',len(all_roads),'bus length (world units)',round(sum(LineString(leg['points']).length for leg in shuttle),1),'trees',len(d['trees']))
if args.proof:
    preview=analysis.copy(); ink=ImageDraw.Draw(canvas:=Image.fromarray(preview))
    for q in d['water']:
        ink.line(list(map(tuple,project_to_pixel(q['points']))),fill='#8cfcff',width=3)
    for q in d['roads']:
        ink.line(list(map(tuple,project_to_pixel(q['points']))),fill='#ffb547',width=2)
    for q in d['buildings']:
        for path in [q['points'],*q['holes']]:
            ink.line(list(map(tuple,project_to_pixel(path))),fill='#ff63b7' if q['id'].startswith('plan-') else '#fff4a1',width=2)
    crop=canvas.crop((492,460,3440,2077))
    proof=Image.new('RGB',(crop.width,crop.height+116),'#f5f4e9')
    proof.paste(crop,(0,116));legend=ImageDraw.Draw(proof)
    font_path='/System/Library/Fonts/Hiragino Sans GB.ttc'
    title=ImageFont.truetype(font_path,40);keyfont=ImageFont.truetype(font_path,25)
    legend.text((33,13),'南京信息工程大学  ·  校园布局套合图',font=title,fill='#203a34')
    legend.text((35,72),'以用户提供的校园鸟瞰图为底图，叠加游戏平面轮廓。',font=keyfont,fill='#48655a')
    for x,color,caption in [(1440,'#fff4a1','原有建筑轮廓'),(1810,'#ff63b7','新增建筑轮廓'),(2180,'#ffb547','道路中心线'),(2540,'#8cfcff','水岸线')]:
        legend.rounded_rectangle((x,38,x+51,62),5,fill=color,outline='#4c6058',width=2)
        legend.text((x+64,32),caption,font=keyfont,fill='#29433c')
    proof.save(args.proof,quality=94)

# The walking scene uses precomputed surface, planting and parking batches.
subprocess.run([sys.executable,Path(__file__).with_name('bake-ground.py')],check=True)
subprocess.run([sys.executable,args.base/'generate-landscape.py'],cwd=project,check=True)
garden=json.loads((project/'landscape-data.js').read_text().split('=',1)[1].strip(' ;\n'))
decks_world=unary_union([Polygon(f['points']) for f in d['bridges']])
garden['shore']=[p for p in garden['shore'] if decks_world.distance(Point(p))>.5]
write('landscape-data.js','landscape',garden)
# Place the same six residential bike bays on clear, dry verges in the new layout.
road_world=unary_union([LineString(q['points']).buffer(q['width']/2+.29) for q in all_roads])
plant_points=[Point(x,z) for x,z,*_ in garden['beds']+garden['trees']+d['trees']]
plant_index=STRtree(plant_points)
unavailable=unary_union([road_world,wet_world,blocked_world,*[Polygon(q['points'],q['holes']) for q in d['sports']]])
parking=[]
for dorm in ['沁园35栋','沁园27栋','文园8栋','文园15栋','沁园22栋','文园4栋']:
    center=Point(next(f for f in d['buildings'] if f['name']==dorm)['center'])
    options=[]
    for q in all_roads:
        ln=LineString(q['points'])
        if ln.distance(center)>14:continue
        for t in np.arange(.25,ln.length-.15,.7):
            pos=np.array(ln.interpolate(t).coords[0]);tangent=np.array(ln.interpolate(t+.1).coords[0])-pos
            tangent/=max(.0001,np.linalg.norm(tangent))
            for side in [-1,1]:
                at=pos+side*(q['width']/2+1.45)*tangent[::-1]*[-1,1];point=Point(at)
                if unavailable.distance(point)<1.10 or plant_index.query(point,predicate='dwithin',distance=1.5).size:continue
                options.append((point.distance(center),[*at,math.atan2(*tangent)]))
    if options:parking.append([round(v,4) for v in min(options,key=lambda item:item[0])[1]])
d['bikeBays']=parking
write('osm-data.js','osm',d)
subprocess.run(['node',project/'build.mjs'],check=True)
