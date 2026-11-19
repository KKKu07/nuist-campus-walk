import * as T from './vendor/three.module.js';
import {landscape} from './landscape-data.js';
import {mergeGeometries} from './vendor/BufferGeometryUtils.js';

export function entrancePaths(scene,doors,osm,valid,height,material){
 const ribbons=[],beds=landscape.beds,trees=[...landscape.trees,...osm.trees];
 for(const door of doors){
  const start=new T.Vector2(door.x,door.z);
  if(height(start.x,start.y)>.025)continue;
  const next=new T.Vector2(door.x+door.nx*.6,door.z+door.nz*.6),targets=[];
  for(const r of osm.roads)for(let i=1;i<r.points.length;i++){
   const [ax,az]=r.points[i-1],[bx,bz]=r.points[i],dx=bx-ax,dz=bz-az,den=dx*dx+dz*dz;
   if(!den)continue;
   const t=T.MathUtils.clamp(((next.x-ax)*dx+(next.y-az)*dz)/den,0,1);
   const target=new T.Vector2(ax+t*dx,az+t*dz);
   const offset=next.clone().sub(target),d=offset.length();
   if(d<=r.width/2+.60||d>12||target.clone().sub(start).dot(new T.Vector2(door.nx,door.nz))<.3)continue;
   target.addScaledVector(offset,(r.width/2+.60)/d);targets.push(target);
  }
  targets.sort((a,b)=>a.distanceToSquared(next)-b.distanceToSquared(next));
  for(const target of targets){
   const curve=new T.QuadraticBezierCurve(start,next,target);
   const positions=[],indices=[],steps=Math.ceil(curve.getLength()/.16);
   for(let k=0;k<=steps;k++){
    const p=curve.getPointAt(k/steps),d=curve.getTangentAt(k/steps);
    if(beds.some(([x,z])=>Math.hypot(x-p.x,z-p.y)<.9)||trees.some(([x,z])=>Math.hypot(x-p.x,z-p.y)<.42))break;
    const row=[-.31,0,.31].map(w=>[p.x+d.y*w,p.y-d.x*w]);
    if(!row.every(([x,z])=>valid(x,z)))break;
    const coords=row.map(([x,z])=>[x,.021,z]);
    positions.push(...coords[0],...coords[2]);
    if(k){const a=(k-1)*2;indices.push(a,a+2,a+1,a+1,a+2,a+3);}
   }
   if(positions.length!==6*(steps+1))continue;
   const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setIndex(indices);
   // Ribbon tangent points away from the doorway. Give both strip triangles an upward winding.
   const a=new T.Vector3().fromArray(positions,0),b=new T.Vector3().fromArray(positions,6),c=new T.Vector3().fromArray(positions,3);
   if(b.sub(a).cross(c.sub(a)).y<0){for(let i=0;i<indices.length;i+=3)[indices[i+1],indices[i+2]]=[indices[i+2],indices[i+1]];g.setIndex(indices);}
   g.computeVertexNormals();ribbons.push(g);break;
  }
 }
 if(!ribbons.length)return;
 const path=new T.Mesh(mergeGeometries(ribbons),material);path.name='宿舍门前铺装';path.receiveShadow=true;scene.add(path);ribbons.forEach(g=>g.dispose());
 return path;
}
