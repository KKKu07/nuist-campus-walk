import json, sys, math, numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=Image.open(R+'web/public/campus/ortho.jpg'); sx=orth.size[0]/W
n=sys.argv[1]; x0,z0,x1,z1=map(float,sys.argv[2:6]); k=float(sys.argv[6]) if len(sys.argv)>6 else 3
a=orth.crop((int((x0+W/2)*sx),int((z0+H/2)*sx),int((x1+W/2)*sx),int((z1+H/2)*sx))).resize((int((x1-x0)*k),int((z1-z0)*k)))
d=ImageDraw.Draw(a,'RGBA')
P=lambda x,z:((x-x0)*k,(z-z0)*k)
for r in c['roads']:
    p=r['pts']
    if r['kind'] in ('footway','path','steps','cycleway','track'): continue
    for i in range(len(p)-1):
        (ax,az),(bx,bz)=p[i],p[i+1]; L=math.hypot(bx-ax,bz-az) or 1; nx,nz=-(bz-az)/L,(bx-ax)/L
        hw=r['w']/2; s=hw+r.get('sw',0)
        d.polygon([P(ax+nx*s,az+nz*s),P(bx+nx*s,bz+nz*s),P(bx-nx*s,bz-nz*s),P(ax-nx*s,az-nz*s)],fill=(255,255,0,40))
        d.polygon([P(ax+nx*hw,az+nz*hw),P(bx+nx*hw,bz+nz*hw),P(bx-nx*hw,bz-nz*hw),P(ax-nx*hw,az-nz*hw)],outline=(255,60,0,200))
    if r.get('name'):
        m=p[len(p)//2]; d.text(P(*m),r['name'],fill=(255,255,255,255))
old=set((t[0],t[1]) for t in json.load(open(R+'data/manual/trees_v2.json')))
for t in c['trees']:
    x,z=t[0],t[1]
    if not (x0<x<x1 and z0<z<z1): continue
    col=(0,255,0,255) if (x,z) in old else (255,0,255,255)
    X,Z=P(x,z); d.ellipse([X-2,Z-2,X+2,Z+2],fill=col)
a.save(R+f'data/raw/wp2/{n}.jpg',quality=88); print(a.size)
