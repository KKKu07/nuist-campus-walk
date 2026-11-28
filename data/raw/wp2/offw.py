import json, math, sys, numpy as np
from PIL import Image
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8'))
off=np.asarray(Image.open(R+'data/official/official_local.jpg')).astype(np.int16)
m=json.load(open(R+'data/official/official_local_meta.json')); k=1/m['m_per_px']
mx=off.max(2); mn=off.min(2); mean=off.mean(2)
grey=((mx-mn)<22)&(mean>45)&(mean<185)
white=((mx-mn)<25)&(mean>=185)
H,W=grey.shape
def val(arr,x,z):
    i=int((x-m['x0'])*k); j=int((z-m['z0'])*k)
    if 0<=i<W and 0<=j<H: return arr[j,i]
    return False
def measure(r,step=4.0,span=30):
    p=np.array(r['pts']); ws=[]; offs=[]
    for i in range(len(p)-1):
        a,b=p[i],p[i+1]; L=np.linalg.norm(b-a)
        if L<1: continue
        d=(b-a)/L; n=np.array([-d[1],d[0]])
        for s in np.arange(step/2,L,step):
            q=a+d*s
            o=np.arange(-span,span+0.01,0.5)
            g=np.array([val(grey,*(q+n*t)) or val(white,*(q+n*t)) for t in o])
            gg=np.array([val(grey,*(q+n*t)) for t in o])
            # nearest grey to centre within 6 m
            cand=[j for j in range(len(o)) if gg[j] and abs(o[j])<=6]
            if not cand: continue
            j0=min(cand,key=lambda j:abs(o[j]))
            lo=j0
            gap=0
            while lo>0:
                if g[lo-1]: lo-=1; gap=0
                elif gap<2 and lo>1 and g[lo-2]: lo-=2
                else: break
            hi=j0
            while hi<len(o)-1:
                if g[hi+1]: hi+=1
                elif hi<len(o)-2 and g[hi+2]: hi+=2
                else: break
            if lo==0 or hi==len(o)-1: continue   # ran off: plaza / parking
            ws.append((hi-lo+1)*0.5); offs.append((o[lo]+o[hi])/2)
    if len(ws)<3: return None
    return float(np.median(ws)), float(np.percentile(ws,25)), float(np.percentile(ws,75)), float(np.median(offs)), len(ws)
if __name__=='__main__':
    ids=[int(a) for a in sys.argv[1:]]
    for r in c['roads']:
        if r['id'] in ids: print(r['id'], r['name'], r['w'], measure(r))
