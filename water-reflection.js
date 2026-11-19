// Shoreline reflections share static spatial batches with the campus scene.
import * as T from './vendor/three.module.js';
import {daylightSky} from './daylight-sky.js';
export const waterLevel=.014;
export const waterUniforms={lakeMap:{value:null},lakeProject:{value:new T.Matrix4()},lakeReflect:{value:0}};
export function lakeReflections(renderer,osm,campus){
 const scene=new T.Scene(),sky=daylightSky(scene),mirror=new T.PerspectiveCamera();
 scene.fog=new T.Fog('#90b7cb',40,160);
 const target=new T.WebGLRenderTarget(512,320);
 waterUniforms.lakeMap.value=target.texture;
 const bounds=osm.water.map(f=>new T.Box3().setFromPoints(f.points.map(([x,z])=>new T.Vector3(x,waterLevel,z))));
 // Reuse the planted geometry so reflected branch forks, crown gaps and reeds
 // occupy the same positions as their counterparts visible above the shore.
 const shared=new Map(),shoreMeshes=[];
 const reflectedMaterials=new Set([
  'shrub','leafCard','leaf','leafLight','leafDark','bark','flower','trim','white','sand','wall','brick','brickBurnt',
  'ceramic','roof','roofLight','blueRoof','slate','glass','glassDeep','glassShade','glassLight','glassSoft','roomPane','wood'
 ]);
 for(const cell of campus.children){
  if(!cell.isMesh||!reflectedMaterials.has(cell.name.replace('校园 / ','')))continue;
  const sphere=cell.geometry.boundingSphere;
  if(!bounds.some(b=>b.distanceToPoint(sphere.center)<sphere.radius+38))continue;
  if(!shared.has(cell.material)){
   const source=cell.material;
   shared.set(source,new T.MeshLambertMaterial({color:source.color,map:source.map,side:source.side,alphaTest:source.alphaTest}));
  }
  const mesh=new T.Mesh(cell.geometry,shared.get(cell.material));scene.add(mesh);shoreMeshes.push(mesh);
 }
 scene.add(new T.HemisphereLight('#f4f5ff','#718296',1));
 const sun=new T.DirectionalLight('#fff1d9',1.8);sun.position.set(-35,55,25);scene.add(sun);
 const lastPosition=new T.Vector3(Infinity,0,0),lastRotation=new T.Quaternion(),lastProjection=new T.Matrix4();
 let previous=-Infinity;const dir=new T.Vector3(),aim=new T.Vector3();
 return function update(camera,time,overview){
  const near=!overview&&bounds.some(b=>b.distanceToPoint(camera.position)<23);
  waterUniforms.lakeReflect.value=near?1:0;if(!near||time-previous<90)return;
  if(lastPosition.distanceToSquared(camera.position)<1e-6&&lastRotation.angleTo(camera.quaternion)<.0005&&lastProjection.equals(camera.projectionMatrix))return;
  previous=time;lastPosition.copy(camera.position);lastRotation.copy(camera.quaternion);lastProjection.copy(camera.projectionMatrix);
  for(const mesh of shoreMeshes){
   const sphere=mesh.geometry.boundingSphere;mesh.visible=sphere.center.distanceTo(camera.position)<sphere.radius+78;
  }
  camera.getWorldDirection(dir);mirror.position.copy(camera.position);mirror.position.y=2*waterLevel-camera.position.y;
  dir.y=-dir.y;mirror.up.set(0,-1,0);mirror.lookAt(aim.copy(mirror.position).add(dir));
  mirror.near=camera.near;mirror.far=camera.far;mirror.projectionMatrix.copy(camera.projectionMatrix);mirror.updateMatrixWorld();sky.position.copy(mirror.position);
  waterUniforms.lakeProject.value.multiplyMatrices(mirror.projectionMatrix,mirror.matrixWorldInverse);
  const old=renderer.getRenderTarget();renderer.setRenderTarget(target);renderer.render(scene,mirror);renderer.setRenderTarget(old);
 };
}
