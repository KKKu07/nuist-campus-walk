// 云游南信大 · 校园三维场景展示版：只有学校整体模型和场景，没有玩法（无角色、手机、打卡、公交/7ma 乘骑、导览）。
// 场景构建与主游戏共用 world.js / sports.js / life.js / textures.js；相机是高空俯瞰 + 地图式操作（MapControls）。
// 坐标：米，原点 = 校园外包框中心，x 向东，z 向南，y 向上。
import * as THREE from 'three';
import { Sky } from 'three/examples/jsm/objects/Sky.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { MapControls } from 'three/examples/jsm/controls/MapControls.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { facadeMaterials, roadTextures, detailTexture, waterNormal } from './textures.js';
import { loadDetailTextures, buildGround, buildRoads, buildJunctions, buildWater, buildBuildings, buildLandmarks, buildPois, buildTrees, buildLamps, buildFlowers, buildEntrances, buildRoadSigns } from './world.js';
import { buildFence, buildCars, createWalkers, createGrass, makeLandcoverReader, makeGroundReader, buildHedges, buildShrubs, buildFurniture } from './life.js';
import { buildSports } from './sports.js';
import { boundaryOpenings, modelGrid, coverage } from './bounds.js';
import { makeUnderpasses } from './underpass.js';
import { makeClearance, bankApron } from './sanity.js';

const $ = (id) => document.getElementById(id);
const setMsg = (t) => { $('loadMsg').textContent = t; };
const loadJSON = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(`${url} ${r.status}`); return r.json(); };
const tick = () => new Promise((r) => setTimeout(r, 20));
const clamp = THREE.MathUtils.clamp, deg = THREE.MathUtils.degToRad;

// ---------- renderer / scene ----------
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, isTouch ? 1.5 : 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.85;
$('app').appendChild(renderer.domElement);
const maxTex = renderer.capabilities.maxTextureSize;
const aniso = renderer.capabilities.getMaxAnisotropy();

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xd3dee6, 2500, 8000);
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 1, 12000);

const sunDir = new THREE.Vector3().setFromSphericalCoords(1, deg(90 - 42), deg(35));
function makeSky(scale) {
  const s = new Sky();
  s.scale.setScalar(scale);
  const u = s.material.uniforms;
  u.turbidity.value = 5; u.rayleigh.value = 1.2; u.mieCoefficient.value = 0.004; u.mieDirectionalG.value = 0.8;
  u.sunPosition.value.copy(sunDir);
  return s;
}
const skyMesh = makeSky(11000);
scene.add(skyMesh);
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
envScene.add(makeSky(1000));
scene.environment = pmrem.fromScene(envScene).texture;
scene.environmentIntensity = 0.5;
scene.add(new THREE.HemisphereLight(0xcfe2ff, 0x5d6650, 0.8));
const sun = new THREE.DirectionalLight(0xfff1dc, 2.6);
sun.castShadow = true;
sun.shadow.mapSize.set(isTouch ? 2048 : 4096, isTouch ? 2048 : 4096);
sun.shadow.normalBias = 0.4;
scene.add(sun, sun.target);

let composer = null;
if (!isTouch) {   // contact shadows at building feet / under trees, as in the game
  const rt = new THREE.WebGLRenderTarget(innerWidth * renderer.getPixelRatio(), innerHeight * renderer.getPixelRatio(), { samples: 4, type: THREE.HalfFloatType });
  composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  const ao = new GTAOPass(scene, camera, innerWidth, innerHeight);
  ao.updateGtaoMaterial({ radius: 1.6, distanceExponent: 1.4, thickness: 1.2, scale: 1.1, samples: 12 });
  ao.blendIntensity = 0.85;
  composer.addPass(ao);
  composer.addPass(new OutputPass());
}

// ---------- terrain helpers (same as the game: main.js heightAt / terrainAt) ----------
let W = 1, D = 1, T = null, boundary = [];
let under = null;          // underpass.js (中苑 <-> 东苑 under 盘城新街)
function heightAt(x, z) {
  const c = under ? under.cutAt(x, z) : null;
  return c ?? terrainAt(x, z);
}
function terrainAt(x, z) {
  const { nx, nz, h } = T;
  const gx = (x + W / 2) / W * (nx - 1), gz = (z + D / 2) / D * (nz - 1);
  const i = Math.max(0, Math.min(nx - 2, Math.floor(gx))), k = Math.max(0, Math.min(nz - 2, Math.floor(gz)));
  const fx = Math.min(1, Math.max(0, gx - i)), fz = Math.min(1, Math.max(0, gz - k));
  const ha = h[k * nx + i], hd = h[k * nx + i + 1], hb = h[(k + 1) * nx + i], hc = h[(k + 1) * nx + i + 1];
  return (fx + fz <= 1 ? ha + (hd - ha) * fx + (hb - ha) * fz : hc + (hb - hc) * (1 - fx) + (hd - hc) * (1 - fz)) / 10;
}
function pointInPoly(x, z, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, zi] = pts[i], [xj, zj] = pts[j];
    if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}
