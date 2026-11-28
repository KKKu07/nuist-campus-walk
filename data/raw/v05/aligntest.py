import json, sys, numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
orth=np.asarray(Image.open(R+'web/public/campus/ortho.jpg').convert('L')).astype(np.float32)
sx=orth.shape[1]/W
off=np.asarray(Image.open(R+'data/official/official_local.jpg').convert('L')).astype(np.float32)
m=json.load(open(R+'data/official/official_local_meta.json'))
def crop_aer(x0,z0,x1,z1,mpp=0.5):
    a=orth[int((z0+H/2)*sx):int((z1+H/2)*sx), int((x0+W/2)*sx):int((x1+W/2)*sx)]
    return cv2.resize(a,(int((x1-x0)/mpp),int((z1-z0)/mpp)),interpolation=cv2.INTER_AREA)
def crop_off(x0,z0,x1,z1,mpp=0.5):
    q=1/m['m_per_px']; a=off[int((z0-m['z0'])*q):int((z1-m['z0'])*q), int((x0-m['x0'])*q):int((x1-m['x0'])*q)]
    return cv2.resize(a,(int((x1-x0)/mpp),int((z1-z0)/mpp)),interpolation=cv2.INTER_AREA)
def edges(a):
    a=cv2.GaussianBlur(a,(0,0),1.5); gx=cv2.Sobel(a,cv2.CV_32F,1,0); gy=cv2.Sobel(a,cv2.CV_32F,0,1); g=np.hypot(gx,gy)
    return (g-g.mean())/(g.std()+1e-6)
def align(x0,z0,x1,z1):
    A=edges(crop_aer(x0,z0,x1,z1)); B=edges(crop_off(x0,z0,x1,z1))
    win=cv2.createHanningWindow(A.shape[::-1],cv2.CV_32F)
    (dx,dy),resp=cv2.phaseCorrelate(B.astype(np.float32),A.astype(np.float32),win)
    return dx*0.5, dy*0.5, resp
if __name__=='__main__':
    for box in [(-280,-420,-110,-320),(-600,-140,-400,80),(-100,-300,100,-100),(800,-600,1000,-400),(300,-450,500,-250)]:
        print(box, [round(v,2) for v in align(*box)])

offc=np.asarray(Image.open(R+'data/official/official_local.jpg').convert('RGB')).astype(np.int16)
def our_mask(x0,z0,x1,z1,mpp=0.5):
    from PIL import ImageDraw
    import math
    Wp,Hp=int((x1-x0)/mpp),int((z1-z0)/mpp); im=Image.new('L',(Wp,Hp),0); d=ImageDraw.Draw(im)
    P=lambda x,z:((x-x0)/mpp,(z-z0)/mpp)
    for r in c['roads']:
        if r['w']<5 or r['kind'] in ('footway','path','steps','cycleway','track'): continue
        for (ax,az),(bx,bz) in zip(r['pts'],r['pts'][1:]):
            L=math.hypot(bx-ax,bz-az) or 1; nx,nz=-(bz-az)/L*r['w']/2,(bx-ax)/L*r['w']/2
            d.polygon([P(ax+nx,az+nz),P(bx+nx,bz+nz),P(bx-nx,bz-nz),P(ax-nx,az-nz)],fill=255)
    for w in c['water']: d.polygon([P(*p) for p in w['pts']],fill=128)
    return np.asarray(im).astype(np.float32)
def off_mask(x0,z0,x1,z1,mpp=0.5):
    q=1/m['m_per_px']; a=offc[int((z0-m['z0'])*q):int((z1-m['z0'])*q), int((x0-m['x0'])*q):int((x1-m['x0'])*q)]
    R_,G,B=a[...,0],a[...,1],a[...,2]; lum=(R_+G+B)/3
    road=((np.abs(R_-G)<14)&(np.abs(G-B)<16)&(lum>45)&(lum<115)).astype(np.float32)*255
    water=((B>R_+25)&(B>G+5)&(lum<170)).astype(np.float32)*128
    mk=np.maximum(road,water)
    return cv2.resize(mk,(int((x1-x0)/mpp),int((z1-z0)/mpp)),interpolation=cv2.INTER_AREA)
def align2(x0,z0,x1,z1,s=28):
    A=cv2.GaussianBlur(our_mask(x0,z0,x1,z1),(0,0),2); B=cv2.GaussianBlur(off_mask(x0,z0,x1,z1),(0,0),2)
    A-=A.mean(); B-=B.mean()
    Ap=A[s:-s,s:-s]; na=np.linalg.norm(Ap)
    scores={}
    for dy in range(-s,s+1):
        for dx in range(-s,s+1):
            Bs=B[s+dy:B.shape[0]-s+dy, s+dx:B.shape[1]-s+dx]
            scores[(dx,dy)]=float((Ap*Bs).sum()/(na*np.linalg.norm(Bs)+1e-6))
    (dx,dy),v=max(scores.items(),key=lambda kv:kv[1])
    vals=np.array(list(scores.values())); z=(v-vals.mean())/(vals.std()+1e-6)
    return round(dx*0.5,1), round(dy*0.5,1), round(v,3), round(float(z),1)
for box in [(-280,-420,-110,-320),(-600,-140,-400,80),(-100,-300,100,-100),(800,-600,1000,-400),(300,-450,500,-250),(600,-350,800,-150)]:
    print('mask', box, align2(*box))
