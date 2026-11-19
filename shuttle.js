import * as T from './vendor/three.module.js';
import {shuttleLegs} from './shuttle-route.js';

function placard(text, background, width, height) {
 const canvas=document.createElement('canvas'); canvas.width=512;canvas.height=128;
 const ctx=canvas.getContext('2d');ctx.fillStyle=background;ctx.fillRect(0,0,512,128);
 ctx.fillStyle='white';ctx.font='bold 72px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,256,67,490);
 const map=new T.CanvasTexture(canvas);map.colorSpace=T.SRGBColorSpace;
 return new T.Mesh(new T.PlaneGeometry(width,height),new T.MeshBasicMaterial({map,side:T.DoubleSide}));
}
function stationBoard(stations,index,dir){
 const c=document.createElement('canvas');c.width=448;c.height=512;
 const ctx=c.getContext('2d');
 const accent=dir===1?'#a83d50':'#22697d',name=stations[index].name;
 ctx.fillStyle='#f4f0e4';ctx.fillRect(0,0,c.width,c.height);
 ctx.fillStyle=accent;ctx.fillRect(0,0,448,160);
 ctx.fillStyle='#fff';ctx.font='22px sans-serif';ctx.fillText('校园小公交   /   CAMPUS BUS',23,39);
 ctx.font='bold 65px sans-serif';ctx.fillText(name,20,124,408);
 ctx.fillStyle='#24424b';ctx.font='bold 30px sans-serif';ctx.fillText(dir===1?'红线  ·  校园环线':'蓝线  ·  校园环线',25,212);
 ctx.strokeStyle=accent;ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(47,266);ctx.lineTo(47,414);ctx.stroke();
 for(let i=0;i<3;i++){
  const y=266+i*73,stop=stations[(index+i*dir+stations.length)%stations.length];
  ctx.fillStyle=i===0?accent:'#f4f0e4';ctx.beginPath();ctx.arc(47,y,10,0,Math.PI*2);ctx.fill();ctx.stroke();
  ctx.fillStyle='#425353';ctx.font=(i===0?'bold ':'')+'31px sans-serif';ctx.fillText(stop.name,82,y+10,326);
 }
 ctx.fillStyle='#294854';ctx.fillRect(0,464,448,48);ctx.fillStyle='#fff';ctx.font='22px sans-serif';ctx.fillText('南京信息工程大学',23,496);
 const texture=new T.CanvasTexture(c);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;
 return new T.Mesh(new T.PlaneGeometry(.202,.232),new T.MeshBasicMaterial({map:texture}));
}
function busModel(){
 const body=new T.Group(), doors=[];
 const white='#f5f2e7',blue='#18a5c1',frame='#25373c',seat='#357995',steel='#9daeb3';
 const mats=new Map();
 function part(geometry,color,x,y,z,parent=body){
  if(!mats.has(color))mats.set(color,new T.MeshStandardMaterial({color,roughness:.65}));
  const mesh=new T.Mesh(geometry,mats.get(color));mesh.position.set(x,y,z);parent.add(mesh);return mesh;
 }
 function box(x,y,z,w,h,d,color,parent){return part(new T.BoxGeometry(w,h,d),color,x,y,z,parent);}
 // Vehicle coordinates are in metres, with the windscreen at positive Z.
 function cap(y,width,height,length,color){
  const shape=new T.Shape(),a=width/2,b=length/2,r=.19;
  shape.moveTo(-a+r,-b);shape.lineTo(a-r,-b);shape.quadraticCurveTo(a,-b,a,-b+r);
  shape.lineTo(a,b-r);shape.quadraticCurveTo(a,b,a-r,b);shape.lineTo(-a+r,b);
  shape.quadraticCurveTo(-a,b,-a,b-r);shape.lineTo(-a,-b+r);shape.quadraticCurveTo(-a,-b,-a+r,-b);
  const g=new T.ExtrudeGeometry(shape,{depth:height,bevelEnabled:true,bevelSize:.045,bevelThickness:.045,bevelSegments:3,curveSegments:6});g.rotateX(-Math.PI/2);
  return part(g,color,0,y,0);
 }
 cap(.43,1.98,.1,5.2,'#545e64');cap(2.38,2.04,.13,5.26,blue);
 box(0,2.362,0,1.91,.027,5.01,'#f0ead8');
 for(const z of [-1.3,.85])box(0,2.61,z,1,.19,.76,white);
 box(0,.86,2.52,1.99,.66,.14,white);box(0,.87,-2.52,1.99,.68,.14,blue);
 const glass=new T.MeshBasicMaterial({color:'#a0ddde',transparent:true,opacity:.13,depthWrite:false,side:T.DoubleSide});
 function pane(x,y,z,w,h,d,parent=body){const m=new T.Mesh(new T.BoxGeometry(w,h,d),glass);m.position.set(x,y,z);parent.add(m);}
 for(const z of [-2.52,2.52]){
  pane(0,1.78,z,1.88,1.12,.012);
  for(const side of [-1,1])box(side*.96,1.81,z,.075,1.15,.08,frame);
 }
 const frontSign=placard('⑥ 校园小公交','#176a80',1.42,.24);frontSign.position.set(0,2.23,2.535);frontSign.material.side=T.FrontSide;body.add(frontSign);
 const cabinSign=placard('校园环线','#243b42',1.42,.24);cabinSign.rotation.y=Math.PI;cabinSign.position.set(0,2.23,2.505);body.add(cabinSign);
 const plate=placard('校园 · 06','#34725b',.66,.15);plate.position.set(0,.67,2.6);body.add(plate);
 for(const x of [-.75,.75]){
  box(x,.91,2.60,.35,.19,.04,frame);box(x,.93,2.63,.22,.095,.025,'#fff3ce');
  box(x,.82,-2.60,.23,.14,.03,'#b95849');
 }
 // Right side relative to the forward-facing driver is negative X.
 for(const side of [-1,1]){
  const x=side*.99;
  const sections=side===-1?[[-2.48,.56],[1.62,2.5]]:[[-2.48,2.5]];
  for(const [a,b] of sections){
   const mid=(a+b)/2;
   box(x,.91,mid,.055,.72,b-a,blue);box(x,1.24,mid,.065,.10,b-a,white);
   pane(x,1.83,mid,.008,1.04,b-a);box(x,2.35,mid,.06,.075,b-a,frame);
   for(let z=a;z<b-.1;z+=1.04)box(x,1.82,z,.06,1.12,.055,frame);
  }
  // Painted lower body band and school identity face outwards on each side.
  box(x*1.029,.64,-.98,.008,.077,2.78,white);
  const identity=placard('南京信息工程大学','#168ba3',1.59,.18);identity.position.set(x*1.032,.99,-.86);identity.rotation.y=side*Math.PI/2;body.add(identity);
  for(const z of [-1.67,1.66]){
   const wheel=part(new T.CylinderGeometry(.39,.39,.15,24),frame,x,.39,z);wheel.rotation.z=Math.PI/2;
   const hub=part(new T.CylinderGeometry(.21,.21,.025,16),steel,side*1.075,.39,z);hub.rotation.z=Math.PI/2;
  }
 }
 for(const z of [.825,1.355]){
  const d=new T.Group();d.position.set(-1,0,z);body.add(d);doors.push(d);
  box(0,.92,0,.04,.73,.51,blue,d);pane(0,1.8,0,.014,1.08,.50,d);
  for(const off of [-.24,.24])box(0,1.52,off,.05,1.69,.037,frame,d);
 }
 for(const z of [-1.87,-1.07,-.27,.53,1.57]){
  for(const x of [-.55,.55]){
   if(x<0&&z>.1)continue;
   box(x,.72,z,.49,.29,.42,steel);box(x,.93,z,.58,.16,.52,seat);
   const back=box(x,1.23,z-.24,.56,.58,.12,seat);back.rotation.x=-.09;
   box(x,1.52,z-.25,.39,.055,.14,steel);
  }
 }
 box(.54,1.22,2.14,.82,.24,.42,frame);
 const wheel=part(new T.TorusGeometry(.21,.026,8,24),frame,.55,1.47,1.99);wheel.rotation.x=-.68;
 for(const z of [-1.96,-.65,.58,1.61])box(-.81,1.44,z,.035,1.79,.035,'#efb949');
 box(-.81,2.21,0,.043,.043,4.52,'#efb949');box(0,2.365,-.24,.14,.03,3.65,'#fff4cc');
 body.scale.setScalar(.2);
 return {body,open(value){doors[0].position.z=.825-.51*value;doors[1].position.z=1.355+.51*value;}};
}

