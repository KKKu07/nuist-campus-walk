import {condenserGrille} from './condenser-grille.js';
import {shrubTexture} from './shrub-texture.js';
import {sportsField} from './sports-fields.js';
import {layouts} from './sports-layout.js';
import {landscape} from './landscape-data.js';
import {surfaces} from './road-surfaces.js';
import {foliageTexture} from './foliage-texture.js';
import {parts} from './building-parts.js';
import {profiles} from './building-profiles.js';
import {osm} from './osm-data.js';
import * as T from './vendor/three.module.js';
import { mergeGeometries } from './vendor/BufferGeometryUtils.js';

// Horizontal geometry is projected from the supplied OSM; elevations are partly estimated.
export function buildCampus(){
 const root=new T.Group();root.name='NUIST · 温暖的校园';
 const buckets=new Map(),edgeGeos=[],dormDoors=[],buildings=[],reserved=[],roads=[];let seed=1960,trees=0;
 const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296};
 const palette={blueRoof:'#607e91',glassDeep:'#4f828c',brick:'#b98a77',wall:'#eee4cf',white:'#fff6df',sand:'#d8c4a0',trim:'#d0bfa0',glass:'#395c70',glassShade:'#304957',glassSoft:'#557281',glassLight:'#b3d2d2',slate:'#85938e',roof:'#bb806f',roofLight:'#d3977d',grass:'#bfd09c',grassLight:'#a5bb85',grassDark:'#a9c38d',road:'#e5d1a7',paving:'#f2e3be',edge:'#827f68',water:'#91c7c5',waterLight:'#b4dddd',wood:'#aa8560',bark:'#92795b',leaf:'#548b55',leafLight:'#80a85f',leafDark:'#326b4a',flower:'#e6b6ad',gold:'#e6cf85',court:'#a3bbb0',track:'#cd9981',dark:'#6a7f78'};
 Object.assign(palette,{linenBlue:'#749ba6',linenClay:'#c78e78',linenOat:'#d4c8a6',roomPane:'#436171',hardcourt:'#518581',keyPaint:'#ba7e62',turfLight:'#62905b',turfDark:'#598853',brickBurnt:'#a56750',ceramic:'#d8dcd0',louvre:'#586866',curtain:'#c7b8a0'});palette.asphalt='#74797b';palette.curb='#c9c7b6';const mats={};for(const [k,v] of Object.entries(palette))mats[k]=new T.MeshStandardMaterial({color:v,roughness:.94,metalness:0,flatShading:['leaf','leafLight','leafDark'].includes(k)});
 mats.leafCard=new T.MeshStandardMaterial({map:foliageTexture(),alphaTest:.45,side:T.DoubleSide,roughness:1});const leafCardG=new T.PlaneGeometry(1,1);
 const boxG=new T.BoxGeometry(1,1,1),sphereG=new T.IcosahedronGeometry(1,1),leafTipG=new T.IcosahedronGeometry(1,0),smoothSphere=new T.SphereGeometry(1,16,12),cylG=new T.CylinderGeometry(1,1,1,12);
 mats.soil=new T.MeshStandardMaterial({color:'#715b45'});
 mats.condenser=new T.MeshStandardMaterial({map:condenserGrille()});
 mats.shrub=new T.MeshStandardMaterial({map:shrubTexture(),roughness:1});
 const shrubG=new T.SphereGeometry(1,10,6),tips=new T.PlaneGeometry(1,1);
 tips.rotateX(-.52);
 // Undulate the shell without a gap at the longitude seam.
 const foliage=shrubG.attributes.position;
 for(let i=0;i<foliage.count;i++){
  const x=foliage.getX(i),y=foliage.getY(i),z=foliage.getZ(i);
  const r=1+.07*Math.sin(5*x+3*y)*Math.cos(4*z-y);
  foliage.setXYZ(i,x*r,y*r,z*r);
 }
 shrubG.computeVertexNormals();
 function shrub(x,y,z,rx,ry,rz,phase,frame){
  add(shrubG,'shrub',x,y,z,rx*.86,ry*.88,rz*.86,phase,frame);
  for(let k=0;k<9;k++){
   const a=phase+k*2.399,top=k===8;
   const cx=x+(top?0:Math.cos(a)*rx*.73),cz=z+(top?0:Math.sin(a)*rz*.73);
   add(tips,'leafCard',cx,y+ry*(top?.83:k%2===0?.24:.53),cz,rx*1.77,ry*1.63,rx,a,frame);
  }
 }
 const tmp=new T.Object3D();
 function add(g,mat,x=0,y=0,z=0,sx=1,sy=1,sz=1,rot=0,parent=null,outline=false){tmp.position.set(x,y,z);tmp.scale.set(sx,sy,sz);tmp.rotation.set(0,rot,0);tmp.updateMatrix();let matrix=tmp.matrix.clone();if(parent)matrix.premultiply(parent);const geom=g.clone();geom.applyMatrix4(matrix);if(!geom.index){/* all variants normalized at flush */}let list=buckets.get(mat);if(!list)buckets.set(mat,list=[]);list.push(geom);if(outline)edgeGeos.push(new T.EdgesGeometry(geom,27));return geom;}
 const box=(x,y,z,w,h,d,mat='wall',p=null,edge=false)=>add(boxG,mat,x,y,z,w,h,d,0,p,edge);
 const ball=(x,y,z,r,mat='leaf',p=null,sx=1,sy=1,sz=1)=>add(sphereG,mat,x,y,z,r*sx,r*sy,r*sz,0,p);
 const cyl=(x,y,z,r,h,mat='trim',p=null)=>add(cylG,mat,x,y,z,r,h,r,0,p);
 function line(points,color='white',width=.16,p=null){for(let i=1;i<points.length;i++){const a=new T.Vector3(...points[i-1]),b=new T.Vector3(...points[i]),delta=b.clone().sub(a);const g=new T.CylinderGeometry(width,width,delta.length(),5);g.applyQuaternion(new T.Quaternion().setFromUnitVectors(new T.Vector3(0,1,0),delta.clone().normalize()));const mid=a.add(b).multiplyScalar(.5);add(g,color,...mid.toArray(),1,1,1,0,p);g.dispose()}}
 function patch(points,color,y=.1,depth=.1){const sh=new T.Shape();points.forEach(([x,z],i)=>i?sh.lineTo(x,-z):sh.moveTo(x,-z));sh.closePath();const g=new T.ExtrudeGeometry(sh,{depth,bevelEnabled:false,curveSegments:16});g.rotateX(-Math.PI/2);add(g,color,0,y,0);g.dispose();}
 function road(points,width=4,major=false){roads.push({points,width});for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i],dx=b[0]-a[0],dz=b[1]-a[1],len=Math.hypot(dx,dz),rot=Math.atan2(dx,dz);add(boxG,'paving',(a[0]+b[0])/2,.015,(a[1]+b[1])/2,width+1.4,.03,len+1,rot);add(boxG,'road',(a[0]+b[0])/2,.038,(a[1]+b[1])/2,width,.016,len+.3,rot);if(major){for(let t=2;t<len;t+=6)add(boxG,'white',a[0]+dx*t/len,.33,a[1]+dz*t/len,.25,.02,2.4,rot)}}}
 function footprint(x,z,w,d,margin=3){reserved.push({x,z,w:w+margin*2,d:d+margin*2})}
 function courtyard(x,z,w,d){box(x,.12,z,w,.2,d,'paving');footprint(x,z,w,d,0)}
 function roof(w,d,h,mat,p,y){const shape=new T.Shape();shape.moveTo(-w/2,0);shape.lineTo(0,h);shape.lineTo(w/2,0);shape.closePath();const g=new T.ExtrudeGeometry(shape,{depth:d,bevelEnabled:false});add(g,mat,0,y,-d/2,1,1,1,0,p,true);g.dispose();for(let xx=-w/2+1;xx<w/2;xx+=1.5){const yy=y+h*(1-Math.abs(xx)/(w/2))+.06;line([[xx,yy,-d/2],[xx,yy,d/2]],mat==='roof'?'roofLight':'trim',.055,p)}}
 function block(x,z,w,d,h,opts={}){
  const {name='校园建筑',roofType='flat',color='wall',roofColor='slate',angle=0,detail=true,landmark=false}=opts;
  const parent=new T.Matrix4().makeRotationY(angle);parent.setPosition(x,0,z);box(0,.4,0,w+1,.8,d+1,'trim',parent);box(0,h/2+.8,0,w,h,d,color,parent,true);
  box(0,h+.95,0,w+1,.35,d+1,roofColor,parent);const floors=Math.max(1,Math.round(h/2.7));
  if(detail){for(let f=0;f<floors;f++){const y=1.9+f*(h-.7)/floors;for(const side of [-1,1]){for(let xx=-w/2+1.4;xx<w/2-.7;xx+=2.3){box(xx,y,side*(d/2+.055),1.1,1.45,.1,'glass',parent);if(landmark)box(xx,y-.8,side*(d/2+.12),1.35,.12,.25,'white',parent)}for(let zz=-d/2+1.4;zz<d/2-.7;zz+=2.5)box(side*(w/2+.055),y,zz,.1,1.45,1.1,'glass',parent)}
    if(f>0)box(0,y-1,0,w+.12,.12,d+.12,'trim',parent)}
   box(0,1.8,d/2+.12,2.1,2.5,.18,'glassLight',parent);box(0,3.35,d/2+.7,3.4,.25,1.8,'white',parent);
  }
  if(roofType==='gable'){
   roof(w+1,d+1,2.3,roofColor,parent,h+1.15);
   if(name.includes('宿舍')||name.includes('晖园')){for(const side of [-1,1])box(side*(w/2-1),h/2+1,0,2.4,h+2,d+1,'white',parent);for(let f=1;f<floors;f++)for(let xx=-w/2+3;xx<w/2-2;xx+=3){box(xx,f*h/floors+.5,d/2+.6,2.1,.18,1.2,'white',parent);box(xx,f*h/floors+1,d/2+1.1,2.1,.8,.12,'trim',parent)}}
  }
  else {box(0,h+1.2,-d/2,w,.6,.35,'white',parent);box(0,h+1.2,d/2,w,.6,.35,'white',parent);box(-w/2,h+1.2,0,.35,.6,d,'white',parent);box(w/2,h+1.2,0,.35,.6,d,'white',parent);box(-w*.22,h+1.7,-d*.15,w*.2,1.4,d*.28,'wall',parent);if(w>15)box(w*.26,h+1.35,0,3,.8,2,'trim',parent);}
  buildings.push({name,x,z,w,d,h:h+4});footprint(x,z,w,d);return parent;
 }
 function tree(x,z,size=1,type=0){trees++;const h=3.8*size;cyl(x,h*.38,z,.16*size,h*.75,'bark');if(type===1){for(let i=0;i<3;i++)add(new T.ConeGeometry(1,1,8),'leafDark',x,h*.6+i*size,z,1.45*size,3*size,1.45*size)}else{for(let branch=0;branch<5;branch++){const a=branch*Math.PI*2/5,xx=x+Math.cos(a)*1.25*size,zz=z+Math.sin(a)*1.25*size;line([[x,h*.45,z],[xx,h*.86,zz]],'bark',.09*size);for(let clump=0;clump<4;clump++){const cx=xx+(rand()-.5)*1.2*size,cz=zz+(rand()-.5)*1.2*size,cy=h*(.85+rand()*.23);ball(cx,cy,cz,.40*size,type===2?'flower':'leafDark',null,1.2,.65,1);for(let face=0;face<3;face++)add(leafCardG,'leafCard',cx,cy,cz,2.2*size,1.5*size,1,face*Math.PI/3+branch*.7);}}}}
 function hedge(x,z,w,d){box(x,.65,z,w,1.2,d,'leafDark');for(let xx=x-w/2;xx<=x+w/2;xx+=2)ball(xx,1.1,z,1,'leaf',null,1,.65,Math.max(.5,d/2));footprint(x,z,w,d,0)}
 function bench(x,z,angle=0){const p=new T.Matrix4().makeRotationY(angle);p.setPosition(x,0,z);box(0,.8,0,2.7,.25,.8,'wood',p);box(0,1.5,-.35,2.7,.7,.15,'wood',p);box(-1,.4,0,.2,.8,.6,'dark',p);box(1,.4,0,.2,.8,.6,'dark',p)}
 function lamp(x,z){cyl(x,2.4,z,.1,4.8,'dark');ball(x,4.9,z,.45,'white');}
 function oval(x,z,w,d,color,y=.3){const shape=new T.Shape();shape.absellipse(0,0,w/2,d/2,0,Math.PI*2,false,0);const g=new T.ShapeGeometry(shape,64);g.rotateX(-Math.PI/2);add(g,color,x,y,z);g.dispose()}
 function track(x,z,w,d,name){footprint(x,z,w,d);oval(x,z,w+3,d+3,'paving');oval(x,z,w,d,'track',.34);oval(x,z,w-9,d-9,'grassDark',.38);for(let k=0;k<4;k++){const pts=[];for(let i=0;i<=96;i++){let a=i/96*Math.PI*2;pts.push([x+(w/2-k*.95)*Math.cos(a),.42,z+(d/2-k*.95)*Math.sin(a)])}line(pts,'white',.065)}const fw=w-15,fd=d-15;box(x,.43,z,fw,.08,fd,'grassDark');for(let a=0;a<5;a++)box(x-fw/2+fw/10+a*fw/5,.48,z,fw/10,.03,fd,'grass');line([[x-fw/2,.55,z-fd/2],[x+fw/2,.55,z-fd/2],[x+fw/2,.55,z+fd/2],[x-fw/2,.55,z+fd/2],[x-fw/2,.55,z-fd/2]],'white',.11);line([[x-fw/2,.55,z],[x+fw/2,.55,z]],'white',.09);const circle=[];for(let i=0;i<=40;i++){const a=i/40*Math.PI*2;circle.push([x+3*Math.cos(a),.55,z+3*Math.sin(a)])}line(circle,'white',.09);for(let side of [-1,1]){const zz=z+side*fd/2;line([[x-2,0,zz],[x-2,2.5,zz],[x+2,2.5,zz],[x+2,0,zz]],'white',.12)}for(let i=0;i<4;i++)box(x-w/2-3,.6+i*.5,z,2,.8,d-6,'sand');buildings.push({name,x,z,w,d,h:3});}
 function court(x,z){footprint(x,z,9,15,1);box(x,.32,z,9,.15,15,'track');box(x,.43,z,7.7,.06,13.7,'court');line([[x-3.5,.5,z-6.5],[x+3.5,.5,z-6.5],[x+3.5,.5,z+6.5],[x-3.5,.5,z+6.5],[x-3.5,.5,z-6.5]],'white',.055);line([[x-3.5,.5,z],[x+3.5,.5,z]],'white',.055);for(let side of [-1,1]){cyl(x,1.5,z+side*6,.08,3,'dark');box(x,3,z+side*5.7,1.8,1,.15,'white')}}
 function pond(x,z,w,d){const points=[];for(let i=0;i<48;i++){const a=i/48*Math.PI*2,scale=1+.12*Math.sin(3*a)+.08*Math.cos(5*a);points.push([x+w/2*Math.cos(a)*scale,z+d/2*Math.sin(a)*scale])}patch(points,'sand',.22,.12);patch(points.map(([a,b])=>[x+(a-x)*.93,z+(b-z)*.93]),'water',.37,.05);footprint(x,z,w+5,d+5);for(let i=0;i<12;i++){const xx=x+(rand()-.5)*w*.65,zz=z+(rand()-.5)*d*.65;line([[xx,.45,zz],[xx+1.7,.45,zz],[xx+2.2,.45,zz-.3]],'waterLight',.08)}}

 function shapeGeo(f,depth){const sh=new T.Shape(f.points.map(([x,z])=>new T.Vector2(x,-z)));for(const hole of f.holes||[])sh.holes.push(new T.Path(hole.map(([x,z])=>new T.Vector2(x,-z))));const g=new T.ExtrudeGeometry(sh,{depth,bevelEnabled:false});g.rotateX(-Math.PI/2);return g;}
 for(const f of osm.campus){const g=shapeGeo(f,2);add(g,'grassLight',0,-2,0);g.dispose();}
 for(const f of osm.water){const g=shapeGeo(f,.02);add(g,'water',0,-.006,0);g.dispose();}
 for(const f of osm.sports){
  const g=shapeGeo(f,.035),type=layouts[f.id][0];
  add(g,f.kind==='track'?'track':type==='soccer'?'turfDark':'court',0,-.012,0);g.dispose();
  sportsField(f,{box,add,cylG,line});
 }
 for(const [material,height] of Object.entries({paving:.03,road:.046,asphalt:.0645,curb:.0725})){
  for(const f of surfaces[material]){
   const shape=new T.Shape(f.points.map(([x,z])=>new T.Vector2(x,-z)));
   for(const ring of f.holes)shape.holes.push(new T.Path(ring.map(([x,z])=>new T.Vector2(x,-z))));
   const geometry=new T.ShapeGeometry(shape);geometry.rotateX(-Math.PI/2);
   add(geometry,material,0,height,0);geometry.dispose();
  }
 }
 // Building-specific reconstruction. Geometry dimensions remain anchored to OSM footprints.
 function inside(x,z,pts){let yes=false;for(let i=0,j=pts.length-1;i<pts.length;j=i++){const a=pts[i],b=pts[j];if((a[1]>z)!=(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])yes=!yes}return yes;}
 function hipRoof(w,d,rise,y,mat,parent,mansard=false){
  const inset=mansard?Math.min(w,d)*.15:Math.min(w,d)*.48;
  const lower=[[-w/2,y,-d/2],[w/2,y,-d/2],[w/2,y,d/2],[-w/2,y,d/2]],upper=[[-w/2+inset,y+rise,-d/2+inset],[w/2-inset,y+rise,-d/2+inset],[w/2-inset,y+rise,d/2-inset],[-w/2+inset,y+rise,d/2-inset]];
  let pos=[];for(let i=0;i<4;i++){let j=(i+1)%4;for(const p of [lower[i],upper[j],lower[j],lower[i],upper[i],upper[j]])pos.push(...p);}
  const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(pos,3));g.computeVertexNormals();add(g,mat,0,0,0,1,1,1,0,parent,true);g.dispose();box(0,y+rise,0,w-inset*2,.06,d-inset*2,mansard?'slate':mat,parent);
  for(const side of [-1,1])line([[-w/2,y,side*d/2],[w/2,y,side*d/2]],'trim',.05,parent);
  if(mansard)for(const side of [-1,1])for(let x=-w/2+1;x<w/2-.5;x+=1.6){const z=side*(d/2-inset*.4);box(x,y+rise*.4,z,.58,rise*.8,.36,'white',parent);box(x,y+rise*.4,z+side*.2,.38,rise*.5,.04,'glass',parent);}
 }
 function surface(f,height,mat,y=.25){const g=shapeGeo(f,height);add(g,mat,0,y,0,1,1,1,0,null,true);g.dispose();}
 // A shallow folded profile puts the cloth over both sides of the handrail.
 const fabric=new T.PlaneGeometry(1,1,12,5);
 const fv=fabric.attributes.position;
 for(let k=0;k<fv.count;k++){
  const u=fv.getX(k),row=Math.round((.5-fv.getY(k))*5);
  const fold=Math.cos(u*23+.65)*.013+Math.sin(u*39)*.005;
  const heights=[-.65,-.18,.015,0,-.35,-1],depths=[-.026,-.017,-.01,.015,.021,.033];
  fv.setXYZ(k,u,heights[row]*(1+.045*Math.sin(u*12)),depths[row]+fold*Math.abs(heights[row]));
 }
 fabric.computeVertexNormals();
 function facade(f,h,p,base=0){
  const pts=f.points,area=pts.reduce((n,a,i)=>{const b=pts[(i+1)%pts.length];return n+a[0]*b[1]-b[0]*a[1]},0),sign=area>0?1:-1;
  const isGlass=['ribbon','gym'].includes(p.kind),step=p.kind==='library'||p.kind==='mansard'?1.15:p.kind==='weather'?.76:p.kind==='linjiang'?.7:.85;
  const floors=Math.max(1,p.floors),fh=h/floors;
  for(let i=1;i<pts.length;i++){
   const a=pts[i-1],b=pts[i],dx=b[0]-a[0],dz=b[1]-a[1],len=Math.hypot(dx,dz);if(len<.4)continue;const nx=sign*dz/len,nz=-sign*dx/len,ang=-Math.atan2(dz,dx);
   function edgeBox(t,y,w,hh,depth,mat,offset=.035){return add(boxG,mat,a[0]+dx*t/len+nx*offset,y+base,a[1]+dz*t/len+nz*offset,w,hh,depth,ang,null,mat==='glass');}
   if(isGlass){edgeBox(len/2,h/2+.25,len-.08,h,.065,'glassDeep');for(let y=.5;y<h;y+=fh)edgeBox(len/2,y,len,.055,.09,'white',.08);}
   const columns=Math.max(1,Math.floor((len-.3)/step)),spacing=len/(columns+1);
   for(let c=1;c<=columns;c++){
    const at=c*spacing;
    const dorm=['qin','wen','eastDorm'].includes(p.kind);
    const classroom=['wende','reading','office','redOffice','slab'].includes(p.kind);
    // A glazed stair bay interrupts the repeated classroom bays on long elevations.
    const stairs=(dorm||classroom)&&columns>=7&&c===Math.ceil(columns*.5);
    if(stairs){
     const band=spacing*.94;
     edgeBox(at,h/2+.25,band,h,.085,'brickBurnt',.045);
     for(let j=0;j<floors;j++){
      const base=.25+j*fh;
      edgeBox(at,base+fh*.52,band*.67,fh*.78,.032,'glassDeep',.097);
      edgeBox(at,base+fh*.47,band*.70,.032,.065,'trim',.12);
      edgeBox(at,base+fh*.52,.017,fh*.78,.028,'white',.125);
     }
     const doorWidth=Math.min(.48,band*.72);
     edgeBox(at,.256,doorWidth+.026,.472,.045,'trim',.12);
     for(const side of [-1,1]){
      const leaf=at+side*doorWidth*.25;
      edgeBox(leaf,.257,doorWidth*.48,.448,.022,'glassShade',.149);
      edgeBox(leaf-side*doorWidth*.14,.222,.008,.076,.022,'gold',.17);
     }
     edgeBox(at,.023,doorWidth+.18,.046,.28,'sand',.18);
     edgeBox(at,.56,band*1.22,.045,.31,'slate',.19);
     if(dorm){
      const width=Math.min(.69,band*1.15),reader=at+doorWidth*.62;
      edgeBox(at,.593,width+.012,.107,.023,'slate',.353);
      dormDoors.push({name:f.name,width,nx,nz,x:a[0]+dx*at/len+nx*.366,z:a[1]+dz*at/len+nz*.366});
      edgeBox(at,.535,.22,.015,.043,'glassLight',.265);
      edgeBox(reader,.294,.041,.083,.024,'slate',.146);
      edgeBox(reader,.31,.030,.023,.005,'glassDeep',.162);
      edgeBox(reader,.281,.015,.005,.005,'leafLight',.162);
      for(const side of [-1,1]){
       const leaf=at+side*doorWidth*.25;
       edgeBox(leaf,.183,doorWidth*.46,.012,.006,'glassLight',.163);
       edgeBox(leaf,.082,doorWidth*.46,.069,.008,'slate',.164);
      }
      for(const offset of [.25,.272,.294])edgeBox(at,.047,doorWidth+.13,.002,.006,'slate',offset);
     }
     continue;
    }
    if(isGlass){edgeBox(at,h/2+.25,.035,h,.1,'glassLight',.09);continue;}
    for(let level=0;level<floors;level++){
     const y=.25+(level+.55)*fh,ww=spacing*(p.kind==='weather'?.57:.65),wh=fh*.56;
     // At 0.2 world units/metre, the former offsets made windows project half a metre.
     // Keep glazing close to the wall and reserve a small projection for the sill.
     const pane=(c*7+level*3+i)%11;
     edgeBox(at,y,ww+.035,wh+.035,.018,'trim',.012);
     const glazing=edgeBox(at,y,ww,wh,.012,'roomPane',.025);
     const tile=(c*7+level*5+i*3)%16,uv=glazing.attributes.uv;
     for(let v=0;v<uv.count;v++){
      uv.setXY(v,(tile%4+.025+.95*uv.getX(v))/4,(Math.floor(tile/4)+.025+.95*uv.getY(v))/4);
     }
     edgeBox(at,y,.012,wh,.012,'white',.037);
     edgeBox(at,y-wh*.18,ww,.012,.012,'white',.037);
     edgeBox(at,y-wh*.5-.012,ww+.045,.018,.048,'white',.028);
     if(classroom&&pane===3){
      edgeBox(at,y+wh*.26,ww*.97,wh*.43,.009,'curtain',.035);
      for(const k of [0,1,2])edgeBox(at,y+wh*(.12+k*.11),ww*.97,.008,.012,'trim',.044);
     }
     if(p.balconies&&len>Math.min(f.width,f.depth)*1.35){
      const width=spacing*.88,base=y-wh*.5-.08,top=base+.255,front=.33;
      edgeBox(at,base,width,.048,front+.045,'white',front*.5);
      edgeBox(at,top,width,.015,.019,'dark',front);
      edgeBox(at,base+.069,width,.012,.015,'dark',front);
      for(let j=0;j<=6;j++){
       const pos=at+width*(j/6-.5);
       edgeBox(pos,base+.14,.010,.225,.012,'dark',front);
      }
      for(const side of [-1,1]){
       const end=at+side*(width*.5-.005);
       edgeBox(end,top,.012,.015,front,'dark',front*.5);
       edgeBox(end,base+.069,.010,.011,front,'dark',front*.5);
       edgeBox(end,base+.14,.010,.225,.012,'dark',front*.5);
      }
      if(dorm&&level>0){
       if(pane===2||pane===6){
        edgeBox(at,base+.078,ww*.57,.089,.095,'brickBurnt',front-.061);
        for(const k of [-1,0,1])edgeBox(at+k*ww*.16,base+.14,ww*.18,.058+.012*k,.079,'leaf',front-.061);
       }else if(pane===1||pane===5||pane===8){
        const middle=at+(pane===5?-.10:.075)*width,offset=front+.004;
        const colour=pane===1?'linenBlue':pane===5?'linenOat':'linenClay';
        // PlaneGeometry faces +Z on its descending section. Reverse for opposite elevations.
        add(fabric,colour,a[0]+dx*middle/len+nx*offset,top+.01,a[1]+dz*middle/len+nz*offset,
         width*(pane===5?.42:.31),pane===5?.17:.145,-sign,ang);
       }else if(pane===4){
        const sill=y+wh*.5;
        edgeBox(at,sill,ww+.032,.035,.062,'slate',.064);
        edgeBox(at,sill-.074,ww,.13,.018,'curtain',.070);
        edgeBox(at,sill-.14,ww+.010,.010,.020,'wood',.070);
       }
      }
     }
     if(dorm&&c%2===0){
      edgeBox(at+ww*.62,y-.15,.19,.13,.10,'ceramic',.075);
      edgeBox(at+ww*.62,y-.15,.173,.109,.009,'condenser',.131);
     }
    }
    if(['library','mansard','weather','admin'].includes(p.kind))edgeBox(at-spacing*.5,h/2+.25,.065,h,.055,'white',.035);
   }
   for(let f=1;f<floors;f++)edgeBox(len/2,.25+f*fh,len,.025,.03,p.kind==='redOffice'?'roofLight':'white',.022);
   edgeBox(len/2,h+.33,len,.18,.16,'white',.07);
  }
 }
 function detailedBuilding(f){
  const p=profiles[f.id],kind=p.kind;let h=p.floors*(kind==='library'?.76:.68);
  let angle=f.angle;while(angle>Math.PI/2)angle-=Math.PI;while(angle<-Math.PI/2)angle+=Math.PI;
  let w=f.width,d=f.depth;if(w<d){[w,d]=[d,w];angle+=Math.PI/2;}
  const [x,z]=f.center,parent=new T.Matrix4().makeRotationY(angle);parent.setPosition(x,0,z);
  const b=(xx,y,zz,ww,hh,dd,mat='wall')=>box(xx,y,zz,ww,hh,dd,mat,parent);
  const local=(xx,zz)=>new T.Vector3(xx,0,zz).applyMatrix4(parent);
  // Close the gap below the raised wall datum without changing facade/roof heights.
  // Use the original polygon (including courtyard holes), never its bounding box.
  if(!['observatory','planBlock','campusTower'].includes(kind))surface(f,.28,'trim',-.03);
  if(kind==='observatory'){
   surface(f,.04,'grassDark',-.01);line(f.points.map(([x,z])=>[x,.5,z]),'white',.04);
   for(let xx=-w/2+1;xx<w/2;xx+=2.3)for(let zz=-d/2+1;zz<d/2;zz+=2.2){const v=local(xx,zz);if(!inside(v.x,v.z,f.points))continue;b(xx,.55,zz,.035,1.1,.035,'white');b(xx,.9,zz,.38,.32,.24,'white');}
   h=.9;
  }else if(kind==='campusTower'){
   // Only the circular base and small central crown can be read in plan view.
   cyl(x,.12,z,w*.54,.24,'sand');cyl(x,1.03,z,w*.30,1.85,'white');
   cyl(x,2.03,z,w*.49,.20,'roof');cyl(x,2.16,z,w*.32,.10,'trim');h=2.22;
  }else if(kind==='planBlock'){
   surface(f,h,'wall',0);surface(f,.07,p.roof,h);
   for(const side of [-1,1]){
    for(let level=0;level<p.floors;level++){
     const y=.38+level*.68;
     b(0,y,side*(d/2+.012),w*.92,.26,.020,'glassShade');
     b(0,y-.15,side*(d/2+.018),w*.95,.035,.04,'trim');
    }
    for(let xx=-w*.45;xx<=w*.45;xx+=.81)b(xx,h/2,side*(d/2+.03),.12,h,.042,'wall');
   }
   if(p.roof==='roof')hipRoof(w,d,.23,h+.06,'roof',parent);
  }else if(kind==='library'){
   surface(f,h,'wall');facade(f,h,p);const wing=w*.24;
   for(const sx of [-1,1]){const pp=parent.clone().multiply(new T.Matrix4().makeTranslation(sx*(w-wing)/2,0,0));box(0,h+.625,0,wing,.75,d,'wall',pp);hipRoof(wing+.1,d+.1,1.2,h+1.1,'blueRoof',pp,true);}
   const mid=new T.Matrix4().copy(parent);hipRoof(w*.52,d,1,h+.1,'blueRoof',mid,true);
   b(0,h+.8,0,w*.4,.12,d*.38,'glassLight');for(let xx=-w*.2;xx<=w*.2;xx+=.65)b(xx,h+.91,0,.045,.05,d*.38,'white');
   for(let xx=-w*.27;xx<=w*.27;xx+=1.1){b(xx,h*.45,d/2+.22,.2,h*.9,.3,'white');}
   b(0,1.3,d/2+.08,w*.35,2.5,.12,'glassDeep');b(0,2.65,d/2+.5,w*.44,.18,1.2,'white');
   // Glazed entrance, door handles and stair rails give the frontage human scale.
   for(let panel=-3;panel<=3;panel++){
    const xx=panel*.62;b(xx,1.28,d/2+.164,.58,1.95,.035,panel%2?'glassShade':'glass');
    b(xx,1.65,d/2+.197,.58,.026,.025,'trim');b(xx+.21,.88,d/2+.203,.018,.18,.028,'gold');
   }
   for(const xx of [-w*.255,-w*.09,w*.09,w*.255]){
    for(let j=0;j<4;j++)b(xx,.16+j*.11,d/2+1.96-j*.34,.022,.30,.022,'dark');
    line([[xx,.31,d/2+1.96],[xx,.64,d/2+.94]],'dark',.022,parent);
   }
   for(let i=0;i<8;i++)b(0,.06+i*.06,d/2+1.5-i*.12,w*.55,.12,1.6-i*.12,'sand');h+=2.5;
  }else if(kind==='linjiang'){
   surface(f,2.7,'white');facade(f,2.7,{...p,floors:4});
   // Narrow tower on the northeast end of the footprint; podium remains in its OSM outline.
   const tw=Math.min(6,w*.25),tx=w/2-tw/2-.2;h=14.3;
   b(tx,h/2+.25,0,tw,h,d*.86,'white');
   const towerPts=[[-tw/2,-d*.43],[tw/2,-d*.43],[tw/2,d*.43],[-tw/2,d*.43],[-tw/2,-d*.43]].map(([a,c])=>{const v=local(tx+a,c);return[v.x,v.z]});facade({...f,points:towerPts,width:tw,depth:d*.86},h,{...p,floors:20});
   b(tx,h-1.2,0,tw+.12,1.6,d*.9,'glassDeep');b(tx,h-.35,0,tw+.3,.35,d*.94,'white');
   // Follow the actual podium polygon, including its open courtyards.
   surface(f,.045,'slate',2.95);
   for(let xx=-w/2+1.1;xx<tx-tw/2-.9;xx+=2.35){
    for(const zz of [-d*.24,d*.24]){
     const supported=[[-.87,-.32],[.87,-.32],[-.87,.32],[.87,.32],[0,0]].every(([ox,oz])=>{
      const at=local(xx+ox,zz+oz);
      return inside(at.x,at.z,f.points)&&!(f.holes||[]).some(hole=>inside(at.x,at.z,hole));
     });
     if(!supported)continue;
     b(xx,3.065,zz,1.70,.14,.57,'trim');
     for(let j=-2;j<=2;j++)shrub(xx+j*.285,3.19,zz,.246,.15,.23,j*1.7,parent);
    }
   }
   for(let i=0;i<10;i++)b(tx, .08+i*.08,d/2+1.7-i*.15,tw*.75,.15,2-i*.15,'sand');
  }else if(kind==='gym'){
   h=4.4;surface(f,h,'glassDeep');facade(f,h,{...p,floors:4});
   const rise=2.1,sh=new T.Shape();sh.moveTo(-w/2,0);for(let i=0;i<=40;i++){const xx=-w/2+i*w/40;sh.lineTo(xx,.15+rise*Math.cos(xx/w*Math.PI));}sh.lineTo(w/2,0);sh.closePath();const g=new T.ExtrudeGeometry(sh,{depth:d+.65,bevelEnabled:false});add(g,'sand',0,h+.3,-d/2-.325,1,1,1,0,parent,true);g.dispose();
   for(let zz=-d/2;zz<=d/2;zz+=.4){let pts=[];for(let i=0;i<=30;i++){const xx=-w/2+i*w/30;pts.push([xx,h+.5+rise*Math.cos(xx/w*Math.PI),zz]);}line(pts,'white',.024,parent);}
   for(const xx of [-w/2+.6,w/2-.6])for(const zz of [-d/2,d/2])b(xx,h/2,zz,1.1,h,1.1,'slate');
   for(const side of [-1,1]){for(let xx=-w/2+1.2;xx<w/2-1;xx+=1.3){const top=h+.2+rise*Math.cos(xx/w*Math.PI);b(xx,top/2,side*(d/2+.05),.07,top,.08,'white');}for(let i=0;i<7;i++)b(0,.06+i*.07,side*(d/2+1.5-i*.14),w*.5,.14,1.6-i*.14,'sand');}
   h+=rise+1;
  }else{
   if(kind==='weather'){surface(f,2.1,'white');facade(f,2.1,{...p,floors:3});const upperHeight=h-2.1;surface(parts[f.id],upperHeight,'wall',2.35);facade({...f,...parts[f.id]},upperHeight,{...p,floors:p.floors-3},2.1);surface(parts[f.id],.12,'slate',h+.25);}else{surface(f,h,kind==='redOffice'?'brick':kind==='ribbon'?'glassDeep':kind==='qin'?'brickBurnt':kind==='wende'||kind==='eastDorm'?'ceramic':'wall');facade(f,h,{...p,width:w,depth:d});surface(f,.12,'slate',h+.25);}
   const rectangular=Math.abs(f.points.reduce((v,a,i)=>{let bb=f.points[(i+1)%f.points.length];return v+a[0]*bb[1]-bb[0]*a[1]},0))/2/(w*d)>.9;
   if(['wen','qin','eastDorm'].includes(kind)){
    hipRoof(w+.12,d+.12,Math.min(1,d*.22),h+.4,p.roof,parent);
    if(kind==='wen')for(const side of [-1,1]){b(side*(w/2-.415),h/2+.3,0,.9,h+.6,d*.97,'white');b(side*(w/2-.45),h+.85,0,.82,.07,d*.92,'roof');for(const sz of [-1,1])b(side*(w/2-.45),h+1,sz*d*.42,.08,.4,.08,'white');}
    if(kind==='qin'||kind==='eastDorm')for(let xx=-w/2+2;xx<w/2-1;xx+=3.2){b(xx,h+.7,0,.45,.6,.65,p.roof);}
    for(const side of [-1,1])for(let floor=0;floor<p.floors;floor++)b(side*(w/2+.03),.6+floor*.68,0,.06,.18,d*.35,'glassDeep');
   }else if(['mansard','clock'].includes(kind)){
    // Follow every actual wing edge; roof strips keep courtyards open.
    for(let i=1;i<f.points.length;i++){const a=f.points[i-1],bb=f.points[i],len=Math.hypot(bb[0]-a[0],bb[1]-a[1]);if(len<1)continue;const par=new T.Matrix4().makeRotationY(-Math.atan2(bb[1]-a[1],bb[0]-a[0]));par.setPosition((a[0]+bb[0])/2,0,(a[1]+bb[1])/2);hipRoof(len,.9,.65,h+.35,'blueRoof',par,true);}
    if(kind==='clock'){
     const tx=w*.38,tz=d*.3,th=8.5;b(tx,th/2,tz,1.15,th,1.15,'white');b(tx,th-1,tz,1.3,1.6,1.3,'blueRoof');const pp=parent.clone().multiply(new T.Matrix4().makeTranslation(tx,0,tz));hipRoof(1.5,1.5,2.2,th-.1,'blueRoof',pp);for(const side of [-1,1]){const circle=new T.CircleGeometry(.46,32);if(side<0)circle.rotateY(Math.PI);add(circle,'white',0,th-.9,side*.67,1,1,1,0,pp);line([[0,th-.9,side*.68],[0,th-.58,side*.68]],'dark',.024,pp);line([[0,th-.9,side*.68],[.24,th-1.03,side*.68]],'dark',.024,pp);}h=th+2.2;
    }
   }else if(kind==='ribbon'){
    for(let y=.3;y<h+.5;y+=.68){const pp={...f,points:f.points.map(([a,b])=>[x+(a-x)*1.015,z+(b-z)*1.015])};surface(pp,.08,'white',y);}
    b(0,h+.55,0,w*.45,.6,d*.35,'slate');
   }else if(kind==='pool'){
    hipRoof(w,d,.45,h+.35,'white',parent);b(0,h+.83,0,w*.8,.08,.65,'glassLight');
   }else if(kind==='weather'){
    const front=d/2,landing=.66;
    const frontWall=Math.max(...f.points.map(([px,pz])=>(px-x)*Math.sin(angle)+(pz-z)*Math.cos(angle)));
    b(0,landing-.035,frontWall+.14,3,.07,.58,'sand');
    b(0,landing+.315,frontWall+.08,2.5,.63,.09,'slate');
    for(let leaf=0;leaf<6;leaf++){
     const xx=(leaf-2.5)*.397;
     b(xx,landing+.285,frontWall+.143,.38,.53,.028,'glassShade');
     b(xx,landing+.56,frontWall+.143,.38,.085,.028,'glassSoft');
     b(xx+(leaf%2===0?.145:-.145),landing+.245,frontWall+.17,.009,.11,.02,'gold');
    }
    b(0,1.35,front+.46,3.08,.065,.89,'slate');
    b(0,1.397,front+.46,3.16,.055,.94,'white');
    for(const side of [-1,1]){
     b(side*1.38,1.0,front+.82,.056,.67,.058,'dark');
     for(let post=0;post<3;post++){
      const z=front+.69+post*.52,base=.59-post*.23;
      b(side*1.425,base+.091,z,.016,.182,.016,'slate');
     }
     line([[side*1.425,.775,front+.69],[side*1.425,.315,front+1.73]],'slate',.012,parent);
    }
    b(0,h/2+.25,d/2+.05,1.6,h,.15,'glassDeep');for(let yy=.4;yy<h;yy+=.32)b(0,yy,d/2+.16,1.1,.035,.06,'white');
    for(let j=0;j<2;j++){const y=h+.55+j*.7;let ps=[];for(let i=0;i<=56;i++){const a=i/56*Math.PI*2;ps.push([Math.cos(a)*4.1,y,Math.sin(a)*2.2]);}line(ps,'white',.055,parent);}
    for(let i=0;i<18;i++){const a=i/18*Math.PI*2;b(Math.cos(a)*4.1,h+.95,Math.sin(a)*2.2,.055,1,.055,'white');}
    for(let i=0;i<4;i++){const a=i/4*Math.PI*2;line([[Math.cos(a)*1.25,h+.3,Math.sin(a)*1.25],[Math.cos(a)*.4,h+2.5,Math.sin(a)*.4]],'white',.065,parent);}
    const obs=new T.CylinderGeometry(1.1,.45,.95,12);add(obs,'glassDeep',0,h+2.7,0,1,1,1,0,parent,true);obs.dispose();cyl(x,h+3.25,z,1.2,.16,'white');add(smoothSphere,'white',x,h+4.35,z,1.15,1.15,1.15);const ed=new T.EdgesGeometry(new T.IcosahedronGeometry(1.16,2),1);ed.translate(x,h+4.35,z);edgeGeos.push(ed);
    for(const xx of [-w*.27,w*.27]){b(xx,h+.7,0,.04,1.4,.04,'slate');}
    for(let i=0;i<9;i++)b(0,.04+i*.07,d/2+1.4-i*.12,3,.12,1.5-i*.12,'sand');h+=5.5;
   }else if(kind==='admin'){
    b(0,h/2,d/2+.04,w*.13,h,.1,'glassDeep');b(0,h+.5,-d*.18,w*.7,.85,d*.45,'white');add(cylG,'white',0,h+.65,-d*.1,.65,1.1,.65,0,parent);b(0,1.1,d/2+.4,w*.26,.12,.9,'glassLight');
   }else if(kind==='glassRound'){
    const rr=Math.min(w,d)*.27;add(new T.CylinderGeometry(rr,rr,h,24,1,false,0,Math.PI),'glassDeep',0,h/2+.3,d*.25,1,1,1,0,parent,true);
    for(let yy=.3;yy<h;yy+=.68){let ps=[];for(let j=0;j<=24;j++){let a=j/24*Math.PI;ps.push([rr*Math.sin(a),yy,d*.25+rr*Math.cos(a)]);}line(ps,'white',.04,parent);}
   }else if(kind==='theatre'){
    // Forecourt extends from the doors towards the walking approach.
    b(0,.012,d/2+2.95,2.18,.024,5.9,'paving');
    for(const side of [-1,1]){
     b(side*1.12,.017,d/2+2.95,.06,.034,5.9,'trim');
     for(const along of [1.65,3.75]){
      b(side*1.39,.068,d/2+along,.40,.136,1.36,'sand');
      for(let j=-2;j<=2;j++)shrub(side*1.39,.21,d/2+along+j*.23,.19,.14,.215,j*1.9,parent);
     }
    }
    b(0,h+.4,-d*.18,w*.65,.7,d*.5,'slate');for(let xx=-w*.4;xx<w*.4;xx+=.65)b(xx,h*.5,d/2+.06,.14,h*.8,.15,'gold');b(0,.7,d/2+.13,w*.48,1.2,.1,'glassDeep');
    b(0,1.24,d/2+.38,w*.60,.11,.78,'wood');b(0,1.30,d/2+.40,w*.61,.035,.80,'gold');
    for(let j=-3;j<=3;j++){const xx=j*w*.062;for(const side of [-1,1]){
      const leaf=xx+side*w*.015;b(leaf,.32,d/2+.21,w*.027,.55,.045,'glassShade');
      b(leaf,.665,d/2+.21,w*.027,.11,.04,'glassSoft');
      b(leaf-side*.036,.28,d/2+.247,.014,.115,.026,'gold');
     }
     b(xx,.94,d/2+.215,w*.057,.38,.04,j%2?'glass':'glassSoft');}
    for(const side of [-1,1]){b(side*w*.28,.59,d/2+.66,.055,1.18,.055,'dark');for(let j=0;j<6;j++)b(side*(w*.32+j*.19),.63,d/2+.15,.065,1.25,.12,'wood');}

   }else if(kind==='reading'||kind==='wende'){
    for(let xx=-w*.4;xx<=w*.4;xx+=1.2)b(xx,h+.7,0,.08,.1,d*.85,'white');for(const zz of [-d*.42,d*.42])b(0,h+.7,zz,w*.85,.12,.1,'white');
   }else if(kind==='shops'||kind==='containers'){
    for(let xx=-w/2+.7;xx<w/2;xx+=1.2){b(xx,.65,d/2+.04,.95,1,.08,'glassDeep');b(xx,1.3,d/2+.35,1.1,.12,.7,'roof');b(xx,1.6,d/2+.06,.9,.25,.12,'gold');}
   }else if(rectangular&&p.roof==='roof')hipRoof(w,d,.5,h+.4,p.roof,parent);
   else {for(let xx=-w*.3;xx<w*.3;xx+=2.8){const vv=local(xx,0);if(inside(vv.x,vv.z,f.points)){b(xx,h+.5,0,1,.35,.6,'trim');for(let j=-2;j<=2;j++)b(xx+j*.15,h+.69,0,.035,.025,.5,'slate');}}}
  }
  buildings.push({...f,x,z,h:h+.6,osmId:f.id,profile:p,angle,width:w,depth:d});
 }
 for(const f of osm.buildings)detailedBuilding(f);

 // Layered roadside gardens, shade trees and lakeshore planting are designed scenery.
 for(const path of landscape.paths){const g=shapeGeo(path,.018);add(g,'paving',0,.004,0);g.dispose();}
 for(const [x,z,angle,variety] of landscape.beds){
  const frame=new T.Matrix4().makeRotationY(angle);frame.setPosition(x,0,z);
  box(0,.032,0,.65,.064,1.12,'soil',frame);
  for(const side of [-1,1]){
   box(side*.313,.043,0,.035,.086,1.13,'trim',frame);
   box(0,.043,side*.547,.598,.086,.036,'trim',frame);
  }
  for(let i=0;i<7;i++){
   const xx=(i%2-.5)*.27,zz=(i/6-.5)*.87;
   shrub(xx,.155,zz,.176,.095+.021*(1+Math.sin(i*3.7+x)),.20,angle+i*1.91,frame);
   if(variety!==2)for(let j=0;j<3;j++)add(leafTipG,variety===0?'gold':variety===1?'flower':'white',xx+(rand()-.5)*.19,.245+rand()*.038,zz+(rand()-.5)*.16,.037,.020,.032,0,frame);
  }
 }
 // Curved foliage cards catch light on both their tops and hanging outer edges.
 const crownCards=[0,.28,-.25].map(tilt=>{
  const g=new T.PlaneGeometry(1,1,3,2),v=g.attributes.position;
  for(let i=0;i<v.count;i++){const x=v.getX(i),y=v.getY(i);v.setXYZ(i,x,y-.23*x*x,.12-.42*x*x-.24*y*y);}
  g.computeVertexNormals();g.rotateX(tilt);return g;
 });
 for(const [x,z,size] of landscape.trees){
  const phase=rand()*Math.PI*2,wide=.9+rand()*.32,h=size*(1.45+rand()*.35);
  const lean=(rand()-.5)*.13;
  line([[x,0,z],[x+lean*.45,h*.42,z],[x+lean,h*.73,z+.025]],'bark',.045*size);
  for(let branch=0;branch<6;branch++){
   const angle=phase+branch*2.40,dx=Math.cos(angle),dz=Math.sin(angle);
   const radius=size*(branch===5?.10:.32+rand()*.29)*wide;
   const xx=x+dx*radius,zz=z+dz*radius,yy=h+size*(branch===5?.54:rand()*.34);
   line([[x+lean*.5,h*(.43+.04*(branch%3)),z],[x+dx*radius*.52,yy-.32*size,z+dz*radius*.52],[xx,yy,zz]],'bark',.023*size);
   ball(xx,yy,zz,.32*size,'leafDark',null,1.32,.66,1.1);
   for(let spray=0;spray<4;spray++){
    const turn=angle+spray*1.91;
    add(crownCards[spray%3],'leafCard',xx+Math.cos(turn)*.15*size,yy+size*(.05+.1*(spray%2)),zz+Math.sin(turn)*.15*size,1.38*size*wide,.87*size,size,turn);
   }
  }
 }
 for(const g of crownCards)g.dispose();
 const blade=new T.BufferGeometry();
 // Two-sided folded ribbon, tapering and leaning outward near its tip.
 const half=[[-.42,0,0],[.42,0,0],[-.30,.6,.15],[.30,.6,.15],[0,1,.58]];
 const tri=[0,1,2,1,3,2,2,3,4];const coords=[];
 for(const id of [...tri,...tri.slice().reverse()])coords.push(...half[id]);
 blade.setAttribute('position',new T.Float32BufferAttribute(coords,3));blade.computeVertexNormals();
 for(const [x,z] of landscape.shore){
  if(rand()<.42)continue;
  const rocks=1+Math.floor(rand()*4);
  for(let j=0;j<rocks;j++){
   const radius=.06+rand()*.16;
   add(sphereG,j%2?'trim':'slate',x+(rand()-.5)*.72,.016,z+(rand()-.5)*.50,radius*1.32,radius*.48,radius,rand()*6.28);
  }
  for(let clump=0;clump<2+rand()*3;clump++){
   const cx=x+(rand()-.5)*.90,cz=z+(rand()-.5)*.55;
   for(let leaf=0;leaf<9;leaf++){
    const h=.10+rand()*.25;
    add(blade,leaf%3?'leaf':'leafLight',cx,.010,cz,.025+rand()*.028,h,h*.92,rand()*Math.PI*2);
   }
   if(rand()<.45){
    const h=.23+rand()*.15;
    line([[cx,.012,cz],[cx+.028,h,cz-.016]],'leaf',.005);
    add(cylG,'wood',cx+.028,h,cz-.016,.009,.055,.009);
   }
  }
 }
 blade.dispose();
 for(const [x,z,size] of osm.trees)tree(x,z,size);
 for(const [key,geos] of buckets){const normalized=geos.map(g=>g.index?g.toNonIndexed():g);for(const g of normalized){if(!['leafCard','roomPane','shrub','condenser'].includes(key))g.deleteAttribute('uv');g.deleteAttribute('normal');g.computeVertexNormals()}const merged=mergeGeometries(normalized);const mesh=new T.Mesh(merged,mats[key]);mesh.name='校园 / '+key;mesh.castShadow=!['road','grass','grassLight','paving','water','waterLight'].includes(key);mesh.receiveShadow=true;root.add(mesh);for(const g of geos)g.dispose();for(const g of normalized)g.dispose()}
 if(edgeGeos.length){const lines=new T.LineSegments(mergeGeometries(edgeGeos),new T.LineBasicMaterial({color:'#746c58',transparent:true,opacity:.25}));root.add(lines);edgeGeos.forEach(g=>g.dispose());}
 const landmarks=[];
 for(const [id,osmId,name,icon,wall,vr] of [
 ['library','862952701','图书馆','book','library','node380'],['weather','478390591','气象楼','sun','weather','node420'],['yard','862952697','风云剧场','music','yard','node380'],['gym','478388467','东苑体育馆','ball',null,'node426'],['admin','478391048','行政楼','building',null,'node424'],['clock','862959368','学科4号楼','clock',null,'node379'],['tower','plan-changwang','长望塔','tower',null,null],['research','1245445293','临江楼','building',null,'node379']]){
 const b=buildings.find(b=>b.id===osmId);if(!b)continue;landmarks.push({id,name,short:name,icon,wall,vr:b.profile.node,x:b.x,z:b.z,h:b.h,osmId,desc:b.profile.note,source:b.profile.node ? '用户鸟瞰图平面轮廓 · 官网 VR '+b.profile.node : '用户鸟瞰图平面轮廓，外立面待核对'});
 }
 const lake=osm.water.find(w=>w.id==='1114848802');if(lake){const ps=lake.points.slice(0,-1);landmarks.push({id:'lake',name:'天鹅湖（名称推定）',short:'天鹅湖',icon:'leaf',wall:'lake',vr:'node379',x:ps.reduce((n,p)=>n+p[0],0)/ps.length,z:ps.reduce((n,p)=>n+p[1],0)/ps.length,h:1,desc:'湖岸使用地图中的真实水体轮廓。地图没有标注名称，天鹅湖名称沿用原项目并根据西苑位置匹配。',source:'OSM way 1114848802；水体名称待核实。'});}
 root.userData={description:'OSM positioned, VR appearance-informed stylized campus; see individual evidence records for observation and uncertainty',attribution:osm.attribution,origin:osm.origin,unitsPerMeter:osm.unitsPerMeter,buildings:buildings.map(({id,name,x,z,height,heightSource})=>({id,name,x,z,height,heightSource}))};
 return {root,landmarks,buildings,dormDoors,stats:{buildings:buildings.length,trees,meshes:root.children.length},palette};
}
