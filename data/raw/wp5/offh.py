# estimate building height from the official 2.5D drawing: roof outline = footprint shifted by h * A[2]
import json, math, sys, numpy as np
from PIL import Image
R='E:/Claude/三维南信大/'
A=np.array(json.load(open(R+'data/official/transform.json'))['A'])
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8'))
cache={}
def tile(tx,ty):
    if (tx,ty) not in cache:
        p=f'{R}data/official/tiles/zoom3/{tx}_{ty}.jpg'
        try:
            import os
            cache[(tx,ty)]=np.asarray(Image.open(p).convert('RGB')).astype(np.float32) if os.path.getsize(p)>3000 else None
        except Exception: cache[(tx,ty)]=None
    return cache[(tx,ty)]
def pix(px,py):
    tx,ty=int(px//256),int(py//256); im=tile(tx,ty)
    if im is None: return None
    return im[int(py-ty*256),int(px-tx*256)]
v=A[2,:2]/4.0
def score(b,h):
    pts=np.array(b['pts']); P=(np.c_[pts,np.zeros(len(pts)),np.ones(len(pts))]@A)/4.0 + h*v
    # orientation for outward normals in drawing space
    ar=0
    for i in range(len(P)): ar+=P[i,0]*P[(i+1)%len(P),1]-P[(i+1)%len(P),0]*P[i,1]
    sg=1 if ar>0 else -1
    diffs=[]
    for i in range(len(P)):
        a,bb=P[i],P[(i+1)%len(P)]; L=np.linalg.norm(bb-a)
        if L<4: continue
        d=(bb-a)/L; n=np.array([d[1],-d[0]])*sg
        for t in np.arange(2,L-2,2):
            q=a+d*t
            ci=pix(*(q-n*2.5)); co=pix(*(q+n*2.5))
            if ci is None or co is None: continue
            diffs.append(np.abs(ci-co).sum())
    return np.mean(diffs) if len(diffs)>8 else 0
def est(b,hmax=90):
    hs=np.arange(3,hmax,0.5); s=np.array([score(b,h) for h in hs])
    # smooth
    k=np.convolve(s,np.ones(3)/3,'same')
    i=int(np.argmax(k)); return float(hs[i]), float(k[i]), float(np.median(k))
if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='val':
        meas=json.load(open(R+'data/manual/measured_heights.json',encoding='utf-8'))['buildings']
        out=[]
        bs={str(b['id']):b for b in c['buildings']}
        keys=[k for k in meas if meas[k].get('cover',0)>0.5][:int(sys.argv[2]) if len(sys.argv)>2 else 40]
        for k in keys:
            b=bs.get(k)
            if not b: continue
            m=meas[k]; mh=m['h'] if isinstance(m,dict) else m
            e,sc,med=est(b)
            out.append((k,b['name'],mh,e,round(sc/max(med,1),2)))
            print(out[-1],flush=True)
        a=np.array([(o[2],o[3]) for o in out]); print('n',len(a),'median abs err',np.median(np.abs(a[:,0]-a[:,1])),'within 3m',np.mean(np.abs(a[:,0]-a[:,1])<3))
