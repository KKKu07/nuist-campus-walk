import {mergeGeometries} from './vendor/BufferGeometryUtils.js';
import * as T from './vendor/three.module.js';
// Decorative campus furniture, not claims about surveyed real-world locations.
export function streetDetails(scene,roads,valid,height,gradient){
 const group=new T.Group();group.name='校园街道设施';scene.add(group);
 const materials=Object.fromEntries(Object.entries({iron:'#354c50',wood:'#a87950',stone:'#c7c1ab',light:'#fff2c9',green:'#4c705e'}).map(([k,color])=>[k,new T.MeshToonMaterial({color,gradientMap:gradient})]));
 const cube=new T.BoxGeometry(1,1,1),pole=new T.CylinderGeometry(1,1,1,8),placed=[];
 function piece(parent,g,x,y,z,w,h,d,material){const m=new T.Mesh(g,materials[material]);m.position.set(x,y,z);m.scale.set(w,h,d);m.castShadow=true;m.receiveShadow=true;parent.add(m);}
 function segmentDistance(x,z,a,b){const dx=b[0]-a[0],dz=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz||1)));return Math.hypot(x-a[0]-t*dx,z-a[1]-t*dz)}
 for(const road of roads){if(road.width<1.4)continue;for(let i=1;i<road.points.length;i++){const a=road.points[i-1],b=road.points[i],dx=b[0]-a[0],dz=b[1]-a[1],len=Math.hypot(dx,dz);for(let t=2;t<len-1;t+=6){const side=(placed.length%2)*2-1,x=a[0]+dx*t/len+side*dz/len*(road.width/2+.32),z=a[1]+dz*t/len-side*dx/len*(road.width/2+.32);if(!valid(x,z)||placed.some(p=>Math.hypot(x-p[0],z-p[1])<3))continue;
 if(roads.some(r=>r.points.some((p,j)=>j&&segmentDistance(x,z,r.points[j-1],p)<r.width/2+.12)))continue;
 const p=new T.Group();p.position.set(x,height(x,z),z);p.rotation.y=Math.atan2(dx,dz);group.add(p);placed.push([x,z]);
 piece(p,cube,0,.025,0,.16,.05,.16,'stone');piece(p,pole,0,.48,0,.017,.9,.017,'iron');piece(p,cube,.085,.92,0,.20,.026,.035,'iron');piece(p,cube,.16,.9,0,.12,.025,.075,'light');
 if(placed.length%3===0){for(let slat=0;slat<4;slat++)piece(p,cube,.42,.09,-.09+slat*.055,.36,.018,.035,'wood');for(const xx of [.28,.56])piece(p,cube,xx,.045,0,.018,.09,.18,'iron');for(let slat=0;slat<3;slat++)piece(p,cube,.42,.14+slat*.035,-.10,.36,.025,.018,'wood');}
 if(placed.length%5===0){piece(p,cube,-.3,.12,0,.13,.24,.13,'green');piece(p,cube,-.3,.245,0,.15,.02,.15,'iron');piece(p,cube,-.3,.19,.067,.08,.035,.005,'iron');}
 }}}
 // Merge furniture by material and local cell to retain view culling.
 group.updateMatrixWorld(true);const batches=new Map();group.traverse(o=>{if(!o.isMesh)return;const at=new T.Vector3();o.getWorldPosition(at);const key=o.material.uuid+':'+Math.floor(at.x/20)+':'+Math.floor(at.z/20);if(!batches.has(key))batches.set(key,{material:o.material,geos:[]});batches.get(key).geos.push(o.geometry.clone().applyMatrix4(o.matrixWorld));});group.clear();for(const {material,geos} of batches.values()){const mesh=new T.Mesh(mergeGeometries(geos),material);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);geos.forEach(g=>g.dispose());}
 return {group,count:placed.length};
}
