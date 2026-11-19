import * as T from './vendor/three.module.js';

export function daylightSky(scene){
 const material=new T.ShaderMaterial({
  side:T.BackSide,depthTest:false,depthWrite:false,fog:false,
  vertexShader:`varying vec3 skyDirection;
   void main(){
    skyDirection=position;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);
   }`,
  fragmentShader:`varying vec3 skyDirection;
   float hash(vec2 p){
    vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));
    q+=dot(q,q.yzx+33.33);
    return fract((q.x+q.y)*q.z);
   }
   float noise(vec2 p){
    vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),
               mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
   }
   float cloudField(vec2 p){
    mat2 rotate=mat2(.8,.6,-.6,.8);
    float v=.54*noise(p);
    p=rotate*p*2.06+9.2;v+=.27*noise(p);
    p=rotate*p*2.09+5.1;v+=.13*noise(p);
    return v+.06*noise(rotate*p*2.07);
   }
   void main(){
    vec3 d=normalize(skyDirection);
    float h=max(d.y,0.);
    vec3 sky=mix(vec3(.58,.78,.92),vec3(.025,.235,.65),smoothstep(0.,.81,pow(h,.62)));
    if(d.y>.005){
     vec2 p=d.xz/max(.08,h+.11)*2.45;
     float density=cloudField(p);
     float cover=smoothstep(.515,.62,density)*smoothstep(.005,.075,h);
     float light=smoothstep(-.055,.095,density-cloudField(p+vec2(.17,-.12)));
     vec3 cloud=mix(vec3(.62,.74,.82),vec3(.98,.974,.93),light);
     sky=mix(sky,cloud,cover*.89);
    }
    // Work around the unit circle so the wrap behind the camera has no seam.
    // Fade the atmospheric silhouettes out as the camera rises into map view.
    if(abs(d.y)<.14 && cameraPosition.y<50.){
     vec2 bearing=normalize(d.xz);
     float sweep=.5+.5*dot(bearing,normalize(vec2(-.8,.55)));
     float high=.014+sweep*(.028+.044*noise(bearing*4.3+7.));
     high+=.009*noise(bearing*14.3);
     float low=.005+sweep*(.009+.024*noise(bearing*7.7+12.));
     low+=.0035*noise(bearing*49.)+.002*noise(bearing*125.);
     float aa=max(.0012,fwidth(d.y));
     float haze=(1.-smoothstep(4.,50.,cameraPosition.y))*smoothstep(-.035,-.004,d.y);
     vec3 distant=mix(vec3(.395,.565,.64),vec3(.48,.64,.71),noise(bearing*16.+h*32.));
     sky=mix(sky,distant,(1.-smoothstep(high-aa,high+aa,d.y))*haze);
     vec3 wooded=mix(vec3(.26,.425,.43),vec3(.345,.50,.49),noise(bearing*80.+h*39.));
     sky=mix(sky,wooded,(1.-smoothstep(low-aa,low+aa,d.y))*haze);
    }
    gl_FragColor=vec4(sky,1.);
    #include <colorspace_fragment>
   }`
 });
 const sky=new T.Mesh(new T.SphereGeometry(900,32,16),material);
 sky.frustumCulled=false;sky.renderOrder=-100;scene.add(sky);return sky;
}
