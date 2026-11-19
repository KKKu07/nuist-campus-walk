import {Vector3} from './vendor/three.module.js';

// The static walking surfaces are sampled many times per frame, including under
// each animated shoe. Bin their upward triangles once when the campus is built.
export function walkSurfaces(){
 const cells=new Map(),size=3;
 const a=new Vector3(),b=new Vector3(),c=new Vector3();
 function add(mesh){
  mesh.updateWorldMatrix(true,false);
  const {index,attributes:{position}}=mesh.geometry;
  const vertex=(out,i)=>out.fromBufferAttribute(position,index?index.getX(i):i).applyMatrix4(mesh.matrixWorld);
  const count=index?index.count:position.count;
  for(let i=0;i<count;i+=3){
   vertex(a,i);vertex(b,i+1);vertex(c,i+2);
   const ux=b.x-a.x,uy=b.y-a.y,uz=b.z-a.z,vx=c.x-a.x,vy=c.y-a.y,vz=c.z-a.z;
   const nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;
   if(ny<=0||3*ny*ny<=nx*nx+nz*nz||Math.min(a.y,b.y,c.y)>2||Math.max(a.y,b.y,c.y)<-.1)continue;
   const tri={x:a.x,y:a.y,z:a.z,uy,vy,uX:-vz/ny,uZ:vx/ny,vX:uz/ny,vZ:-ux/ny};
   const left=Math.floor(Math.min(a.x,b.x,c.x)/size),right=Math.floor(Math.max(a.x,b.x,c.x)/size);
   const top=Math.floor(Math.min(a.z,b.z,c.z)/size),bottom=Math.floor(Math.max(a.z,b.z,c.z)/size);
   for(let col=left;col<=right;col++)for(let row=top;row<=bottom;row++){
    const key=col+','+row;
    if(!cells.has(key))cells.set(key,[]);
    cells.get(key).push(tri);
   }
  }
 }
 function height(x,z){
  const candidates=cells.get(Math.floor(x/size)+','+Math.floor(z/size));
  if(!candidates)return 0;
  let best=-Infinity;
  for(const t of candidates){
   const dx=x-t.x,dz=z-t.z,u=dx*t.uX+dz*t.uZ,v=dx*t.vX+dz*t.vZ;
   if(u< -1e-9||v< -1e-9||u+v>1+1e-9)continue;
   const y=t.y+t.uy*u+t.vy*v;
   if(y<=2&&y>=-.1&&y>best)best=y;
  }
  return best===-Infinity?0:best;
 }
 return {add,height};
}
