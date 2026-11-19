import * as T from './vendor/three.module.js';
// Game wayfinding fixtures; their positions are designed, not surveyed.
export function wayfinding(scene,landmarks,valid,height){
 const iron=new T.MeshToonMaterial({color:'#304f4c'}),stone=new T.MeshToonMaterial({color:'#c4bea8'});
 for(const [index,l] of landmarks.entries()){
 const lakeside=l.id==='lake';
 const forward=new T.Vector2(lakeside?-133-l.entry.x:l.x-l.entry.x,lakeside?29-l.entry.z:l.z-l.entry.z).normalize();
 const side=new T.Vector2(-forward.y,forward.x);
 // Put the lake guide on the walking approach, clear of the view over the water.
 const offsets=lakeside?[1.10,-1.10,1.45,-1.45]:[-.6,.6,-.9,.9];
 let location=null;
 for(const ahead of (lakeside?[.35,.1,-.15]:[-.35,.5,1,1.5])){
  for(const offset of offsets){
   const x=l.entry.x+(lakeside?forward.x*ahead+side.x*offset:offset);
   const z=l.entry.z+(lakeside?forward.y*ahead+side.y*offset:ahead);
   const corners=[[-.14,-.07],[.14,-.07],[-.14,.07],[.14,.07]];
   const levels=corners.map(([dx,dz])=>height(x+dx,z+dz));
   if(valid(x,z)&&corners.every(([dx,dz])=>valid(x+dx,z+dz))&&Math.max(...levels)-Math.min(...levels)<.008){location={x,z};break;}
  }
  if(location)break;
 }
 if(!location)continue;
 const group=new T.Group();group.name='导览牌 / '+l.name;group.position.set(location.x,height(location.x,location.z),location.z);scene.add(group);
 if(lakeside){
  group.rotation.y=Math.atan2(l.entry.x-location.x,l.entry.z-location.z);
  group.scale.setScalar(.80);
 }
 function box(x,y,z,w,h,d,m){const o=new T.Mesh(new T.BoxGeometry(w,h,d),m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;group.add(o);}
 box(0,.018,0,.28,.036,.14,stone);for(const x of [-.10,.10])box(x,.22,0,.018,.42,.018,iron);box(0,.38,0,.38,.25,.035,iron);
 const canvas=document.createElement('canvas');canvas.width=768;canvas.height=480;const c=canvas.getContext('2d');c.fillStyle='#304f4c';c.fillRect(0,0,768,480);c.fillStyle='#d7cb9e';c.fillRect(34,36,7,55);c.font='22px sans-serif';c.fillText('NUIST  /  CAMPUS WALK',64,70);c.fillStyle='#fff3d7';c.font='bold 64px sans-serif';c.fillText(l.short.replace('（名称推定）',''),38,190);c.fillStyle='#b9c9b5';c.fillRect(38,235,692,2);c.font='28px sans-serif';c.fillText('校园故事 · 照片与回忆',38,305);c.font='24px sans-serif';c.fillText('走近后查看故事',38,400);c.fillStyle='#e4c77b';c.font='bold 38px sans-serif';c.fillText(String(index+1).padStart(2,'0'),655,406);
 const tex=new T.CanvasTexture(canvas);tex.colorSpace=T.SRGBColorSpace;tex.anisotropy=8;const face=new T.MeshBasicMaterial({map:tex});for(const side of [-1,1]){const plane=new T.Mesh(new T.PlaneGeometry(.36,.225),face);plane.position.set(0,.38,side*.019);plane.rotation.y=side<0?Math.PI:0;group.add(plane);}l.sign=group;
 }
}
