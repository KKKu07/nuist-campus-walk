// World builders: ground, roads, water, buildings (styled facades, hip roofs, parapets), trees, lamps, landmarks.
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { GROUND } from './palette.js';

export class GeoBuf {
  constructor() { this.p = []; this.n = []; this.u = []; this.c = []; }
  v(x, y, z, nx, ny, nz, u, w, col) { this.p.push(x, y, z); this.n.push(nx, ny, nz); this.u.push(u, w); this.c.push(col.r, col.g, col.b); }
  // triangle with its true normal, flipped to face up (roofs, ground-like surfaces); uv(x, z) -> [u, v]
  triFace(a, b, c, col, uv) {
    let ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    if (ny < 0) { [b, c] = [c, b]; nx = -nx; ny = -ny; nz = -nz; }
    const l = Math.hypot(nx, ny, nz) || 1;
    for (const q of [a, b, c]) { const [u, w] = uv(q[0], q[2]); this.v(q[0], q[1], q[2], nx / l, ny / l, nz / l, u, w, col); }
  }
  // vertical quad a-b at bottom, height range [y0, y1], normal (nx, nz)
  wall(ax, az, bx, bz, y0, y1, nx, nz, u0, u1, v0, v1, col) {
    this.v(ax, y0, az, nx, 0, nz, u0, v0, col); this.v(ax, y1, az, nx, 0, nz, u0, v1, col); this.v(bx, y0, bz, nx, 0, nz, u1, v0, col);
    this.v(bx, y0, bz, nx, 0, nz, u1, v0, col); this.v(ax, y1, az, nx, 0, nz, u0, v1, col); this.v(bx, y1, bz, nx, 0, nz, u1, v1, col);
  }
  box(cx, cz, y0, sx, sy, sz, ang, col) {      // axis = rotation about y
    const c = Math.cos(ang), s = Math.sin(ang);
    const P = (u, w) => [cx + u * c - w * s, cz + u * s + w * c];
    const hx = sx / 2, hz = sz / 2, y1 = y0 + sy;
    const pts = [P(-hx, -hz), P(hx, -hz), P(hx, hz), P(-hx, hz)];
    for (let i = 0; i < 4; i++) {
      const [ax, az] = pts[i], [bx, bz] = pts[(i + 1) % 4];
      const dx = bx - ax, dz = bz - az, l = Math.hypot(dx, dz) || 1;
      this.wall(ax, az, bx, bz, y0, y1, dz / l, -dx / l, 0.02, 0.02, 0.5, 0.5, col);
    }
    const t = (q) => [q[0], y1, q[1]];
    this.triFace(t(pts[0]), t(pts[1]), t(pts[2]), col, () => [0.02, 0.5]);
    this.triFace(t(pts[0]), t(pts[2]), t(pts[3]), col, () => [0.02, 0.5]);
  }
  empty() { return this.p.length === 0; }
  geometry() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.u, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.computeBoundingSphere();
    return g;
  }
}

// ---------------------------------------------------------------- CC0 photo textures (data/assets, see LICENSES.md)
export async function loadDetailTextures(aniso) {
  const loader = new THREE.TextureLoader(), out = {};
  await Promise.all(['grass', 'paving', 'dirt', 'asphalt', 'rooftiles'].map(async (n) => {
    try {
      const t = await loader.loadAsync(`tex/${n}.jpg`);
      t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = aniso;
      const c = document.createElement('canvas'); c.width = c.height = 16;
      const x = c.getContext('2d'); x.drawImage(t.image, 0, 0, 16, 16);
      const d = x.getImageData(0, 0, 16, 16).data; let r = 0, g = 0, b = 0;
      for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
      const k = d.length / 4, m = new THREE.Color().setRGB(r / k / 255, g / k / 255, b / k / 255, THREE.SRGBColorSpace);
      out[n] = { tex: t, mean: new THREE.Vector3(m.r, m.g, m.b) };
    } catch { /* texture is optional */ }
  }));
  return out;
}
const injectWPos = (sh) => {
  sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\n#ifdef USE_INSTANCING\nvWPos = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;\n#else\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;\n#endif');
};
// multiply a world-space tiling photo texture (normalised by its mean colour) into a material, fading with distance
export function addWorldDetail(mat, d, scale, strength, far = 160) {
  if (!d) return;
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.dMap = { value: d.tex }; sh.uniforms.dMean = { value: d.mean };
    injectWPos(sh);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;\nuniform sampler2D dMap;\nuniform vec3 dMean;')
      .replace('#include <map_fragment>', `#include <map_fragment>
      { float k = 1.0 - smoothstep(${(far * 0.25).toFixed(1)}, ${far.toFixed(1)}, length(vWPos - cameraPosition));
        vec3 dt = texture2D(dMap, vWPos.xz / ${scale.toFixed(2)}).rgb / max(dMean, vec3(0.02));
        diffuseColor.rgb *= mix(vec3(1.0), dt, ${strength.toFixed(2)} * k); }`);
  };
}

const hash = (x, z) => { const s = Math.sin(x * 12.9898 + z * 78.233) * 43758.5453; return s - Math.floor(s); };

// ---------------------------------------------------------------- ground
export function buildGround(ctx, T, orthoTex, detailTex, det = {}) {
  const { scene, W, D } = ctx;
  const g = new THREE.PlaneGeometry(W, D, T.nx - 1, T.nz - 1);
  g.rotateX(-Math.PI / 2);
  const pos = g.attributes.position;
  for (let k = 0; k < T.nz; k++) for (let i = 0; i < T.nx; i++) pos.setY(k * T.nx + i, T.h[k * T.nx + i] / 10);
  g.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ map: orthoTex, roughness: 0.95 });
  // up close the aerial photo is blurry; multiply in a tiling detail texture that fades out with distance
  const hasPhoto = det.grass && det.paving && det.dirt;
  const hasLC = hasPhoto && det.lc && det.asphalt;
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.detailMap = { value: detailTex };
    if (hasPhoto) {
      sh.uniforms.gMap = { value: det.grass.tex }; sh.uniforms.gMean = { value: det.grass.mean };
      sh.uniforms.pMap = { value: det.paving.tex }; sh.uniforms.pMean = { value: det.paving.mean };
      sh.uniforms.tMap = { value: det.dirt.tex }; sh.uniforms.tMean = { value: det.dirt.mean };
    }
    if (hasLC) {
      sh.uniforms.lcMap = { value: det.lc }; sh.uniforms.lcSize = { value: new THREE.Vector2(W, D) };
      sh.uniforms.aMap = { value: det.asphalt.tex }; sh.uniforms.aMean = { value: det.asphalt.mean };
      // 地表色板 (palette.js), linear; the canvas paving textures are drawn in the same colours
      const col = (k) => ({ value: new THREE.Color(GROUND[k]) });
      for (const k of ['lawn', 'lawnDry', 'shade', 'soil', 'asphalt', 'plaza', 'rubber', 'turf', 'court', 'stone']) sh.uniforms['u_' + k] = col(k);
      const s = new THREE.Color(GROUND.stone), dk = new THREE.Color(GROUND.stoneDark);
      sh.uniforms.u_darkK = { value: new THREE.Vector3(dk.r / s.r, dk.g / s.g, dk.b / s.b) };
      sh.uniforms.u_det = { value: detailStats(detailTex) };
      // smooth class edges everywhere: with every texture sampled once it costs about what the old single-tap shader did
      sh.defines = { ...(sh.defines || {}), GND_SMOOTH: '' };
    }
    // 0.5 m ground-material map (tools/ground_map.py) over the campus; the 1 m land cover elsewhere
    const gm = det.groundMeta;
    sh.uniforms.gndMap = { value: det.ground || det.lc };
    sh.uniforms.gndO = { value: new THREE.Vector2(gm ? gm.x0 : -W / 2, gm ? gm.z0 : -D / 2) };
    sh.uniforms.gndE = { value: new THREE.Vector2(gm ? gm.size[0] * gm.m_per_px : 0, gm ? gm.size[1] * gm.m_per_px : 0) };
    sh.uniforms.gndSize = { value: new THREE.Vector2(gm ? gm.size[0] : 1, gm ? gm.size[1] : 1) };
    sh.uniforms.tileMap = { value: det.tileTex || det.lc }; sh.uniforms.brickMap = { value: det.brickTex || det.lc };
    sh.uniforms.stoneMap = { value: det.stoneTex || det.tileTex || det.lc };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWPos;\nuniform sampler2D detailMap;' + (hasPhoto ? '\nuniform sampler2D gMap, pMap, tMap;\nuniform vec3 gMean, pMean, tMean;' : '') + (hasLC ? GROUND_FUNCS : ''))
      .replace('#include <map_fragment>', hasLC ? GROUND_LC : hasPhoto ? GROUND_PHOTO : `#include <map_fragment>
      {
        // close to the camera: grass blades on green ground, a paving grid on grey ground, noise on both
        float k = 1.0 - smoothstep(25.0, 220.0, length(vWPos - cameraPosition));
        float d = texture2D(detailMap, vWPos.xz / 3.0).r * 0.55 + texture2D(detailMap, vWPos.xz / 17.0).r * 0.45;
        vec3 c = diffuseColor.rgb;
        float green = clamp((c.g - max(c.r, c.b)) * 9.0 + 0.15, 0.0, 1.0);
        float grey = clamp(1.0 - (max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b))) * 8.0, 0.0, 1.0) * (1.0 - green);
        float blades = texture2D(detailMap, vWPos.xz * vec2(1.7, 0.35)).r;
        vec2 cell = abs(fract(vWPos.xz / 0.8) - 0.5);
        float joint = smoothstep(0.47, 0.5, max(cell.x, cell.y));
        float pattern = mix(1.0, 0.75 + blades * 0.45, green) * mix(1.0, 1.0 - joint * 0.35, grey * smoothstep(60.0, 10.0, length(vWPos - cameraPosition)));
        diffuseColor.rgb *= mix(1.0, d * 1.32 * pattern, 0.6 * k);
        diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.92, 1.06, 0.9), green * k * 0.5);
      }`);
    // underpass cuts (underpass.js): the terrain is not drawn over the sunken roads, their walls close the sides
    const cuts = (ctx.under?.segments || []).slice(0, 16);
    if (cuts.length) {
      sh.uniforms.uCut = { value: cuts.map(([ax, az, bx, bz]) => new THREE.Vector4(ax, az, bx, bz)) };
      sh.uniforms.uCutH = { value: cuts.map((c) => c[4]) };
      sh.fragmentShader = sh.fragmentShader.replace('void main() {', `uniform vec4 uCut[${cuts.length}]; uniform float uCutH[${cuts.length}];
void main() {
  for (int i = 0; i < ${cuts.length}; i++) { vec2 a = uCut[i].xy, e = uCut[i].zw - a, p = vWPos.xz; float t = dot(p - a, e) / max(dot(e, e), 1e-6);
    if (t > 0.0 && t < 1.0 && length(a + e * t - p) < uCutH[i]) discard; }`);
    }
  };
  const ground = new THREE.Mesh(g, mat);
  ground.receiveShadow = true;
  scene.add(ground);
  const R = 9000, shape = new THREE.Shape();
  shape.moveTo(-R, -R); shape.lineTo(R, -R); shape.lineTo(R, R); shape.lineTo(-R, R); shape.closePath();
  const hole = new THREE.Path();
  hole.moveTo(-W / 2, -D / 2); hole.lineTo(-W / 2, D / 2); hole.lineTo(W / 2, D / 2); hole.lineTo(W / 2, -D / 2); hole.closePath();
  shape.holes.push(hole);
  const outer = new THREE.Mesh(new THREE.ShapeGeometry(shape).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: '#7a8668', roughness: 1 }));
  outer.position.y = -1.5;
  scene.add(outer);
}

const GROUND_PHOTO = `#include <map_fragment>
      {
        float dist = length(vWPos - cameraPosition);
        float k = 1.0 - smoothstep(18.0, 190.0, dist);
        vec3 c = diffuseColor.rgb;
        float green = clamp((c.g - max(c.r, c.b)) * 9.0 + 0.15, 0.0, 1.0);
        float sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
        float grey = clamp(1.0 - sat * 8.0, 0.0, 1.0) * (1.0 - green);
        float dirtW = clamp(1.0 - green - grey, 0.0, 1.0);
        vec3 g = texture2D(gMap, vWPos.xz / 2.2).rgb / max(gMean, vec3(0.02));
        vec3 p = texture2D(pMap, vWPos.xz / 3.2).rgb / max(pMean, vec3(0.02));
        vec3 t = texture2D(tMap, vWPos.xz / 3.0).rgb / max(tMean, vec3(0.02));
        diffuseColor.rgb *= mix(vec3(1.0), g * green + p * grey + t * dirtW, 0.78 * k);
        diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.93, 1.05, 0.9), green * k * 0.4);
        float n = texture2D(detailMap, vWPos.xz / 17.0).r;
        diffuseColor.rgb *= mix(1.0, n * 1.3, 0.3);
      }`;

// mean / std of the procedural detail noise (textures.js detailTexture), so the shader can use it as unit noise
function detailStats(tex) {
  const im = tex?.image;
  if (!im?.getContext) return new THREE.Vector2(0.79, 0.06);
  const d = im.getContext('2d').getImageData(0, 0, im.width, im.height).data;
  let s = 0, s2 = 0, n = 0;
  for (let i = 0; i < d.length; i += 4 * 7) { const v = d[i] / 255; s += v; s2 += v * v; n++; }
  const m = s / n;
  return new THREE.Vector2(m, Math.sqrt(Math.max(1e-6, s2 / n - m * m)));
}

