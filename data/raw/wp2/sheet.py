# contact sheet: for each road id, aerial crop (S m square, k px/m) around a point along the road, with our road edges drawn
import json, sys, math, numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=Image.open(R+'web/public/campus/ortho.jpg'); sx=orth.size[0]/W
roads={r['id']:r for r in c['roads']}
def at(p,t):
    L=[math.dist(p[i],p[i+1]) for i in range(len(p)-1)]; s=t*sum(L)
    for i,l in enumerate(L):
        if s<=l: f=s/max(l,1e-9); return (p[i][0]+(p[i+1][0]-p[i][0])*f, p[i][1]+(p[i+1][1]-p[i][1])*f)
        s-=l
    return p[-1]
def tile(rid,t=0.5,S=70,k=5):
    r=roads[rid]; cx,cz=at(r['pts'],t); x0,z0=cx-S/2,cz-S/2
    a=orth.crop((int((x0+W/2)*sx),int((z0+H/2)*sx),int((x0+S+W/2)*sx),int((z0+S+H/2)*sx))).resize((S*k,S*k),Image.LANCZOS)
    d=ImageDraw.Draw(a)
    for rr in c['roads']:
        p=np.array(rr['pts'])
        if p[:,0].max()<x0 or p[:,0].min()>x0+S or p[:,1].max()<z0 or p[:,1].min()>z0+S: continue
        q=[((x-x0)*k,(z-z0)*k) for x,z in p]
        col=(255,0,0) if rr['id']==rid else (0,220,255)
        d.line(q,fill=col,width=1)
        if rr['id']==rid:
            # edges
            for sgn in (-1,1):
                e=[]
                for i in range(len(p)):
                    a0=p[max(0,i-1)]; a1=p[min(len(p)-1,i+1)]; dx,dz=a1-a0; l=math.hypot(dx,dz) or 1
                    e.append(((p[i][0]-dz/l*rr['w']/2*sgn-x0)*k,(p[i][1]+dx/l*rr['w']/2*sgn-z0)*k))
                d.line(e,fill=(255,120,0),width=1)
    for m in range(0,S+1,5): d.line([(m*k,0),(m*k,6 if m%10 else 12)],fill=(255,255,0))
    d.rectangle([0,S*k-14,S*k,S*k],fill=(0,0,0)); d.text((3,S*k-13),f"{rid} {r['kind']} w{r['w']} {r['name']} @({cx:.0f},{cz:.0f})",fill=(255,255,255))
    return a
if __name__=='__main__':
    name=sys.argv[1]; items=[a.split(':') for a in sys.argv[2:]]
    ims=[tile(int(i[0]),float(i[1]) if len(i)>1 else 0.5) for i in items]
    cols=3; S=ims[0].size[0]; rows=math.ceil(len(ims)/cols)
    out=Image.new('RGB',(cols*S+(cols-1)*4,rows*S+(rows-1)*4),(255,255,255))
    for i,im in enumerate(ims): out.paste(im,((i%cols)*(S+4),(i//cols)*(S+4)))
    out.save(R+f'data/raw/wp2/{name}.jpg',quality=88); print(out.size)
