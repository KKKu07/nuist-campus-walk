export function miniMap(osm, landmarks, open, shuttle){
 const panel=document.createElement('button'); panel.id='miniMap';panel.setAttribute('aria-label','实时位置，打开校园鸟瞰');
 panel.innerHTML='<b>校园位置　↗</b><small></small><svg viewBox="-18 -18 36 36" aria-hidden="true"><g class="cartography"></g><path class="bearing" d="M0 -1.8 L1.2 1.35 L0 .85 L-1.2 1.35Z" fill="#2877d8" stroke="white" stroke-width=".32"/></svg><i>北 N</i>';
 document.body.append(panel);panel.onclick=open;const g=panel.querySelector('g'),ns='http://www.w3.org/2000/svg';
 function path(item,color,stroke=false){const el=document.createElementNS(ns,'path');el.setAttribute('d',[item.points,...(item.holes||[])].map(r=>'M'+r.map(p=>p.join(' ')).join('L')+(stroke?'':'Z')).join(''));el.setAttribute('fill',stroke?'none':color);el.setAttribute('fill-rule','evenodd');if(stroke){el.setAttribute('stroke',color);el.setAttribute('stroke-width',item.width);el.setAttribute('stroke-linejoin','round');}g.append(el);}
 for(const p of osm.campus)path(p,'#cee1ba');for(const p of osm.water)path(p,'#91cbde');for(const r of osm.roads)path(r,r.width>2?'#ffe4a2':'#fffbee',true);for(const p of osm.buildings)path(p,'#98a79d');
 for(const l of landmarks){const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx',l.x);dot.setAttribute('cy',l.z);dot.setAttribute('r','.75');dot.setAttribute('fill','#99662b');g.append(dot);}
 const line={points:shuttle.points.map(p=>[p.x,p.z]),width:.24};line.points.push(line.points[0]);path(line,'#25819a',true);
 function transitDot(color,r){
  const dot=document.createElementNS(ns,'circle');dot.setAttribute('fill',color);dot.setAttribute('r',r);dot.setAttribute('stroke','white');dot.setAttribute('stroke-width','.15');g.append(dot);return dot;
 }
 for(const stop of shuttle.stops.filter(s=>s.dir===1)){const dot=transitDot('#227084','.62');dot.setAttribute('cx',stop.entry.x);dot.setAttribute('cy',stop.entry.z);}
 const buses=shuttle.fleet.map(b=>transitDot(b.dir===1?'#b43d50':'#2879be','.85'));
 const coords=panel.querySelector('small'),arrow=panel.querySelector('.bearing');
 const destination = document.createElementNS(ns,'path');
 destination.setAttribute('d','M0 -1.05 L.88 0 L0 1.05 L-.88 0Z');
 destination.setAttribute('fill','#efc557');
 destination.setAttribute('stroke','#4e4834');
 destination.setAttribute('stroke-width','.24');
 panel.querySelector('svg').insertBefore(destination,arrow);
 return (x,z,yaw,target)=>{
  shuttle.fleet.forEach((b,i)=>{
   buses[i].setAttribute('cx',b.body.position.x);
   buses[i].setAttribute('cy',b.body.position.z);
  });
  g.setAttribute('transform','translate('+(-x)+' '+(-z)+')');
  arrow.setAttribute('transform','rotate('+(-yaw*180/Math.PI)+')');
  destination.style.display=target?'':'none';
  if(target){
   const dx=target.entry.x-x,dz=target.entry.z-z,scale=Math.min(1,15.8/(Math.hypot(dx,dz)||1));
   destination.setAttribute('transform','translate('+dx*scale+' '+dz*scale+')');
  }
  const position='X '+x.toFixed(1)+'　Z '+z.toFixed(1);
  if(coords.textContent!==position)coords.textContent=position;
 };
}