const inCampus = (x, z) => boundary.some((r) => pointInPoly(x, z, r));

// as main.js does before building: fix each water level and dig the ground mesh (only) below it, plus the first ring
// of vertices outside each outline (returned as dugH: grid index -> dug height); level every sports ground
function shapeTerrain(C) {
  const dugH = new Map();
  for (const wp of C.water || []) {
    if (wp.pts.length < 3) continue;
    wp.level = wp.pts.reduce((s, [x, z]) => s + heightAt(x, z), 0) / wp.pts.length - 0.6;
    const xs = wp.pts.map((q) => q[0]), zs = wp.pts.map((q) => q[1]);
    const i0 = Math.max(0, Math.floor((Math.min(...xs) + W / 2) / W * (T.nx - 1))), i1 = Math.min(T.nx - 1, Math.ceil((Math.max(...xs) + W / 2) / W * (T.nx - 1)));
    const k0 = Math.max(0, Math.floor((Math.min(...zs) + D / 2) / D * (T.nz - 1))), k1 = Math.min(T.nz - 1, Math.ceil((Math.max(...zs) + D / 2) / D * (T.nz - 1)));
    for (let k = k0; k <= k1; k++) for (let i = i0; i <= i1; i++) {
      const x = -W / 2 + i * W / (T.nx - 1), z = -D / 2 + k * D / (T.nz - 1), j = k * T.nx + i;
      if (pointInPoly(x, z, wp.pts)) dugH.set(j, Math.min(dugH.get(j) ?? T.h[j], Math.round((wp.level - 1.2) * 10)));
    }
  }
  for (const j of [...dugH.keys()]) {
    const i = j % T.nx, k = (j - i) / T.nx;
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      const ii = i + a, kk = k + b, nj = kk * T.nx + ii;
      if (ii >= 0 && kk >= 0 && ii < T.nx && kk < T.nz && !dugH.has(nj)) dugH.set(nj, Math.min(T.h[nj], dugH.get(j)));
    }
  }
  const flats = [...(C.sports || []).map((s) => s.obb),
    ...(C.pois || []).filter((q) => q.field).map((q) => [(q.field[0] + q.field[2]) / 2, (q.field[1] + q.field[3]) / 2, q.field[2] - q.field[0] - 20, q.field[3] - q.field[1] - 20, 0])];
  for (const [cx, cz, L, Wd, ang] of flats) {
    const ca = Math.cos(ang), sa = Math.sin(ang), idx = [];
    for (let k = 0; k < T.nz; k++) for (let i = 0; i < T.nx; i++) {
      const x = -W / 2 + i * W / (T.nx - 1) - cx, z = -D / 2 + k * D / (T.nz - 1) - cz;
      if (Math.abs(x * ca + z * sa) < L / 2 + 12 && Math.abs(-x * sa + z * ca) < Wd / 2 + 12) idx.push(k * T.nx + i);
    }
    if (!idx.length) continue;
    const mean = Math.round(idx.reduce((s, j) => s + T.h[j], 0) / idx.length);
    for (const j of idx) T.h[j] = mean;
  }
  return dugH;
}

function prepModelMesh(o) { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } }

// ---------- camera: high oblique overview, map-style controls ----------
const controls = new MapControls(camera, renderer.domElement);
Object.assign(controls, {
  enableDamping: true, dampingFactor: 0.08, screenSpacePanning: false, zoomToCursor: true,
  minDistance: 25, maxDistance: 4200, maxPolarAngle: deg(84), autoRotateSpeed: 0.8,
});
const view = { target: new THREE.Vector3(), r: 2000, phi: deg(45), theta: 0 };   // theta 0: camera south of the target, north is up
let home = null, anim = null, presets = [];

