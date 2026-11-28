# aerial crop with a 5 m ruler grid, enlarged; args: name x0 z0 x1 z1 [scale]
import json, sys, numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=Image.open(R+'web/public/campus/ortho.jpg'); sx=orth.size[0]/W
n=sys.argv[1]; x0,z0,x1,z1=map(float,sys.argv[2:6]); k=float(sys.argv[6]) if len(sys.argv)>6 else 6
a=orth.crop((int((x0+W/2)*sx),int((z0+H/2)*sx),int((x1+W/2)*sx),int((z1+H/2)*sx)))
a=a.resize((int((x1-x0)*k),int((z1-z0)*k)),Image.LANCZOS)
d=ImageDraw.Draw(a)
for x in np.arange(np.ceil(x0/5)*5,x1,5):
    X=(x-x0)*k; d.line([(X,0),(X,8 if x%10 else 16)],fill=(255,255,0),width=1)
    if x%10==0: d.text((X+2,16),str(int(x)),fill=(255,255,0))
for z in np.arange(np.ceil(z0/5)*5,z1,5):
    Z=(z-z0)*k; d.line([(0,Z),(8 if z%10 else 16,Z)],fill=(255,255,0),width=1)
    if z%10==0: d.text((18,Z-5),str(int(z)),fill=(255,255,0))
for r in c['roads']:
    p=np.array(r['pts'])
    if p[:,0].max()<x0 or p[:,0].min()>x1 or p[:,1].max()<z0 or p[:,1].min()>z1: continue
    d.line([((x-x0)*k,(z-z0)*k) for x,z in p],fill=(255,0,0),width=1)
a.save(R+f'data/raw/wp2/{n}.jpg',quality=90); print(a.size)
