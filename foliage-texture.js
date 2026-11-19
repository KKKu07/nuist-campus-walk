import * as T from './vendor/three.module.js';

// Paint overlapping sprays onto one transparent texture for the whole campus.
export function foliageTexture(){
 const canvas=document.createElement('canvas');
 canvas.width=canvas.height=256;
 const brush=canvas.getContext('2d');
 let seed=731;
 function random(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;}
 function leaf(x,y,length,angle,color){
  brush.save();brush.translate(x,y);brush.rotate(angle);brush.fillStyle=color;
  brush.beginPath();brush.moveTo(-length*.47,0);
  brush.quadraticCurveTo(-length*.11,-length*.37,length*.59,-length*.05);
  brush.quadraticCurveTo(length*.18,length*.31,-length*.47,0);brush.fill();brush.restore();
 }
 const sprays=Array.from({length:28},()=>{
  const a=random()*Math.PI*2,r=Math.sqrt(random());
  return {x:126+Math.cos(a)*r*86,y:125+Math.sin(a)*r*65,a,scale:.72+random()*.42};
 }).sort((a,b)=>b.y-a.y);
 for(const spray of sprays){
  const {x,y,a,scale}=spray,dx=Math.cos(a)*scale,dy=Math.sin(a)*scale;
  const palette=y<111?['#568247','#70934b','#93ae62']:y>149?['#2d5847','#3d6948','#507646']:['#416f49','#57864b','#74994e'];
  for(let i=0;i<8;i++){
   const side=i%2?1:-1,t=i*3.7,spread=(8-i*.6)*side;
   leaf(x+dx*t-dy*spread,y+dy*t+dx*spread,(20-i*.8+random()*4)*scale,a+side*(.58+random()*.23),palette[Math.floor(random()*3)]);
  }
 }
 const texture=new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;
 return texture;
}