// frame the built-up campus (buildings inside the campus boundary, 2–98 % quantiles), not the hills around it
function overview(metas) {
  const inside = metas.filter((m) => m.kind !== 'wall' && m.cx !== undefined && inCampus(m.cx, m.cz));
  const q = (a, f) => { const b = a.slice().sort((x, y) => x - y); return b[Math.floor(f * (b.length - 1))]; };
  const xs = inside.map((m) => m.cx), zs = inside.map((m) => m.cz);
  const x0 = q(xs, 0.02) - 100, x1 = q(xs, 0.98) + 100, z0 = q(zs, 0.02) - 80, z1 = q(zs, 0.98) + 80;
  const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  const th = Math.tan(Math.atan(Math.tan(deg(camera.fov / 2)) * camera.aspect)), tv = Math.tan(deg(camera.fov / 2));
  const fit = (across, deep) => Math.max(across * 0.57 / th, deep * 0.72 / tv);   // 0.57: the near (lower) edge is closer, so it needs a margin
  // landscape screens look north (east–west across the screen); portrait phones look west so the long axis runs up the screen
  const rN = fit(x1 - x0, z1 - z0), rW = fit(z1 - z0, x1 - x0);
  return { label: '全校全景', target: new THREE.Vector3(cx, heightAt(cx, cz), cz), r: clamp(Math.min(rN, rW), 700, 4000), phi: deg(45), theta: rN <= rW ? 0 : deg(90) };
}
function setCamera(v) {
  controls.target.copy(v.target);
  camera.position.setFromSphericalCoords(v.r, v.phi, v.theta).add(v.target);
  camera.lookAt(v.target);
}
function currentView() {
  const s = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  return { target: controls.target.clone(), r: s.radius, phi: s.phi, theta: s.theta };
}
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
function flyTo(v) {
  const from = currentView();
  let dTheta = v.theta - from.theta;
  dTheta = Math.atan2(Math.sin(dTheta), Math.cos(dTheta));
  const travel = from.target.distanceTo(v.target);
  anim = { from, to: v, dTheta, t: 0, dur: clamp(1.4 + travel / 900, 1.6, 3.2), lift: clamp(travel * 0.6 - Math.max(from.r, v.r) * 0.4, 0, 1500) };
  showView(v.label);
}
function stepAnim(dt) {
  anim.t = Math.min(1, anim.t + dt / anim.dur);
  const e = ease(anim.t), { from, to } = anim;
  setCamera({
    target: from.target.clone().lerp(to.target, e),
    r: Math.exp(Math.log(from.r) + (Math.log(to.r) - Math.log(from.r)) * e) + anim.lift * Math.sin(Math.PI * e),
    phi: from.phi + (to.phi - from.phi) * e,
    theta: from.theta + anim.dTheta * e,
  });
  if (anim.t >= 1) anim = null;
}
for (const ev of ['pointerdown', 'wheel', 'touchstart']) renderer.domElement.addEventListener(ev, () => { anim = null; }, { passive: true });

// keyboard: WASD / arrows move, Q/E turn, R/F (or +/-) zoom, Shift faster
const keys = new Set();
addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement) return;
  keys.add(e.code);
  if (e.code === 'KeyH' || e.code === 'Home') flyTo(home);
  if (e.code === 'KeyO') toggleOrbit();
});
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());
const kv = new THREE.Vector3(), off = new THREE.Vector3();
function keyMove(dt) {
  const k = (...c) => (c.some((x) => keys.has(x)) ? 1 : 0);
  const f = k('KeyW', 'ArrowUp') - k('KeyS', 'ArrowDown'), s = k('KeyD', 'ArrowRight') - k('KeyA', 'ArrowLeft');
  const turn = k('KeyE') - k('KeyQ'), zoom = k('KeyF', 'Minus', 'NumpadSubtract') - k('KeyR', 'Equal', 'NumpadAdd');
  if (!f && !s && !turn && !zoom) return;
  anim = null;
  const fast = k('ShiftLeft', 'ShiftRight') ? 2.5 : 1;
  off.copy(camera.position).sub(controls.target);
  const dist = off.length();
  if (f || s) {
    const yaw = Math.atan2(off.x, off.z);
    kv.set(-Math.sin(yaw) * f + Math.cos(yaw) * s, 0, -Math.cos(yaw) * f - Math.sin(yaw) * s).multiplyScalar(dist * 0.7 * fast * dt);
    controls.target.add(kv); camera.position.add(kv);
  }
  if (turn) { off.applyAxisAngle(THREE.Object3D.DEFAULT_UP, -turn * 0.9 * fast * dt); camera.position.copy(controls.target).add(off); }
  if (zoom) { off.multiplyScalar(Math.exp(zoom * 1.2 * fast * dt)); off.setLength(clamp(off.length(), controls.minDistance, controls.maxDistance)); camera.position.copy(controls.target).add(off); }
}