// 地表 (地表观感 2026-11-27). Ground classes (tools/ground_map.py, 0.5 m; outside it the 1 m land cover of
// tools/landcover.py uses the same ids 1-10): 1 lawn 2 planting under trees 3 grey granite 4 asphalt 5 water 6 track
// 7 turf 8 court 9 soil 10 building 11 light tiles 12 red brick 13 coloured plaza 14 dark granite.
// Every class is its palette colour (palette.js) x the texture's own variation, at every distance, so a surface looks
// the same from 2 m and from 300 m (no more fade to the blotchy winter aerial inside the campus) and matches the road
// meshes. Class edges: the 4 surrounding 0.5 m cells blended by bilinear weight, sharpened (W^4) -> smooth contours
// instead of 0.5 m staircases; a smooth +-0.35 m wobble keeps long edges from looking ruled.
const GROUND_FUNCS = `
uniform sampler2D lcMap, aMap, gndMap, tileMap, brickMap, stoneMap;
uniform vec2 lcSize, gndO, gndE, gndSize, u_det;
uniform vec3 aMean, u_lawn, u_lawnDry, u_shade, u_soil, u_asphalt, u_plaza, u_rubber, u_turf, u_court, u_stone, u_darkK;
// every texture is sampled once per pixel (uniform control flow), then shared by the up to 4 classes blended there
struct GS { vec3 g, t, a, st, ti, br; };
GS gSample(vec2 p) {
  GS s;
  s.g = texture2D(gMap, p / 2.2).rgb / max(gMean, vec3(0.02));
  s.t = texture2D(tMap, p / 2.6).rgb / max(tMean, vec3(0.02));
  s.a = texture2D(aMap, p / 3.5).rgb / max(aMean, vec3(0.02));
  s.st = texture2D(stoneMap, p / 4.0).rgb;
  s.ti = texture2D(tileMap, p / 4.0).rgb;
  s.br = texture2D(brickMap, p / 4.0).rgb;
  return s;
}
vec3 gCol(float c, GS s, vec3 c0, vec3 cOut, vec3 q) {
  if (c < 0.5) return cOut;
  if (c < 1.5) {                       // lawn: palette green x the grass photo's own variation, drier patches at ~60 m
    vec3 base = mix(u_lawn, u_lawnDry, smoothstep(0.7, 2.0, q.z) * 0.8);
    return base * mix(vec3(1.0), s.g, 0.75) * (1.0 + 0.05 * q.y);
  }
  if (c < 2.5) {                       // planting under trees: dark ground cover with leaf-litter / soil patches
    float soil = smoothstep(0.3, 1.6, q.y + q.x * 0.5);
    return mix(u_shade * mix(vec3(1.0), s.g, 0.7), u_soil * mix(vec3(1.0), s.t, 0.5), soil * 0.7);
  }
  if (c < 3.5) return s.st * (1.0 + 0.025 * q.y);
  if (c < 4.5) return u_asphalt * mix(vec3(1.0), s.a, 0.55) * (1.0 + 0.03 * q.y);
  if (c < 5.5) return c0;
  if (c < 6.5) return u_rubber * (1.0 + 0.06 * q.x);
  if (c < 7.5) return u_turf * mix(vec3(1.0), s.g, 0.4);
  if (c < 8.5) return u_court * (1.0 + 0.04 * q.x);
  if (c < 9.5) return u_soil * mix(vec3(1.0), s.t, 0.6);
  if (c < 10.5) return s.st;           // under a footprint: where a model is smaller than its outline, paving, not the roof in the aerial
  if (c < 11.5) return s.ti;
  if (c < 12.5) return s.br;
  if (c < 13.5) return u_plaza / u_stone * s.st;
  return s.st * u_darkK;
}
// outside the 0.5 m map: the aerial, pulled towards the palette by the 1 m land cover (more so up close)
vec3 gOutside(vec2 p, GS s, vec3 c0, vec3 q, float dist) {
  vec2 jit = q.yz * 1.2 / lcSize;
  vec2 luv = vec2((p.x + lcSize.x * 0.5) / lcSize.x, 1.0 - (p.y + lcSize.y * 0.5) / lcSize.y);
  float cls = floor(texture2D(lcMap, luv + jit).r * 255.0 + 0.5);
  vec3 a = c0 * (1.0 + 0.08 * q.y);
  // cyan in the aerial off the campus is dust netting over building sites (西苑 west), not water or lawn: grey it
  // and treat it as bare ground, so it no longer reads as a light-blue lake
  float cy = smoothstep(0.03, 0.12, min(c0.g, c0.b) - c0.r);
  a = mix(a, vec3(dot(a, vec3(0.3, 0.59, 0.11))) * vec3(1.02, 0.98, 0.9), cy);
  if (cy > 0.5 && cls > 0.5 && cls < 9.5) cls = 9.0;
  if (cls < 0.5) return a;
  return mix(a, gCol(cls, s, c0, c0, q), 0.35 + 0.4 * (1.0 - smoothstep(60.0, 400.0, dist)));
}
`;
const GROUND_LC = `#include <map_fragment>
      {
        vec3 c0 = diffuseColor.rgb;
        vec2 p = vWPos.xz;
        float dist = length(vWPos - cameraPosition);
        vec3 q = (vec3(texture2D(detailMap, p / 1.7).r, texture2D(detailMap, p / 17.0).r, texture2D(detailMap, p / 61.0).r) - u_det.x) / u_det.y;
        GS s = gSample(p);
        vec2 guv = (p - gndO) / max(gndE, vec2(1.0));
        vec3 col;
        if (gndE.x > 0.0 && guv.x > 0.0 && guv.x < 1.0 && guv.y > 0.0 && guv.y < 1.0) {
          // low-pass (mip bias 3) noise: a ~1 m undulation of the edges, no fine fringe
          vec2 wob = (vec2(texture2D(detailMap, p / 9.0, 3.0).r, texture2D(detailMap, p.yx / 7.3, 3.0).r) - u_det.x) / u_det.y;
          vec2 T = vec2(guv.x, 1.0 - guv.y) * gndSize - 0.5 + wob * vec2(0.22, -0.22);
          vec2 iv = 1.0 / gndSize;
#ifdef GND_SMOOTH
          vec2 i0 = floor(T), f = T - i0;
          vec4 cc = floor(vec4(texture2D(gndMap, (i0 + vec2(0.5, 0.5)) * iv).r, texture2D(gndMap, (i0 + vec2(1.5, 0.5)) * iv).r,
                               texture2D(gndMap, (i0 + vec2(0.5, 1.5)) * iv).r, texture2D(gndMap, (i0 + vec2(1.5, 1.5)) * iv).r) * 255.0 + 0.5);
          vec4 w = vec4((1.0 - f.x) * (1.0 - f.y), f.x * (1.0 - f.y), (1.0 - f.x) * f.y, f.x * f.y);
          vec4 Wc = vec4(dot(w, vec4(equal(cc, cc.xxxx))), dot(w, vec4(equal(cc, cc.yyyy))), dot(w, vec4(equal(cc, cc.zzzz))), dot(w, vec4(equal(cc, cc.wwww))));
          vec4 first = vec4(1.0, step(0.5, abs(cc.y - cc.x)), step(0.5, abs(cc.z - cc.x)) * step(0.5, abs(cc.z - cc.y)),
                            step(0.5, abs(cc.w - cc.x)) * step(0.5, abs(cc.w - cc.y)) * step(0.5, abs(cc.w - cc.z)));
          // sharper edges up close, softer far away (fewer sparkles where a pixel spans several cells)
          vec4 e = pow(max(Wc, vec4(1e-4)), vec4(mix(4.0, 1.6, smoothstep(120.0, 500.0, dist)))) * first;
          e /= dot(e, vec4(1.0));
          vec3 cOut = any(lessThan(cc, vec4(0.5))) ? gOutside(p, s, c0, q, dist) : c0;
          col = e.x * gCol(cc.x, s, c0, cOut, q);
          if (e.y > 0.0) col += e.y * gCol(cc.y, s, c0, cOut, q);
          if (e.z > 0.0) col += e.z * gCol(cc.z, s, c0, cOut, q);
          if (e.w > 0.0) col += e.w * gCol(cc.w, s, c0, cOut, q);
#else
          float gc = floor(texture2D(gndMap, (floor(T) + 0.5) * iv).r * 255.0 + 0.5);
          col = gc > 0.5 ? gCol(gc, s, c0, c0, q) : gOutside(p, s, c0, q, dist);
#endif
        } else col = gOutside(p, s, c0, q, dist);
        diffuseColor.rgb = col;
      }`;

