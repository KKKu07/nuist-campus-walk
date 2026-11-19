import * as T from './vendor/three.module.js';

// A seamless broadleaf hedge pattern with small interlocking sprays.
export function shrubTexture(){
 const canvas=document.createElement('canvas');canvas.width=256;canvas.height=128;
 const c=canvas.getContext('2d');let seed=47069;
 const random=()=>((seed=Math.imul(seed,1664525)+1013904223>>>0)/4294967296);
 c.fillStyle='#3c5c41';c.fillRect(0,0,256,128);
 const greens=['#3f6447','#557a4b','#71914e','#809957','#647f46'];
 for(let spray=0;spray<220;spray++){
  const x=random()*256,y=random()*128,a=random()*Math.PI*2;
  const tint=greens[Math.floor(random()*greens.length)],length=4+random()*4;
  for(const dx of [-256,0,256])for(const dy of [-128,0,128]){
   if(x+dx< -20||x+dx>276||y+dy< -20||y+dy>148)continue;
   c.save();c.translate(x+dx,y+dy);c.rotate(a);
   for(let n=0;n<5;n++){
    c.save();c.translate(n*2.1,(n%2?.9:-.9));c.rotate(n%2?.74:-.74);
    c.fillStyle=tint;c.beginPath();c.moveTo(0,0);c.quadraticCurveTo(length*.5,-2.7,length,0);
    c.quadraticCurveTo(length*.5,2.6,0,0);c.fill();c.restore();
   }
   c.restore();
  }
 }
 const texture=new T.CanvasTexture(canvas);texture.wrapS=T.RepeatWrapping;texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;return texture;
}
