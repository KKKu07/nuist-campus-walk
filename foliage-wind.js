import * as T from './vendor/three.module.js';
import {surfaceTime} from './outdoor-style.js';
function sway(material){const previous=material.onBeforeCompile.bind(material),key=material.customProgramCacheKey();material.onBeforeCompile=shader=>{previous(shader);shader.uniforms.windTime=surfaceTime;shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nuniform float windTime;');shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',`#include <begin_vertex>
float wave=sin(windTime*1.1+position.x*.8+position.z*.63)*.014+sin(windTime*2.4+position.z*2.7)*.006;
float tipWeight=.3+.7*uv.y;
transformed.x+=wave*tipWeight;
transformed.z+=cos(windTime*.9+position.x*.7)*.009*tipWeight;`);};material.customProgramCacheKey=()=>key+'-leaf-wind-v1';}
export function windMaterials(mesh){sway(mesh.material);const depth=new T.MeshDepthMaterial({depthPacking:T.RGBADepthPacking,map:mesh.material.map,alphaTest:mesh.material.alphaTest,side:T.DoubleSide});sway(depth);mesh.customDepthMaterial=depth;}
