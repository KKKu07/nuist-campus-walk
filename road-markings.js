import * as T from './vendor/three.module.js';
import {batchRoads} from './batch-roads.js';

// Cosmetic paint and drain covers follow the same centre lines as the baked road.
export function roadMarkings(scene,roads,crossings){
 const group=new T.Group();group.name='车道标线与雨水篦';scene.add(group);
 const coating=color=>new T.MeshToonMaterial({color,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2});
 const white=coating('#e8eadc'),yellow=coating('#d7ba74'),iron=coating('#6d7370'),recess=coating('#343d40');
 function plate(x,z,y,width,length,angle,material){
  const geometry=new T.PlaneGeometry(width,length);geometry.rotateX(-Math.PI/2);
  const mesh=new T.Mesh(geometry,material);mesh.position.set(x,y,z);mesh.rotation.y=angle;group.add(mesh);
 }
 const vertices=new Map();
 for(const r of roads)for(const [i,p] of r.points.entries()){
  const key=p.map(v=>Math.round(v*20)).join(',');
  const node=vertices.get(key)||{x:p[0],z:p[1],arms:new Set()};
  for(const q of [r.points[i-1],r.points[i+1]])if(q)node.arms.add(q.map(v=>Math.round(v*20)).join(','));
  vertices.set(key,node);
 }
 const junctions=[...vertices.values()].filter(v=>v.arms.size>=3);
 for(const r of roads){
  if(r.width<1.4)continue;
  let chain=0;
  for(let j=1;j<r.points.length;j++){
   const [x,z]=r.points[j-1],[endX,endZ]=r.points[j];
   const dx=endX-x,dz=endZ-z,len=Math.hypot(dx,dz);if(!len)continue;
   const ux=dx/len,uz=dz/len,angle=Math.atan2(ux,uz),spacing=1.52;
   // Preserve dash phase through bends, splitting a stripe at the polyline vertex.
   for(let start=Math.floor(chain/spacing)*spacing;start<chain+len;start+=spacing){
    const lo=Math.max(start,chain),hi=Math.min(start+.55,chain+len);
    if(hi-lo<.012)continue;
    const at=(hi+lo)*.5-chain,px=x+ux*at,pz=z+uz*at;
    if(junctions.some(n=>Math.hypot(n.x-px,n.z-pz)<1.35)||
       crossings.some(n=>Math.hypot(n.x-px,n.z-pz)<.79))continue;
    plate(px,pz,.066,.025,hi-lo,angle,yellow);
    if(r.width>4.5){
     const lanes=Math.max(2,Math.round(r.width/1.6));
     for(let n=1;n<lanes;n++){
      const off=r.width*(n/lanes-.5);
      if(Math.abs(off)<.08)continue;
      plate(px+uz*off,pz-ux*off,.066,.025,hi-lo,angle,white);
     }
    }
   }
   chain+=len;
  }
 }
 for(const c of crossings){
  const ux=Math.sin(c.angle),uz=Math.cos(c.angle);
  const x=c.x+ux*.59+uz*(c.width*.55-.06),z=c.z+uz*.59-ux*(c.width*.55-.06);
  plate(x,z,.066,.10,.21,c.angle,iron);
  for(let j=-3;j<=3;j++)plate(x+ux*j*.025,z+uz*j*.025,.067,.076,.011,c.angle,recess);
 }
 return batchRoads(group);
}
