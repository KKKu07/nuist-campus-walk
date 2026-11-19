import {campusHud} from './campus-hud.js';
import {entrancePaths} from './entrance-paths.js';
import {dormSigns} from './dorm-signs.js';
import {cycleBays} from './cycle-bays.js';
import {campusShuttle} from './shuttle.js';
import {shuttleControls} from './shuttle-controls.js';
import {lakeReflections} from './water-reflection.js';
import {entranceSigns} from './entrance-signs.js';
import {miniMap} from './mini-map.js';
import {characterCreator} from './character-creator.js';
import {roadMarkings} from './road-markings.js';
import {crosswalks} from './crosswalks.js';
import {windMaterials} from './foliage-wind.js';
import {wayfinding} from './wayfinding.js';
import {comicPass} from './comic-pass.js';
import {walkSurfaces} from './walk-surfaces.js';
import {daylightSky} from './daylight-sky.js';
import {streetDetails} from './street-details.js';
import {outdoorMaterial,createSpatialIndex,surfaceTime} from './outdoor-style.js';
import * as T from './vendor/three.module.js';
import {buildCampus} from './model.js';
import {osm} from './osm-data.js';
const $=s=>document.querySelector(s);const {root,landmarks,buildings,dormDoors}=buildCampus();
const scene=new T.Scene();scene.background=new T.Color('#80b9e3');scene.fog=new T.Fog('#80b9e3',90,220);const walkingFog=scene.fog;const sky=daylightSky(scene);scene.add(root,new T.HemisphereLight('#f4f5ff','#718296',1.0));const sun=new T.DirectionalLight('#fff1d9',1.8);sun.position.set(-60,100,50);scene.add(sun);
sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);Object.assign(sun.shadow.camera,{left:-10,right:10,top:10,bottom:-10,near:1,far:160});sun.shadow.bias=-.00015;sun.shadow.normalBias=.008;scene.add(sun.target);
const gradient=new T.DataTexture(new Uint8Array([95,155,210,255]),4,1,T.RedFormat);gradient.needsUpdate=true;gradient.minFilter=gradient.magFilter=T.NearestFilter;
root.traverse(o=>{if(o.isMesh){const old=o.material;o.material=outdoorMaterial(old.color,gradient,/校园 \/ (brick|brickBurnt|ceramic)$/.test(o.name)?(o.name.endsWith('ceramic')?'ceramic':'brick'):o.name==='校园 / asphalt'?'asphalt':o.name==='校园 / curb'?'curb':o.name==='校园 / soil'?'soil':['校园 / paving','校园 / road'].includes(o.name)?'paving':o.name==='校园 / roomPane'?'roomPane':o.name.includes('glass')?'glass':/校园 \/ grass(?:Light|Dark)?$/.test(o.name)?'grass':o.name==='校园 / water'?'water':'paper');if(o.name.includes(' / linen'))o.material.side=T.DoubleSide;if(old.map){o.material.map=old.map;o.material.alphaTest=old.alphaTest;o.material.side=old.side;}}if(o.isMesh&&o.name==='校园 / leafCard')windMaterials(o);if(o.isLineSegments){
  const ink=o.material;
  ink.opacity=.62;ink.color.set('#303a40');ink.depthWrite=false;
  ink.onBeforeCompile=shader=>{
   shader.vertexShader=shader.vertexShader.replace('#include <logdepthbuf_vertex>',`#include <logdepthbuf_vertex>
    #ifdef USE_LOGDEPTHBUF
      vFragDepth -= clamp(gl_Position.w * .00002, .00012, .004);
    #endif`);
   shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>',`
    #ifdef USE_LOGDEPTHBUF
      diffuseColor.a *= 1.0 - smoothstep(12.0, 55.0, vFragDepth - 1.0);
    #endif
    #include <opaque_fragment>`);
  };
 }});
