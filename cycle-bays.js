import {osm} from './osm-data.js';
import * as T from './vendor/three.module.js';
import {mergeGeometries} from './vendor/BufferGeometryUtils.js';

// Designed parking pockets on the grass side of the dormitory walks.
const locations=osm.bikeBays;
export function cycleBays(scene,height,gradient){
 const rubber='#30383a',steel='#abb6b3',iron='#586362',saddle='#55483f';
 const paints=['#477e85','#b76747','#c1aa6d','#5f7460','#4f6676'];
 const cube=new T.BoxGeometry(),tube=new T.CylinderGeometry(1,1,1,8);
 const tire=new T.TorusGeometry(.066,.005,6,24),rim=new T.TorusGeometry(.060,.002,5,24);
 const chainring=new T.TorusGeometry(.019,.0023,5,20),seat=new T.SphereGeometry(1,10,6);
 const material=new T.MeshToonMaterial({vertexColors:true,gradientMap:gradient});
 for(const [index,[x,z,angle]] of locations.entries()){
  const pieces=[],transform=new T.Object3D(),up=new T.Vector3(0,1,0);
  let local=new T.Matrix4();
  function part(source,color){
   transform.updateMatrix();
   const g=source.clone().applyMatrix4(transform.matrix).applyMatrix4(local);
   g.deleteAttribute('uv');
   const rgb=new T.Color(color),colors=new Float32Array(3*g.attributes.position.count);
   for(let i=0;i<colors.length;i+=3){colors[i]=rgb.r;colors[i+1]=rgb.g;colors[i+2]=rgb.b;}
   g.setAttribute('color',new T.BufferAttribute(colors,3));pieces.push(g);
  }
  function box(x,y,z,w,h,d,color){
   transform.position.set(x,y,z);transform.rotation.set(0,0,0);transform.scale.set(w,h,d);part(cube,color);
  }
  function rod(a,b,r,color){
   const first=new T.Vector3(...a),last=new T.Vector3(...b),delta=last.clone().sub(first);
   transform.position.copy(first).lerp(last,.5);transform.scale.set(r,delta.length(),r);
   transform.quaternion.setFromUnitVectors(up,delta.normalize());part(tube,color);
  }
  function ring(x,y,g,color){
   transform.position.set(x,y,0);transform.rotation.set(0,0,0);transform.scale.setScalar(1);part(g,color);
  }
  box(0,.0075,0,.52,.015,1.30,'#c5c0ac');
  for(let i=0;i<6;i++){
   const lane=(i-2.5)*.194;
   // Low galvanised front-wheel hoop, including the unoccupied space.
   local=new T.Matrix4();
   for(const off of [-.022,.022])rod([.14,.015,lane+off],[.14,.116,lane+off],.004,steel);
   rod([.14,.116,lane-.022],[.14,.116,lane+.022],.004,steel);
   if(i===(index+2)%6)continue;
   local.makeRotationY((i%3-1)*.075).setPosition((i%2)*.017,.016,lane);
   const paint=paints[(i+index)%paints.length];
   for(const wx of [-.102,.102]){
    ring(wx,.071,tire,rubber);ring(wx,.071,rim,steel);
    for(let k=0;k<6;k++){
     const a=k*Math.PI/6,dx=Math.cos(a)*.058,dy=Math.sin(a)*.058;
     rod([wx-dx,.071-dy,0],[wx+dx,.071+dy,0],.0009,steel);
    }
   }
   const crank=[-.018,.064,0],post=[-.048,.16,0],head=[.068,.158,0],rear=[-.102,.071,0];
   rod(rear,crank,.004,paint);rod(rear,post,.004,paint);rod(crank,post,.005,paint);
   rod(crank,head,.0055,paint);rod([-.036,i%2?.118:.15,0],head,.0045,paint);
   rod([.102,.071,0],head,.0045,steel);rod(post,[-.053,.181,0],.0035,steel);
   transform.position.set(-.059,.184,0);transform.rotation.set(0,0,.04);transform.scale.set(.027,.007,.016);part(seat,saddle);
   transform.position.set(-.018,.064,.007);transform.rotation.set(0,0,0);transform.scale.setScalar(1);part(chainring,iron);
   for(const sign of [-1,1]){
    rod([-.102,.071+sign*.007,.007],[-.018,.064+sign*.017,.007],.0016,rubber);
    rod([.102,.071,sign*.009],[.068,.158,sign*.003],.0032,steel);
   }
   rod(head,[.062,.202,0],.003,steel);rod([.062,.202,-.032],[.062,.202,.032],.003,rubber);
   rod([-.018,.064,0],[-.032,.048,.013],.0025,iron);box(-.032,.048,.021,.019,.005,.016,rubber);
   box(-.104,.147,0,.070,.005,.031,iron);
   rod([-.127,.145,.012],[-.103,.073,.012],.0025,iron);
   if(i%2===0){
    box(.105,.155,0,.049,.004,.046,iron);
    rod([.102,.071,.009],[.124,.155,.02],.0023,steel);
    rod([.067,.165,0],[.09,.158,0],.0028,steel);
    for(const side of [-1,1]){
     rod([.079,.186,side*.027],[.132,.186,side*.027],.0022,iron);
     for(let j=0;j<4;j++)rod([.082+j*.015,.155,side*.022],[.079+j*.017,.186,side*.027],.0017,iron);
     rod([side*.026+.106,.186,-.027],[side*.026+.106,.186,.027],.0022,iron);
    }
   }
  }
  const merged=mergeGeometries(pieces);pieces.forEach(g=>g.dispose());
  const bay=new T.Mesh(merged,material);bay.name='宿舍自行车停放区';bay.position.set(x,height(x,z),z);bay.rotation.y=angle;
  bay.castShadow=true;bay.receiveShadow=true;scene.add(bay);
 }
 for(const g of [cube,tube,tire,rim,chainring,seat])g.dispose();
}
