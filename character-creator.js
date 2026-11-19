import * as T from './vendor/three.module.js';
const storageKey='nuist-appearance-v1';
const categories=[
 ['hairStyle','发型',[['short','利落短发'],['bob','齐耳短发'],['pony','轻盈马尾']]],
 ['hair','发色',[['#302f31','墨黑'],['#634536','栗棕'],['#99764f','浅棕']]],
 ['skin','肤色',[['#f1cfb1','浅暖'],['#e9ba93','自然'],['#bc875f','小麦'],['#80563e','深棕']]],
 ['shirt','上衣',[['#7795ac','晴空蓝'],['#c27e70','珊瑚粉'],['#829a70','草木绿'],['#eee8d8','米白'],['#364552','深海蓝']]],
 ['pants','长裤',[['#596c78','牛仔蓝'],['#343c43','炭灰'],['#b6a88d','卡其'],['#dedbd0','浅米']]],
 ['bag','背包',[['yes','带上背包'],['no','轻装出发']]],
];
export function characterCreator({avatar,skin,shirt,pants,hairMaterial,onEnter}){
 const welcome=document.querySelector('#welcome'),canvas=document.querySelector('#characterPreview'),options=document.querySelector('#appearanceOptions'),rotation=document.querySelector('#characterRotation');
 let selection={hairStyle:'short',hair:'#302f31',skin:'#e9ba93',shirt:'#7795ac',pants:'#596c78',bag:'yes'},saved=false;
 try{const data=JSON.parse(localStorage.getItem(storageKey));if(data&&typeof data==='object'){for(const [key,,values] of categories)if(values.some(([v])=>v===data[key]))selection[key]=data[key];saved=true;}}catch{}
 // Clone only visual state; animation userData contains live joint references.
 const data=[];avatar.traverse(o=>{data.push([o,o.userData]);o.userData={};});const preview=avatar.clone(true);for(const [o,d] of data)o.userData=d;
 preview.position.set(0,-.88,0);preview.scale.setScalar(1);preview.rotation.set(0,0,0);
 const scene=new T.Scene();scene.add(preview,new T.HemisphereLight('#fff9e9','#6c8090',2));const keyLight=new T.DirectionalLight('#fff1d9',2.6);keyLight.position.set(-3,5,5);scene.add(keyLight);
 const camera=new T.PerspectiveCamera(32,1,.1,20);camera.position.set(0,.05,3.6);camera.lookAt(0,0,0);
 const renderer=new T.WebGLRenderer({canvas,alpha:true,antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;
 function draw(){if(welcome.hidden)return;const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;renderer.setSize(rect.width,rect.height,false);camera.aspect=rect.width/rect.height;camera.updateProjectionMatrix();preview.rotation.y=Number(rotation.value)*Math.PI/180;renderer.render(scene,camera);}
 function apply(){skin.color.set(selection.skin);shirt.color.set(selection.shirt);pants.color.set(selection.pants);hairMaterial.color.set(selection.hair);for(const model of [avatar,preview])model.traverse(o=>{if(o.name==='outfit-bag')o.visible=selection.bag==='yes';if(o.name==='hair-cropped')o.visible=selection.hairStyle!=='bob';if(o.name==='hair-bob')o.visible=selection.hairStyle==='bob';if(o.name==='hair-pony')o.visible=selection.hairStyle==='pony';});for(const button of options.querySelectorAll('button'))button.setAttribute('aria-pressed',String(selection[button.dataset.key]===button.dataset.value));draw();}
 for(const [key,label,values] of categories){const field=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=label;field.append(legend);for(const [value,name] of values){const button=document.createElement('button');button.type='button';button.dataset.key=key;button.dataset.value=value;button.setAttribute('aria-label',label+'：'+name);if(value.startsWith('#')){const dot=document.createElement('span');dot.className='color-dot';dot.style.background=value;button.append(dot);}button.append(document.createTextNode(name));button.onclick=()=>{selection[key]=value;apply();};field.append(button);}options.append(field);}
 const start=document.querySelector('#start');start.textContent=saved?'就这身，进入校园 →':'穿好啦，进入校园 →';start.onclick=()=>{try{localStorage.setItem(storageKey,JSON.stringify(selection));}catch{document.querySelector('#notice').textContent='当前浏览器无法保存装扮，本次仍可使用';}welcome.hidden=true;onEnter();};rotation.oninput=draw;
 new ResizeObserver(draw).observe(canvas);apply();
 return {open(){welcome.hidden=false;start.textContent='保存装扮，返回校园 →';apply();}};
}
