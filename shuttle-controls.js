export function shuttleControls(shuttle,avatar,arrive,ride,disembark){
 const nav=document.querySelector('nav'),menu=document.createElement('button'),action=document.createElement('button');
 const dialog=document.createElement('dialog');dialog.id='shuttlePanel';
 dialog.innerHTML='<h2>校园小公交</h2><p>选择方向和站点，前往站台候车。</p><label>行驶方向 <select><option value="1">红线 · 图书馆往滨江楼</option><option value="-1">蓝线 · 图书馆往中苑老食堂</option></select></label><div class="stationList"></div><button class="closeBus">关闭</button>';
 document.body.append(dialog);menu.textContent='校园小公交';menu.id='shuttleMenu';action.id='shuttleAction';nav.append(menu,action);
 const select=dialog.querySelector('select'),list=dialog.querySelector('.stationList');
 function render(){
  const dir=Number(select.value);
  const stops=shuttle.stops.filter(s=>s.dir===dir);
  if(dir<0)stops.splice(1,stops.length-1,...stops.slice(1).reverse());
  list.replaceChildren(...stops.map(s=>{
   const button=document.createElement('button');button.textContent=s.name;button.onclick=()=>{dialog.close();arrive(s);};return button;
  }));
 }
 select.onchange=render;menu.onclick=()=>{render();dialog.showModal();};dialog.querySelector('.closeBus').onclick=()=>dialog.close();
 let perform=null;
 action.onclick=()=>perform?.();
 return function refresh(active){
  perform=null;const rider=shuttle.rider;menu.hidden=!active||!!rider;action.hidden=!active;
  if(!active)return;
  if(rider){
   const canLeave=rider.hold>.5;
   action.textContent=canLeave?'F · '+shuttle.stopFor(rider).name+'下车':'下一站 · '+shuttle.nextName(rider);
   if(canLeave)perform=()=>{const p=shuttle.leave();if(p)disembark(p);};
  }else{
   const closest=shuttle.stops.reduce((a,b)=>avatar.position.distanceToSquared(a.entry)<avatar.position.distanceToSquared(b.entry)?a:b);
   if(avatar.position.distanceTo(closest.entry)>1.8){action.hidden=true;return;}
   const bus=shuttle.fleet.find(b=>b.dir===closest.dir);
   if(bus.index===closest.index&&bus.hold>.5){
    action.textContent='F · 上车往'+shuttle.nextName(bus);
    perform=()=>{if(shuttle.board(bus))ride(bus);};
   }else{
    action.textContent='F · '+closest.name+'候车';
    perform=()=>shuttle.waitAt(closest);
   }
  }
  action.disabled=!perform;
 };
}
