import json, sys, numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=np.asarray(Image.open(R+'web/public/campus/ortho.jpg').convert('RGB'))
sx=orth.shape[1]/W
off=np.asarray(Image.open(R+'data/official/official_local.jpg').convert('RGB'))
m=json.load(open(R+'data/official/official_local_meta.json'))
MPP=1.0
def crop(img,x0,z0,x1,z1,ox,oz,scale):
    a=img[int((z0-oz)*scale):int((z1-oz)*scale), int((x0-ox)*scale):int((x1-ox)*scale)]
    return cv2.resize(a,(int((x1-x0)/MPP),int((z1-z0)/MPP)),interpolation=cv2.INTER_AREA)
def feat(a):  # quantised colour class: greenness and brightness
    a=a.astype(np.int16); R_,G,B=a[...,0],a[...,1],a[...,2]
    lum=(R_+G+B)//3; exg=2*G-R_-B
    q=np.clip(lum//32,0,7)*4+np.digitize(exg,[0,15,35])
    return q.astype(np.int32)
def mi(a,b,bins=32):
    h,_,_=np.histogram2d(a.ravel(),b.ravel(),bins=bins,range=[[0,bins],[0,bins]])
    p=h/h.sum(); px=p.sum(1,keepdims=True); py=p.sum(0,keepdims=True); nz=p>0
    return float((p[nz]*np.log(p[nz]/(px@py)[nz])).sum())
def reg(x0,z0,x1,z1,s=16):
    A=feat(crop(orth,x0,z0,x1,z1,-W/2,-H/2,sx))
    best=[];
    for dz in range(-s,s+1):
        for dx in range(-s,s+1):
            Bi=feat(crop(off,x0+dx,z0+dz,x1+dx,z1+dz,m['x0'],m['z0'],1/m['m_per_px']))
            best.append((mi(A,Bi),dx,dz))
    best.sort(reverse=True); vals=np.array([b[0] for b in best])
    return best[0], round(float((best[0][0]-vals.mean())/vals.std()),1), best[1:4]
if len(sys.argv)<2:
  for box in [(-280,-420,-80,-220),(-600,-140,-400,60),(-100,-200,100,0),(800,-600,1000,-400),(300,-450,500,-250)]:
      print(box, reg(*box))

def reg2(x0,z0,x1,z1,s=26,step=2):
    A=feat(crop(orth,x0,z0,x1,z1,-W/2,-H/2,sx)); best=[]
    for dz in range(-s,s+1,step):
        for dx in range(-s,s+1,step):
            Bi=feat(crop(off,x0+dx,z0+dz,x1+dx,z1+dz,m['x0'],m['z0'],1/m['m_per_px'])); best.append((mi(A,Bi),dx,dz))
    best.sort(reverse=True); v=np.array([b[0] for b in best])
    return best[0], round(float((best[0][0]-v.mean())/v.std()),1)
import sys
if len(sys.argv)>1:
    for box in [(-280,-420,-80,-220),(-100,-200,100,0),(800,-600,1000,-400)]:
        print('wide', box, reg2(*box))
