import * as T from './vendor/three.module.js';
import {mergeGeometries} from './vendor/BufferGeometryUtils.js';

export function dormSigns(scene,doors){
 if(!doors.length)return;
 const names=[...new Set(doors.map(d=>d.name))],columns=4,w=384,h=96;
 const canvas=document.createElement('canvas');canvas.width=w*columns;canvas.height=h*Math.ceil(names.length/columns);
 const c=canvas.getContext('2d');
 for(const [i,name] of names.entries()){
  const x=i%columns*w,y=Math.floor(i/columns)*h;
  c.fillStyle='#274348';c.fillRect(x,y,w,h);
  c.fillStyle='#d1b984';c.fillRect(x+13,y+14,4,h-28);
  c.fillStyle='#faf2d9';c.textBaseline='middle';c.font='bold 45px sans-serif';
  c.fillText(name,x+30,y+47,w-105);
  c.fillStyle='#bdcbbd';c.font='16px sans-serif';c.fillText('宿舍',x+w-55,y+48);
 }
 const atlas=new T.CanvasTexture(canvas);atlas.colorSpace=T.SRGBColorSpace;atlas.anisotropy=4;
 const faces=doors.map(d=>{
  const i=names.indexOf(d.name),left=(i%columns*w+1)/canvas.width,bottom=1-(Math.floor(i/columns)*h+h-1)/canvas.height;
  const face=new T.PlaneGeometry(d.width,.096),uv=face.attributes.uv;
  for(let v=0;v<uv.count;v++)uv.setXY(v,left+uv.getX(v)*(w-2)/canvas.width,bottom+uv.getY(v)*(h-2)/canvas.height);
  face.rotateY(Math.atan2(d.nx,d.nz));face.translate(d.x,.593,d.z);return face;
 });
 const signs=new T.Mesh(mergeGeometries(faces),new T.MeshBasicMaterial({map:atlas}));
 signs.name='宿舍入口楼号牌';scene.add(signs);faces.forEach(g=>g.dispose());
}
