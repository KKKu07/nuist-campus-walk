import {roomWindows} from './room-windows.js';
let rooms;
import {groundFinish} from './ground-finishes.js';
import {waterUniforms} from './water-reflection.js';
import * as T from './vendor/three.module.js';
export const surfaceTime={value:0};
// Original implementation: world-space paper grain and restrained shadow hatching.
export function outdoorMaterial(color,gradient,surface="paper"){
 const m=new T.MeshToonMaterial({color,gradientMap:gradient});
 m.onBeforeCompile=s=>{s.uniforms.surfaceTime=surfaceTime;
 if(surface==='roomPane'){
  rooms??=roomWindows();s.uniforms.roomAtlas={value:rooms};
  s.vertexShader='varying vec2 roomUV;\n'+s.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nroomUV=uv;');
  s.fragmentShader='varying vec2 roomUV; uniform sampler2D roomAtlas;\n'+s.fragmentShader;
 }
 if(surface==='grass'||surface==='paving'||surface==='asphalt'||surface==='soil'){
  s.uniforms.groundFinish={value:groundFinish(surface==='soil'?'asphalt':surface)};
  s.fragmentShader='uniform sampler2D groundFinish;\n'+s.fragmentShader;
 }
 if(surface==='water'){Object.assign(s.uniforms,waterUniforms);s.fragmentShader='uniform sampler2D lakeMap; uniform mat4 lakeProject; uniform float lakeReflect;\n'+s.fragmentShader;}s.vertexShader=s.vertexShader.replace('#include <common>','#include <common>\nvarying vec3 vPaperWorld; varying vec3 vFacadeNormal;');s.vertexShader=s.vertexShader.replace('#include <project_vertex>','#include <project_vertex>\nvPaperWorld=(modelMatrix*vec4(transformed,1.0)).xyz; vFacadeNormal=inverseTransformDirection(transformedNormal,viewMatrix);');s.fragmentShader=s.fragmentShader.replace('#include <common>','#include <common>\nvarying vec3 vPaperWorld; varying vec3 vFacadeNormal;\nuniform float surfaceTime;');s.fragmentShader=s.fragmentShader.replace('#include <opaque_fragment>',`vec2 grainUV=vPaperWorld.xz*110.0;
vec2 grainFootprint=fwidth(grainUV);
float paperWeight=1.0-smoothstep(.22,1.0,max(grainFootprint.x,grainFootprint.y));
vec2 seed=fract(floor(grainUV)*vec2(.1031,.11369));
float paper=fract((seed.x+seed.y)*dot(seed,seed.yx+19.19));
float stroke=(vPaperWorld.x+vPaperWorld.y)*12.0;
float hatch=smoothstep(.82,.99,.5+.5*cos(stroke*6.283185))*(1.-smoothstep(.2,.85,fwidth(stroke)));
float shade=1.0-smoothstep(.18,.55,dot(outgoingLight,vec3(.2126,.7152,.0722)));
outgoingLight*=1.0+(paper-.5)*.025*paperWeight-hatch*shade*.025;
${['brick','ceramic'].includes(surface) ? `vec3 n=normalize(vFacadeNormal);
vec2 tangent=abs(n.y)>.98?vec2(1.,0.):normalize(vec2(-n.z,n.x));
vec2 grid=vec2(dot(vPaperWorld.xz,tangent),vPaperWorld.y)*${surface==='brick'?'vec2(19.,55.)':'vec2(5.,11.)'};
grid.x += ${surface==='brick'?'mod(floor(grid.y),2.)*.5':'0.'};
vec2 fw=max(fwidth(grid),vec2(.001)),d=min(fract(grid),1.-fract(grid));
vec2 line=1.-smoothstep(vec2(.025),vec2(.025)+fw*.55,d);
float nearDetail=1.-smoothstep(.13,.7,max(fw.x,fw.y));
float grain=fract(sin(dot(floor(grid),vec2(31.1,73.7)))*4723.41);
outgoingLight*=1.+(grain-.5)*.12*nearDetail;
outgoingLight=mix(outgoingLight,vec3(.48,.42,.34),max(line.x,line.y)*nearDetail*.27);
` : ''}
${surface==='paving' ? `vec2 pavingUV=mat2(.9659,-.2588,.2588,.9659)*vPaperWorld.xz/.48;
float paver=texture2D(groundFinish,pavingUV).r;
outgoingLight*=vec3(1.0,.985,.965)*(.30+1.12*paver);` : ''}
${surface==='grass' ? `vec2 lawn=vPaperWorld.xz;
float turf=texture2D(groundFinish,lawn/.55).r;
float clumps=texture2D(groundFinish,mat2(.8,-.6,.6,.8)*lawn/3.7).r;
float patches=.5+.5*sin(lawn.x*.79+sin(lawn.y*.46))*sin(lawn.y*.85+sin(lawn.x*.38));
patches=mix(.5,patches,1.-smoothstep(8.,50.,length(cameraPosition-vPaperWorld)));
outgoingLight*=mix(vec3(.78,.91,.80),vec3(1.,1.04,.89),patches)*(.25+turf*.99+clumps*.43);` : ''}
${surface==='water' ? `vec2 pt=vPaperWorld.xz;
float phase=pt.x*8.+pt.y*9.+sin(pt.y*1.9)+surfaceTime*.92;
float wave=sin(phase)+sin(pt.y*15.-pt.x*3.-surfaceTime*.72);
vec4 projection=lakeProject*vec4(vPaperWorld,1.);
vec2 uv=projection.xy/max(.001,projection.w)*.5+.5;
float resolved=1.-smoothstep(.24,1.7,max(fwidth(phase),fwidth(pt.y*15.-pt.x*3.)));
float rippleScale=mix(.28,1.,resolved);
uv+=vec2(sin(phase)+.33*sin(pt.y*5.+surfaceTime*.46),wave)*vec2(.0019,.0031)*rippleScale;
vec3 reflection=texture2D(lakeMap,clamp(uv,.003,.997)).rgb;
float grazing=1.-abs(normalize(cameraPosition-vPaperWorld).y);
float fade=1.-smoothstep(.18,1.2,fwidth(phase));
vec3 deep=mix(vec3(.028,.135,.14),vec3(.065,.245,.23),.5+.5*sin(pt.y*.41+sin(pt.x*.57)));
outgoingLight=mix(deep,mix(vec3(.28,.51,.62),reflection,lakeReflect),.25+.52*grazing*grazing);
outgoingLight+=smoothstep(1.52,1.94,wave)*vec3(.09,.12,.105)*fade;` : ''}
${surface==='roomPane' ? `vec3 wallNormal=normalize(vFacadeNormal);
vec3 incident=normalize(vPaperWorld-cameraPosition);
vec3 rayDir=reflect(incident,wallNormal);
float angle=1.-abs(dot(incident,wallNormal));
vec3 interior=texture2D(roomAtlas,roomUV).rgb;
vec3 skyline=mix(vec3(.055,.11,.13),vec3(.30,.48,.66),smoothstep(-.08,.50,rayDir.y));
float glaze=.18+.43*angle*angle;
outgoingLight=mix(interior*(vec3(.44,.52,.57)+outgoingLight*.85),skyline,glaze);
` : ''}
${surface==='glass' ? `vec3 worldN=normalize(vFacadeNormal);vec3 viewDir=normalize(cameraPosition-vPaperWorld);if(dot(worldN,viewDir)<0.)worldN=-worldN;vec3 reflected=reflect(-viewDir,worldN);float fresnel=pow(1.-clamp(dot(worldN,viewDir),0.,1.),3.);float skyHeight=smoothstep(-.12,.65,reflected.y);vec3 reflectedSky=mix(vec3(.075,.13,.15),vec3(.36,.57,.72),skyHeight);float cloud=pow(max(0.,sin(reflected.x*8.+reflected.z*6.)*sin(reflected.y*13.)),6.)*.07;reflectedSky+=vec3(cloud);outgoingLight=mix(outgoingLight*.72,reflectedSky,.25+fresnel*.45);` : ''}
${surface==='soil' ? `float crumble=texture2D(groundFinish,vPaperWorld.xz*.91).r;
float grains=texture2D(groundFinish,vPaperWorld.xz*3.6).r;
outgoingLight*=.30+.88*crumble+.51*grains;` : ''}
${surface==='curb' ? `vec2 stone=mat2(.966,-.259,.259,.966)*vPaperWorld.xz*4.8;
vec2 cell=fract(stone),joint=min(cell,1.-cell),aa=max(fwidth(stone),vec2(.001));
vec2 lines=1.-smoothstep(vec2(.006),vec2(.006)+aa*.65,joint);
float visibility=1.-smoothstep(.12,.65,max(aa.x,aa.y));
float block=fract(sin(dot(floor(stone),vec2(27.31,78.16)))*1737.25);
outgoingLight*=1.+visibility*((block-.5)*.16-.33*max(lines.x,lines.y));` : ''}
${surface==='asphalt' ? `vec2 roadUV=vPaperWorld.xz;
float grit=texture2D(groundFinish,roadUV/.64).r;
float wear=texture2D(groundFinish,roadUV/2.7).r;
outgoingLight*=vec3(.98,.987,1.)*(.35+.92*grit+.33*wear);` : ''}\n#include <opaque_fragment>`);};m.customProgramCacheKey=()=> 'nuist-paper-v2-'+surface;return m;
}
export function createSpatialIndex(features,cell=10){const grid=new Map();for(const f of features){const xs=f.points.map(p=>p[0]),zs=f.points.map(p=>p[1]);for(let x=Math.floor((Math.min(...xs)-1)/cell);x<=Math.floor((Math.max(...xs)+1)/cell);x++)for(let z=Math.floor((Math.min(...zs)-1)/cell);z<=Math.floor((Math.max(...zs)+1)/cell);z++){const key=x+','+z;if(!grid.has(key))grid.set(key,[]);grid.get(key).push(f);}}return(x,z)=>grid.get(Math.floor(x/cell)+','+Math.floor(z/cell))||[];}
