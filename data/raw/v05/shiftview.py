import json, sys, numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=Image.open(R+'web/public/campus/ortho.jpg'); sx=orth.size[0]/W
off=Image.open(R+'data/official/official_local.jpg'); m=json.load(open(R+'data/official/official_local_meta.json')); q=1/m['m_per_px']
x0,z0,x1,z1,dx,dz=map(float,sys.argv[1:7]); k=2
size=(int((x1-x0)*k),int((z1-z0)*k))
a=np.asarray(orth.crop((int((x0+W/2)*sx),int((z0+H/2)*sx),int((x1+W/2)*sx),int((z1+H/2)*sx))).resize(size)).astype(np.float32)
def offc(dx,dz): return np.asarray(off.crop((int((x0+dx-m['x0'])*q),int((z0+dz-m['z0'])*q),int((x1+dx-m['x0'])*q),int((z1+dz-m['z0'])*q))).resize(size)).astype(np.float32)
outs=[]
for (ddx,ddz) in [(0,0),(dx,dz)]:
    b=offc(ddx,ddz); e=cv2.Canny(b.astype(np.uint8),80,160)
    blend=(a*0.75).copy(); blend[e>0]=[255,40,40]
    outs.append(blend.astype(np.uint8))
out=np.concatenate([outs[0],np.full((size[1],6,3),255,np.uint8),outs[1]],1)
Image.fromarray(out).save(R+'data/raw/v05/shiftview.jpg',quality=85); print(out.shape)