// ---------------------------------------------------------------- roads: asphalt, lane markings, curbs, sidewalks
// Per road (campus.json): w = carriageway width, sw = sidewalk width each side (0 = none), oneway, kind, name.
// Markings follow GB 5768 practice: public roads 4+ lanes double yellow centre line, 2 lanes single yellow,
// lane dividers white dashed 2 m / 4 m gap (6 m / 9 m on the expressway), edge lines white; campus lanes a
// yellow dashed centre line; one-way carriageways yellow on the median side.
const NONCAR = new Set(['footway', 'path', 'steps', 'cycleway', 'track', 'pedestrian']);
const PUBLIC_K = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary']);
export function roadIndex(roads) {
  const grid = new Map(), C = 20;
  for (const r of roads) {
    if (r.w < 3.5 || NONCAR.has(r.kind)) continue;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [ax, az] = r.pts[i], [bx, bz] = r.pts[i + 1], pad = r.w / 2 + 1;
      for (let cx = Math.floor((Math.min(ax, bx) - pad) / C); cx <= Math.floor((Math.max(ax, bx) + pad) / C); cx++)
        for (let cz = Math.floor((Math.min(az, bz) - pad) / C); cz <= Math.floor((Math.max(az, bz) + pad) / C); cz++) {
          const k = cx * 100003 + cz;
          if (!grid.has(k)) grid.set(k, []);
          grid.get(k).push([r, ax, az, bx, bz]);
        }
    }
  }
  // is (x, z) on the carriageway of a road other than `self` (margin m beyond its edge)?
  return (x, z, self, margin = 0.1) => {
    const lst = grid.get(Math.floor(x / C) * 100003 + Math.floor(z / C));
    if (!lst) return false;
    for (const [r, ax, az, bx, bz] of lst) {
      if (r === self) continue;
      const dx = bx - ax, dz = bz - az, L2 = dx * dx + dz * dz;
      const t = L2 ? Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / L2)) : 0;
      if (Math.hypot(ax + dx * t - x, az + dz * t - z) < r.w / 2 + margin) return true;
    }
    return false;
  };
}
export function buildRoads(ctx, roads, tex, det = {}) {
  const { scene, heightAt } = ctx;
  const onOther = ctx.onRoad || (ctx.onRoad = roadIndex(roads));
  const bufs = { main: new GeoBuf(), minor: new GeoBuf(), paving: new GeoBuf(), track: new GeoBuf(), walk: new GeoBuf(), pavingRed: new GeoBuf(), walkRed: new GeoBuf() };
  const curb = new GeoBuf(), mark = new GeoBuf();
  const bridgeSpots = [], deckPts = [];
  const white = new THREE.Color('#ffffff'), curbC = new THREE.Color(GROUND.curb), lineW = new THREE.Color('#ecebe6'), lineY = new THREE.Color('#e3b937');
  const uvOf = (map) => (x, z) => { for (const [q, uv] of map) if (q[0] === x && q[2] === z) return uv; return [0, 0]; };
  const quad = (b, p0, p1, p2, p3, uv) => {
    const m = uv ? new Map([[p0, uv[0]], [p1, uv[1]], [p2, uv[2]], [p3, uv[3]]]) : null;
    const f = m ? uvOf(m) : () => [0, 0];
    const col = b === curb ? curbC : b.col || white;
    b.triFace(p0, p1, p2, col, f); b.triFace(p2, p1, p3, col, f);
  };
  for (const r of roads) {
    const car = !NONCAR.has(r.kind) && r.w >= 5.5;
    const kind = !car ? (r.kind === 'track' ? 'track' : 'paving') : PUBLIC_K.has(r.kind) ? 'main' : 'minor';
    const pts = [];
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1];
      const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, z1 - z0) / 4));
      for (let k = 0; k < n; k++) pts.push([x0 + (x1 - x0) * k / n, z0 + (z1 - z0) * k / n]);
    }
    pts.push(r.pts[r.pts.length - 1]);
    if (pts.length < 2) continue;
    const hw = r.w / 2, lift = 0.16 + Math.min(r.w, 18) * 0.006;
    const sw = car ? (r.sw ?? (r.w >= 7 ? 2.4 : 0)) : 0, CW = 0.18;
    // bridge decks: level across each water crossing, 10 m approach ramps, footbridges arched (official map); the deck
    // ~0.95 m over the water / 0.35 m over the bank (banks are levelled ~0.6 m above the water, tools/campus_terrain.py),
    // so a crossing climbs ~0.35 m, not a 1 m hump in 6 m; many bridges are their own short OSM way, so the ramp
    // cannot reach into the next way (地表观感: 跨湖的路和桥要缓)
    const BR_RAMP = 10;
    const pre = pts.map(([x, z]) => { const wl = ctx.waterAt ? ctx.waterAt(x, z) : null; return wl === null ? null : Math.max(wl + 0.95, heightAt(x, z) + 0.35); });
    const sArr = [0];
    for (let i = 1; i < pts.length; i++) sArr.push(sArr[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const decks = pre.slice();
    for (let i = 0; i < pts.length;) {
      if (pre[i] === null) { i++; continue; }
      let j = i;
      while (j < pts.length && pre[j] !== null) j++;
      const S0 = sArr[i] - 4, S1 = sArr[j - 1] + 4, top = Math.max(...pre.slice(i, j));
      const arch = NONCAR.has(r.kind) ? Math.min(1.5, (S1 - S0) * 0.07) : 0;
      for (let k = i; k < j; k++) decks[k] = top + arch * Math.sin(Math.PI * (sArr[k] - S0) / (S1 - S0));
      for (let k = i - 1; k >= 0 && pre[k] === null && sArr[i] - sArr[k] < BR_RAMP; k--) {
        const g = heightAt(pts[k][0], pts[k][1]), t = 1 - (sArr[i] - sArr[k]) / BR_RAMP;
        decks[k] = Math.max(g, g + (decks[i] - g) * t);
      }
      for (let k = j; k < pts.length && pre[k] === null && sArr[k] - sArr[j - 1] < BR_RAMP; k++) {
        const g = heightAt(pts[k][0], pts[k][1]), t = 1 - (sArr[k] - sArr[j - 1]) / BR_RAMP;
        decks[k] = Math.max(g, g + (decks[j - 1] - g) * t);
      }
      i = j;
    }
    // a public road crossing over an underpass cut (underpass.js): its own deck / ramp levels, not the cut floor
    const ov = ctx.under ? pts.map(([x, z]) => ctx.under.upperAt(r, x, z)) : null;
    const hAt = ctx.under?.isUpper(r) ? ctx.terrainAt : heightAt;     // a road over a cut never dips into it
    if (ov) for (let k = 0; k < pts.length; k++) if (ov[k] !== null) decks[k] = ov[k];
    const rows = [];
    let s = 0;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[Math.max(0, i - 1)], c = pts[Math.min(pts.length - 1, i + 1)];
      let dx = c[0] - a[0], dz = c[1] - a[1];
      const len = Math.hypot(dx, dz) || 1;
      dx /= len; dz /= len;
      if (i > 0) s += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      const nx = -dz, nz = dx, [x, z] = pts[i];
      const deck = decks[i];
      if (pre[i] !== null) bridgeSpots.push([x, z, deck, nx, nz, hw + sw]);
      if (deck !== null && !(ov && ov[i] !== null)) deckPts.push([x, z, deck + lift + (sw > 0 ? 0.15 : 0), nx, nz, hw + sw + 0.2]);
      const at = (o, up) => [x + nx * o, (deck ?? hAt(x + nx * o, z + nz * o)) + lift + up, z + nz * o];
      const row = { s, x, z, nx, nz, L: at(hw, 0), R: at(-hw, 0) };
      // no sidewalks inside a vehicle tunnel cut (the pedestrians have their own tunnel)
      if (sw > 0 && ctx.under && hAt === heightAt && ctx.under.inTunnel(x, z)) row.Lin = row.Rin = true;
      else if (sw > 0) {
        row.Lf = at(hw, 0); row.Lt = at(hw, 0.15); row.Lc = at(hw + CW, 0.15); row.Lo = at(hw + sw, 0.15);
        row.Rf = at(-hw, 0); row.Rt = at(-hw, 0.15); row.Rc = at(-hw - CW, 0.15); row.Ro = at(-hw - sw, 0.15);
        row.Lin = onOther(row.Lo[0], row.Lo[2], r, 0.3) || onOther(row.Lt[0], row.Lt[2], r, 0.3);
        row.Rin = onOther(row.Ro[0], row.Ro[2], r, 0.3) || onOther(row.Rt[0], row.Rt[2], r, 0.3);
      }
      rows.push(row);
    }
    // sidewalks along carriageways: light tiles (user: main-road walks are white tiles); footpaths keep their own colour
    const red = r.pave === 'red', buf = kind === 'paving' && red ? bufs.pavingRed : bufs[kind], walkBuf = bufs.walk;
    const tile = kind === 'paving' || kind === 'track' ? 4 : 8;
    for (let i = 0; i < rows.length - 1; i++) {
      const A = rows[i], B = rows[i + 1];
      quad(buf, A.L, A.R, B.L, B.R, [[0, A.s / tile], [r.w / tile, A.s / tile], [0, B.s / tile], [r.w / tile, B.s / tile]]);
      if (sw > 0) {
        if (!A.Lin && !B.Lin) {
          curb.wall(A.Lf[0], A.Lf[2], B.Lf[0], B.Lf[2], Math.min(A.Lf[1], B.Lf[1]) - 0.02, Math.max(A.Lt[1], B.Lt[1]), -A.nx, -A.nz, 0, 0, 0, 0, curbC);
          quad(curb, A.Lt, A.Lc, B.Lt, B.Lc);
          quad(walkBuf, A.Lo, A.Lc, B.Lo, B.Lc, [[0, A.s / 4], [sw / 4, A.s / 4], [0, B.s / 4], [sw / 4, B.s / 4]]);
        }
        if (!A.Rin && !B.Rin) {
          curb.wall(A.Rf[0], A.Rf[2], B.Rf[0], B.Rf[2], Math.min(A.Rf[1], B.Rf[1]) - 0.02, Math.max(A.Rt[1], B.Rt[1]), A.nx, A.nz, 0, 0, 0, 0, curbC);
          quad(curb, A.Rc, A.Rt, B.Rc, B.Rt);
          quad(walkBuf, A.Rc, A.Ro, B.Rc, B.Ro, [[0, A.s / 4], [sw / 4, A.s / 4], [0, B.s / 4], [sw / 4, B.s / 4]]);
        }
      }
    }
    if (car && r.w >= 6) addMarkings(r, rows, hw, mark, lineW, lineY, onOther);
  }
  // bridge-deck lookup (player, bus and walkers stand on the deck, not in the riverbed)
  const dgrid = new Map(), DC = 6;
  for (const d of deckPts) { const k = Math.floor(d[0] / DC) * 100003 + Math.floor(d[1] / DC); if (!dgrid.has(k)) dgrid.set(k, []); dgrid.get(k).push(d); }
  ctx.deckAt = (x, z) => {
    let best = null;
    const cx = Math.floor(x / DC), cz = Math.floor(z / DC);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      const lst = dgrid.get((cx + i) * 100003 + cz + j);
      if (!lst) continue;
      for (const [px, pz, y, nx, nz, half] of lst) {
        const dx = x - px, dz = z - pz, across = Math.abs(dx * nx + dz * nz), along = Math.abs(dx * nz - dz * nx);
        if (across < half && along < 2.6 && (best === null || y > best)) best = y;
      }
    }
    return best;
  };
  ctx.surfaceAt = (x, z) => { const d = ctx.deckAt(x, z), g = heightAt(x, z); return d !== null && d > g ? d : g; };
  const mk = (map, extra = {}) => new THREE.MeshStandardMaterial({ map, roughness: 0.92, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, ...extra });
  const mats = { main: mk(tex.main), minor: mk(tex.minor), paving: mk(tex.paving), track: mk(tex.track), walk: mk(tex.tile || tex.paving, { side: THREE.DoubleSide }),
    pavingRed: mk(tex.brick || tex.paving), walkRed: mk(tex.brick || tex.paving, { side: THREE.DoubleSide }) };
  if (bridgeSpots.length) {
    const br = new GeoBuf(), bc = new THREE.Color('#c9c5bb');
    const fc = new THREE.Color('#b3ada2');
    for (const [x, z, deck, nx, nz, hw] of bridgeSpots) for (const s of [-1, 1]) {
      const bx = x + nx * (hw + 0.3) * s, bz = z + nz * (hw + 0.3) * s, ang = Math.atan2(nz, nx);
      br.box(bx, bz, deck, 0.3, 1.1, 0.3, ang, bc);                   // baluster post
      br.box(bx, bz, deck + 1.0, 0.26, 0.12, 4.3, ang, bc);           // continuous handrail
      br.box(bx, bz, deck - 0.9, 0.42, 1.05, 4.3, ang, fc);           // deck edge fascia
    }
    const bm = new THREE.Mesh(br.geometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8 })); bm.castShadow = true; scene.add(bm);
  }
  addWorldDetail(mats.main, det.asphalt, 3, 0.55); addWorldDetail(mats.minor, det.asphalt, 3, 0.55);
  // paving textures carry the palette colour and pattern (textures.js); only a light aggregate grain on top (地表色板)
  addWorldDetail(mats.paving, det.asphalt, 2.6, 0.18); addWorldDetail(mats.walk, det.asphalt, 2.6, 0.12); addWorldDetail(mats.track, det.dirt, 3, 0.6);
  addWorldDetail(mats.pavingRed, det.asphalt, 2.6, 0.15); addWorldDetail(mats.walkRed, det.asphalt, 2.6, 0.15);
  for (const [k, b] of Object.entries(bufs)) {
    if (b.empty()) continue;
    const m = new THREE.Mesh(b.geometry(), mats[k]);
    m.receiveShadow = true;
    scene.add(m);
  }
  if (!curb.empty()) {
    const cm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    addWorldDetail(cm, det.asphalt, 1.5, 0.3);
    const m = new THREE.Mesh(curb.geometry(), cm); m.receiveShadow = true; scene.add(m);
  }
  if (!mark.empty()) {
    const mm = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
    const m = new THREE.Mesh(mark.geometry(), mm); m.receiveShadow = true; scene.add(m);
  }
}

// lane lines for one road: list of [offset from centre, colour, dash on, dash off, width]
function laneLines(r) {
  const pub = PUBLIC_K.has(r.kind), hw = r.w / 2, out = [];
  const dash = r.kind === 'trunk' || r.kind === 'motorway' ? [6, 9] : [2, 4];
  if (r.oneway) {
    const n = Math.max(1, Math.round(r.w / 3.5)), lw = r.w / n;
    out.push([hw - 0.3, 'y', 0, 0, 0.15], [-hw + 0.3, 'w', 0, 0, 0.15]);   // left (median side) yellow, right edge white
    for (let k = 1; k < n; k++) out.push([hw - k * lw, 'w', ...dash, 0.15]);
    return out;
  }
  if (pub) {
    const per = Math.max(1, Math.round(r.w / 7)), lw = hw / per;
    if (per >= 2) out.push([0.15, 'y', 0, 0, 0.15], [-0.15, 'y', 0, 0, 0.15]);
    else out.push([0, 'y', 0, 0, 0.15]);
    for (let k = 1; k < per; k++) out.push([k * lw, 'w', ...dash, 0.15], [-k * lw, 'w', ...dash, 0.15]);
    out.push([hw - 0.3, 'w', 0, 0, 0.15], [-hw + 0.3, 'w', 0, 0, 0.15]);
    return out;
  }
  out.push([0, 'y', 2, 4, 0.12]);                         // campus lane: yellow dashed centre line
  if (r.w >= 7) out.push([hw - 0.3, 'w', 0, 0, 0.12], [-hw + 0.3, 'w', 0, 0, 0.12]);
  return out;
}

function addMarkings(r, rows, hw, mark, lineW, lineY, onOther) {
  for (const [o, c, on, off, lw] of laneLines(r)) {
    const col = c === 'y' ? lineY : lineW, period = on + off;
    const f = (o + hw) / (2 * hw);
    const P = (row, t, s2) => {   // point on the road surface at lateral offset o + s2 between rows
      const y = row.R[1] + (row.L[1] - row.R[1]) * f + 0.02;
      return [row.x + row.nx * (o + s2), y, row.z + row.nz * (o + s2)];
    };
    for (let i = 0; i < rows.length - 1; i++) {
      const A = rows[i], B = rows[i + 1], segL = B.s - A.s;
      if (segL < 0.01) continue;
      const pieces = [];
      if (!on) pieces.push([0, 1]);
      else {
        let k = Math.floor(A.s / period) * period;
        for (; k < B.s; k += period) {
          const a = Math.max(A.s, k), b = Math.min(B.s, k + on);
          if (b > a + 0.05) pieces.push([(a - A.s) / segL, (b - A.s) / segL]);
        }
      }
      for (const [t0, t1] of pieces) {
        const lerp = (t) => ({ x: A.x + (B.x - A.x) * t, z: A.z + (B.z - A.z) * t, nx: A.nx + (B.nx - A.nx) * t, nz: A.nz + (B.nz - A.nz) * t,
          L: [0, A.L[1] + (B.L[1] - A.L[1]) * t], R: [0, A.R[1] + (B.R[1] - A.R[1]) * t] });
        const a = lerp(t0), b = lerp(t1);
        a.L = [0, a.L[1]]; a.R = [0, a.R[1]]; b.L = [0, b.L[1]]; b.R = [0, b.R[1]];
        const mx = (a.x + b.x) / 2 + a.nx * o, mz = (a.z + b.z) / 2 + a.nz * o;
        if (onOther(mx, mz, r, 0.5)) continue;                 // no lines across junctions
        const p0 = P(a, 0, -lw / 2), p1 = P(a, 0, lw / 2), p2 = P(b, 0, -lw / 2), p3 = P(b, 0, lw / 2);
        mark.triFace(p0, p1, p2, col, () => [0, 0]); mark.triFace(p2, p1, p3, col, () => [0, 0]);
      }
    }
  }
}