// ---------- UI ----------
let viewT = 0;
function showView(label) { if (!label) return; $('viewName').textContent = label; viewT = 0; }
function toggleOrbit(on = !controls.autoRotate) {
  controls.autoRotate = on;
  $('orbitBtn').classList.toggle('on', on);
  $('orbitBtn').textContent = on ? '⟳ 环绕中' : '⟳ 自动环绕';
}
function buildPresetBar() {
  const bar = $('presets');
  const all = [home, ...presets];
  for (const v of all) {
    const b = document.createElement('button');
    b.textContent = v.label;
    b.addEventListener('click', () => flyTo(v));
    bar.appendChild(b);
  }
  const o = document.createElement('button');
  o.id = 'orbitBtn'; o.className = 'orbit';
  o.addEventListener('click', () => toggleOrbit());
  bar.appendChild(o);
  toggleOrbit(false);
}
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer?.setSize(innerWidth, innerHeight);
});

// ---------- per-frame: keep near plane, fog and the sun's shadow box matched to the viewing distance ----------
let walkers = null, grass = null, waterMat = null, shadowExt = 0;
const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05);
  if (anim) stepAnim(dt); else keyMove(dt);
  controls.update(dt);
  // stay inside the map and above the ground; the pivot sits on the terrain
  const t = controls.target;
  const tx = clamp(t.x, -W / 2 + 50, W / 2 - 50), tz = clamp(t.z, -D / 2 + 50, D / 2 - 50), ty = heightAt(tx, tz);
  camera.position.add(kv.set(tx - t.x, ty - t.y, tz - t.z)); t.set(tx, ty, tz);
  camera.position.y = Math.max(camera.position.y, heightAt(camera.position.x, camera.position.z) + 3);
  const dist = camera.position.distanceTo(t);

  camera.near = clamp(dist * 0.004, 0.3, 10); camera.far = clamp(dist * 3 + 5000, 6000, 14000); camera.updateProjectionMatrix();
  scene.fog.near = dist * 0.8 + 600; scene.fog.far = dist * 2.4 + 3200;
  const ext = clamp(dist * 0.8, 160, 1700);
  if (Math.abs(ext - shadowExt) / ext > 0.08) {
    shadowExt = ext;
    Object.assign(sun.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext, near: 1, far: ext * 2 + 1800 });
    sun.shadow.camera.updateProjectionMatrix();
    sun.shadow.bias = -0.0003 * 1200 / (ext * 2 + 1800);
  }
  sun.target.position.copy(t);
  sun.position.copy(t).addScaledVector(sunDir, ext + 900);
  sun.target.updateMatrixWorld();

  if (walkers) walkers.update(dt, clock.elapsedTime);
  if (grass && dist < 220) grass.update(t);
  if (waterMat) waterMat.normalMap.offset.set(clock.elapsedTime * 0.004, clock.elapsedTime * 0.0025);
  viewT += dt;
  $('viewName').classList.toggle('fade', viewT > 6);

  if (composer) composer.render(); else renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