export function campusShuttle(scene,floorHeight,valid){
 const points=[], stations=[];
 let distance=0;
 for(const leg of shuttleLegs){
  if(leg.stop)stations.push({name:leg.stop,distance});
  for(let i=1;i<leg.points.length;i++){
   const a=leg.points[i-1],b=leg.points[i],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
   if(length<.001)continue;
   points.push({x:a[0],z:a[1],dx:(b[0]-a[0])/length,dz:(b[1]-a[1])/length,distance,length});distance+=length;
  }
 }
 const wrap=n=>(n%distance+distance)%distance;
 function sample(d){
  d=wrap(d);let l=0,r=points.length-1;
  while(l<r){const mid=Math.ceil((l+r)/2);if(points[mid].distance<=d)l=mid;else r=mid-1;}
  const s=points[l],t=d-s.distance;return {x:s.x+s.dx*t,z:s.z+s.dz*t};
 }
 function pose(d,dir){
  const a=sample(d-.32*dir),b=sample(d+.32*dir),angle=Math.atan2(b.x-a.x,b.z-a.z);
  const p=sample(d);return {x:p.x-.3*Math.cos(angle),z:p.z+.3*Math.sin(angle),angle};
 }
 const stops=[];
 for(const [index,s] of stations.entries())for(const dir of [1,-1]){
  const p=pose(s.distance,dir),nx=-Math.cos(p.angle),nz=Math.sin(p.angle);
  let x,z;
  search: for(const along of [0,.4,-.4,.8,-.8,1.2,-1.2]){
   for(const offset of [.8,.65,.5,.38]){
    x=p.x+nx*offset+Math.sin(p.angle)*along;z=p.z+nz*offset+Math.cos(p.angle)*along;
    if(valid(x,z))break search;
   }
  }
  const entry=new T.Vector3(x,floorHeight(x,z),z);
  const group=new T.Group();group.position.copy(entry);group.rotation.y=p.angle;
  group.translateZ(.54);
  const metal=new T.MeshStandardMaterial({color:'#637777',roughness:.55});
  const pole=new T.Mesh(new T.CylinderGeometry(.012,.016,.27,10),metal);pole.position.y=.135;group.add(pole);
  const base=new T.Mesh(new T.BoxGeometry(.09,.022,.09),metal);base.position.y=.011;group.add(base);
  const housing=new T.Mesh(new T.BoxGeometry(.019,.244,.216),metal);housing.position.y=.387;group.add(housing);
  for(const side of [-1,1]){
   const sign=stationBoard(stations,index,dir);sign.position.set(side*.0105,.387,0);sign.rotation.y=side*Math.PI/2;group.add(sign);
  }
  scene.add(group);
  stops.push({name:s.name,index,dir,entry,short:s.name});
 }
 const fleet=[1,-1].map((dir,i)=>{
  const model=busModel();scene.add(model.body);
  const index=i?Math.floor(stations.length/2):0;
  return {dir,index,d:stations[index].distance,hold:12,door:1,...model};
 });
 let rider=null;
 function next(bus){return (bus.index+bus.dir+stations.length)%stations.length;}
 function update(bus,dt){
  if(bus.hold>0){bus.hold=Math.max(0,bus.hold-dt);bus.door=Math.min(1,bus.hold*2,(12-bus.hold)*2+.02);}
  else{
   bus.door=0;const dest=next(bus),remaining=wrap((stations[dest].distance-bus.d)*bus.dir);
   const step=Math.min(remaining,dt*Math.min(2.2,.65+remaining));
   bus.d=wrap(bus.d+step*bus.dir);
   if(remaining-step<.0001){bus.index=dest;bus.hold=12;}
  }
  const p=pose(bus.d,bus.dir);bus.body.position.set(p.x,floorHeight(p.x,p.z),p.z);bus.body.rotation.y=p.angle;bus.open(bus.door);
 }
 function stopFor(bus){return stops.find(s=>s.index===bus.index&&s.dir===bus.dir);}
 function seat(){return rider.body.localToWorld(new T.Vector3(.49,1.69,-.85));}
 for(const b of fleet)update(b,0);
 return {stops,stations,fleet,points,get rider(){return rider;},seat,
  tick(dt){for(const b of fleet)update(b,dt);},
  nextName:b=>stations[next(b)].name,stopFor,
  board(bus){if(rider||bus.hold<=.5)return false;rider=bus;return true;},
  leave(){if(!rider||rider.hold<=.5)return null;const point=stopFor(rider).entry.clone();rider=null;return point;},
  waitAt(stop){const b=fleet.find(b=>b.dir===stop.dir);b.index=stop.index;b.d=stations[b.index].distance;b.hold=11.4;update(b,0);}
 };
}