// ---------------------------------------------------------------- junction patches (hide crossing lane lines) and zebra crossings
export function buildJunctions(ctx, junctions, det = {}) {
  if (!junctions?.length) return;
  const { scene, heightAt } = ctx;
  const disc = new GeoBuf(), zebra = new GeoBuf(), white = new THREE.Color('#ffffff');
  // patch and stripes follow the terrain vertex by vertex (常识排查: flat at the centre height, sloped junctions had
  // their patch edge floating up to 1.2 m over the road on one side and sunk under it on the other)
  const Y = (x, z, up) => [x, heightAt(x, z) + up, z];
  for (const j of junctions) {
    const n = 28, rings = [0.5, 1];
    for (let i = 0; i < n; i++) {
      const a0 = i / n * Math.PI * 2, a1 = (i + 1) / n * Math.PI * 2, c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
      disc.triFace(Y(j.x, j.z, 0.3), Y(j.x + c0 * j.r * rings[0], j.z + s0 * j.r * rings[0], 0.3), Y(j.x + c1 * j.r * rings[0], j.z + s1 * j.r * rings[0], 0.3), white, (x, z) => [x / 4, z / 4]);
      const p0 = Y(j.x + c0 * j.r * rings[0], j.z + s0 * j.r * rings[0], 0.3), p1 = Y(j.x + c0 * j.r, j.z + s0 * j.r, 0.3);
      const p2 = Y(j.x + c1 * j.r * rings[0], j.z + s1 * j.r * rings[0], 0.3), p3 = Y(j.x + c1 * j.r, j.z + s1 * j.r, 0.3);
      disc.triFace(p0, p1, p2, white, (x, z) => [x / 4, z / 4]); disc.triFace(p2, p1, p3, white, (x, z) => [x / 4, z / 4]);
    }
    for (const [x, z, ang, wd] of j.cross) {
      const dx = Math.cos(ang), dz = Math.sin(ang), nx = -dz, nz = dx;
      for (let o = -wd / 2 + 0.7; o <= wd / 2 - 0.7; o += 1.0) {
        const cx = x + nx * o, cz = z + nz * o, P = (a, b) => Y(cx + dx * a + nx * b, cz + dz * a + nz * b, 0.32);
        zebra.triFace(P(-1.5, -0.22), P(1.5, -0.22), P(1.5, 0.22), white, () => [0, 0]);
        zebra.triFace(P(-1.5, -0.22), P(1.5, 0.22), P(-1.5, 0.22), white, () => [0, 0]);
      }
    }
  }
  const dm = new THREE.MeshStandardMaterial({ color: GROUND.asphalt, roughness: 0.92, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
  addWorldDetail(dm, det.asphalt, 3, 0.55);
  const zm = new THREE.MeshStandardMaterial({ color: '#eeeeea', roughness: 0.7, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  for (const [buf, mat] of [[disc, dm], [zebra, zm]]) { if (buf.empty()) continue; const m = new THREE.Mesh(buf.geometry(), mat); m.receiveShadow = true; scene.add(m); }
}

// ---------------------------------------------------------------- water
export function buildWater(ctx, list, normalTex, roads = []) {
  const { scene, heightAt, inCampus } = ctx;
  const buf = new GeoBuf(), bank = new GeoBuf(), rail = new GeoBuf();
  // the bank railing leaves a gap wherever a road or path crosses the bank (bridges), carriageway + sidewalks + 0.8 m
  const segs = [];
  for (const r of roads) for (let i = 0; i < r.pts.length - 1; i++) segs.push([...r.pts[i], ...r.pts[i + 1], r.w / 2 + (r.sw || 0) + 0.8]);
  const onCrossing = (x, z) => segs.some(([ax, az, bx, bz, hw]) => {
    if (x < Math.min(ax, bx) - hw || x > Math.max(ax, bx) + hw || z < Math.min(az, bz) - hw || z > Math.max(az, bz) + hw) return false;
    const ex = bx - ax, ez = bz - az, l2 = ex * ex + ez * ez || 1e-9, t = Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2));
    return Math.hypot(ax + ex * t - x, az + ez * t - z) < hw;
  });
  const col = new THREE.Color('#ffffff'), stone = new THREE.Color('#8f8a7e'), railC = new THREE.Color('#d9d6cf');
  const pools = [];
  for (const w of list) {
    const pts = w.pts.map(([x, z]) => new THREE.Vector2(x, z));
    if (pts.length < 3) continue;
    const level = w.level ?? pts.reduce((s, p) => s + heightAt(p.x, p.y), 0) / pts.length - 0.6;
    pools.push({ pts: w.pts, level });
    let tris = [];
    try { tris = THREE.ShapeUtils.triangulateShape(pts, []); } catch { tris = []; }
    for (const [a, b, c] of tris) {
      buf.triFace([pts[a].x, level, pts[a].y], [pts[b].x, level, pts[b].y], [pts[c].x, level, pts[c].y], col, (x, z) => [x / 18, z / 18]);
    }
    // stone embankment from below the water line up to the bank, and a railing along campus banks
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], c = pts[(i + 1) % pts.length];
      const len = Math.hypot(c.x - a.x, c.y - a.y);
      if (len < 0.3) continue;
      const top = Math.max(heightAt(a.x, a.y), heightAt(c.x, c.y), level + 0.5) + 0.25;
      const nx = (c.y - a.y) / len, nz = -(c.x - a.x) / len;
      bank.wall(a.x, a.y, c.x, c.y, level - 1.2, top, nx, nz, 0, len / 2, 0, 1, stone);
      bank.wall(c.x, c.y, a.x, a.y, level - 1.2, top, -nx, -nz, 0, len / 2, 0, 1, stone);
      if (inCampus((a.x + c.x) / 2, (a.y + c.y) / 2) && len > 0.5) {
        // railing in runs of 0.5 m steps, broken where a road or path crosses the bank
        const n = Math.max(1, Math.ceil(len / 0.5)), P = (k) => [a.x + (c.x - a.x) * k / n, a.y + (c.y - a.y) * k / n];
        let run = -1;
        for (let k = 0; k <= n; k++) {
          const [x, z] = P(k), free = k < n && !onCrossing(...P(k + 0.5));
          if (free && run < 0) run = k;
          if (!free && run >= 0) {
            const [x0, z0] = P(run);
            rail.wall(x0, z0, x, z, top + 0.95, top + 1.05, nx, nz, 0, 0, 0, 0, railC);
            rail.wall(x, z, x0, z0, top + 0.95, top + 1.05, -nx, -nz, 0, 0, 0, 0, railC);
            for (let t = 0; t <= Math.hypot(x - x0, z - z0) + 0.01; t += 2.5) {
              const f = t / (Math.hypot(x - x0, z - z0) || 1);
              rail.box(x0 + (x - x0) * f, z0 + (z - z0) * f, top, 0.08, 1.05, 0.08, 0, railC);
            }
            run = -1;
          }
        }
      }
    }
  }
  normalTex.wrapS = normalTex.wrapT = THREE.RepeatWrapping;
  const mat = new THREE.MeshStandardMaterial({ color: '#2a5661', roughness: 0.08, metalness: 0.1, normalMap: normalTex,
    normalScale: new THREE.Vector2(0.42, 0.42), transparent: true, opacity: 0.93, envMapIntensity: 1.4 });
  // one ripple tile repeated every 18 m reads as a pattern of blotches: blend three rotated scales of it instead
  mat.onBeforeCompile = (sh) => {
    sh.fragmentShader = sh.fragmentShader.replace('vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;', `vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
      vec3 mapN2 = texture2D( normalMap, mat2(0.8, -0.6, 0.6, 0.8) * vNormalMapUv * 2.7 + vec2(0.37, 0.11) ).xyz * 2.0 - 1.0;
      vec3 mapN3 = texture2D( normalMap, mat2(0.28, 0.96, -0.96, 0.28) * vNormalMapUv * 0.43 + vec2(0.13, 0.71) ).xyz * 2.0 - 1.0;
      mapN = normalize(vec3(mapN.xy * 0.45 + mapN2.xy * 0.4 + mapN3.xy * 0.4, 1.0));`);
  };
  if (!buf.empty()) scene.add(new THREE.Mesh(buf.geometry(), mat));
  for (const [b, m] of [[bank, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 })], [rail, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5 })]]) {
    if (b.empty()) continue;
    const mesh = new THREE.Mesh(b.geometry(), m); mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh);
  }
  // 性能: point-in-polygon tests only the edges spanning the point's 2 m z-band (same edges the ray can cross, so the
  // result is identical); bankApron, tree / prop placement and the sanity rules call this hundreds of thousands of times
  const BAND = 2;
  for (const pl of pools) {
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
    for (const [x, z] of pl.pts) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z); }
    const nb = Math.max(1, Math.ceil((z1 - z0) / BAND) + 1), bands = Array.from({ length: nb }, () => []);
    for (let i = 0, j = pl.pts.length - 1; i < pl.pts.length; j = i++) {
      const a = Math.min(pl.pts[i][1], pl.pts[j][1]), b = Math.max(pl.pts[i][1], pl.pts[j][1]);
      for (let k = Math.floor((a - z0) / BAND); k <= Math.floor((b - z0) / BAND); k++) bands[k].push(i, j);
    }
    pl.ix = { x0, x1, z0, z1, bands };
  }
  const inPoly = (x, z, pl) => {
    const { x0, x1, z0, z1, bands } = pl.ix;
    if (x < x0 || x > x1 || z < z0 || z > z1) return false;
    const e = bands[Math.floor((z - z0) / BAND)], pts = pl.pts;
    let s = false;
    for (let n = 0; n < e.length; n += 2) { const [xi, zi] = pts[e[n]], [xj, zj] = pts[e[n + 1]]; if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) s = !s; }
    return s;
  };
  // water level under a point (for bridges), or null on dry land
  ctx.waterAt = (x, z) => { for (const pl of pools) if (inPoly(x, z, pl)) return pl.level; return null; };
  return mat;
}

// ---------------------------------------------------------------- buildings
const KIND_COLOR = { dorm: '#dcc4a2', teach: '#e8e4dd', hall: '#efece6', canteen: '#e7d5b8', other: '#d6d1c8', apartment: '#ece8df', wall: '#d2cabb' };
const KIND_STYLE = { dorm: 'dorm', apartment: 'apartment', hall: 'hall', canteen: 'modern', teach: 'modern', other: 'modern' };

export function buildBuildings(ctx, list, facadeMats, orthoTex, det = {}, roofTex = null) {
  const { scene, heightAt, inCampus, W, D } = ctx;
  const facade = {}, roofBuf = new GeoBuf(), hipBuf = new GeoBuf(), plainBuf = new GeoBuf(), pvBuf = new GeoBuf();
  const roofC = new THREE.Color(), pvC = new THREE.Color('#22304f');
  const worldUV = (x, z) => [x / 4, z / 4];
  const wallC = new THREE.Color(), plainC = new THREE.Color(), grey = new THREE.Color('#bab7b1'), white = new THREE.Color('#ffffff');
  const orthoUV = (x, z) => [(x + W / 2) / W, 1 - (z + D / 2) / D];
  const out = [];
  for (const b of list) {
    let pts = b.pts.map(([x, z]) => new THREE.Vector2(x, z));
    pts = pts.filter((p, i) => i === 0 || p.distanceTo(pts[i - 1]) > 0.05);
    if (pts.length > 3 && pts[0].distanceTo(pts[pts.length - 1]) < 0.05) pts.pop();
    if (pts.length < 3) continue;
    if (THREE.ShapeUtils.isClockWise(pts)) pts.reverse();
    let base = Infinity, cx = 0, cz = 0, minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const p of pts) {
      base = Math.min(base, heightAt(p.x, p.y));
      cx += p.x; cz += p.y;
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minZ = Math.min(minZ, p.y); maxZ = Math.max(maxZ, p.y);
    }
    cx /= pts.length; cz /= pts.length;
    const top = base + b.h, bot = base - 1.5;
    const campus = b.campus ?? inCampus(cx, cz);
    const isWall = b.kind === 'wall';
    const style = isWall ? 'wall' : (b.style || KIND_STYLE[b.kind] || 'modern');
    wallC.set(b.color || KIND_COLOR[b.kind] || KIND_COLOR.other);
    if (!campus && !isWall) wallC.lerp(grey, 0.45);
    plainC.copy(wallC).multiplyScalar(0.9);
    const hide = b.replaced || b.generic;       // landmark GLB or Blender generic chunk stands here instead
    const buf = hide ? new GeoBuf() : isWall ? plainBuf : (facade[style] ??= new GeoBuf());
    const rBuf = hide ? new GeoBuf() : roofBuf, hBuf = hide ? new GeoBuf() : hipBuf, pBuf = hide ? new GeoBuf() : plainBuf;
    // walls, one bay = 3.2 m, one floor = 3.6 m
    let s = 0, longest = 0, ang = 0;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], c = pts[(i + 1) % pts.length];
      const dx = c.x - a.x, dz = c.y - a.y, len = Math.hypot(dx, dz);
      if (len < 0.01) continue;
      if (len > longest) { longest = len; ang = Math.atan2(dz, dx); }
      const bays = Math.max(1, Math.round(len / 3.2));
      const u0 = isWall ? 0.02 : s, u1 = isWall ? 0.02 : s + bays;   // whole bays per edge, so windows never get cut
      s += bays;
      buf.wall(a.x, a.y, c.x, c.y, bot, top, dz / len, -dx / len, u0, u1, isWall ? 0.5 : (bot - base) / 3.6, isWall ? 0.5 : (top - base) / 3.6, isWall ? plainC : wallC);
    }
    const hip = b.roof && b.roof.type === 'hip';
    if (hip) {
      const [ox, oz, L0, W0, a] = b.roof.obb, L = L0 + 1.2, Wd = W0 + 1.2;
      const dx = Math.cos(a), dz = Math.sin(a), nx = -dz, nz = dx;
      const P = (u, v, y) => [ox + dx * u + nx * v, y, oz + dz * u + nz * v];
      const e = top - 0.2, ry = top + b.roof.rise, hl = L / 2, hw = Wd / 2, rl = Math.max(0, hl - hw * 0.9);
      const A = P(-hl, -hw, e), B = P(hl, -hw, e), C = P(hl, hw, e), Dd = P(-hl, hw, e), R1 = P(-rl, 0, ry), R2 = P(rl, 0, ry);
      roofC.set(b.roofc || '#a34a3c');
      if (det.rooftiles) { const mn = det.rooftiles.mean; roofC.r /= Math.max(0.05, mn.x); roofC.g /= Math.max(0.05, mn.y); roofC.b /= Math.max(0.05, mn.z); }   // tile texture keeps the pattern, the official colour sets the tone
      for (const [p, q, r] of [[A, B, R2], [A, R2, R1], [C, Dd, R1], [C, R1, R2], [B, C, R2], [Dd, A, R1]]) hBuf.triFace(p, q, r, roofC, (x, z) => [x / 3, z / 3]);
    } else {
      let tris = [];
      try { tris = THREE.ShapeUtils.triangulateShape(pts, []); } catch { tris = []; }
      // clean flat roof in the colour the official map draws (not the blurry aerial)
      roofC.set(b.roofc || (campus ? '#c9c7c1' : '#b8b6b0'));
      for (const [i0, i1, i2] of tris) rBuf.triFace([pts[i0].x, top, pts[i0].y], [pts[i1].x, top, pts[i1].y], [pts[i2].x, top, pts[i2].y], roofC, worldUV);
      if (b.solar && !isWall) {        // solar module rows (official map shows blue panel arrays on this roof)
        const ca = Math.cos(ang), sa = Math.sin(ang);
        for (let u = -longest / 2; u <= longest / 2; u += 2.3) for (let v = -40; v <= 40; v += 3.2) {
          const px = cx + u * ca - v * sa, pz = cz + u * sa + v * ca;
          let ok = pointIn(px, pz, pts);
          for (const [ex, ez] of [[1.8, 1.8], [-1.8, 1.8], [1.8, -1.8], [-1.8, -1.8]]) ok = ok && pointIn(px + ex, pz + ez, pts);
          if (ok) pvBuf.box(px, pz, top + 0.35, 2.1, 0.12, 1.6, ang, pvC);
        }
      }
      if (!isWall && b.h > 4) {
        // parapet
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i], c = pts[(i + 1) % pts.length];
          const dx = c.x - a.x, dz = c.y - a.y, len = Math.hypot(dx, dz) || 1;
          pBuf.wall(a.x, a.y, c.x, c.y, top, top + 0.9, dz / len, -dx / len, 0.02, 0.02, 0.5, 0.5, plainC);
        }
        // rooftop stair / lift housing and a few AC units on taller blocks
        const area = (maxX - minX) * (maxZ - minZ);
        const lv = b.lv || Math.round(b.h / 3.6);
        if (lv >= 5 && area > 500 && pointIn(cx, cz, pts)) {
          pBuf.box(cx, cz, top, Math.min(9, longest * 0.18), 3.2, 5, ang, plainC);
          const r = hash(cx, cz);
          for (let k = 0; k < 3; k++) {
            const ux = (hash(cx + k, cz) - 0.5) * longest * 0.5, uz = (hash(cz, cx + k) - 0.5) * 6;
            const px = cx + ux * Math.cos(ang) - uz * Math.sin(ang), pz = cz + ux * Math.sin(ang) + uz * Math.cos(ang);
            if (pointIn(px, pz, pts)) pBuf.box(px, pz, top, 1.6, 1.1 + r, 1.2, ang, grey);
          }
        }
      }
    }
    out.push({ name: b.label || b.name, kind: b.kind, cx, cz, base, top, campus, minX, maxX, minZ, maxZ,
      photos: b.photos || null, landmark: b.replaced ? null : b.landmark || null, replaced: !!b.replaced, generic: !!b.generic, id: b.id,
      xs: Float32Array.from(pts, (p) => p.x), zs: Float32Array.from(pts, (p) => p.y) });
  }
  for (const [style, buf] of Object.entries(facade)) {
    const m = new THREE.Mesh(buf.geometry(), facadeMats[style] || facadeMats.modern);
    m.castShadow = true; m.receiveShadow = true;
    scene.add(m);
  }
  const roof = new THREE.Mesh(roofBuf.geometry(), new THREE.MeshStandardMaterial({ map: roofTex || orthoTex, vertexColors: !!roofTex, roughness: 0.9 }));
  roof.castShadow = true; roof.receiveShadow = true;
  if (!hipBuf.empty()) {
    const hm = new THREE.MeshStandardMaterial({ map: det.rooftiles?.tex || orthoTex, vertexColors: !!det.rooftiles, roughness: 0.8 });
    const hip = new THREE.Mesh(hipBuf.geometry(), hm); hip.castShadow = true; hip.receiveShadow = true; scene.add(hip);
  }
  const plain = new THREE.Mesh(plainBuf.geometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide }));
  plain.castShadow = true; plain.receiveShadow = true;
  scene.add(roof, plain);
  if (!pvBuf.empty()) { const pv = new THREE.Mesh(pvBuf.geometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.25, metalness: 0.6 })); pv.castShadow = true; scene.add(pv); }
  return out;
}

