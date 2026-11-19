import * as T from './vendor/three.module.js';
export function comicPass(renderer,camera){
 renderer.info.autoReset=false;
 const target=new T.WebGLRenderTarget(1,1,{samples:4,type:T.HalfFloatType,minFilter:T.LinearFilter,magFilter:T.LinearFilter});target.depthTexture=new T.DepthTexture(1,1,T.UnsignedIntType);
 const uniforms={colorMap:{value:target.texture},depthMap:{value:target.depthTexture},pixel:{value:new T.Vector2(1,1)},far:{value:camera.far},strength:{value:.65}};
 const material=new T.ShaderMaterial({uniforms,depthTest:false,depthWrite:false,vertexShader:`varying vec2 uvScreen;void main(){uvScreen=uv;gl_Position=vec4(position.xy,0.,1.);}`,fragmentShader:`varying vec2 uvScreen;uniform sampler2D colorMap,depthMap;uniform vec2 pixel;uniform float far,strength;
 float distanceAt(vec2 uv){float z=texture2D(depthMap,uv).x;return exp2(z*log2(far+1.0))-1.0;}
 void main(){
 vec2 dx=vec2(pixel.x,0.),dy=vec2(0.,pixel.y);
 vec3 color=texture2D(colorMap,uvScreen).rgb;
 float d=distanceAt(uvScreen);
 // Narrow distant mullions can move through an entire pixel between frames.
 // Resolve isolated high-contrast strokes while leaving flat colours untouched.
 if(d>1.5 && d<far*.95){
   vec3 horizontal=.5*(texture2D(colorMap,uvScreen-dx).rgb+texture2D(colorMap,uvScreen+dx).rgb);
   vec3 vertical=.5*(texture2D(colorMap,uvScreen-dy).rgb+texture2D(colorMap,uvScreen+dy).rgb);
   const vec3 luma=vec3(.2126,.7152,.0722);
   float dh=abs(dot(horizontal-color,luma)),dv=abs(dot(vertical-color,luma));
   vec3 filtered=(horizontal*dh+vertical*dv)/max(dh+dv,.0001);
   float contrast=max(dh,dv)/(.08+dot(color,luma));
   color=mix(color,filtered,.45*smoothstep(.025,.3,contrast)*smoothstep(1.5,7.,d));
 }
 float l=distanceAt(uvScreen-dx),r=distanceAt(uvScreen+dx),u=distanceAt(uvScreen+dy),b=distanceAt(uvScreen-dy);
 float discontinuity=max(abs(l+r-2.*d),abs(u+b-2.*d))/max(d,.1);
 float ink=smoothstep(.018,.07,discontinuity)*(1.-smoothstep(65.,120.,d));
 color=mix(color,vec3(.022,.032,.038),ink*strength);gl_FragColor=vec4(color,1.);
 #include <tonemapping_fragment>
 if(d>far*.95)gl_FragColor.rgb=color;
 #include <colorspace_fragment>
 }`});
 const screen=new T.Scene();screen.add(new T.Mesh(new T.PlaneGeometry(2,2),material));const screenCamera=new T.Camera();
 return {enabled:true,resize(){const size=renderer.getDrawingBufferSize(new T.Vector2());target.setSize(size.x,size.y);uniforms.pixel.value.set(1/size.x,1/size.y)},render(scene){uniforms.far.value=camera.far;renderer.info.reset();if(!this.enabled){renderer.render(scene,camera);return;}renderer.setRenderTarget(target);renderer.render(scene,camera);renderer.setRenderTarget(null);renderer.render(screen,screenCamera)}};
}
