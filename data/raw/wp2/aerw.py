# measure carriageway centre offset and width on the aerial ortho along a road (asphalt = low saturation, mid-dark)
import json, sys, numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8')); W,H=c['size']
o=np.asarray(Image.open(R+'web/public/campus/ortho.jpg').convert('RGB')).astype(np.float32)
k=o.shape[1]/W
hsv=cv2.cvtColor(o.astype(np.uint8),cv2.COLOR_RGB2HSV).astype(np.float32)
sat=hsv[...,1]; val=hsv[...,2]
asph=(sat<40)&(val>55)&(val<175)
lines=(sat<45)&(val>=175)
def samp(m,x,z):
    i=int((x+W/2)*k); j=int((z+H/2)*k)
    return m[j,i] if 0<=j<m.shape[0] and 0<=i<m.shape[1] else False
def run(rid,step=5,span=22):
    r=[r for r in c['roads'] if r['id']==rid][0]; p=np.array(r['pts']); res=[]
    for i in range(len(p)-1):
        a,b=p[i],p[i+1]; L=np.linalg.norm(b-a)
        if L<1: continue
        d=(b-a)/L; n=np.array([-d[1],d[0]])
        for s in np.arange(step/2,L,step):
            q=a+d*s; ts=np.arange(-span,span+.01,0.5)
            g=np.array([samp(asph,*(q+n*t)) or samp(lines,*(q+n*t)) for t in ts])
            # smooth: close gaps <=1 m
            g2=g.copy()
            for j in range(1,len(g)-2):
                if not g[j] and g[j-1] and (g[j+1] or g[j+2]): g2[j]=True
            # runs
            runs=[];st=None
            for j,v in enumerate(g2):
                if v and st is None: st=j
                if (not v or j==len(g2)-1) and st is not None:
                    e=j if v else j-1; runs.append((st,e)); st=None
            runs=[(a_,b_) for a_,b_ in runs if (b_-a_+1)*0.5>=4]
            if not runs: continue
            best=min(runs,key=lambda ab: 0 if ts[ab[0]]<=0<=ts[ab[1]] else min(abs(ts[ab[0]]),abs(ts[ab[1]])))
            if best[0]==0 or best[1]==len(ts)-1: continue
            res.append(((ts[best[0]]+ts[best[1]])/2,(best[1]-best[0]+1)*0.5))
    if not res: return None
    a=np.array(res)
    return dict(id=rid,name=r['name'],w=r['w'],n=len(a),shift=round(float(np.median(a[:,0])),1),width=round(float(np.median(a[:,1])),1),w25=float(np.percentile(a[:,1],25)),w75=float(np.percentile(a[:,1],75)),dir=(p[-1]-p[0]).round().tolist())
if __name__=='__main__':
    for a in sys.argv[1:]: print(run(int(a)))