function pointIn(x, z, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x ?? pts[i][0], zi = pts[i].y ?? pts[i][1], xj = pts[j].x ?? pts[j][0], zj = pts[j].y ?? pts[j][1];
    if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

// ---------------------------------------------------------------- rooftop landmarks + POIs (gates, flags, radar tower)
const MAT = () => ({
  white: new THREE.MeshStandardMaterial({ color: '#f4f4f2', roughness: 0.35 }),
  steel: new THREE.MeshStandardMaterial({ color: '#9aa3ab', roughness: 0.5, metalness: 0.6 }),
  navy: new THREE.MeshStandardMaterial({ color: '#2c3f63', roughness: 0.55 }),
  dark: new THREE.MeshStandardMaterial({ color: '#1e2633', roughness: 0.4 }),
  stone: new THREE.MeshStandardMaterial({ color: '#9a6a52', roughness: 0.85 }),
  stoneDark: new THREE.MeshStandardMaterial({ color: '#7a5242', roughness: 0.85 }),
  pillar: new THREE.MeshStandardMaterial({ color: '#d8d6d0', roughness: 0.6 }),
  paving: new THREE.MeshStandardMaterial({ color: '#c9c2b4', roughness: 0.9 }),
});
const mesh = (geo, mat, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; };

export function buildLandmarks(ctx, metas) {
  const M = MAT();
  for (const m of metas) {
    const g = new THREE.Group();
    if (m.landmark === 'radar') {
      g.add(mesh(new THREE.CylinderGeometry(2.2, 3.2, 10, 8), M.steel, 0, 5), mesh(new THREE.SphereGeometry(7, 32, 20), M.white, 0, 16));
    } else if (m.landmark === 'clocktower') {
      g.add(mesh(new THREE.BoxGeometry(9, 26, 9), M.white, 0, 7));
      const sp = mesh(new THREE.ConeGeometry(7, 18, 4), M.navy, 0, 29); sp.rotation.y = Math.PI / 4; g.add(sp);
      for (let i = 0; i < 4; i++) {
        const a = i * Math.PI / 2, ck = mesh(new THREE.CircleGeometry(2.4, 24), M.dark, Math.sin(a) * 4.56, 15, Math.cos(a) * 4.56);
        ck.rotation.y = a; g.add(ck);
      }
    } else continue;
    g.position.set(m.cx, m.top, m.cz);
    ctx.scene.add(g);
  }
}

export function buildPois(ctx, pois) {
  const M = MAT(), out = [];
  const flagColors = ['#d62828', '#1d4fa3', '#f2f2f2', '#2a9d3f', '#f4c430', '#e76f2a', '#111111', '#4cb4e7'];
  for (let p of pois || []) {
    const g = new THREE.Group(), y = ctx.heightAt(p.x, p.z);
    let h = 8;
    if (p.replaced) p = { ...p, landmark: 'none' };
    if (p.landmark === 'gate_old') {
      // long flat stone canopy on two piers with low side walls (老校门 photo)
      g.add(mesh(new THREE.BoxGeometry(24, 1.3, 4), M.stoneDark, 0, 6.2), mesh(new THREE.BoxGeometry(3, 5.6, 3), M.stone, -9.5, 2.8),
        mesh(new THREE.BoxGeometry(3, 5.6, 3), M.stone, 9.5, 2.8), mesh(new THREE.BoxGeometry(7, 1.4, 0.6), M.stone, -14.5, 0.7),
        mesh(new THREE.BoxGeometry(7, 1.4, 0.6), M.stone, 14.5, 0.7));
      h = 7;
    } else if (p.landmark === 'gate_east') {
      g.add(mesh(new THREE.CylinderGeometry(11, 11, 0.4, 40), M.paving, 0, 0.2));
      for (let i = 0; i < 8; i++) {
        const a = -Math.PI * 0.42 + i * (Math.PI * 0.84 / 7);
        g.add(mesh(new THREE.BoxGeometry(1.6, 14, 1.6), M.pillar, Math.sin(a) * 24, 7, -Math.cos(a) * 24 + 12));
      }
      h = 14;
    } else if (p.landmark === 'flags') {
      const poleGeo = new THREE.CylinderGeometry(0.06, 0.08, 10, 6), flagGeo = new THREE.PlaneGeometry(1.8, 1.2);
      for (let i = 0; i < 21; i++) {
        const a = Math.PI * (0.15 + 0.7 * i / 20), px = Math.cos(a) * 15, pz = -Math.sin(a) * 9;
        g.add(mesh(poleGeo, M.steel, px, 5, pz));
        const fm = new THREE.MeshStandardMaterial({ color: flagColors[i % flagColors.length], side: THREE.DoubleSide, roughness: 0.8 });
        g.add(mesh(flagGeo, fm, px + 0.9, 9.2, pz));
      }
      g.add(mesh(new THREE.CylinderGeometry(0.08, 0.1, 14, 6), M.steel, 0, 7, -2));
      g.add(mesh(flagGeo.clone().scale(1.4, 1.4, 1), new THREE.MeshStandardMaterial({ color: '#de2910', side: THREE.DoubleSide }), 1.26, 13, -2));
      h = 12;
    } else if (p.landmark === 'gate_generic') {
      // campus gate from the official map's 出入口 list: two stone pillars, a beam with a sign, a guard booth.
      // pois.json may set span (pillar spacing, default 16 m), pillars:false / booth:false (booth built as a real
      // building in extra_buildings), barrier:true (a boom barrier across the opening)
      const span = p.span || 16, hs = span / 2;
      if (p.pillars !== false) {
        g.add(mesh(new THREE.BoxGeometry(1.4, 5.6, 1.4), M.pillar, -hs, 2.8), mesh(new THREE.BoxGeometry(1.4, 5.6, 1.4), M.pillar, hs, 2.8),
          mesh(new THREE.BoxGeometry(span + 1.6, 1.1, 1.3), M.pillar, 0, 6.1), mesh(new THREE.BoxGeometry(Math.min(6.5, span * 0.6), 1.0, 0.25), M.stoneDark, 0, 6.1, 0.72));
      }
      if (p.booth !== false) {
        g.add(mesh(new THREE.BoxGeometry(3, 2.8, 3), M.white, hs + 3.5, 1.4), mesh(new THREE.BoxGeometry(3.6, 0.3, 3.6), M.navy, hs + 3.5, 2.95));
      }
      if (p.barrier) {      // boom barrier: post at one side, red-white arm across most of the opening, 1 m up
        const arm = Math.max(3, span - 1.5);
        g.add(mesh(new THREE.BoxGeometry(0.5, 1.1, 0.5), M.white, -hs + 0.3, 0.55),
          mesh(new THREE.BoxGeometry(arm, 0.12, 0.12), new THREE.MeshStandardMaterial({ color: '#d93b30', roughness: 0.6 }), -hs + 0.3 + arm / 2, 1.0));
      }
      h = p.pillars === false ? 3 : 7;
    } else if (p.landmark === 'obs_field' && p.plots) {
      // 气象观测场: fenced instrument plots (lawn + white walkway grid + Stevenson screens + masts), dish, brick path
      const L = (x, z) => [x - p.x, z - p.z];
      const lawn = new THREE.MeshStandardMaterial({ color: '#6f9a48', roughness: 0.95 }), walk = new THREE.MeshStandardMaterial({ color: '#e9e7e1', roughness: 0.8 });
      const white = new THREE.MeshStandardMaterial({ color: '#f4f4f2', roughness: 0.5 }), mesh2 = new THREE.MeshStandardMaterial({ color: '#c8ccd0', roughness: 0.6, metalness: 0.5, transparent: true, opacity: 0.35, side: THREE.DoubleSide });
      const brick = new THREE.MeshStandardMaterial({ color: '#9e4f45', roughness: 0.9 });
      const flat = (x0, z0, x1, z1, mat, yy) => { const [a0, b0] = L(x0, z0), [a1, b1] = L(x1, z1); const m2 = mesh(new THREE.BoxGeometry(Math.abs(a1 - a0), 0.06, Math.abs(b1 - b0)), mat, (a0 + a1) / 2, yy, (b0 + b1) / 2); m2.receiveShadow = true; g.add(m2); };
      if (p.path) flat(p.path[0], p.path[1], p.path[2], p.path[3], brick, 0.33);
      let k = 0;
      for (const [x0, z0, x1, z1, nNS, nEW] of p.plots) {
        flat(x0, z0, x1, z1, lawn, 0.3);
        for (let i = 1; i <= nNS; i++) { const x = x0 + (x1 - x0) * i / (nNS + 1); flat(x - 0.6, z0 + 1.5, x + 0.6, z1 - 1.5, walk, 0.36); }
        for (let j = 1; j <= nEW; j++) { const z = z0 + (z1 - z0) * j / (nEW + 1); flat(x0 + 2.5, z - 0.5, x1 - 2.5, z + 0.5, walk, 0.36); }
        // 1.3 m wire-mesh fence with posts every 3 m
        const cs = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]];
        for (let e = 0; e < 4; e++) {
          const [ax, az] = L(...cs[e]), [bx, bz] = L(...cs[(e + 1) % 4]), len = Math.hypot(bx - ax, bz - az);
          const f = mesh(new THREE.PlaneGeometry(len, 1.3), mesh2, (ax + bx) / 2, 0.95, (az + bz) / 2); f.rotation.y = -Math.atan2(bz - az, bx - ax); g.add(f);
          for (let t = 0; t <= len; t += 3) g.add(mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.4, 5), M.steel, ax + (bx - ax) * t / len, 0.95, az + (bz - az) * t / len));
        }
        // Stevenson screens (百叶箱) on legs beside the cross walkways, and instrument masts
        for (let j = 1; j <= nEW; j++) for (let i = 0; i <= nNS; i++) {
          if ((i + j + k) % 2) continue;
          const x = x0 + (x1 - x0) * (i + 0.5) / (nNS + 1), z = z0 + (z1 - z0) * j / (nEW + 1) - 1.6, [lx, lz] = L(x, z);
          g.add(mesh(new THREE.BoxGeometry(0.8, 0.75, 0.65), white, lx, 1.85, lz));
          for (const [ux, uz] of [[-0.32, -0.25], [0.32, -0.25], [-0.32, 0.25], [0.32, 0.25]]) g.add(mesh(new THREE.BoxGeometry(0.05, 1.5, 0.05), white, lx + ux, 1.05, lz + uz));
        }
        const [mx, mz] = L(x1 - 3, z0 + 3);
        g.add(mesh(new THREE.CylinderGeometry(0.06, 0.09, 10, 6), white, mx, 5.3, mz), mesh(new THREE.BoxGeometry(1.4, 0.06, 0.06), M.steel, mx, 10.1, mz));
        k++;
      }
      // lattice wind tower in the east plot, tall white masts along the brick path, satellite dish at the north-west corner
      const last = p.plots[p.plots.length - 1], [tx, tz] = L(last[2] - 8, (last[1] + last[3]) / 2);
      for (const [ux, uz] of [[-0.8, -0.8], [0.8, -0.8], [0.8, 0.8], [-0.8, 0.8]]) g.add(mesh(new THREE.CylinderGeometry(0.06, 0.06, 20, 5), M.steel, tx + ux * 0.6, 10.3, tz + uz * 0.6));
      for (let yy = 2; yy < 20; yy += 2.5) g.add(mesh(new THREE.BoxGeometry(1.1, 0.05, 1.1), M.steel, tx, yy, tz));
      if (p.path) for (let i = 0; i < 6; i++) { const [px2, pz2] = L(p.path[0] + 12 + i * 21, p.path[3] + 1.5); g.add(mesh(new THREE.CylinderGeometry(0.07, 0.1, 12, 6), white, px2, 6.3, pz2)); }
      if (p.dish) {
        const [dx2, dz2] = L(p.dish[0], p.dish[1]), r = p.dish[2];
        const dish = mesh(new THREE.SphereGeometry(r, 24, 12, 0, Math.PI * 2, 0, Math.PI * 0.32), new THREE.MeshStandardMaterial({ color: '#f6f6f4', roughness: 0.4, side: THREE.DoubleSide }), dx2, r * 0.9 + 3.2, dz2);
        dish.rotation.x = Math.PI * 0.72; g.add(dish, mesh(new THREE.CylinderGeometry(0.5, 0.9, 3.2, 10), white, dx2, 1.9, dz2));
      }
      h = 6;
    } else if (p.landmark === 'radar_tower') {
      g.add(mesh(new THREE.CylinderGeometry(0.9, 1.7, 26, 10), M.white, 0, 13), mesh(new THREE.CylinderGeometry(3.2, 3.2, 0.6, 16), M.steel, 0, 26.3),
        mesh(new THREE.SphereGeometry(4.5, 28, 18), M.white, 0, 30.5));
      h = 34;
    }
    g.position.set(p.x, y, p.z);
    g.rotation.y = THREE.MathUtils.degToRad(p.rot || 0);
    ctx.scene.add(g);
    out.push({ name: p.name, kind: 'poi', cx: p.x, cz: p.z, base: y, top: y + h, campus: true,
      minX: p.x - 6, maxX: p.x + 6, minZ: p.z - 6, maxZ: p.z + 6, photos: p.photos || null, landmark: p.landmark });
  }
  return out;
}

