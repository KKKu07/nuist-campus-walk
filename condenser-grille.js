import * as T from './vendor/three.module.js';

// Painted condenser face for the dormitory outdoor units.
export function condenserGrille(){
 const canvas=document.createElement('canvas');canvas.width=256;canvas.height=144;
 const c=canvas.getContext('2d');
 c.fillStyle='#b8c3bc';c.fillRect(0,0,256,144);
 c.fillStyle='#546364';c.beginPath();c.arc(82,74,62,0,Math.PI*2);c.fill();
 for(let i=0;i<5;i++){
  c.save();c.translate(82,74);c.rotate(i*Math.PI*2/5);
  c.fillStyle='#849491';c.beginPath();c.moveTo(0,0);c.quadraticCurveTo(-11,-30,15,-54);
  c.quadraticCurveTo(41,-42,28,-23);c.quadraticCurveTo(16,-9,0,0);c.fill();c.restore();
 }
 c.strokeStyle='#aeb9b1';c.lineWidth=2;
 for(let r=12;r<=61;r+=8){c.beginPath();c.arc(82,74,r,0,Math.PI*2);c.stroke();}
 for(let i=0;i<8;i++){const a=i*Math.PI/4;c.beginPath();c.moveTo(82,74);c.lineTo(82+Math.cos(a)*60,74+Math.sin(a)*60);c.stroke();}
 c.fillStyle='#adb7ae';c.beginPath();c.arc(82,74,8,0,Math.PI*2);c.fill();
 c.fillStyle='#788c87';for(let j=0;j<9;j++)c.fillRect(164,36+j*7,66,2);
 c.fillStyle='#648079';c.fillRect(164,109,35,6);
 const map=new T.CanvasTexture(canvas);map.colorSpace=T.SRGBColorSpace;map.anisotropy=4;return map;
}