const renderer=new T.WebGLRenderer({canvas:$('#canvas'),antialias:true,logarithmicDepthBuffer:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.4));renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.02;renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
// Split material batches into spatial cells without duplicating triangles.
for(const mesh of [...root.children]){if(!mesh.isMesh)continue;let g=mesh.geometry.index?mesh.geometry.toNonIndexed():mesh.geometry;const position=g.getAttribute('position'),groups=new Map();for(let i=0;i<position.count;i+=3){const x=(position.getX(i)+position.getX(i+1)+position.getX(i+2))/3,z=(position.getZ(i)+position.getZ(i+1)+position.getZ(i+2))/3,key=Math.floor(x/30)+','+Math.floor(z/30);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i);}for(const ids of groups.values()){const cell=new T.BufferGeometry();for(const name of Object.keys(g.attributes)){const attr=g.attributes[name],out=new Float32Array(ids.length*3*attr.itemSize);let o=0;for(const i of ids)for(let j=0;j<3;j++)for(let k=0;k<attr.itemSize;k++)out[o++]=attr.array[(i+j)*attr.itemSize+k];cell.setAttribute(name,new T.BufferAttribute(out,attr.itemSize));}cell.computeBoundingSphere();const part=new T.Mesh(cell,mesh.material);part.name=mesh.name;part.customDepthMaterial=mesh.customDepthMaterial;if(part.name==='校园 / leafCard')cell.boundingSphere.radius+=.04;part.castShadow=mesh.castShadow;part.receiveShadow=true;root.add(part);}root.remove(mesh);g.dispose();}
const updateLake=lakeReflections(renderer,osm,root);
entranceSigns(scene,buildings);dormSigns(scene,dormDoors);
const camera=new T.PerspectiveCamera(52,innerWidth/innerHeight,.015,2000);const avatar=new T.Group();scene.add(avatar);const mat=c=>new T.MeshToonMaterial({color:c,gradientMap:gradient});const skin=mat('#e9ba93'),shirt=mat('#7795ac'),pants=mat('#596c78'),hairMaterial=mat('#302f31');function mesh(g,m,x,y,z){const o=new T.Mesh(g,m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;avatar.add(o);return o;}
// Human proportions in metres; 0.2 world units per metre.
avatar.scale.setScalar(.2);
const headGeo=new T.SphereGeometry(.115,16,12);const hp=headGeo.attributes.position;for(let i=0;i<hp.count;i++){const y=hp.getY(i),jaw=T.MathUtils.smoothstep(y,-.115,-.015);hp.setXYZ(i,hp.getX(i)*(.60+.28*jaw),y*1.16,hp.getZ(i)*(.78+.14*jaw));}headGeo.computeVertexNormals();mesh(headGeo,skin,0,1.60,0);
mesh(new T.LatheGeometry([[.145,0],[.15,.04],[.145,.14],[.17,.32],[.205,.40],[.18,.44],[.065,.48]].map(([x,y])=>new T.Vector2(x,y)),16),shirt,0,.95,0).scale.z=.62;
mesh(new T.CylinderGeometry(.055,.06,.09,8),skin,0,1.48,0);
// Hairline rises above the brows and falls behind the ears and neck.
function hairShell(long){
 const positions=[],indices=[],segments=32,rows=10;
 for(let row=0;row<=rows;row++)for(let col=0;col<=segments;col++){
  const t=row/rows,a=col*Math.PI*2/segments,front=Math.cos(a);
  const fringe=T.MathUtils.smoothstep(front,.28,.88);
  const lower=1.59+.07*fringe-.027*(1-front)*.5
   +.009*Math.sin(5*a+.6)+.004*Math.sin(11*a);
  const end=Math.acos(T.MathUtils.clamp((lower-1.622)/.126,-1,1));
  const theta=t*end;
  const spread=long?.009*t*(1-fringe):0;
  positions.push(Math.sin(a)*Math.sin(theta)*(.109+spread)-.014*(1-t),
   1.622+.126*Math.cos(theta)-(long?.096*t**3*(1-fringe):0),
   -.006+Math.cos(a)*Math.sin(theta)*(.115+spread));
  if(row&&col){const i=row*(segments+1)+col;indices.push(i-segments-2,i-1,i,i-segments-2,i,i-segments-1);}
 }
 const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setIndex(indices);g.computeVertexNormals();g.translate(0,-1.62,0);return g;
}
mesh(hairShell(false),hairMaterial,0,1.62,0).name='hair-cropped';
// Cross-sections run from the bottom hem upwards. Their depth and centre can
// vary independently so cuffs, the seat and sneaker toe have different profiles.
function clothingGeometry(rings, sides=18){
 const profile=rings.map(([y,width])=>new T.Vector2(width,y));
 const geometry=new T.LatheGeometry(profile,sides);
 const vertices=geometry.attributes.position;
 for(let i=0;i<vertices.count;i++){
  const [,width,depth,offset=0]=rings[i%rings.length];
  vertices.setZ(i,offset+vertices.getZ(i)*depth/Math.max(.00001,width));
 }
 geometry.computeVertexNormals();
 return geometry;
}
mesh(clothingGeometry([[0,0,0],[.01,.124,.079],[.055,.151,.10,-.008],[.12,.149,.10],[.166,.134,.084],[.166,0,0]]),pants,0,.825,0);
const legs=[],arms=[];
function limb(x,y,material,length,radius){
 const joint=new T.Group(),bend=new T.Group();
 joint.position.set(x,y,0);avatar.add(joint);
 const upperLength=length*.51,lowerLength=length-upperLength;
 bend.position.y=-upperLength;joint.add(bend);
 const trouser=material===pants;
 function segment(parent,len,top,bottom,isLower){
  let geometry;
  if(trouser){
   const sections=isLower?[[0,.80],[.048,.80],[.068,.77],[.28,.78],[.53,.91],[.74,.97],[.94,.85],[1.04,.79]]:[[0,.79],[.13,.83],[.47,1.01],[.78,1.12],[1.03,1.06]];
   geometry=clothingGeometry(sections.map(([t,r])=>[len*(t-1),radius*r,radius*r*(isLower?.93:1.05)]));
  }else{geometry=new T.CylinderGeometry(top,bottom,len,12);geometry.translate(0,-len/2,0);}
  const part=new T.Mesh(geometry,material);part.castShadow=part.receiveShadow=true;parent.add(part);
 }
 segment(joint,upperLength,radius,radius*.82,false);segment(bend,lowerLength,radius*.82,radius*.65,true);
 joint.userData={bend,lowerLength};return joint;
}
const shoeUpper=clothingGeometry([[-.029,.058,.116,0],[-.012,.061,.119,0],[.002,.057,.114,-.003],[.024,.05,.083,-.021],[.049,.043,.057,-.036],[.063,.041,.045,-.039],[.063,0,0,-.039]]);
const shoeSole=clothingGeometry([[-.044,0,0],[-.044,.059,.118],[-.039,.0625,.1225],[-.026,.062,.122],[-.023,.059,.119],[-.023,0,0]]);
for(const x of [-.082,.082]){
 const leg=limb(x,.90,pants,.79,.074);legs.push(leg);
 const shoe=new T.Mesh(shoeUpper,mat('#e3e6db'));shoe.castShadow=true;
 shoe.position.set(0,-leg.userData.lowerLength-.052,.035);leg.userData.bend.add(shoe);leg.userData.shoe=shoe;
 shoe.add(new T.Mesh(shoeSole,mat('#434d50')));
 for(let i=0;i<3;i++){
  const lace=new T.Mesh(new T.CapsuleGeometry(.003,.052,2,6),mat('#9aa7a4'));
  lace.rotation.z=Math.PI/2+(i%2?.12:-.12);lace.position.set(0,.049-i*.008,.008+i*.016);shoe.add(lace);
 }
}
const sleeveShape=clothingGeometry([[-.173,.057,.061],[-.161,.059,.062],[-.155,.056,.060],[-.090,.064,.072],[-.036,.070,.076],[.004,.063,.069],[.027,.041,.050],[.038,0,0]]);
const palmShape=clothingGeometry([[-.084,0,0],[-.076,.018,.024],[-.056,.022,.037],[-.033,.025,.042],[-.009,.024,.033],[.009,.022,.024],[.015,0,0]]);
for(const side of [-1,1]){
 const arm=limb(side*.185,1.388,skin,.50,.044);arms.push(arm);
 arm.rotation.z=side*.075;
 const sleeve=new T.Mesh(sleeveShape,shirt);sleeve.castShadow=true;arm.add(sleeve);
 const palm=new T.Mesh(palmShape,skin);palm.position.y=-arm.userData.lowerLength;palm.rotation.x=-.13;palm.castShadow=true;arm.userData.bend.add(palm);
 const thumb=new T.Mesh(new T.SphereGeometry(.015,10,8),skin);
 thumb.position.set(-side*.015,-.037,.031);thumb.scale.set(.8,1.65,.86);thumb.rotation.x=-.32;palm.add(thumb);
}
const bagStart=avatar.children.length;
mesh(clothingGeometry([[-.15,0,0],[-.146,.087,.041],[-.127,.121,.061],[-.06,.13,.065],[.09,.124,.062],[.14,.106,.052],[.164,.073,.04],[.177,0,0]]),mat('#87684d'),0,1.245,-.139);
mesh(clothingGeometry([[-.058,0,0],[-.05,.087,.022],[.028,.096,.026],[.056,.083,.019],[.058,0,0]]),mat('#a18460'),0,1.19,-.188);
for(const side of [-1,1]){
 const path=new T.CatmullRomCurve3([[.086,1.37,-.152],[.122,1.427,-.072],[.129,1.431,.019],[.125,1.383,.093],[.112,1.236,.090],[.122,1.143,.049],[.125,1.12,-.047],[.112,1.123,-.134]].map(([x,y,z])=>new T.Vector3(side*x,y,z)));
 mesh(new T.TubeGeometry(path,24,.011,6,false),mat('#72543e'),0,0,0);
}
for(const part of avatar.children.slice(bagStart))part.name='outfit-bag';
for(const x of [-.045,.045]){const brow=mesh(new T.BoxGeometry(.035,.008,.009),mat('#3b352f'),x,1.635,.10);brow.rotation.z=x<0?-.08:.08;}
for(const x of [-.045,.045])mesh(new T.SphereGeometry(.012,8,6),mat('#252d32'),x,1.61,.102);
for(const x of [-.104,.104])mesh(new T.SphereGeometry(.024,8,6),skin,x,1.60,0);
mesh(new T.SphereGeometry(.018,8,6),skin,0,1.58,.108);
mesh(new T.BoxGeometry(.036,.008,.012),mat('#975d4d'),0,1.54,.10);
mesh(new T.BoxGeometry(.055,.06,.015),mat('#e6e4ce'),.07,1.29,.123);
for(const x of [-.055,.055]){const collar=mesh(new T.BoxGeometry(.085,.055,.02),mat('#d9e0d4'),x,1.42,.095);collar.rotation.z=x<0?-.4:.4;}
// Flattened locks sweep across the forehead and taper towards their tips.
for(const [x,y,roll,len] of [[-.075,1.672,-.56,.049],[-.047,1.678,-.73,.058],[-.006,1.683,-.82,.051],[.040,1.689,-.91,.038]]){
 const lock=mesh(clothingGeometry([[-len,0,0],[-len*.55,.012,.009],[0,.021,.015],[.023,.014,.011],[.035,0,0]],12),hairMaterial,x,y,.080-Math.abs(x)*.30);
 lock.rotation.z=roll;
}
const bob=mesh(hairShell(true),hairMaterial,0,1.62,-.001);bob.name='hair-bob';bob.visible=false;
const pony=mesh(clothingGeometry([[-.20,0,0,-.03],[-.17,.025,.025,-.041],[-.11,.044,.039,-.043],[-.05,.052,.042,-.034],[.015,.035,.032,-.012],[.055,.022,.019],[.068,0,0]]),hairMaterial,0,1.59,-.105);
pony.name='hair-pony';pony.visible=false;
const outlineMaterial=new T.MeshBasicMaterial({color:'#343c38',side:T.BackSide});const outlined=[];avatar.traverse(o=>{if(o.isMesh)outlined.push(o)});for(const part of outlined){const edge=new T.Mesh(part.geometry,outlineMaterial);edge.scale.setScalar(1.045);part.add(edge);}
const shadow=new T.Mesh(new T.CircleGeometry(.11,24),new T.MeshBasicMaterial({color:'#485242',transparent:true,opacity:.2,depthWrite:false}));shadow.rotation.x=-Math.PI/2;scene.add(shadow);
const ground=new T.Mesh(new T.PlaneGeometry(650,450),outdoorMaterial(new T.Color('#93ad79'),gradient,'grass'));ground.rotation.x=-Math.PI/2;ground.position.y=-.02;ground.receiveShadow=true;scene.add(ground);
// Bare ground uses the walking datum at zero. Index the paving, turf and steps above it.
const floors=walkSurfaces(),floorHeight=floors.height;
scene.updateMatrixWorld(true);
for(const mesh of root.children)if(mesh.isMesh&&/ \/ (sand|paving|road|asphalt|curb|grass|grassLight|grassDark|turfLight|turfDark|court|track)$/.test(mesh.name))floors.add(mesh);
let save;try{save=JSON.parse(localStorage.getItem('nuist-game-v1')||'{}')}catch{save={}}save.visited||=[];save.photos||=[];save.read||=[];const persist=()=>{
 try{localStorage.setItem('nuist-game-v1',JSON.stringify(save));}
 catch{/* Browsers may restrict local storage for files. Keep progress in memory. */}
};
function inside(x,z,p){let v=false;for(let i=0,j=p.length-1;i<p.length;j=i++){let a=p[i],b=p[j];if((a[1]>z)!=(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])v=!v}return v;}
function dist(x,z,a,b){let dx=b[0]-a[0],dz=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz||1)));return Math.hypot(x-a[0]-t*dx,z-a[1]-t*dz)}
const waterBodies=new Set(osm.water);
const nearbyDecks=createSpatialIndex(osm.bridges);
const blockers=[...osm.buildings.filter(b=>b.id!=='1114843846'),...osm.water];const nearbyBlockers=createSpatialIndex(blockers);function valid(x,z){if(Math.abs(x)>320||Math.abs(z)>220)return false;return !nearbyBlockers(x,z).some(p=>{if(waterBodies.has(p)&&nearbyDecks(x,z).some(deck=>inside(x,z,deck.points)))return false;const holes=p.holes||[];if(holes.some(h=>inside(x,z,h)&&!h.some((a,i)=>dist(x,z,h[(i+h.length-1)%h.length],a)<.055)))return false;return inside(x,z,p.points)||p.points.some((a,i)=>dist(x,z,p.points[(i+p.points.length-1)%p.points.length],a)<.055);});}
const crossings=crosswalks(scene,osm.roads,valid);
const roadBatchStats=roadMarkings(scene,osm.roads,crossings);
const dormPaths=entrancePaths(scene,dormDoors,osm,valid,floorHeight,outdoorMaterial(new T.Color('#d8c9aa'),gradient,'paving'));
if(dormPaths)floors.add(dormPaths);
cycleBays(scene,floorHeight,gradient);
const streetFurniture=streetDetails(scene,osm.roads,valid,floorHeight,gradient);
function spawn(lm){
 if(lm.id==='lake'){
  // East shore at a wide bend of the mapped lake, on the landscaped footpath.
  for(const x of [-122.45,-122.25,-122.05])if(valid(x,26)){
   avatar.position.set(x,floorHeight(x,26),26);return;
  }
 }
 const building=buildings.find(b=>b.id===lm.osmId);if(lm.id==='yard'&&building){
 const nx=Math.sin(building.angle),nz=Math.cos(building.angle);
 const front=building.depth/2+.85;
 for(const back of [4,3.4,2.8,2.2])for(const offset of [0,-1,1,-2,2]){
  const x=building.x+nx*(front+back)+nz*offset,z=building.z+nz*(front+back)-nx*offset;
  if(valid(x,z)&&[.25,.5,.75].every(t=>valid(x-nx*back*t,z-nz*back*t))){
   avatar.position.set(x,floorHeight(x,z)-.004,z);return;
  }
 }
}const candidates=[];for(const road of osm.roads){for(let i=1;i<road.points.length;i++){const a=road.points[i-1],b=road.points[i],len=Math.hypot(b[0]-a[0],b[1]-a[1]);for(let t=0;t<=len;t+=.7){const x=a[0]+(b[0]-a[0])*t/(len||1),z=a[1]+(b[1]-a[1])*t/(len||1),distance=Math.hypot(x-lm.x,z-lm.z);if(distance>35||!valid(x,z))continue;const clearance=nearbyBlockers(x,z).reduce((best,p)=>Math.min(best,...p.points.map((v,j)=>dist(x,z,p.points[(j+p.points.length-1)%p.points.length],v))),100);if(clearance<.8)continue;const front=building?((x-lm.x)*Math.sin(building.angle)+(z-lm.z)*Math.cos(building.angle))/(distance||1):1;const treePenalty=osm.trees.some(([tx,tz])=>Math.hypot(tx-x,tz-z)<.8)?20:0;candidates.push({x,z,score:distance+Math.max(0,(lm.id==='yard'?4.8:2.4)-clearance)*7+(1-front)*20+treePenalty});}}}candidates.sort((a,b)=>a.score-b.score);if(candidates.length){const {x,z}=candidates[0];avatar.position.set(x,floorHeight(x,z)-.004,z);return;}for(let r=3;r<35;r+=.5)for(let a=0;a<Math.PI*2;a+=.15){const x=lm.x+Math.sin(a)*r,z=lm.z+Math.cos(a)*r;if(valid(x,z)&&!nearbyBlockers(x,z).some(p=>p.points.some((v,i)=>i&&dist(x,z,p.points[i-1],v)<2))){avatar.position.set(x,floorHeight(x,z)-.004,z);return}}}
spawn(landmarks.find(l=>l.id==='library'));let firstPerson=false,mapZoom=1;
const mapBounds=new T.Box2();
for(const area of osm.campus)for(const [x,z] of area.points)mapBounds.expandByPoint(new T.Vector2(x,z));
const atlasSize=mapBounds.getSize(new T.Vector2()),atlasMid=mapBounds.getCenter(new T.Vector2());
const mapCenter=new T.Vector3(atlasMid.x,0,atlasMid.y);
const mapBackground=new T.Color('#e6ece5'),walkBackground=scene.background;
let atlasHeight=310,modeChanged=false;
let yaw=0,pitch=.15,overview=false,started=false,near=null,keys={},stick={x:0,y:0},drag=null;
const mapPinPoint = new T.Vector3();
const target=new T.Vector3(),desired=new T.Vector3(),ray=new T.Raycaster();const collisionMeshes=buildings.filter(b=>b.profile.kind!=='observatory').map(b=>{const sh=new T.Shape(b.points.map(([x,z])=>new T.Vector2(x,-z)));for(const hole of b.holes||[])sh.holes.push(new T.Path(hole.map(([x,z])=>new T.Vector2(x,-z))));const g=new T.ExtrudeGeometry(sh,{depth:b.h,bevelEnabled:false});g.rotateX(-Math.PI/2);g.computeBoundingSphere();const m=new T.Mesh(g,new T.MeshBasicMaterial());m.updateMatrixWorld();return m;});const comic=comicPass(renderer,camera);const samples=[];let frameCount=0;function resize(){renderer.setSize(innerWidth,innerHeight);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();comic.resize();if(overview)fitAtlas()}addEventListener('resize',resize);resize();
const playable=landmarks.filter(l=>!l.pending);for(const l of playable){const marker=new T.Mesh(new T.OctahedronGeometry(.3),mat('#e8bc64'));spawn(l);marker.position.copy(avatar.position).add(new T.Vector3(0,1.7,0));l.entry=avatar.position.clone();l.marker=marker;scene.add(marker);}spawn(playable.find(l=>l.id==='library'));faceLandmark(playable.find(l=>l.id==='library'));wayfinding(scene,playable,valid,floorHeight);
const wardrobe=characterCreator({avatar,skin,shirt,pants,hairMaterial,onEnter:()=>{started=true;keys={};stick={x:0,y:0};}});
const outfitButton=document.createElement('button');outfitButton.id='wardrobeButton';outfitButton.textContent='人物装扮';outfitButton.onclick=()=>{started=false;keys={};stick={x:0,y:0};wardrobe.open();};document.querySelector('nav').append(outfitButton);
const introductions={
 library:'图书馆是校园阅读、自习与查阅资料的地方。浅色立面、成组窗列与蓝灰色坡屋顶构成了这里鲜明的轮廓。沿入口台阶走近，开启今天的校园漫游。',
 weather:'气象楼以高耸的主体、中央玻璃带和屋顶观测设施形成独特的校园地标。抬头可以看到屋顶的环形构架与球形罩体。',
 yard:'风云剧场是校园文化活动的空间。宽阔的入口、浅色墙面与竖向装饰构成了它的主要外观。可以停下脚步看看建筑，或在附近留影。',
 gym:'东苑体育馆是一座大跨度体育建筑。弧形屋顶、端部玻璃幕墙和入口台阶让它与周边教学楼形成鲜明区别。',
 admin:'行政楼的浅色立面排列着整齐的窗列，中央玻璃带突出入口轴线。上部的退台与屋顶构件组成了简洁的轮廓。',
 clock:'学科4号楼在图书馆西南侧，沿万象路可以走到它的南侧。楼体折转成翼，北面隔着支路是学科3号楼。',
 tower:'长望塔位于启明楼西南侧的小园内。从环形场地向东，可以走到北辰楼和长望楼。',
 research:'临江楼位于万象路以南、滨江楼以东。低层裙房与较高的窄塔共同组成建筑轮廓，竖向窗列强化了塔楼的高度感。',
 lake:'这片湖面位于校园西苑一带，沿岸可欣赏水面与树影。项目暂沿用“天鹅湖”的称呼，具体名称尚待核实。'
};
function interact(){if(!started||overview||!near)return;save.visited=[...new Set([...save.visited,near.id])];save.read=[...new Set([...save.read,near.id])];persist();hud.updateProgress();$('#storyName').textContent=near.name;$('#storyText').textContent=introductions[near.id]||near.desc;$('#story').showModal();}
$('#interact').onclick=interact;$('#closeStory').onclick=()=>$('#story').close();
function photo(){if(!started)return;comic.render(scene);const a=document.createElement('a');a.download='我的校园留影.png';a.href=renderer.domElement.toDataURL('image/png');a.click();if(near&&!overview){save.photos=[...new Set([...save.photos,near.id])];persist();hud.updateProgress();}hud.toast('留影已保存')}$('#photo').onclick=photo;
function faceLandmark(l){yaw=Math.atan2(avatar.position.x-l.x,avatar.position.z-l.z);pitch=l.id==='lake'?.15:-.12;if(l.id==='lake')yaw=Math.atan2(avatar.position.x+133,avatar.position.z-29);avatar.rotation.y=yaw+Math.PI;}
// North is always up. Reserve the actual destination panel area so the map
// midpoint remains visible on both a wide screen and a portrait phone.
function fitAtlas(){
  if(!overview)return;
  const panel=$('#destinations').getBoundingClientRect();
  const right=innerWidth<=600?innerWidth:panel.left;
  const bottom=innerWidth<=600?panel.top:innerHeight;
  const margin=Math.min(28,right*.05),top=innerWidth<=600?86:35;
  const width=Math.max(100,right-margin*2),height=Math.max(100,bottom-top-22);
  const scale=Math.max(atlasSize.x/width,atlasSize.y/height);
  atlasHeight=scale*innerHeight*.53/Math.tan(camera.fov*Math.PI/360);
  camera.setViewOffset(innerWidth,innerHeight,(innerWidth-right)/2,(innerHeight-bottom-top+22)/2,innerWidth,innerHeight);
}
new ResizeObserver(fitAtlas).observe($('#destinations'));
function changeMap(open) {
  if (!started || overview === open) return;
  overview = open;
  modeChanged=true;
  camera.far=open?6500:2000;
  ground.visible=sky.visible=!open;
  scene.background=open?mapBackground:walkBackground;
  keys = {};
  stick = {x:0, y:0};
  if (open) mapTools.querySelector('span').textContent = shuttle.rider ? '乘车中' : '点空地传送';
  hud.mapOpened(open);
  if(open)fitAtlas();else camera.clearViewOffset();
}
const hud = campusHud({
  places:playable, save,
  distance:place => Math.hypot(place.entry.x-avatar.position.x, place.entry.z-avatar.position.z) / osm.unitsPerMeter,
  changeMap,
  focusPlace:place => { mapCenter.set(place.entry.x,0,place.entry.z); mapZoom=.21; },
  jump:place => { avatar.position.copy(place.entry); faceLandmark(place); },
  riding:() => Boolean(shuttle.rider), read:interact, photo
});
$('#map').onclick=()=>changeMap(!overview);
addEventListener('keydown', e => {
  if (!started || document.querySelector('dialog[open]') || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (overview && e.code === 'Escape') { e.preventDefault(); changeMap(false); return; }
  if (e.target.matches('input, textarea, select, [contenteditable=true]')) return;
  if (e.code === 'KeyM' && !e.repeat) { changeMap(!overview); return; }
  if (overview) return;
  keys[e.code] = true;
  if (['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.code)) e.preventDefault();
  if (e.repeat) return;
  if (e.code === 'KeyC' && !shuttle.rider) toggleView();
  if (e.code === 'KeyF' && !$('#shuttleAction').hidden) $('#shuttleAction').click();
  if (e.code === 'KeyE' && !shuttle.rider) interact();
  if (e.code === 'KeyP') photo();
});
addEventListener('keyup',e=>keys[e.code]=false);
addEventListener('blur',()=>{keys={};stick={x:0,y:0}});
const viewButton=document.createElement('button');viewButton.id='viewMode';viewButton.dataset.key='C';viewButton.textContent='切换第一人称';document.querySelector('nav').prepend(viewButton);
function toggleView(){firstPerson=!firstPerson;viewButton.textContent=firstPerson?'切换第三人称':'切换第一人称';}viewButton.onclick=toggleView;
const shuttle=campusShuttle(scene,floorHeight,valid);
let priorView=false,busHeading=0;
const refreshShuttle=shuttleControls(shuttle,avatar,stop=>{
 avatar.position.copy(stop.entry);
 const opposite=shuttle.stops.find(s=>s.index===stop.index&&s.dir!==stop.dir);
 yaw=Math.atan2(stop.entry.x-opposite.entry.x,stop.entry.z-opposite.entry.z);
 pitch=.04;avatar.rotation.y=yaw+Math.PI;
},bus=>{
 priorView=firstPerson;if(!firstPerson)toggleView();busHeading=bus.body.rotation.y;yaw=busHeading+Math.PI;pitch=.06;
},point=>{avatar.position.copy(point);if(firstPerson!==priorView)toggleView();});
const mapTools=document.createElement('div');mapTools.id='mapTools';mapTools.hidden=true;mapTools.title='点击道路或空地传送';mapTools.innerHTML='<span>点空地传送</span><button id="zoomIn" aria-label="放大鸟瞰">＋</button><button id="zoomOut" aria-label="缩小鸟瞰">−</button><button id="locateMe">我的位置</button><button id="resetMap">全校</button>';document.body.append(mapTools);
$('#locateMe').onclick=()=>{mapCenter.set(avatar.position.x,0,avatar.position.z);mapZoom=.13;};
function zoomMap(f){mapZoom=T.MathUtils.clamp(mapZoom*f,.025,2);}$('#zoomIn').onclick=()=>zoomMap(.72);$('#zoomOut').onclick=()=>zoomMap(1/.72);$('#resetMap').onclick=()=>{mapZoom=1;mapCenter.set(atlasMid.x,0,atlasMid.y)};
const canvas=$('#canvas'),pointers=new Map();canvas.style.touchAction='none';let pinchDistance=0;
canvas.onpointerdown=e=>{pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});canvas.setPointerCapture(e.pointerId);
 if(pointers.size===2){const [first,second]=pointers.values();pinchDistance=Math.hypot(first.x-second.x,first.y-second.y);}
 else pinchDistance=0;};
canvas.onpointermove=e=>{const old=pointers.get(e.pointerId);if(!old)return;const dx=e.clientX-old.x,dy=e.clientY-old.y;pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});if(overview&&pointers.size===2){const [a,b]=[...pointers.values()],d=Math.hypot(a.x-b.x,a.y-b.y);if(pinchDistance>0)zoomMap(pinchDistance/d);pinchDistance=d;return;}if(overview){const groundPoint=(x,y)=>{
 const cast=new T.Raycaster();cast.setFromCamera(new T.Vector2(x/innerWidth*2-1,1-y/innerHeight*2),camera);
 return cast.ray.intersectPlane(new T.Plane(new T.Vector3(0,1,0),0),new T.Vector3());
};const prior=groundPoint(old.x,old.y),current=groundPoint(e.clientX,e.clientY);
if(prior&&current)mapCenter.add(prior.sub(current));}else{yaw-=dx*.006;pitch=T.MathUtils.clamp(pitch+dy*.004,-1.35,1.35);}};
canvas.onpointerup=canvas.onpointercancel=e=>{pointers.delete(e.pointerId);pinchDistance=0;};canvas.addEventListener('wheel',e=>{if(overview){e.preventDefault();zoomMap(Math.exp(e.deltaY*.001));}},{passive:false});
const updateMini=miniMap(osm,playable,()=>$('#map').click(),shuttle);$('#contextActions').append($('#shuttleAction'));
let tap=null;
canvas.addEventListener('pointerdown',e=>{tap=overview&&pointers.size===1?{x:e.clientX,y:e.clientY,id:e.pointerId}:null;});
canvas.addEventListener('pointermove',e=>{if(tap&&Math.hypot(e.clientX-tap.x,e.clientY-tap.y)>5)tap=null;});
canvas.addEventListener('pointercancel',()=>tap=null);
canvas.addEventListener('pointerup',e=>{
 if(shuttle.rider||!overview||!tap||tap.id!==e.pointerId)return;tap=null;
 const cast=new T.Raycaster();cast.setFromCamera(new T.Vector2(e.clientX/innerWidth*2-1,1-e.clientY/innerHeight*2),camera);
 const pos=cast.ray.intersectPlane(new T.Plane(new T.Vector3(0,1,0),0),new T.Vector3());
 if(!pos||!valid(pos.x,pos.z)||cast.intersectObjects(collisionMeshes).length){hud.toast('请选择道路或空地');return;}
 avatar.position.set(pos.x,floorHeight(pos.x,pos.z),pos.z);$('#map').click();
});
const joy=$('#joystick');let jid=null;function joyMove(e){if(e.pointerId!==jid)return;const r=joy.getBoundingClientRect();let x=(e.clientX-r.left-r.width/2)/40,y=(e.clientY-r.top-r.height/2)/40;const d=Math.max(1,Math.hypot(x,y));stick={x:x/d,y:y/d};$('#knob').style.transform=`translate(${stick.x*32}px,${stick.y*32}px)`}joy.onpointerdown=e=>{jid=e.pointerId;joy.setPointerCapture(jid);joyMove(e)};joy.onpointermove=joyMove;joy.onpointerup=joy.onpointercancel=()=>{jid=null;stick={x:0,y:0};$('#knob').style.transform=''};
const solePoints=[new T.Vector3(-.0625,-.044,-.1225),new T.Vector3(.0625,-.044,-.1225),new T.Vector3(-.0625,-.044,.1225),new T.Vector3(.0625,-.044,.1225)];let soleCorrection=0;
function lowestSoleGap(){let gap=Infinity;for(const leg of legs)for(const local of solePoints){const point=local.clone().applyMatrix4(leg.userData.shoe.matrixWorld);gap=Math.min(gap,point.y-floorHeight(point.x,point.z));}return gap;}
// The eye follows the standing surface. The avatar root separately follows its soles.
const eye=new T.Vector3(),forward=new T.Vector3(),arm=new T.Vector3();
const lastFollowPosition=new T.Vector2(Infinity,Infinity);
let followHeight=0,armLength=1.5,previousView=null,previousRider=null;
function walkingCamera(groundY,dt){
 const rider=shuttle.rider;
 const x=avatar.position.x,z=avatar.position.z;
 const reset=modeChanged || previousView!==firstPerson || previousRider!==rider ||
   Math.hypot(x-lastFollowPosition.x,z-lastFollowPosition.y)>.5;
 lastFollowPosition.set(x,z);previousView=firstPerson;previousRider=rider;
 followHeight=reset?groundY:T.MathUtils.damp(followHeight,groundY,14,dt);
 eye.set(x,followHeight+.32,z);
 if(rider)eye.copy(avatar.position);
 forward.set(-Math.sin(yaw)*Math.cos(pitch),-Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch));
 target.copy(eye).addScaledVector(forward,firstPerson?1:.65);
 if(firstPerson){desired.copy(eye);return;}
 arm.copy(forward).multiplyScalar(-1.5);
 arm.y=Math.max(arm.y,-.24);
 const length=arm.length();arm.normalize();
 ray.set(eye,arm);ray.far=length;
 const nearby=collisionMeshes.filter(m=>m.geometry.boundingSphere.center.distanceTo(eye)<m.geometry.boundingSphere.radius+length);
 const hit=ray.intersectObjects(nearby,false)[0];
 const limit=hit?Math.max(.035,hit.distance-.045):length;
 armLength=reset||limit<armLength?limit:T.MathUtils.damp(armLength,limit,10,dt);
 desired.copy(eye).addScaledVector(arm,armLength);
}
let gaitPhase=0,gaitWeight=0;let prev=0;function tick(t){surfaceTime.value=t*.001;requestAnimationFrame(tick);const rawDt=(t-prev)/1000;const dt=Math.min(rawDt,.10);prev=t;if(frameCount++>30&&samples.length<240)samples.push(rawDt*1000);const priorX=avatar.position.x,priorZ=avatar.position.z;const blocked=!!document.querySelector('dialog[open]');let xx=0,zz=0;if(started&&!blocked)shuttle.tick(Math.min(rawDt,.3));if(started&&!blocked&&!overview&&!shuttle.rider){xx=(keys.KeyD||keys.ArrowRight?1:0)-(keys.KeyA||keys.ArrowLeft?1:0)+stick.x;zz=(keys.KeyS||keys.ArrowDown?1:0)-(keys.KeyW||keys.ArrowUp?1:0)+stick.y;const len=Math.max(1,Math.hypot(xx,zz));xx/=len;zz/=len;const dx=(Math.cos(yaw)*xx+Math.sin(yaw)*zz)*dt*(keys.ShiftLeft?.95:.5),dz=(-Math.sin(yaw)*xx+Math.cos(yaw)*zz)*dt*(keys.ShiftLeft?.95:.5);const steps=Math.max(1,Math.ceil(Math.hypot(dx,dz)/.035));
for(let i=0;i<steps;i++){
 if(dx&&valid(avatar.position.x+dx/steps,avatar.position.z))avatar.position.x+=dx/steps;
 if(dz&&valid(avatar.position.x,avatar.position.z+dz/steps))avatar.position.z+=dz/steps;
}if(xx||zz)avatar.rotation.y=Math.atan2(dx,dz);}
const groundY=floorHeight(avatar.position.x,avatar.position.z);avatar.position.y=groundY-.004;const traveled=Math.hypot(avatar.position.x-priorX,avatar.position.z-priorZ);const walking=traveled>.00001;gaitPhase+=traveled*32;gaitWeight=T.MathUtils.lerp(gaitWeight,walking?1:0,1-Math.exp(-dt*18));legs.forEach((l,i)=>{const phase=gaitPhase+i*Math.PI;l.rotation.x=Math.sin(phase)*.42*gaitWeight;l.userData.bend.rotation.x=Math.max(0,-Math.sin(phase))*.72*gaitWeight;});arms.forEach((l,i)=>{l.rotation.x=-Math.sin(gaitPhase+i*Math.PI)*.32*gaitWeight;l.userData.bend.rotation.x=-.10-Math.max(0,Math.sin(gaitPhase+i*Math.PI))*.32*gaitWeight;});
avatar.updateMatrixWorld(true);soleCorrection=T.MathUtils.clamp(lowestSoleGap(),-.12,.12);avatar.position.y-=soleCorrection;avatar.updateMatrixWorld(true);
if(shuttle.rider){
 const heading=shuttle.rider.body.rotation.y;yaw+=heading-busHeading;busHeading=heading;
 avatar.position.copy(shuttle.seat());shadow.visible=false;
}else shadow.visible=true;
refreshShuttle(started&&!overview);viewButton.hidden=!!shuttle.rider;
const cameraNear=overview?1:.015;if(camera.near!==cameraNear){camera.near=cameraNear;camera.updateProjectionMatrix();}
near=hud.update({x:avatar.position.x,z:avatar.position.z,yaw,started,overview,now:t});if(started&&!overview)updateMini(avatar.position.x,avatar.position.z,yaw,hud.target);mapTools.hidden=!overview;avatar.visible=!firstPerson||overview;
if(overview){scene.fog=null;target.copy(mapCenter);const height=atlasHeight*mapZoom;desired.set(0,height,height*.16).add(target);}else{scene.fog=walkingFog;walkingCamera(groundY,dt);}
if(overview&&!modeChanged)camera.position.lerp(desired,1-Math.exp(-dt*8));else camera.position.copy(desired);
modeChanged=false;camera.lookAt(target);sky.position.copy(camera.position);
if (overview && hud.selected) {
  const place = hud.selected;
  camera.updateMatrixWorld();
  mapPinPoint.set(place.x,place.h + .4,place.z).project(camera);
  hud.positionPin(mapPinPoint);
}

for(const l of playable){l.marker.rotation.y=t*.001;l.marker.visible=overview||!(firstPerson&&near===l);}shadow.position.set(avatar.position.x,groundY+.003,avatar.position.z);const sunForward=new T.Vector3(-35,55,25).normalize(),sunRight=new T.Vector3().crossVectors(new T.Vector3(0,1,0),sunForward).normalize(),sunUp=new T.Vector3().crossVectors(sunForward,sunRight);const texel=20/2048;const anchor=new T.Vector3(avatar.position.x,shuttle.rider?avatar.position.y:groundY,avatar.position.z);anchor.addScaledVector(sunRight,Math.round(anchor.dot(sunRight)/texel)*texel-anchor.dot(sunRight));anchor.addScaledVector(sunUp,Math.round(anchor.dot(sunUp)/texel)*texel-anchor.dot(sunUp));sun.position.copy(anchor).add(new T.Vector3(-35,55,25));sun.target.position.copy(anchor);sun.shadow.camera.updateProjectionMatrix();updateLake(camera,t,overview);comic.render(scene);}requestAnimationFrame(tick);window.game={shuttle,roadBatchStats,crossings,get gaitState(){return {soleGap:lowestSoleGap(),soleCorrection,phase:gaitPhase,weight:gaitWeight,knees:legs.map(l=>l.userData.bend.rotation.x)}},get viewState(){return {firstPerson,pitch,overview,mapZoom,center:mapCenter.toArray()}},comic,scene,renderer,osm,samples,avatar,valid,floorHeight,playable,save,camera,get near(){return near},get started(){return started}};