// ---------------------------------------------------------------- trees: per-tree height / crown from the drone DSM, three species shapes
// crowns are smooth-shaded clusters with a dark-to-light vertical gradient (vertex colour x instance colour)
function gradient(geo, y0, y1, lo = 0.55, hi = 1.12) {
  const pos = geo.attributes.position, col = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const t = Math.min(1, Math.max(0, (pos.getY(i) - y0) / (y1 - y0))), v = lo + (hi - lo) * t;
    col[i * 3] = v; col[i * 3 + 1] = v; col[i * 3 + 2] = v;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return geo;
}
// leaf-card shell around the crown blobs: alpha-tested cards with a canvas leaf-cluster texture and
// spherical normals, so close-up crowns get a leafy silhouette while the blob keeps them dense
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
let LEAF_TEX = null;
function leafTexture() {
  if (LEAF_TEX) return LEAF_TEX;
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d'), r = rng(77);
  for (let i = 0; i < 260; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r()) * 108, cx = 128 + Math.cos(a) * d, cy = 128 + Math.sin(a) * d;
    const l = 26 + r() * 22, w = l * (0.38 + r() * 0.12), rot = r() * Math.PI * 2, v = 150 + r() * 105 | 0;
    x.save(); x.translate(cx, cy); x.rotate(rot);
    x.fillStyle = `rgb(${v * 0.74 | 0},${v * 0.92 | 0},${v * 0.58 | 0})`;
    x.beginPath(); x.ellipse(0, 0, l / 2, w / 2, 0, 0, Math.PI * 2); x.fill();
    x.strokeStyle = `rgba(60,80,40,0.35)`; x.lineWidth = 1.2; x.beginPath(); x.moveTo(-l / 2, 0); x.lineTo(l / 2, 0); x.stroke();
    x.restore();
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  LEAF_TEX = t; return t;
}
// spheres: [[cx, cy, cz, r, sy]], cards per sphere n, card size k * r
function leafCards(spheres, n, k, y0, y1, seed) {
  const r = rng(seed), pos = [], nor = [], uv = [], col = [];
  for (const [cx, cy, cz, rad, sy = 1] of spheres) {
    for (let i = 0; i < n; i++) {
      // point on the sphere surface (upper hemisphere favoured), card facing outwards with a random twist
      const u = r() * 1.9 - 0.85, th = r() * Math.PI * 2, sq = Math.sqrt(Math.max(0, 1 - Math.min(1, u * u)));
      const dir = new THREE.Vector3(sq * Math.cos(th), Math.min(1, u), sq * Math.sin(th)).normalize();
      const c = new THREE.Vector3(cx + dir.x * rad * 0.92, cy + dir.y * rad * 0.92 * sy, cz + dir.z * rad * 0.92);
      const t1 = new THREE.Vector3().crossVectors(dir, Math.abs(dir.y) > 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)).normalize();
      const t2 = new THREE.Vector3().crossVectors(dir, t1).normalize();
      const tw = r() * Math.PI, ct = Math.cos(tw), st = Math.sin(tw), h = rad * k / 2;
      const a = t1.clone().multiplyScalar(ct).addScaledVector(t2, st).multiplyScalar(h);
      const b = t2.clone().multiplyScalar(ct).addScaledVector(t1, -st).multiplyScalar(h);
      const P = [c.clone().sub(a).sub(b), c.clone().add(a).sub(b), c.clone().add(a).add(b), c.clone().sub(a).add(b)];
      const UV = [[0, 0], [1, 0], [1, 1], [0, 1]];
      for (const j of [0, 1, 2, 0, 2, 3]) {
        const q = P[j], nn = new THREE.Vector3(q.x - cx, (q.y - cy) / sy, q.z - cz).normalize();
        pos.push(q.x, q.y, q.z); nor.push(nn.x, nn.y * 0.8 + 0.2, nn.z); uv.push(...UV[j]);
        const v = 0.55 + 0.57 * Math.min(1, Math.max(0, (q.y - y0) / (y1 - y0)));
        col.push(v, v, v);
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.computeBoundingSphere();
  return g;
}
// irregular crown lobes: push each vertex of a blob in or out along its radius by a smooth position hash (vertices
// shared between faces move together, so no cracks); normals stay spherical for soft shading
function lumpy(geo, cx, cy, cz, amp, seed) {
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    const k = 1 + amp * (Math.sin(x * 2.1 + seed) * Math.sin(z * 1.9 - seed * 0.7) * 0.6 + Math.sin(y * 2.7 + x * 0.8 + seed * 1.3) * 0.4);
    pos.setXYZ(i, cx + (x - cx) * k, cy + (y - cy) * k, cz + (z - cz) * k);
  }
  return geo;
}
// 植被 (地表观感 2026-11-27). The DSM gave every tree the same 9 m / 3.2 m, so all crowns were identical blobs.
// Each campus tree now gets a species from its patch (~32 m groups planted together, 12 % odd ones out) and the
// data's own type (broad / conifer / ginkgo / redleaf), willows and dawn redwoods along the water, and a size from
// that species' range. Species (typical Nanjing campus planting): broad = plane / zelkova (tall, light), round =
// camphor (wide dark dome), small = osmanthus / photinia (3-5 m), slim = ginkgo, conifer = cedar (wide bluish cone),
// column = dawn redwood (narrow, tall), willow (drooping), red = red-leaf plum / maple; simple = outside the campus.
const TREE_SP = {   // [h0, h1, crown r0, r1], HSL [h0, h1, s0, s1, l0, l1]
  broad: { size: [10, 15, 3.3, 4.7], hsl: [0.21, 0.25, 0.36, 0.48, 0.25, 0.31] },
  round: { size: [8.5, 12.5, 3.0, 4.5], hsl: [0.26, 0.30, 0.36, 0.46, 0.18, 0.24] },
  small: { size: [3.5, 5.5, 1.5, 2.3], hsl: [0.27, 0.31, 0.30, 0.40, 0.15, 0.20] },
  slim: { size: [9, 13, 1.7, 2.5], hsl: [0.17, 0.21, 0.46, 0.56, 0.28, 0.34] },
  conifer: { size: [8, 13, 2.6, 4.0], hsl: [0.37, 0.43, 0.14, 0.24, 0.16, 0.21] },
  column: { size: [13, 20, 1.5, 2.3], hsl: [0.23, 0.27, 0.40, 0.50, 0.24, 0.30] },
  willow: { size: [7, 10, 3.2, 4.4], hsl: [0.19, 0.23, 0.40, 0.50, 0.31, 0.37] },
  red: { size: [4, 6.5, 1.8, 2.6], hsl: [0.97, 1.01, 0.38, 0.48, 0.22, 0.28] },
  simple: { size: [8, 12, 2.6, 3.6], hsl: [0.24, 0.32, 0.24, 0.34, 0.17, 0.25] },
};
export function buildTrees(ctx, trees, lite) {
  const { scene, W, D, heightAt, inCampus } = ctx;
  const ico = (r, x, y, z, sy = 1, detail = 1) => new THREE.IcosahedronGeometry(r, detail).scale(1, sy, 1).translate(x, y, z);
  const blob = (r, x, y, z, sy = 1, detail = 1, amp = 0.13) => lumpy(ico(r, x, y, z, sy, detail), x, y, z, amp, x * 3.7 + z * 1.3 + r);
  const cone = (r, h, y) => new THREE.ConeGeometry(r, h, 10, 1).translate(0, y, 0).toNonIndexed();
  const fine = !lite, d1 = fine ? 1 : 0;
  // crown shapes: [lobes], gradient [y0, y1, lo, hi]; R = crown radius, H = top (instance scale = size / these)
  const SH = {
    broad: { lobes: fine ? [[1.55, 0, 4.4, 0], [1.25, 1.15, 3.8, 0.5], [1.15, -1.05, 3.9, -0.6], [1.07, 0.3, 5.4, -0.45], [1.0, -0.45, 4.8, 1.05]]
      : [[1.8, 0, 4.4, 0], [1.4, 1.1, 3.8, 0.5], [1.3, -1.0, 3.9, -0.6]], g: [2.4, 6.6], R: 2.3, H: 6.6 },
    round: { lobes: fine ? [[1.75, 0, 4.5, 0, 0.82], [1.35, 1.5, 4.0, 0.3, 0.8], [1.35, -1.45, 4.05, -0.4, 0.8], [1.25, 0.2, 4.1, 1.5, 0.8], [1.25, -0.3, 4.0, -1.5, 0.8], [1.15, 0.3, 5.3, 0.1, 0.8]]
      : [[2.0, 0, 4.4, 0, 0.8], [1.5, 1.3, 4.0, 0.3, 0.8], [1.5, -1.3, 4.0, -0.4, 0.8]], g: [2.9, 6.3], R: 2.9, H: 6.3 },
    small: { lobes: fine ? [[1.25, 0, 1.95, 0, 0.9], [0.95, 0.7, 1.65, 0.3], [0.9, -0.62, 1.7, -0.4], [0.85, 0.1, 2.55, 0.2]] : [[1.4, 0, 2.0, 0, 0.95]], g: [0.7, 3.3], R: 1.6, H: 3.3 },
    slim: { lobes: [[fine ? 1.08 : 1.25, 0, 4.4, 0, 1.9], [fine ? 0.82 : 0.95, 0.2, 6.1, 0.1, 1.5]], g: [2.2, 7.4], R: 1.3, H: 7.4 },
    willow: { lobes: [[1.75, 0, 5.0, 0, 0.72], ...(fine ? [0, 1, 2, 3, 4, 5, 6, 7] : [0, 2, 4, 6]).map((k) => [0.5, Math.cos(k * 0.785 + 0.3) * 1.55, 3.7, Math.sin(k * 0.785 + 0.3) * 1.55, 2.5])], g: [2.0, 6.3], R: 2.1, H: 6.3 },
    simple: { lobes: [[2.0, 0, 4.4, 0, 1.05]], g: [2.4, 6.5], R: 2.0, H: 6.5, d: 0 },
  };
  const V = {}, CARDS = {};
  for (const [k, s] of Object.entries(SH)) {
    V[k] = gradient(mergeGeometries(s.lobes.map(([r, x, y, z, sy = 1]) => blob(r, x, y, z, sy, s.d ?? d1, k === 'willow' && sy > 2 ? 0.05 : 0.13))), s.g[0], s.g[1]);
    if (fine && k !== 'simple') CARDS[k] = leafCards(s.lobes.map(([r, x, y, z, sy = 1]) => [x, y, z, r * 1.12, sy]), k === 'willow' ? 9 : 13, 1.1, s.g[0], s.g[1], k.length * 7);
  }
  V.conifer = gradient(mergeGeometries([cone(2.0, 3.2, 3.0), cone(1.65, 2.8, 4.4), cone(1.25, 2.4, 5.7), cone(0.8, 2.0, 6.9)]), 1.4, 7.9, 0.5, 1.05);
  V.column = gradient(mergeGeometries([cone(1.3, 3.0, 3.4), cone(1.1, 2.8, 5.3), cone(0.9, 2.6, 7.1), cone(0.65, 2.4, 8.8), cone(0.4, 2.0, 10.4)]), 1.9, 11.4, 0.5, 1.05);
  if (fine) {
    CARDS.conifer = leafCards([[0, 3.0, 0, 1.9, 0.7], [0, 4.4, 0, 1.55, 0.75], [0, 5.7, 0, 1.15, 0.8], [0, 6.9, 0, 0.7, 1]], 9, 1.0, 1.4, 7.9, 7);
    CARDS.column = leafCards([[0, 3.4, 0, 1.2, 0.9], [0, 5.3, 0, 1.0, 0.9], [0, 7.1, 0, 0.82, 0.9], [0, 8.8, 0, 0.6, 1], [0, 10.4, 0, 0.36, 1]], 8, 0.9, 1.9, 11.4, 9);
  }
  const DIM = { conifer: [2.0, 7.9], column: [1.3, 11.4] };
  for (const [k, s] of Object.entries(SH)) DIM[k] = [s.R, s.H];
  const geoOf = (v) => (v === 'red' ? 'small' : v);
  const leafM = new THREE.MeshStandardMaterial({ map: leafTexture(), color: '#ffffff', vertexColors: true, roughness: 0.8, alphaTest: 0.5,
    side: THREE.DoubleSide, alphaToCoverage: true });
  const trunkG = mergeGeometries([
    new THREE.CylinderGeometry(0.13, 0.22, 3.0, 6).translate(0, 1.5, 0),
    new THREE.CylinderGeometry(0.06, 0.1, 1.6, 5).rotateZ(0.6).translate(0.45, 2.9, 0),
    new THREE.CylinderGeometry(0.06, 0.1, 1.5, 5).rotateZ(-0.7).translate(-0.4, 3.0, 0.1),
  ]);
  const trunkM = new THREE.MeshStandardMaterial({ color: '#5b4636', roughness: 1 });
  const crownM = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: 0.82 });
  const coniferM = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: 0.85, flatShading: true });
  // never let a tree block the third-person camera: drop fragments within 4 m of the camera
  for (const mat of [trunkM, crownM, coniferM, leafM]) {
    mat.onBeforeCompile = (sh) => {
      injectWPos(sh);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWPos;')
        .replace('void main() {', 'void main() {\n  if (length(vWPos - cameraPosition) < 4.0) discard;');
    };
  }
  { // foliage cards: light both faces like the front (no normal flip), so card backs do not turn black
    const base = leafM.onBeforeCompile;
    leafM.onBeforeCompile = (sh) => {
      base(sh);
      sh.fragmentShader = sh.fragmentShader.replace('#include <normal_fragment_begin>',
        THREE.ShaderChunk.normal_fragment_begin.replace('float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;', 'float faceDirection = 1.0;'));
    };
  }
  // within ~12 m of a pond or river: water sampled on an 8 m grid, memoised (a few thousand waterAt calls in all)
  const wc = new Map(), WC = 8;
  const wcell = (i, j) => { const k = i * 100003 + j; let v = wc.get(k); if (v === undefined) { v = ctx.waterAt((i + 0.5) * WC, (j + 0.5) * WC) !== null; wc.set(k, v); } return v; };
  const nearWater = (x, z) => {
    if (!ctx.waterAt) return false;
    const i = Math.floor(x / WC), j = Math.floor(z / WC);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) if (wcell(i + a, j + b)) return true;
    return false;
  };
  const pick = (t, near) => {
    const sp = t.length > 4 ? t[4] : (hash(t[0], t[1]) < 0.75 ? 'broad' : 'conifer');
    if (!near) return sp === 'conifer' ? 'conifer' : 'simple';
    if (sp === 'ginkgo') return 'slim';
    if (sp === 'redleaf') return 'red';
    const gx = Math.floor((t[0] + (hash(t[0] * 0.37, t[1]) - 0.5) * 14) / 32), gz = Math.floor((t[1] + (hash(t[1] * 0.41, t[0]) - 0.5) * 14) / 32);
    const odd = hash(t[0] * 3.1, t[1] * 1.3) < 0.12, u = odd ? hash(t[1] * 2.7, t[0] * 0.9) : hash(gx * 1.7 + 0.5, gz * 2.3 + 0.5);
    if (sp === 'conifer') return u < 0.6 ? 'conifer' : 'column';
    if (nearWater(t[0], t[1])) return u < 0.5 ? 'willow' : u < 0.75 ? 'column' : 'broad';
    return u < 0.4 ? 'round' : u < 0.68 ? 'broad' : u < 0.85 ? 'small' : 'slim';
  };
  const CH = ctx.treeChunk || 600, groups = new Map(), VARS = ['broad', 'round', 'small', 'slim', 'willow', 'red', 'simple', 'conifer', 'column'];
  trees.forEach((t, i) => {
    const near = inCampus(t[0], t[1]);
    if (lite && i % 2) return;
    if (!near && i % 3 === 0) return;                    // thinner forest outside the campus
    const v = pick(t, near);
    // size: the species' range, shared partly by the patch (planted together), crown following height; a crown that
    // main.js narrowed next to a wall (< 3 m) stays narrow
    const [h0, h1, r0, r1] = TREE_SP[v].size;
    const a = Math.min(1, Math.max(0, 0.5 * hash(Math.floor(t[0] / 25) + 0.3, Math.floor(t[1] / 25) + 0.7) + 0.5 * hash(t[1] * 1.9, t[0] * 2.3)));
    const h = (h0 + (h1 - h0) * a) * (t[2] / 9) ** 0.5, cr0 = r0 + (r1 - r0) * (0.7 * a + 0.3 * hash(t[0] * 5.3, t[1] * 4.1));
    let cr = t.length > 4 && t[3] < 3.0 ? Math.min(cr0, t[3]) : cr0;
    // no crown in a wall, inside the campus or not (search <= 4 m, sanity.js PAD; / 1.1 for the crown's x/z jitter below)
    if (ctx.buildingDist) cr = Math.max(1.0, Math.min(cr, (ctx.buildingDist(t[0], t[1], Math.min(4, cr * 1.1)) + 0.4) / 1.1));
    const key = `${Math.floor((t[0] + W / 2) / CH)},${Math.floor((t[1] + D / 2) / CH)}`;
    if (!groups.has(key)) groups.set(key, Object.fromEntries(VARS.map((k) => [k, []])));
    groups.get(key)[v].push([t[0], t[1], h, cr]);
  });
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color(), up = new THREE.Vector3(0, 1, 0);
  // 性能 (perf.js): far away a chunk draws one 20-triangle blob per broadleaf and an 8-sided cone per conifer instead of
  // the lobed crowns, leaf cards and trunks (ctx.detail swaps them by camera distance; unit size, instance scale = tree size)
  const det = ctx.detail;
  const FAR = det && { blob: gradient(new THREE.IcosahedronGeometry(1, 0).scale(1, 0.34, 1).translate(0, 0.66, 0), 0.32, 1.0),
    cone: gradient(new THREE.ConeGeometry(1, 0.85, 8, 1, true).translate(0, 0.575, 0), 0.15, 1.0, 0.5, 1.05) };
  for (const grp of groups.values()) {
    const all = VARS.flatMap((k) => grp[k].map((t) => [t, k]));
    const far = { blob: [], cone: [] };
    const tm = new THREE.InstancedMesh(trunkG, trunkM, all.length);
    all.forEach(([t, k], i) => {
      const [R, H] = DIM[geoOf(k)], sx = t[3] / R, sy = t[2] / H;
      p.set(t[0], heightAt(t[0], t[1]) - 0.1, t[1]); q.setFromAxisAngle(up, hash(t[1], t[0]) * 6.283);
      const tw = Math.min(1.6, Math.sqrt(sx * sy)); s.set(tw, sy, tw); m4.compose(p, q, s); tm.setMatrixAt(i, m4);
    });
    tm.computeBoundingSphere(); tm.receiveShadow = true; tm.castShadow = true; tm.userData.sanity = { kind: 'tree' }; scene.add(tm);
    const cs = det && tm.boundingSphere.clone();     // one LOD distance per chunk, so crowns and far blobs switch together
    if (cs) cs.radius += 15;
    for (const k of VARS) {
      const list = grp[k];
      if (!list.length) continue;
      const gk = geoOf(k), [R, H] = DIM[gk], [hh0, hh1, s0, s1, l0, l1] = TREE_SP[k].hsl;
      const cm = new THREE.InstancedMesh(V[gk], gk === 'conifer' || gk === 'column' ? coniferM : crownM, list.length);
      list.forEach((t, i) => {
        const r1 = hash(t[1], t[0]), sx = t[3] / R, sy = t[2] / H;
        const pg = hash(Math.floor(t[0] / 32) + 0.1, Math.floor(t[1] / 32) + 0.9);     // patch tint
        p.set(t[0], heightAt(t[0], t[1]) - 0.1, t[1]);
        q.setFromAxisAngle(up, r1 * 6.283);
        s.set(sx * (0.9 + r1 * 0.2), sy, sx * (1.1 - r1 * 0.2));
        m4.compose(p, q, s); cm.setMatrixAt(i, m4);
        c.setHSL((hh0 + (hh1 - hh0) * (0.6 * pg + 0.4 * r1)) % 1, s0 + (s1 - s0) * ((r1 * 7) % 1), l0 + (l1 - l0) * (0.5 * pg + 0.5 * ((r1 * 13) % 1)), THREE.SRGBColorSpace);
        cm.setColorAt(i, c);
        if (FAR) far[gk === 'conifer' || gk === 'column' ? 'cone' : 'blob'].push([p.clone(), q.clone(), new THREE.Vector3(t[3] * (0.9 + r1 * 0.2), t[2], t[3] * (1.1 - r1 * 0.2)), c.clone()]);
      });
      cm.computeBoundingSphere(); cm.castShadow = true; cm.receiveShadow = true;
      cm.userData.sanity = { kind: 'crown', R };   // sanity.js scan
      scene.add(cm);
      det?.tag(cm, 'crown', cs);
      if (CARDS[gk]) {
        const lm = new THREE.InstancedMesh(CARDS[gk], leafM, list.length);
        lm.instanceMatrix.copy(cm.instanceMatrix); lm.instanceColor = cm.instanceColor;
        lm.computeBoundingSphere(); lm.receiveShadow = true;
        scene.add(lm);
        det?.tag(lm, 'cards', cs);
      }
    }
    det?.tag(tm, 'trunk', cs);
    if (FAR) for (const [k, list] of Object.entries(far)) {
      if (!list.length) continue;
      const fm = new THREE.InstancedMesh(FAR[k], k === 'cone' ? coniferM : crownM, list.length);
      list.forEach(([pp, qq, ss, cc], i) => { m4.compose(pp, qq, ss); fm.setMatrixAt(i, m4); fm.setColorAt(i, cc); });
      fm.computeBoundingSphere(); fm.castShadow = true; fm.receiveShadow = true;
      scene.add(fm);
      det.tag(fm, 'crownFar', cs);
    }
  }
}

