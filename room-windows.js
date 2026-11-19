import * as T from './vendor/three.module.js';

// Sixteen daylight interiors share one atlas. The narrow border around each
// tile protects the glass from neighbouring colours when viewed at a distance.
export function roomWindows(){
 const tile=128,canvas=document.createElement('canvas');canvas.width=canvas.height=4*tile;
 const ctx=canvas.getContext('2d');
 function rect(x,y,w,h,color){ctx.fillStyle=color;ctx.fillRect(x,y,w,h);}
 function polygon(points,color){ctx.fillStyle=color;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();}
 for(let k=0;k<16;k++){
  ctx.save();ctx.translate(k%4*tile,Math.floor(k/4)*tile);ctx.beginPath();ctx.rect(0,0,tile,tile);ctx.clip();
  const warm=k%4===1,edge=11+(k*11)%26;
  rect(0,0,128,128,warm?'#928d79':'#687977');
  polygon([[0,0],[128,0],[114,22],[edge,22]],'#596767');
  polygon([[0,0],[edge,22],[edge,93],[0,122]],warm?'#776e60':'#4e6368');
  polygon([[128,0],[114,22],[114,93],[128,122]],'#506469');
  polygon([[0,122],[edge,93],[114,93],[128,122],[128,128],[0,128]],'#45585c');
  rect(edge+8,30,35,24,'#65716e');rect(edge+10,32,31,20,k%3?'#859693':'#a6a08b');
  if(k%3===0){
   rect(73,56,34,38,'#525e5c');
   for(let j=0;j<9;j++)rect(76+j*3,59+j%3,2,13,['#938272','#a89b80','#7f9390'][j%3]);
   rect(73,73,34,2,'#807c70');
  }else{
   rect(31,81,65,4,'#534e46');rect(35,85,3,15,'#484f4e');rect(89,85,3,15,'#484f4e');
  }
  if(k%4===0||k%4===2){
   const width=12+(k*7)%30;
   for(let x=0;x<width;x++)rect(x,0,1,118+2*Math.sin(x*.5),`hsl(43,12%,${59+7*Math.cos(x*.53)}%)`);
  }else if(k%4===1){
   const drop=23+k*2;rect(0,0,128,drop,'#b5b19e');
   for(let y=4;y<drop;y+=5)rect(0,y,128,1,'#8f9287');
  }
  rect(0,0,128,4,'#414e50');rect(0,0,3,128,'#475658');ctx.restore();
 }
 const texture=new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;return texture;
}
