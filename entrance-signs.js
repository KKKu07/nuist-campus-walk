import * as T from './vendor/three.module.js';

// Original lettering for the reconstructed entrances, dimensioned in map units.
export function entranceSigns(scene, buildings){
 for(const [kind,title,caption,width,height,level,offset] of [
  ['library','图  书  馆','NUIST   /   LIBRARY',3.3,.48,2.64,1.13],
  ['weather','气  象  楼','NUIST   /   METEOROLOGY',1.07,.16,1.38,.947],
  ['theatre','风 云 剧 场','NUIST   /   CAMPUS THEATRE',2.35,.29,1.29,.83]
 ]){
  const building=buildings.find(b=>b.profile.kind===kind);
  if(!building)continue;
  const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=160;
  const c=canvas.getContext('2d');c.fillStyle=kind==='library'?'#314944':'#563a30';c.fillRect(0,0,1024,160);
  c.fillStyle='#c6ad7a';c.fillRect(18,11,988,2);c.fillRect(18,147,988,2);
  c.textAlign='center';c.fillStyle='#f8e7bd';c.font='600 78px serif';c.fillText(title,512,96);
  c.font='22px sans-serif';c.fillText(caption,512,131);
  const texture=new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;
  const sign=new T.Mesh(new T.PlaneGeometry(width,height),new T.MeshBasicMaterial({map:texture}));
  const depth=building.depth/2+offset;
  sign.position.set(building.x+Math.sin(building.angle)*depth,level,building.z+Math.cos(building.angle)*depth);
  sign.rotation.y=building.angle;scene.add(sign);
 }
}