// ---------------------------------------------------------------- flowering trees at the official map's 百花 spots
export function buildFlowers(ctx, flowers) {
  if (!flowers?.length) return;
  const { scene, heightAt } = ctx;
  const ico = (r, x, y, z) => new THREE.IcosahedronGeometry(r, 1).translate(x, y, z);
  const crown = gradient(mergeGeometries([ico(1.3, 0, 3.0, 0), ico(1.0, 0.8, 2.6, 0.3), ico(0.9, -0.7, 2.7, -0.4), ico(0.85, 0.1, 3.7, 0.2)]), 1.8, 4.5, 0.7, 1.1);
  const trunk = new THREE.CylinderGeometry(0.1, 0.16, 2.0, 5).translate(0, 1.0, 0);
  const palette = (name) => /樱|桃|海棠|梅|紫薇|夹竹桃|蔷薇|杜鹃/.test(name) ? ['#f3a6c8', '#f7c4da', '#ec8fb7']
    : /玉兰|梨|李|栀子|女贞/.test(name) ? ['#f5f3ee', '#efe9f2', '#fbfbf7']
    : /桂|金丝|迎春|银杏|腊梅|连翘/.test(name) ? ['#f2cf4a', '#e9c03a', '#f6dc74']
    : /茶花|石榴|月季/.test(name) ? ['#d9394f', '#e65468', '#c92f45'] : ['#f0a5c5', '#f5c0d6', '#ffffff'];
  const spots = [];
  // the official 百花 points can sit on a road or the riverbank: keep each tree off carriageways + sidewalks and
  // out of the water, nudging it around its point, else drop it
  const blocked = (x, z) => (ctx.onRoad && ctx.onRoad(x, z, null, 4.0)) || (ctx.waterAt && ctx.waterAt(x, z) !== null)
    || !!ctx.blockedBy?.(x, z, { r: 0.3, sport: 1, road: false, path: 0, cover: 0.5 });     // nor in a building, on a path, pitch or model plaza
  for (const [x, z, name] of flowers) for (let i = 0; i < 5; i++) {
    for (let k = 0; k < 12; k++) {
      const a = i * 1.257 + x + k * 0.9, r = (i ? 3.5 + (i % 2) * 2 : 0) + k * 1.5;
      const px = x + Math.cos(a) * r, pz = z + Math.sin(a) * r;
      if (!blocked(px, pz)) { spots.push([px, pz, palette(name)[i % 3]]); break; }
    }
  }
  const cm = new THREE.InstancedMesh(crown, new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: 0.8 }), spots.length);
  const tm = new THREE.InstancedMesh(trunk, new THREE.MeshStandardMaterial({ color: '#5a4634', roughness: 1 }), spots.length);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color(), up = new THREE.Vector3(0, 1, 0);
  spots.forEach(([x, z, col], i) => {
    p.set(x, heightAt(x, z) - 0.05, z); q.setFromAxisAngle(up, i); s.setScalar(0.85 + (i % 3) * 0.15);
    m4.compose(p, q, s); cm.setMatrixAt(i, m4); tm.setMatrixAt(i, m4); cm.setColorAt(i, c.set(col));
  });
  for (const m of [cm, tm]) { m.castShadow = true; m.receiveShadow = true; m.computeBoundingSphere(); scene.add(m); }
  tm.userData.sanity = { kind: 'flower' };
}

