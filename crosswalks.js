import * as T from './vendor/three.module.js';
import {mergeGeometries} from './vendor/BufferGeometryUtils.js';
// Designed crossing markings at connected OSM road vertices, not surveyed paint.
export function crosswalks(scene,roads,valid){
 const vertices=new Map(),geometries=[],locations=[];
 for(const road of roads){if(road.width<1.4)continue;road.points.forEach((p,i)=>{const key=p.map(v=>Math.round(v*20)).join(',');if(!vertices.has(key))vertices.set(key,[]);for(const j of [i-1,i+1])if(road.points[j]){const q=road.points[j],len=Math.hypot(q[0]-p[0],q[1]-p[1]);if(len>1)vertices.get(key).push({p,q,len,width:road.width});}});}
 for(const branches of vertices.values()){if(branches.length<3)continue;for(const branch of branches){const {p,q,len,width}=branch,ux=(q[0]-p[0])/len,uz=(q[1]-p[1])/len;
 const along=Math.max(...branches.map(b=>b.width))*.6+.45;if(len<along+1)continue;const x=p[0]+ux*along,z=p[1]+uz*along;
 if(locations.some(v=>Math.hypot(x-v.x,z-v.z)<1.5))continue;
 const roadWidth=width*.76,corners=[[-roadWidth/2,-.25],[roadWidth/2,-.25],[-roadWidth/2,.25],[roadWidth/2,.25]];if(!corners.every(([side,forward])=>valid(x+uz*side+ux*forward,z-ux*side+uz*forward)))continue;
 const n=Math.floor(roadWidth/.20),angle=Math.atan2(ux,uz);for(let stripe=0;stripe<n;stripe++){const side=(stripe-(n-1)/2)*.20;const g=new T.PlaneGeometry(.10,.50);g.rotateX(-Math.PI/2);g.rotateY(angle);g.translate(x+uz*side,.079,z-ux*side);geometries.push(g);}locations.push({x,z,angle,width:roadWidth});
 }}
 if(geometries.length){const mesh=new T.Mesh(mergeGeometries(geometries),new T.MeshToonMaterial({color:'#ede6cf',polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1}));mesh.receiveShadow=true;mesh.name='路口人行横道';scene.add(mesh);geometries.forEach(g=>g.dispose());}return locations;
}