// ---------- boot: the same scene as the game, without any gameplay ----------
const PRESETS = ['图书馆', '气象楼', '钟楼', '文德楼', '信息科技大楼（临江楼）', '尚贤楼', '藕舫楼', '见山园', '东苑体育馆', '老校门', '东大门', '升旗广场'];
async function main() {
  setMsg('加载校园数据…');
  const [C, terrain] = await Promise.all([loadJSON('campus/campus.json'), loadJSON('campus/terrain.json')]);
  W = C.size[0]; D = C.size[1]; T = terrain; boundary = C.boundary || [];
  const openings = boundary.length ? boundaryOpenings(boundary, (C.pois || []).filter((p) => /gate/.test(p.landmark || '')), C.roads || []) : [];
  under = C.underpasses?.length ? makeUnderpasses(C.underpasses, terrainAt) : null;
  setMsg('加载航拍影像…');
  const orthoTex = await new THREE.TextureLoader().loadAsync(maxTex >= 8192 && !isTouch ? 'campus/ortho.jpg' : 'campus/ortho_4k.jpg');
  orthoTex.colorSpace = THREE.SRGBColorSpace;
  orthoTex.anisotropy = aniso;
  const ctx = { scene, heightAt, inCampus, W, D, aniso, under, terrainAt };
  const dugH = shapeTerrain(C);
  const modelGrids = [], modelledIds = new Set();   // model footprints, so trees / props keep out of the Blender buildings

  setMsg('加载天空和地面贴图…');
  const det = await loadDetailTextures(aniso);
  try {
    det.lc = await new THREE.TextureLoader().loadAsync('campus/landcover.png');
    det.lc.magFilter = det.lc.minFilter = THREE.NearestFilter; det.lc.generateMipmaps = false;
  } catch { /* optional */ }
  try {
    const hdr = await new RGBELoader().loadAsync('tex/sky.hdr');
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    scene.environment = pmrem.fromEquirectangular(hdr).texture;
    scene.background = hdr; scene.backgroundIntensity = 0.85; scene.environmentIntensity = 0.55;
    skyMesh.visible = false;
  } catch (e) { console.warn('sky.hdr not loaded, using procedural sky', e); }
  try {
    det.groundMeta = await (await fetch('campus/ground_meta.json')).json();
    det.ground = await new THREE.TextureLoader().loadAsync('campus/ground.png');
    det.ground.magFilter = det.ground.minFilter = THREE.NearestFilter; det.ground.generateMipmaps = false;
  } catch { det.ground = null; det.groundMeta = null; }

  setMsg('生成地形、道路和水面…'); await tick();
  const rtex = roadTextures(aniso);
  det.tileTex = rtex.tile; det.brickTex = rtex.brick; det.stoneTex = rtex.stone; det.lite = isTouch;   // 地表色板 granite slabs
  const renderH = T.h.slice();
  for (const [j, v] of dugH) renderH[j] = Math.min(renderH[j], v);
  const nGround = scene.children.length;
  buildGround(ctx, { ...T, h: renderH }, orthoTex, detailTexture(aniso), det);
  const groundMesh = scene.children.slice(nGround).find((o) => o.isMesh);
  waterMat = buildWater(ctx, C.water, waterNormal(), C.roads);
  if (groundMesh && dugH.size) bankApron(ctx, T, renderH, new Set(dugH.keys()), groundMesh.material, { cell: isTouch ? 1 : 0.5 });
  buildRoads(ctx, C.roads, rtex, det);
  if (under) { const ug = under.build(ctx, C.roads); if (ug) modelGrids.push(ug); }   // cut walls, deck / tunnel roof
  buildJunctions(ctx, C.junctions, det);
  buildSports(ctx, C.sports);

  setMsg('生成建筑…'); await tick();
  const metas = buildBuildings(ctx, C.buildings, facadeMaterials(aniso), orthoTex, det, rtex.roof);
  buildLandmarks(ctx, metas);
  buildEntrances(ctx, metas, C.roads);
  const named = [...metas.filter((m) => m.name), ...buildPois(ctx, C.pois)];

  const loader = new GLTFLoader();
  if (C.models?.length) {
    setMsg('加载精修模型…');
    await Promise.all(C.models.map(async (md) => {
      try {
        const gltf = await loader.loadAsync(md.file);
        const reps = metas.filter((m) => m.replaced && Math.hypot(m.cx - md.x, m.cz - md.z) < 120);
        const base = reps.length ? Math.min(...reps.map((m) => m.base)) : heightAt(md.x, md.z);
        gltf.scene.position.set(md.x, base, md.z);
        gltf.scene.rotation.y = deg(md.rotY || 0);
        gltf.scene.traverse(prepModelMesh);
        scene.add(gltf.scene);
        const g = modelGrid(gltf.scene, base);
        if (g) { g.name = md.name; modelGrids.push(g); }
      } catch (e) { console.warn('model failed', md.file, e); }
    }));
    for (const m of metas) if (m.replaced && m.xs && modelGrids.some((g) => coverage(g, m.xs, m.zs) > 0.5)) modelledIds.add(String(m.id));
  }
  if (C.generic?.length) {
    setMsg('加载楼宇模型…');
    const byId = new Map(metas.filter((m) => m.generic).map((m) => [String(m.id), m]));
    await Promise.all(C.generic.map(async (ch) => {
      try {
        const gltf = await loader.loadAsync(ch.file);
        gltf.scene.position.set(ch.x, 0, ch.z);
        for (const node of [...gltf.scene.children]) {
          const m = byId.get(node.name);
          if (!m) { node.visible = false; continue; }
          node.position.y = m.base;
        }
        gltf.scene.traverse(prepModelMesh);
        scene.add(gltf.scene);
      } catch (e) { console.warn('generic chunk failed', ch.file, e); }
    }));
  }

  // common-sense placement rules (sanity.js): nothing in water, on pitches, inside buildings / models or on carriageways
  makeClearance(ctx, { roads: C.roads, sports: C.sports, metas, modelGrids, modelledIds, junctions: C.junctions });
  setMsg('种树、装路灯…'); await tick();
  // trees, same rules as main.js: a trunk on a road / path moves up to 2 m off it, a crown reaching into a wall is narrowed
  const treeOpt = { r: 0.25, sport: 2, road: 0.2, path: 0 }, treeList = [];
  for (const t0 of C.trees) {
    let t = t0, why = ctx.blockedBy(t[0], t[1], treeOpt);
    if (why === 'road' || why === 'path') {
      why = 'moved';
      search: for (let rr = 0.5; rr <= 2; rr += 0.5) for (let k = 0; k < 8; k++) {
        const x = t[0] + Math.cos(k * Math.PI / 4) * rr, z = t[1] + Math.sin(k * Math.PI / 4) * rr;
        if (!ctx.blockedBy(x, z, treeOpt)) { t = [x, z, ...t.slice(2)]; why = null; break search; }
      }
    }
    if (why) continue;
    const R = (t.length > 4 ? t[3] : t[2] * 2.3) * 1.1, d = ctx.buildingDist(t[0], t[1], Math.min(4, R));
    if (d < R - 0.5) {
      if (d < 0.8) continue;
      t = t.length > 4 ? [t[0], t[1], t[2], Math.max(1.0, (d + 0.4) / 1.1), ...t.slice(4)] : [t[0], t[1], Math.max(0.45, (d + 0.4) / 2.5)];
    }
    treeList.push(t);
  }
  buildTrees(ctx, treeList, isTouch);
  buildLamps(ctx, C.roads);
  buildRoadSigns(ctx, C.roads);      // after the models: signs keep out of buildings too
  buildFlowers(ctx, C.flowers);
  const markers = C.markers || [];
  buildFence(ctx, boundary, openings);
  buildCars(ctx, C.roads, markers.filter((mk) => mk.cat === '停车场'));
  walkers = createWalkers(ctx, C.roads, isTouch ? 40 : 90, isTouch ? 8 : 14);
  // grass tufts, hedges, shrubs, benches follow the ground the terrain shows (ground.png), else the aerial land cover
  const lcAt = det.ground && det.groundMeta ? makeGroundReader(ctx, det.ground.image, det.groundMeta) : det.lc ? makeLandcoverReader(ctx, det.lc.image) : null;
  if (!isTouch && lcAt) grass = createGrass(ctx, lcAt);
  if (lcAt) {
    buildHedges(ctx, C.roads, lcAt);
    if (!isTouch) buildShrubs(ctx, lcAt);
    buildFurniture(ctx, C.roads, lcAt);
  }

  // preset views: the overview plus the main landmarks (seen from the south-south-east, ~55° down)
  home = overview(metas);
  for (const name of PRESETS) {
    const m = named.find((q) => q.name === name) || (() => { const mk = markers.find((q) => q.name === name); return mk && { name, cx: mk.x, cz: mk.z, kind: 'poi' }; })();
    if (!m) continue;
    const size = m.maxX !== undefined ? Math.max(m.maxX - m.minX, m.maxZ - m.minZ, 0) : 0;
    const tall = m.top !== undefined && m.base !== undefined ? m.top - m.base : 20;
    presets.push({ label: name.replace('信息科技大楼（临江楼）', '临江楼'), target: new THREE.Vector3(m.cx, heightAt(m.cx, m.cz) + Math.min(tall, 40) * 0.3, m.cz),
      r: clamp(size * 2.2 + tall * 2, 170, 520), phi: deg(57), theta: deg(20) });
  }
  setCamera(home);
  buildPresetBar();
  showView(home.label);
  $('stats').textContent = `${metas.filter((m) => m.kind !== 'wall').length} 栋建筑 · ${(C.models?.length || 0)} 个精修模型 · ${treeList.length.toLocaleString()} 棵树`;
  if (import.meta.env.DEV) window.__showcase = { scene, camera, controls, flyTo, presets, get home() { return home; }, heightAt, THREE };
  $('loading').remove();
  setTimeout(() => $('hint').classList.add('fade'), 12000);
  frame();
}

main().catch((e) => { console.error(e); setMsg(`加载失败：${e.message}`); });