// ---------------------------------------------------------------- street lamps along campus roads
// ---------------------------------------------------------------- road-name signs (blue plate, white Chinese + Hanyu Pinyin, GB 17733 style)
const PINYIN = { '正气路': 'ZHENGQI LU', '正气东路': 'ZHENGQI DONGLU', '万象路': 'WANXIANG LU', '盘城新街': 'PANCHENG XINJIE',
  '万家坝路': 'WANJIABA LU', '龙山北路': 'LONGSHAN BEILU', '六合大道': 'LUHE DADAO', '杨新路': 'YANGXIN LU', '凤滨路': 'FENGBIN LU' };
export function buildRoadSigns(ctx, roads) {
  const { scene, heightAt, inCampus } = ctx;
  const mats = new Map();
  const matFor = (name) => {
    if (mats.has(name)) return mats.get(name);
    const c = document.createElement('canvas'); c.width = 512; c.height = 160;
    const x = c.getContext('2d');
    x.fillStyle = '#1d4f9c'; x.fillRect(0, 0, 512, 160);
    x.strokeStyle = '#ffffff'; x.lineWidth = 6; x.strokeRect(8, 8, 496, 144);
    x.fillStyle = '#ffffff'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.font = 'bold 72px "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif';
    x.fillText(name, 256, 66);
    x.font = 'bold 26px Arial, sans-serif'; x.fillText(PINYIN[name] || '', 256, 126);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
    const m = new THREE.MeshStandardMaterial({ map: t, roughness: 0.5 });
    mats.set(name, m); return m;
  };
  const pole = new GeoBuf(), grey = new THREE.Color('#8d9298');
  const plateGeo = new THREE.BoxGeometry(1.7, 0.53, 0.05);
  const edge = new THREE.MeshStandardMaterial({ color: '#d9dde2', roughness: 0.4, metalness: 0.5 });
  let n = 0;
  for (const r of roads) {
    if (!r.name || !(r.name in PINYIN) || r.w < 5) continue;
    let acc = 18, side = 1;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1], L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 0.1) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = acc; t < L; t += 140) {
        const o = r.w / 2 + (r.sw ? r.sw - 0.35 : 1.0);
        const x = x0 + dx * t - dz * o * side, z = z0 + dz * t + dx * o * side;
        side = -side;
        if (!inCampus(x, z) && !inCampus(x - dz * 30, z + dx * 30) && !inCampus(x + dz * 30, z - dx * 30)) continue;
        if (ctx.onRoad?.(x, z, r, 1)) continue;
        if (ctx.blockedBy?.(x, z, { r: 0.15, road: false })) continue;       // water / pitch / building (sanity.js)
        const y = ctx.topAt ? ctx.topAt(x, z) : heightAt(x, z) + 0.3, ang = Math.atan2(dz, dx);   // sidewalk or bridge deck
        pole.box(x, z, y, 0.09, 3.05, 0.09, ang, grey);
        const m = new THREE.Mesh(plateGeo, [edge, edge, edge, edge, matFor(r.name), matFor(r.name)]);
        m.position.set(x, y + 3.0, z); m.rotation.y = -ang;   // plate parallel to the road it names
        m.castShadow = true; m.userData.sanity = { kind: 'sign', dy: 3.0 }; scene.add(m); n++;
      }
      acc = (acc - L) % 140; if (acc < 0) acc += 140;
    }
  }
  if (!pole.empty()) { const pm = new THREE.Mesh(pole.geometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.4 })); pm.castShadow = true; scene.add(pm); }
  return n;
}

export function buildLamps(ctx, roads) {
  const { scene, heightAt, inCampus } = ctx;
  const geo = mergeGeometries([
    new THREE.CylinderGeometry(0.07, 0.1, 6, 6).translate(0, 3, 0),
    new THREE.BoxGeometry(0.08, 0.08, 1.3).translate(0, 5.95, -0.6),
  ]);
  const headGeo = new THREE.BoxGeometry(0.32, 0.14, 0.55).translate(0, 5.88, -1.2);
  const spots = [];
  for (const r of roads) {
    if (r.w < 5.5 || r.area) continue;      // area = paved street surface (road_audit "area"), not a carriageway
    let acc = 12, side = 1;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1];
      const L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 0.1) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = acc; t < L; t += 30) {
        const x = x0 + dx * t, z = z0 + dz * t;
        if (!inCampus(x, z)) continue;
        const o = r.w / 2 + (r.sw ? 0.6 : 0.9);
        if (ctx.onRoad?.(x - dz * o * side, z + dx * o * side, r, 1)) continue;
        if (ctx.blockedBy?.(x - dz * o * side, z + dx * o * side, { r: 0.15, road: false })) continue;   // water / pitch / building
        // arm (local -z) reaches back over the carriageway: rotation a maps -z to (-sin a, -cos a) = (dz, -dx) * side
        spots.push([x - dz * o * side, z + dx * o * side, Math.atan2(-dz * side, dx * side)]);
        side = -side;
      }
      acc = (acc - L) % 30;
      if (acc < 0) acc += 30;
    }
  }
  const im = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: '#3d4247', roughness: 0.6, metalness: 0.4 }), spots.length);
  const headMat = new THREE.MeshStandardMaterial({ color: '#e8e4da', roughness: 0.4, emissive: new THREE.Color('#fff0c8'), emissiveIntensity: 0 });
  const hm = new THREE.InstancedMesh(headGeo, headMat, spots.length);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), one = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
  const topAt = ctx.topAt || heightAt;      // on the sidewalk / bridge deck, not the terrain or riverbed under it
  spots.forEach(([x, z, a], i) => { p.set(x, topAt(x, z), z); q.setFromAxisAngle(up, a); m4.compose(p, q, one); im.setMatrixAt(i, m4); hm.setMatrixAt(i, m4); });
  im.computeBoundingSphere(); im.castShadow = true; hm.computeBoundingSphere(); im.userData.sanity = { kind: 'lamp', arm: 1.2 };
  scene.add(im, hm);
  // garden lamps (庭院灯) along campus footpaths: 3.3 m post with a globe, every 20 m, alternating sides
  const gs = [];
  for (const r of roads) {
    if (!NONCAR.has(r.kind) || r.kind === 'steps' || r.area) continue;
    let acc = 8, side = 1;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1];
      const L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 0.1) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = acc; t < L; t += 20) {
        const o = r.w / 2 + 0.45, x = x0 + dx * t - dz * o * side, z = z0 + dz * t + dx * o * side;
        side = -side;
        if (!inCampus(x, z) || ctx.onRoad?.(x, z, null, 1) || (ctx.waterAt && ctx.waterAt(x, z) !== null)) continue;
        if (ctx.blockedBy?.(x, z, { r: 0.15, road: false, path: 0.05 })) continue;   // building / pitch / any path (own at bends)
        gs.push([x, z]);
      }
      acc = (acc - L) % 20; if (acc < 0) acc += 20;
    }
  }
  if (gs.length) {
    const post = mergeGeometries([new THREE.CylinderGeometry(0.05, 0.07, 3.2, 6).translate(0, 1.6, 0), new THREE.CylinderGeometry(0.12, 0.14, 0.3, 8).translate(0, 0.15, 0),
      new THREE.CylinderGeometry(0.16, 0.05, 0.12, 8).translate(0, 3.18, 0)]);
    const globe = new THREE.SphereGeometry(0.2, 12, 8).translate(0, 3.42, 0);
    const pm = new THREE.InstancedMesh(post, new THREE.MeshStandardMaterial({ color: '#2f3336', roughness: 0.5, metalness: 0.5 }), gs.length);
    const gm = new THREE.InstancedMesh(globe, headMat, gs.length);
    gs.forEach(([x, z], i) => { p.set(x, topAt(x, z), z); m4.compose(p, q.identity(), one); pm.setMatrixAt(i, m4); gm.setMatrixAt(i, m4); });
    pm.computeBoundingSphere(); gm.computeBoundingSphere(); pm.castShadow = true; pm.userData.sanity = { kind: 'glamp' };
    scene.add(pm, gm);
  }
  // night: warm light pools on the ground under every lamp (additive decals, hidden by day)
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const x2 = c.getContext('2d'), gr = x2.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,214,150,0.85)'); gr.addColorStop(0.45, 'rgba(255,190,120,0.35)'); gr.addColorStop(1, 'rgba(255,170,90,0)');
  x2.fillStyle = gr; x2.fillRect(0, 0, 128, 128);
  const poolMat = new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 });
  const all = [...spots.map(([x, z, a]) => [x - Math.sin(a) * 1.2, z - Math.cos(a) * 1.2, 9]), ...gs.map(([x, z]) => [x, z, 5])];
  const pool = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2), poolMat, all.length);
  all.forEach(([x, z, r], i) => { p.set(x, topAt(x, z) + 0.3, z); m4.compose(p, q.identity(), new THREE.Vector3(r, 1, r)); pool.setMatrixAt(i, m4); });
  pool.computeBoundingSphere(); pool.visible = false; pool.renderOrder = 2;
  scene.add(pool);
  headMat.userData.pools = pool;
  return headMat;
}

// ---------------------------------------------------------------- entrances: door + canopy on the wall facing the nearest road, name plaque
export function buildEntrances(ctx, metas, roads) {
  const { scene, heightAt } = ctx;
  const rp = [];
  for (const r of roads) {
    if (r.w < 3) continue;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1], L = Math.hypot(x1 - x0, z1 - z0);
      for (let t = 0; t <= L; t += 4) rp.push(x0 + (x1 - x0) * t / Math.max(L, 1e-6), z0 + (z1 - z0) * t / Math.max(L, 1e-6));
    }
  }
  const canopy = new GeoBuf(), door = new GeoBuf();
  const cC = new THREE.Color('#e9e7e1'), dC = new THREE.Color('#25313b'), colC = new THREE.Color('#cfcbc2');
  let plaques = 0;
  for (const m of metas) {
    if (m.replaced || !m.xs || m.kind === 'wall' || m.kind === 'poi' || m.top - m.base < 5 || !m.campus) continue;
    let best = null;
    const n = m.xs.length;
    for (let i = 0; i < n; i++) {
      const ax = m.xs[i], az = m.zs[i], bx = m.xs[(i + 1) % n], bz = m.zs[(i + 1) % n];
      const len = Math.hypot(bx - ax, bz - az);
      if (len < 8) continue;
      const mx = (ax + bx) / 2, mz = (az + bz) / 2;
      let d = Infinity;
      for (let k = 0; k < rp.length; k += 2) { const dd = (rp[k] - mx) ** 2 + (rp[k + 1] - mz) ** 2; if (dd < d) d = dd; }
      if (!best || d < best.d) best = { d, ax, az, bx, bz, len, mx, mz };
    }
    if (!best) continue;
    const { ax, az, bx, bz, len, mx, mz } = best;
    const ux = (bx - ax) / len, uz = (bz - az) / len, nx = uz, nz = -ux;   // outward normal (counter-clockwise footprints)
    const y = m.base + 0.0, ang = Math.atan2(uz, ux);
    const P = (u, v, h) => [mx + ux * u + nx * v, y + h, mz + uz * u + nz * v];
    // door spot 4 m in front of the entrance, facing out (life.js: a few students standing at teaching buildings)
    (ctx.doors ||= []).push({ x: mx + nx * 4, z: mz + nz * 4, nx, nz, kind: m.kind, name: m.name || '' });
    if (!m.generic) {      // Blender generic buildings bring their own entrance canopy; only the name plaque is added
      // glass door on the wall
      const d0 = P(-1.4, 0.06, 0), d1 = P(1.4, 0.06, 0);
      door.wall(d0[0], d0[2], d1[0], d1[2], y, y + 2.7, nx, nz, 0, 0, 0, 0, dC);
      // canopy slab and two columns
      const cx = mx + nx * 1.1, cz = mz + nz * 1.1;
      canopy.box(cx, cz, y + 3.1, 4.6, 0.28, 2.2, ang, cC);
      for (const s of [-1, 1]) { const q = P(s * 2.1, 2.0, 0); canopy.box(q[0], q[2], y, 0.22, 3.1, 0.22, ang, colC); }
    }
    // name plaque above the canopy
    if (m.name && plaques < 140) {
      const c = document.createElement('canvas'); c.width = 512; c.height = 96;
      const x = c.getContext('2d');
      x.fillStyle = '#7a1f1f'; x.fillRect(0, 0, 512, 96);
      x.fillStyle = '#f1d9a6'; x.font = 'bold 60px "KaiTi", "STKaiti", "Microsoft YaHei", serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(m.name.replace(/（.*?）/g, ''), 256, 52);
      const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
      const pl = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 0.8), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6 }));
      const q = P(0, 0.08, 3.9);
      pl.position.set(q[0], q[1], q[2]);
      pl.rotation.y = Math.atan2(nx, nz);
      scene.add(pl);
      plaques++;
    }
  }
  for (const [buf, mat] of [[canopy, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7 })], [door, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.15, metalness: 0.3 })]]) {
    if (buf.empty()) continue;
    const mesh = new THREE.Mesh(buf.geometry(), mat); mesh.castShadow = true; mesh.receiveShadow = true; scene.add(mesh);
  }
  return plaques;
}
