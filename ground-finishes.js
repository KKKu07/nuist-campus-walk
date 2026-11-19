import * as T from './vendor/three.module.js';

// These repeatable luminance maps are sampled in world coordinates. Mip levels
// average subpixel blades and mortar joints at low viewing angles.
const maps=new Map();
export function groundFinish(surface){
 if(maps.has(surface))return maps.get(surface);
 const canvas=document.createElement('canvas'),size=512;
 canvas.width=canvas.height=size;
 const ctx=canvas.getContext('2d');let seed=381701;
 const random=()=>((seed=Math.imul(seed,1664525)+1013904223>>>0)/4294967296);
 const gray=n=>'rgb('+n+' '+n+' '+n+')';
 ctx.fillStyle=gray(142);ctx.fillRect(0,0,size,size);
 if(surface==='grass'){
  for(let i=0;i<16000;i++){
   const x=random()*size,y=random()*size;
   const tint=Math.floor(70+random()*125),stem=2+random()*5,lean=(random()-.4)*6;
   // Wrap each tuft across the texture boundary.
   const dx=x<8?size:x>size-8?-size:0,dy=y<10?size:0;
   for(const ox of dx?[0,dx]:[0])for(const oy of dy?[0,dy]:[0]){
    ctx.fillStyle=gray(tint);ctx.beginPath();ctx.moveTo(x+ox-1.2,y+oy);
    ctx.quadraticCurveTo(x+ox-1,y+oy-stem*.43,x+ox+lean,y+oy-stem);
    ctx.lineTo(x+ox+1.4,y+oy);ctx.fill();
   }
  }
 }else if(surface==='asphalt'){
  // Fine aggregate in a darker binder, on a repeat small enough for foot-level viewing.
  const pixels=ctx.createImageData(size,size);
  for(let i=0;i<pixels.data.length;i+=4){
   const shade=125+Math.round((random()+random()-1)*25);
   pixels.data.set([shade,shade,shade,255],i);
  }
  ctx.putImageData(pixels,0,0);
  for(let n=0;n<17500;n++){
   const x=random()*size,y=random()*size,r=.35+random()*1.25;
   ctx.fillStyle=gray(Math.round(85+random()*94));
   ctx.beginPath();ctx.moveTo(x-r,y);ctx.lineTo(x,y-r*.8);
   ctx.lineTo(x+r,y-random()*.3);ctx.lineTo(x+r*.2,y+r*.7);ctx.fill();
  }
 }else{
  // Basket-weave brick pairs: four orientations meet without cutting a brick.
  const pitch=64;
  ctx.fillStyle=gray(106);ctx.fillRect(0,0,size,size);
  for(let y=0;y<size;y+=pitch)for(let x=0;x<size;x+=pitch){
   const horizontal=((x+y)/pitch)%2===0;
   for(let half=0;half<2;half++){
    const w=horizontal?pitch:pitch/2,h=horizontal?pitch/2:pitch;
    const left=x+(horizontal?0:half*w),top=y+(horizontal?half*h:0);
    const light=Math.round(148+random()*21);
    ctx.fillStyle=gray(light+12);ctx.fillRect(left+1,top+1,w-2,h-2);
    ctx.fillStyle=gray(light);ctx.fillRect(left+2,top+2,w-3,h-3);
    for(let n=0;n<115;n++){
     ctx.fillStyle=gray(Math.round(light-19+random()*35));ctx.fillRect(left+2+random()*(w-5),top+2+random()*(h-5),1.4,1.4);
    }
   }
  }
 }
 const texture=new T.CanvasTexture(canvas);
 texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.anisotropy=4;
 maps.set(surface,texture);return texture;
}
