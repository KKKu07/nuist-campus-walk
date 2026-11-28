# side-by-side crop: aerial ortho | official map (warped), with our road centrelines
import json, sys, numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS=None
R='E:/Claude/三维南信大/'
c=json.load(open(R+'web/public/campus/campus.json',encoding='utf-8'))
W,H=c['size']
orth=Image.open(R+'web/public/campus/ortho.jpg'); sx=orth.size[0]/W
off=Image.open(R+'data/official/official_local.jpg'); m=json.load(open(R+'data/official/official_local_meta.json'))
def crop(name,x0,z0,x1,z1,lines=True):
    a=orth.crop((int((x0+W/2)*sx),int((z0+H/2)*sx),int((x1+W/2)*sx),int((z1+H/2)*sx)))
    b=off.crop((int((x0-m['x0'])/m['m_per_px']),int((z0-m['z0'])/m['m_per_px']),int((x1-m['x0'])/m['m_per_px']),int((z1-m['z0'])/m['m_per_px']))).resize(a.size)
    s=a.size[0]/(x1-x0)
    for im in (a,b):
        d=ImageDraw.Draw(im)
        if not lines: continue
        for r in c['roads']:
            p=np.array(r['pts'])
            if p[:,0].max()<x0 or p[:,0].min()>x1 or p[:,1].max()<z0 or p[:,1].min()>z1: continue
            col=(255,0,0) if r['w']>=12 else (255,220,0) if r['w']>=7 else (0,220,255)
            d.line([((x-x0)*s,(z-z0)*s) for x,z in p],fill=col,width=1)
            mm=p[len(p)//2]; d.text(((mm[0]-x0)*s,(mm[1]-z0)*s),f"{r['id']%100000}:{r['w']}",fill=col)
    out=Image.new('RGB',(a.size[0],a.size[1]*2+4),(255,255,255)); out.paste(a,(0,0)); out.paste(b,(0,a.size[1]+4))
    out.save(R+f'data/raw/wp2/{name}.jpg',quality=88); print(name,out.size)
if __name__=='__main__':
    n,x0,z0,x1,z1=sys.argv[1],*map(float,sys.argv[2:6])
    crop(n,x0,z0,x1,z1,len(sys.argv)<7)
