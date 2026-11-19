import * as T from './vendor/three.module.js';
import {layouts} from './sports-layout.js';
export function sportsField(f,{box,add,cylG,line}){
 const [kind,x,z,angle,width,length]=layouts[f.id];
 const frame=new T.Matrix4().makeRotationY(angle);frame.setPosition(x,0,z);
 const ground=.032,ink='white';
 function paint(cx,cz,w,l,color=ink,y=ground){box(cx,y,cz,w,.002,l,color,frame);}
 function arc(cx,cz,r,start,end){
  const points=Array.from({length:37},(_,i)=>{const a=start+(end-start)*i/36;return [cx+r*Math.cos(a),ground+.002,cz+r*Math.sin(a)]});
  line(points,ink,.010,frame);
 }
 if(kind==='loop'){
  const outer=f.points,inner=f.holes[0];
  // Match each outside sample to the closest point on the inside boundary.
  const pairs=outer.map(([x,z])=>{let best=[x,z],distance=Infinity;for(let i=1;i<inner.length;i++){const [ax,az]=inner[i-1],[bx,bz]=inner[i],dx=bx-ax,dz=bz-az,t=Math.max(0,Math.min(1,((x-ax)*dx+(z-az)*dz)/(dx*dx+dz*dz||1))),px=ax+t*dx,pz=az+t*dz,d=Math.hypot(px-x,pz-z);if(d<distance){distance=d;best=[px,pz];}}return [x,z,...best];});
  for(let lane=0;lane<=8;lane++)line(pairs.map(([x,z,a,b])=>[x+(a-x)*lane/8,ground,z+(b-z)*lane/8]),ink,.009);
  return;
 }
 if(kind==='sprint'){for(let j=1;j<8;j++)paint(width*(j/8-.5),0,.015,length*.97);return;}
 if(!['basketball','soccer','tennis','volleyball'].includes(kind))return;
 const target={basketball:[3,5.6],soccer:[13,20],tennis:[2.2,4.75],volleyball:[1.8,3.6]}[kind];
 const cols=Math.max(1,Math.floor(width/target[0])),rows=Math.max(1,Math.floor(length/target[1]));
 const w=width/cols*.91,l=length/rows*.91;
 for(let row=0;row<rows;row++)for(let col=0;col<cols;col++){
  const cx=width*((col+.5)/cols-.5),cz=length*((row+.5)/rows-.5);
  if(kind==='basketball')paint(cx,cz,w,l,'hardcourt',.027);
  if(kind==='soccer')for(let j=0;j<10;j++)paint(cx,cz+l*((j+.5)/10-.5),w,l/10,j%2?'turfLight':'turfDark',.027);
  for(const side of [-1,1]){
   paint(cx+side*w/2,cz,.018,l);paint(cx,cz+side*l/2,w,.018);
   const end=cz+side*l/2;
   if(kind==='soccer'||kind==='basketball'){
    const zone=kind==='soccer'?w*.52:w*.33,depth=l*.17;
    if(kind==='basketball'){
     paint(cx,end-side*depth/2,zone,depth,'keyPaint',.029);
     arc(cx,end-side*.10,Math.min(w*.44,l*.21),side>0?Math.PI:0,side>0?2*Math.PI:Math.PI);
    }
    paint(cx,end-side*depth,zone,.018);for(const s of [-1,1])paint(cx+s*zone/2,end-side*depth/2,.018,depth);
    if(kind==='soccer'){
     for(const s of [-1,1])box(cx+s*.70,.265,end,.022,.47,.022,ink,frame);box(cx,.50,end,1.42,.024,.024,ink,frame);
    }else{
     const board=end-side*.10;
     box(cx,.36,end+side*.075,.036,.67,.036,'slate',frame);box(cx,.68,board,.36,.21,.023,ink,frame);
     const hoop=new T.TorusGeometry(.048,.006,5,16);hoop.rotateX(Math.PI/2);add(hoop,'roof',cx,.633,board-side*.062,1,1,1,0,frame);hoop.dispose();
     arc(cx,end-side*depth,zone/2,side>0?Math.PI:0,side>0?2*Math.PI:Math.PI);
    }
   }else{paint(cx,cz+side*l*.22,w,.013);if(side===1){const top=kind==='tennis'?.22:.49;
    for(const side of [-1,1])box(cx+side*w/2,top/2,cz,.021,top,.021,'dark',frame);
    for(let y=top-.16;y<top;y+=.04)box(cx,y,cz,w,.004,.004,'dark',frame);
    for(let x=-w/2;x<w/2;x+=.065)box(cx+x,top-.08,cz,.004,.16,.004,'dark',frame);
    box(cx,top,cz,w,.012,.012,ink,frame);}}
  }
  paint(cx,cz,w,.015);if(kind==='soccer'||kind==='basketball')arc(cx,cz,w*(kind==='soccer'?.14:.12),0,2*Math.PI);
 }
}
