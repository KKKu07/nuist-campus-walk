// 云游南信大 · 原型 v0.2
// Data: campus/campus.json (buildings/roads/water/trees/zones/pois/bus/ebikes in local metres), campus/terrain.json, campus/ortho*.jpg
// Local coordinates: metres, origin = bbox centre, x = east, z = south, y = up.
import * as THREE from 'three';
import { Sky } from 'three/examples/jsm/objects/Sky.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { facadeMaterials, roadTextures, detailTexture, waterNormal, litWindows } from './textures.js';
import { loadDetailTextures, buildGround, buildRoads, buildJunctions, buildWater, buildBuildings, buildLandmarks, buildPois, buildTrees, buildLamps, buildFlowers, buildEntrances, buildRoadSigns } from './world.js';
import { createBus, createEbikes, ebikeModel, setEbikeGLB } from './vehicles.js';
import { buildFence, buildCars, createWalkers, createGrass, makeLandcoverReader, makeGroundReader, buildHedges, buildShrubs, buildFurniture } from './life.js';
import { buildSports } from './sports.js';
import { createQuest } from './quest.js';
import { createTour } from './tour.js';
import { createPhone } from './phone/phone.js';
import { createStunt } from './stunt.js';
import { createAvatar } from './avatar.js';
import { createRoute } from './route.js';
import { showStartMenu } from './start.js';
import { makeAirWall, boundaryOpenings, modelGrid, collideGrid, coverage } from './bounds.js';
import { makeUnderpasses } from './underpass.js';
import { makeClearance, scanWorld, bankApron } from './sanity.js';
import { chooseTier, pixelRatio, createDetail, splitInstanced, mergeStatic, createFpsGuard, mountQualityMenu, devBench, compactGroups, createTextureDedupe } from './perf.js';
import { stuntsOn as STUNTS } from './features.js';   // 飙车 / 翘头 on/off: features.js (or ?stunt=0 / ?stunt=1)

const $ = (id) => document.getElementById(id);
const setMsg = (t) => { $('loadMsg').textContent = t; performance.mark?.(t); };   // marks: load phases (性能)
const progress = (label, total) => { let n = 0; return () => { n++; $('loadMsg').textContent = `${label} ${n}/${total}`; }; };
const loadJSON = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(`${url} ${r.status}`); return r.json(); };
const loadImage = (url) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error(url)); i.src = url; });
const tick = () => new Promise((r) => setTimeout(r, 20));

// ---------- renderer / scene (phones get a lighter setup) ----------
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
// 性能 (perf.js): 画质 流畅 / 均衡 / 高清, picked from the GPU or the player's saved choice; detail hides far vegetation
const Q = chooseTier(renderer, isTouch);
let tier = Q.tier, qmenu = null;
const detail = createDetail(), texDedupe = createTextureDedupe();
detail.setLod(tier.lod);
renderer.setPixelRatio(pixelRatio(tier, isTouch));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = tier.id === 'low' ? THREE.PCFShadowMap : THREE.PCFSoftShadowMap;
renderer.shadowMap.autoUpdate = tier.id === 'high';   // 流畅 / 均衡: shadowTick() decides
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.85;
$('app').appendChild(renderer.domElement);
const maxTex = renderer.capabilities.maxTextureSize;
const aniso = renderer.capabilities.getMaxAnisotropy();

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xd3dee6, 700, 3600);
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.2, 9000);

const sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - 42), THREE.MathUtils.degToRad(35));
function makeSky(scale) {
  const s = new Sky();
  s.scale.setScalar(scale);
  const u = s.material.uniforms;
  u.turbidity.value = 5; u.rayleigh.value = 1.2; u.mieCoefficient.value = 0.004; u.mieDirectionalG.value = 0.8;
  u.sunPosition.value.copy(sunDir);
  return s;
}
const skyMesh = makeSky(10000);
scene.add(skyMesh);
const pmrem = new THREE.PMREMGenerator(renderer);
const envScene = new THREE.Scene();
envScene.add(makeSky(1000));
const envRT = pmrem.fromScene(envScene);
scene.environment = envRT.texture;
scene.environmentIntensity = 0.5;
const hemi = new THREE.HemisphereLight(0xcfe2ff, 0x5d6650, 0.8);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xfff1dc, 2.6);
sun.castShadow = true;
sun.shadow.mapSize.set(tier.shadow, tier.shadow);
Object.assign(sun.shadow.camera, { left: -150, right: 150, top: 150, bottom: -150, near: 1, far: 1200 });
sun.shadow.bias = -0.0003;
sun.shadow.normalBias = 0.4;
scene.add(sun, sun.target);

// ambient occlusion (contact shadows at building feet, under trees, in corners) on the 高清 tier; G toggles it
let composer = null, aoOn = tier.ao;
function makeComposer() {
  const rt = new THREE.WebGLRenderTarget(innerWidth * renderer.getPixelRatio(), innerHeight * renderer.getPixelRatio(), { samples: 4, type: THREE.HalfFloatType });
  composer = new EffectComposer(renderer, rt);
  composer.addPass(new RenderPass(scene, camera));
  const ao = new GTAOPass(scene, camera, innerWidth, innerHeight);
  ao.updateGtaoMaterial({ radius: 1.6, distanceExponent: 1.4, thickness: 1.2, scale: 1.1, samples: 12 });
  ao.blendIntensity = 0.85;
  composer.addPass(ao);
  composer.addPass(new OutputPass());
}
if (tier.ao) makeComposer();
// switch tier while playing: resolution, shadows, AO and view distances change at once; tree detail, shrubs, grass and
// the aerial photo resolution are built at load (the quality menu offers a reload)
function applyTier(t, { auto } = {}) {
  tier = t;
  if (auto !== undefined) Q.auto = auto;
  renderer.setPixelRatio(pixelRatio(t, isTouch));
  renderer.setSize(innerWidth, innerHeight);
  if (sun.shadow.mapSize.x !== t.shadow) { sun.shadow.mapSize.set(t.shadow, t.shadow); sun.shadow.map?.dispose(); sun.shadow.map = null; }
  renderer.shadowMap.autoUpdate = t.id === 'high';
  renderer.shadowMap.needsUpdate = true;
  aoOn = t.ao;
  if (aoOn && !composer) makeComposer();
  if (!aoOn && composer) { for (const p of composer.passes) p.dispose?.(); composer.dispose(); composer = null; }
  if (composer) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(innerWidth, innerHeight); }
  detail.setLod(t.lod);
  qmenu?.set(t, { auto: Q.auto });
}

// ---------- world state ----------
let W = 1, D = 1, T = null;
let metas = [], named = [], buildingCount = 0;
const grid = new Map(), CELL = 40;
let stamp = new Int32Array(0), frameId = 1;
let mapImg = null, boundary = [], zones = [], busRoute = [], roadLabels = [];
let facadeMats = {}, lampMat = null, night = false;
const modelNightMats = [];   // glass + window-textured walls of the Blender landmark models
let bus = null, ebikes = null, waterMat = null, markers = [], walkers = null, quest = null, questNext = null, grass = null;
let phone = null, stunt = null, route = null;   // phone/: Tab 手机、钱包、任务、食堂 · stunt.js: 飙车 + 翘头 · route.js: 路线游览
// official campus map POI categories (map.nuist.edu.cn)
const CAT_COLOR = { 食堂餐厅: '#f39c3d', 商业服务: '#e05aa8', 文化风景: '#4fb3ff', 停车场: '#8a9bb0', AED: '#e23b3b', 体育场馆: '#3fbf6f', 校内医疗: '#ff6b6b', 邮寄快递: '#b48a5a', 学生宿舍: '#c9b28f', 家属住宅: '#c9b28f', 教学科研: '#9fb8d8' };
const catColor = (c) => CAT_COLOR[c] || '#d8d8d8';

// ground height everywhere the player, roads and props stand: the terrain, lowered inside the underpass cuts
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
  // same triangulation as the ground PlaneGeometry, so everything sits exactly on the rendered terrain
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

function buildGrid() {
  stamp = new Int32Array(metas.length);
  metas.forEach((m, idx) => {
    if (!m.xs) return;
    const i0 = Math.floor((m.minX + W / 2) / CELL), i1 = Math.floor((m.maxX + W / 2) / CELL);
    const k0 = Math.floor((m.minZ + D / 2) / CELL), k1 = Math.floor((m.maxZ + D / 2) / CELL);
    for (let i = i0; i <= i1; i++) for (let k = k0; k <= k1; k++) {
      const key = `${i},${k}`;
      if (!grid.has(key)) grid.set(key, []);
      grid.get(key).push(idx);
    }
  });
}

// ---------- player ----------
// ride: null | 'bike' (own bicycle, B) | 'ebike' (7ma shared, E) | 'bus' (campus shuttle, E)
let world = null;   // build context (deckAt / surfaceAt / waterAt / onRoad) once the world is built
const P = { pos: new THREE.Vector3(), vy: 0, yaw: 0, pitch: -0.22, onGround: true, fly: false, ride: null, ebikeIdx: -1, first: false, dist: 7 };
const avatar = new THREE.Group();
const rider = new THREE.Group(), bicycle = new THREE.Group(), ebikeMesh = ebikeModel(), rig = createAvatar();
{
  rider.add(rig.root);   // low-poly 男生 / 女生 (avatar.js), picked on the start menu
  const wheelM = new THREE.MeshStandardMaterial({ color: '#222', roughness: 0.6 });
  for (const z of [-0.55, 0.55]) { const w = new THREE.Mesh(new THREE.TorusGeometry(0.33, 0.04, 8, 20), wheelM); w.rotation.y = Math.PI / 2; w.position.set(0, 0.35, z); bicycle.add(w); }
  const frame = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, 1.1), new THREE.MeshStandardMaterial({ color: '#f2c200' }));
  frame.position.y = 0.62; bicycle.add(frame);
  avatar.add(rider, bicycle, ebikeMesh);
  avatar.traverse((o) => { if (o.isMesh) o.castShadow = true; });
}
scene.add(avatar);

function collide(p, r) {
  frameId++;
  const ci = Math.floor((p.x + W / 2) / CELL), ck = Math.floor((p.z + D / 2) / CELL);
  for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
    const list = grid.get(`${ci + a},${ck + b}`);
    if (!list) continue;
    for (const idx of list) {
      if (stamp[idx] === frameId) continue;
      stamp[idx] = frameId;
      const m = metas[idx];
      if (p.y > m.top - 0.3 || (m.replaced && modelledIds.has(String(m.id)))) continue;   // the model's own grid is used
      if (p.x < m.minX - r || p.x > m.maxX + r || p.z < m.minZ - r || p.z > m.maxZ + r) continue;
      const xs = m.xs, zs = m.zs, n = xs.length;
      let inside = false, best = Infinity, bx = 0, bz = 0;
      for (let i = 0, j = n - 1; i < n; j = i++) {
        const xi = xs[i], zi = zs[i], xj = xs[j], zj = zs[j];
        if ((zi > p.z) !== (zj > p.z) && p.x < (xj - xi) * (p.z - zi) / (zj - zi) + xi) inside = !inside;
        const ex = xi - xj, ez = zi - zj, l2 = ex * ex + ez * ez || 1e-9;
        let t = ((p.x - xj) * ex + (p.z - zj) * ez) / l2;
        t = t < 0 ? 0 : t > 1 ? 1 : t;
        const qx = xj + ex * t, qz = zj + ez * t, d2 = (p.x - qx) ** 2 + (p.z - qz) ** 2;
        if (d2 < best) { best = d2; bx = qx; bz = qz; }
      }
      if (inside) { const d = Math.sqrt(best) || 1e-6; p.x = bx + (bx - p.x) / d * r; p.z = bz + (bz - p.z) / d * r; }
      else if (best < r * r) { const d = Math.sqrt(best) || 1e-6; p.x = bx + (p.x - bx) / d * r; p.z = bz + (p.z - bz) / d * r; }
    }
  }
  for (const g of modelGrids) collideGrid(g, p, r);
}
// solid Blender landmark models (bounds.js): occupancy grids at walking height; campus air wall
const modelGrids = [], modelledIds = new Set();
let airWall = null;

// walled off-campus zones (talent apartments): on foot you land just outside the wall
function outsideZones(x, z) {
  for (const zn of zones) {
    const pts = zn.pts;
    if (!pointInPoly(x, z, pts)) continue;
    let best = Infinity, bx = x, bz = z;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, zi] = pts[i], [xj, zj] = pts[j];
      const ex = xi - xj, ez = zi - zj, l2 = ex * ex + ez * ez || 1e-9;
      const t = Math.max(0, Math.min(1, ((x - xj) * ex + (z - zj) * ez) / l2));
      const qx = xj + ex * t, qz = zj + ez * t, d = Math.hypot(x - qx, z - qz);
      if (d < best) { best = d; bx = qx; bz = qz; }
    }
    const d = best || 1e-6;
    return [bx + (bx - x) / d * 3, bz + (bz - z) / d * 3];
  }
  return [x, z];
}

function teleport(x, z, faceX, faceZ) {
  if (phone && !P.fly && Math.hypot(x - P.pos.x, z - P.pos.z) > 30 && !phone.allowTravel()) return;
  if (P.ride === 'bus') leaveBus(false);
  if (!P.fly) [x, z] = outsideZones(x, z);
  if (!P.fly && airWall) [x, z] = airWall.snap(x, z);
  if (!P.fly && world?.waterAt) {       // never land in a river or pond (map teleport, landing from flight): nearest dry spot
    const wet = (a, b) => world.waterAt(a, b) !== null && !(world.deckAt && world.deckAt(a, b) !== null);
    if (wet(x, z)) {
      search: for (let r = 2; r <= 80; r += 2) for (let k = 0; k < 16; k++) {
        const a = k / 16 * Math.PI * 2, px = x + Math.cos(a) * r, pz = z + Math.sin(a) * r;
        if (!wet(px, pz)) { x = px; z = pz; break search; }
      }
    }
  }
  P.pos.set(x, 0, z);
  for (let i = 0; i < 8; i++) collide(P.pos, 1.2);
  P.pos.y = heightAt(P.pos.x, P.pos.z) + (P.fly ? 60 : 0);
  P.vy = 0;
  if (faceX !== undefined) P.yaw = Math.atan2(-(faceX - P.pos.x), -(faceZ - P.pos.z));
}

// ---------- riding: E boards/leaves the bus, takes/parks a 7ma e-bike ----------
let toast = '', toastT = 0;
const say = (t, s = 3) => { toast = t; toastT = s; };
function leaveBus(placeBeside = true) {
  P.ride = null;
  if (placeBeside && bus) {
    const a = bus.heading, rx = Math.cos(a), rz = -Math.sin(a);
    P.pos.set(bus.x + rx * 3.2, 0, bus.z + rz * 3.2);
    for (let i = 0; i < 6; i++) collide(P.pos, 0.6);
    P.pos.y = heightAt(P.pos.x, P.pos.z);
  }
  P.dist = 7;
}
function interact() {
  if (P.fly) return;
  if (phone?.interact('high')) return;   // phone/ task targets first; canteens come after the bus and 7ma (bottom)
  if (P.ride === 'bus') { leaveBus(); say('已下车'); return; }
  if (P.ride === 'ebike') { ebikes.park(P.ebikeIdx, P.pos.x, P.pos.z, avatar.rotation.y); P.ride = null; P.ebikeIdx = -1; if (phone) phone.endEbike(); else say('已还车'); return; }
  if (P.ride === 'bike') { P.ride = null; }
  if (bus && Math.hypot(bus.x - P.pos.x, bus.z - P.pos.z) < 8 && bus.v < 2.5) { if (phone && !phone.payBus()) return; P.ride = 'bus'; P.dist = 16; say(`上车了，下一站：${bus.nextStop()}`); return; }
  const i = ebikes ? ebikes.nearest(P.pos.x, P.pos.z, 3.5) : -1;
  if (i >= 0) {
    const ride = () => {   // phone scans the QR code first, then unlocks
      if (ebikes.list[i].used || P.ride || P.fly) return false;
      if (Math.hypot(ebikes.list[i].x - P.pos.x, ebikes.list[i].z - P.pos.z) > 5) return false;   // walked off during the 1 s scan
      ebikes.take(i); P.ebikeIdx = i; P.ride = 'ebike'; avatar.rotation.y = ebikes.list[i].a; say('骑上 7ma 电动车，再按 E 还车');
      return true;
    };
    if (phone) phone.scanEbike(ride); else ride();
    return;
  }
  phone?.interact('low');   // canteen ordering / closed-canteen notes (a bus stop or 7ma beside a canteen wins)
}
function promptText() {
  if (P.fly) return '';
  if (P.ride === 'bus') return `乘坐校园小公交 · 下一站：${bus.nextStop()} · E 下车`;
  if (P.ride === 'ebike') return phone?.ebikePrompt() || '骑行 7ma · E 还车';
  const pp = phone?.prompt('high');
  if (pp) return pp;
  if (bus && Math.hypot(bus.x - P.pos.x, bus.z - P.pos.z) < 8) return bus.v < 2.5 ? '按 E 上车（校园小公交）' : '小公交行驶中，等它停下';
  if (ebikes && ebikes.nearest(P.pos.x, P.pos.z, 3.5) >= 0) return phone ? '按 E 扫码骑 7ma（起步 ¥1.5 含 5 分钟）' : '按 E 骑 7ma 电动车';
  return phone?.prompt('low') || route?.prompt() || '';
}

// ---------- input ----------
const keys = new Set();
const canvas = renderer.domElement;
let dragging = false, runLatch = false, jumpReq = false;
let tour = null;
function toggleTour() {
  if (!tour) return;
  if (tour.active) { tour.stop(); say('导览已结束，可自由飞行（F 降落）', 3); return; }
  if (P.ride === 'bus' || P.ride === 'ebike') { say('先下车再开始导览', 2); return; }
  if (phone && !phone.allowTravel()) return;
  if (!P.fly) toggleFly();
  closeMap();
  tour.start(camera);
  say('云游导览开始：依次飞览 12 个地标', 3);
}
function toggleFly() {
  if (!P.fly && phone && !phone.allowTravel()) return;
  if (P.ride === 'bus') leaveBus();
  P.fly = !P.fly;
  if (P.fly) { P.pos.y += 60; P.pitch = -0.55; } else teleport(P.pos.x, P.pos.z);
}
function toggleBike() {
  if (P.fly || P.ride === 'bus' || P.ride === 'ebike') return;
  P.ride = P.ride === 'bike' ? null : 'bike';
}
addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') { if (e.code === 'Escape') closeMap(); return; }
  keys.add(e.code);
  $('start').hidden = true;
  if (e.code === 'Space') e.preventDefault();
  if (e.repeat) return;
  if (e.code === 'KeyF') toggleFly();
  if (e.code === 'KeyV') P.first = !P.first;
  if (e.code === 'KeyB') toggleBike();
  if (e.code === 'KeyE') interact();
  if (e.code === 'KeyH') $('help').hidden = !$('help').hidden;
  if (e.code === 'KeyM') ($('bigmap').hidden ? openMap() : closeMap());
  if (e.code === 'KeyP') openPhoto();
  if (e.code === 'KeyJ') toggleBook();
  if (e.code === 'KeyT') setNight(!night);
  if (e.code === 'KeyY') toggleTour();
  if (e.code === 'Escape' && tour?.active) toggleTour();
  if (e.code === 'KeyG' && composer) { aoOn = !aoOn; say(aoOn ? '画质：环境光遮蔽 开' : '画质：环境光遮蔽 关', 2); }
  if (e.code === 'KeyN' && cardFor) { cardIdx++; showCard(cardFor); }
  if (e.code === 'Escape') { closeMap(); $('lightbox').hidden = true; }
});
addEventListener('keyup', (e) => keys.delete(e.code));
addEventListener('blur', () => keys.clear());

// touch: left joystick moves, drag elsewhere looks around, buttons for the rest
const joy = { id: null, x: 0, y: 0 }, lookTouch = { id: null, x: 0, y: 0 };
if (isTouch) {
  document.body.classList.add('touch');
  $('touch').hidden = false;
  $('start').textContent = '左下摇杆走路，右侧滑动转视角';
  const joyEl = $('joy'), knob = $('knob');
  const setJoy = (e) => {
    const r = joyEl.getBoundingClientRect();
    let dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const R = r.width / 2 - 10, d = Math.hypot(dx, dy);
    if (d > R) { dx *= R / d; dy *= R / d; }
    joy.x = dx / R; joy.y = dy / R;
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
  };
  const endJoy = () => { joy.id = null; joy.x = joy.y = 0; knob.style.transform = ''; };
  joyEl.addEventListener('pointerdown', (e) => {
    joy.id = e.pointerId;
    try { joyEl.setPointerCapture(e.pointerId); } catch { /* capture is a nicety */ }
    setJoy(e); $('start').hidden = true;
  });
  joyEl.addEventListener('pointermove', (e) => { if (e.pointerId === joy.id) setJoy(e); });
  joyEl.addEventListener('pointerup', endJoy);
  joyEl.addEventListener('pointercancel', endJoy);
  canvas.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'touch' || lookTouch.id !== null) return;
    lookTouch.id = e.pointerId; lookTouch.x = e.clientX; lookTouch.y = e.clientY; $('start').hidden = true;
  });
  addEventListener('pointermove', (e) => {
    if (e.pointerId !== lookTouch.id) return;
    P.yaw -= (e.clientX - lookTouch.x) * 0.005;
    P.pitch = Math.max(-1.35, Math.min(1.2, P.pitch - (e.clientY - lookTouch.y) * 0.005));
    lookTouch.x = e.clientX; lookTouch.y = e.clientY;
  });
  const endLook = (e) => { if (e.pointerId === lookTouch.id) lookTouch.id = null; };
  addEventListener('pointerup', endLook);
  addEventListener('pointercancel', endLook);
  for (const b of document.querySelectorAll('#tbtns button')) {
    b.addEventListener('click', () => {
      const act = b.dataset.act;
      if (act === 'jump') jumpReq = true;
      if (act === 'run') { runLatch = !runLatch; b.classList.toggle('on', runLatch); }
      if (act === 'bike') toggleBike();
      if (act === 'use') interact();
      if (act === 'fly') { toggleFly(); b.classList.toggle('on', P.fly); }
      if (act === 'view') P.first = !P.first;
      if (act === 'map') openMap();
      if (act === 'book') toggleBook();
      if (act === 'night') setNight(!night);
      if (act === 'tour') toggleTour();
    });
  }
}
canvas.addEventListener('click', () => { if (!isTouch && document.pointerLockElement !== canvas) canvas.requestPointerLock?.()?.catch?.(() => {}); });
document.addEventListener('pointerlockchange', () => { $('start').hidden = true; });
canvas.addEventListener('mousedown', () => { dragging = true; $('start').hidden = true; });
addEventListener('mouseup', () => { dragging = false; });
addEventListener('mousemove', (e) => {
  if (document.pointerLockElement === canvas || dragging) {
    P.yaw -= e.movementX * 0.0025;
    P.pitch = Math.max(-1.35, Math.min(1.2, P.pitch - e.movementY * 0.0025));
  }
});
canvas.addEventListener('wheel', (e) => { P.dist = Math.max(2.5, Math.min(80, P.dist * (e.deltaY > 0 ? 1.12 : 0.89))); }, { passive: true });
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer?.setSize(innerWidth, innerHeight);
  if (!$('bigmap').hidden) drawBigMap();
});

// ---------- HUD: labels, nearby + photo card, minimap, big map ----------
const labelPool = [];
for (let i = 0; i < 10; i++) { const d = document.createElement('div'); d.className = 'label'; $('labels').appendChild(d); labelPool.push(d); }
const tmpV = new THREE.Vector3();
const mlabelPool = [];
for (let i = 0; i < 10; i++) { const d = document.createElement('div'); d.className = 'label mlabel'; $('labels').appendChild(d); mlabelPool.push(d); }
function updateMarkerLabels() {
  const range = P.fly ? 0 : 75;
  const cands = markers.map((m) => ({ m, d: Math.hypot(m.x - camera.position.x, m.z - camera.position.z) })).filter((o) => o.d < range).sort((a, b) => a.d - b.d).slice(0, mlabelPool.length);
  mlabelPool.forEach((el, i) => {
    const o = cands[i];
    if (!o) { el.style.display = 'none'; return; }
    tmpV.set(o.m.x, (o.m.y ?? heightAt(o.m.x, o.m.z)) + 3.2, o.m.z).project(camera);
    if (tmpV.z > 1 || Math.abs(tmpV.x) > 1.05 || Math.abs(tmpV.y) > 1.05) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    if (el.dataset.k !== o.m.name) { el.dataset.k = o.m.name; el.innerHTML = ''; const dot = document.createElement('i'); dot.style.background = catColor(o.m.cat); el.append(dot, o.m.name); }
    el.style.opacity = String(Math.max(0.4, 1 - o.d / 90));
    el.style.transform = `translate(${(tmpV.x + 1) / 2 * innerWidth}px, ${(1 - tmpV.y) / 2 * innerHeight}px) translate(-50%, -100%)`;
  });
}
function updateLabels() {
  const cands = named
    .map((m) => ({ m, d: Math.hypot(m.cx - camera.position.x, m.cz - camera.position.z) }))
    .filter((o) => o.d < (P.fly ? 700 : 260))
    .sort((a, b) => a.d - b.d)
    .slice(0, labelPool.length);
  labelPool.forEach((el, i) => {
    const o = cands[i];
    if (!o) { el.style.display = 'none'; return; }
    tmpV.set(o.m.cx, o.m.top + 3, o.m.cz).project(camera);
    if (tmpV.z > 1 || Math.abs(tmpV.x) > 1.05 || Math.abs(tmpV.y) > 1.05) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    el.textContent = o.m.name;
    el.style.opacity = String(Math.max(0.35, 1 - o.d / (P.fly ? 900 : 320)));
    el.style.transform = `translate(${(tmpV.x + 1) / 2 * innerWidth}px, ${(1 - tmpV.y) / 2 * innerHeight}px) translate(-50%, -100%)`;
  });
}
const useBtn = document.querySelector('#tbtns [data-act="use"]');
function updateNearby() {
  let best = null, bd = 70;
  for (const m of named) {
    if (!m.campus) continue;
    const d = Math.hypot(m.cx - P.pos.x, m.cz - P.pos.z) - Math.max(m.maxX - m.minX, m.maxZ - m.minZ) / 2;
    if (d < bd) { bd = d; best = m; }
  }
  const p = promptText();
  let mk = null, md = 12;
  for (const m of markers) { const d = Math.hypot(m.x - P.pos.x, m.z - P.pos.z); if (d < md) { md = d; mk = m; } }
  let text = toastT > 0 ? toast : p || (P.fly ? '' : mk ? `附近：${mk.name} · ${mk.cat}` : best ? `附近：${best.name}` : '');
  if (isTouch) {   // phones: name the on-screen button instead of the E key, and label the button for what it does here
    const lab = P.ride === 'ebike' ? '还车' : P.ride === 'bus' ? '下车' : /上车/.test(p) ? '上车' : /7ma/.test(p) ? '扫码骑车' : /点餐/.test(p) ? '点餐' : /按 E/.test(p) ? '互动' : '上车/骑';
    if (useBtn && useBtn.textContent !== lab) useBtn.textContent = lab;
    text = text.replace(/按 ?E ?扫码/g, `点「${lab}」`).replace(/按 ?E ?/g, `点「${lab}」`).replace(/(^| · )E (还车|下车)/g, '$1点按钮$2');
  }
  $('nearby').textContent = text;
  showCard(P.fly ? null : best);
}

let cardFor = null, cardIdx = 0;
function showCard(m) {
  if (!m || !m.photos) { $('card').hidden = true; cardFor = null; return; }
  if (cardFor !== m) { cardFor = m; cardIdx = 0; }
  const n = m.photos.length, p = m.photos[cardIdx % n];
  if ($('cardImg').getAttribute('src') !== p.file) $('cardImg').src = p.file;
  $('cardName').textContent = m.name;
  $('cardCap').textContent = n > 1 ? `${p.caption} · ${cardIdx % n + 1}/${n}` : p.caption;
  $('cardNext').hidden = n < 2;
  $('card').hidden = false;
}
function openPhoto() {
  if ($('card').hidden) return;
  document.exitPointerLock?.();
  $('lbImg').src = $('cardImg').src;
  $('lbCap').textContent = `${$('cardName').textContent} · ${$('cardCap').textContent}`;
  $('lightbox').hidden = false;
}
$('cardNext').addEventListener('click', () => { cardIdx++; showCard(cardFor); });
$('cardImg').addEventListener('click', openPhoto);
$('lightbox').addEventListener('click', () => { $('lightbox').hidden = true; });

const mm = $('minimap'), mctx = mm.getContext('2d');
function drawMini() {
  if (!mapImg) return;
  const w = mm.width, h = mm.height, mPerPx = 1.4;
  const ix = (P.pos.x + W / 2) / W * mapImg.width, iz = (P.pos.z + D / 2) / D * mapImg.height;
  const half = (w / 2) * mPerPx * (mapImg.width / W);
  mctx.fillStyle = '#556052'; mctx.fillRect(0, 0, w, h);
  mctx.drawImage(mapImg, ix - half, iz - half, half * 2, half * 2, 0, 0, w, h);
  if (bus) {
    const bx = (bus.x - P.pos.x) / mPerPx + w / 2, bz = (bus.z - P.pos.z) / mPerPx + h / 2;
    mctx.fillStyle = '#1e6fc4'; mctx.strokeStyle = '#fff'; mctx.lineWidth = 3;
    mctx.beginPath(); mctx.arc(bx, bz, 9, 0, 7); mctx.fill(); mctx.stroke();
  }
  if (ebikes && !P.fly) {   // parked 7ma e-bikes (blue dots) so players can find one
    mctx.fillStyle = '#2f8cff'; mctx.strokeStyle = '#fff'; mctx.lineWidth = 1.5;
    for (const b of ebikes.list) {
      if (b.used) continue;
      const ex = (b.x - P.pos.x) / mPerPx + w / 2, ez = (b.z - P.pos.z) / mPerPx + h / 2;
      if (ex < 0 || ez < 0 || ex > w || ez > h) continue;
      mctx.beginPath(); mctx.arc(ex, ez, 4, 0, 7); mctx.fill(); mctx.stroke();
    }
  }
  mctx.save();
  mctx.translate(w / 2, h / 2); mctx.rotate(-P.yaw);
  mctx.fillStyle = '#ff8450'; mctx.strokeStyle = '#fff'; mctx.lineWidth = 3;
  mctx.beginPath(); mctx.moveTo(0, -18); mctx.lineTo(12, 14); mctx.lineTo(0, 7); mctx.lineTo(-12, 14); mctx.closePath();
  mctx.fill(); mctx.stroke();
  mctx.restore();
  mctx.fillStyle = '#fff'; mctx.font = 'bold 22px system-ui'; mctx.textAlign = 'center'; mctx.fillText('北', w / 2, 30);
}
mm.addEventListener('click', () => openMap());

const mc = $('mapCanvas');
let mapT = { s: 1, ox: 0, oy: 0 };
function drawBigMap() {
  const dpr = Math.min(devicePixelRatio, 2);
  mc.width = mc.clientWidth * dpr; mc.height = mc.clientHeight * dpr;
  const ctx = mc.getContext('2d');
  const s = Math.min(mc.width / mapImg.width, mc.height / mapImg.height);
  mapT = { s, ox: (mc.width - mapImg.width * s) / 2, oy: (mc.height - mapImg.height * s) / 2 };
  ctx.drawImage(mapImg, mapT.ox, mapT.oy, mapImg.width * s, mapImg.height * s);
  const toMap = (x, z) => [mapT.ox + (x + W / 2) / W * mapImg.width * s, mapT.oy + (z + D / 2) / D * mapImg.height * s];
  const path = (pts, close) => { ctx.beginPath(); pts.forEach(([x, z], i) => { const [X, Y] = toMap(x, z); i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); }); if (close) ctx.closePath(); };
  ctx.strokeStyle = 'rgba(120,220,255,.9)'; ctx.lineWidth = 2 * dpr;
  for (const r of boundary) { path(r, true); ctx.stroke(); }
  if (busRoute.length) { ctx.strokeStyle = 'rgba(30,111,196,.95)'; ctx.lineWidth = 3 * dpr; path(busRoute, true); ctx.stroke(); }
  ctx.font = `${12 * dpr}px "Microsoft YaHei", system-ui`; ctx.textAlign = 'center';
  for (const zn of zones) {
    ctx.save(); ctx.setLineDash([6 * dpr, 4 * dpr]); ctx.strokeStyle = '#ff7ad9'; ctx.lineWidth = 2 * dpr; ctx.fillStyle = 'rgba(255,122,217,.18)';
    path(zn.pts, true); ctx.fill(); ctx.stroke(); ctx.restore();
    const [X, Y] = toMap(zn.pts.reduce((a, p) => a + p[0], 0) / zn.pts.length, zn.pts.reduce((a, p) => a + p[1], 0) / zn.pts.length);
    ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(0,0,0,.75)'; ctx.strokeText(zn.name, X, Y); ctx.fillStyle = '#ffd1f2'; ctx.fillText(zn.name, X, Y);
  }
  for (const m of markers) { const [X, Y] = toMap(m.x, m.z); ctx.fillStyle = catColor(m.cat); ctx.beginPath(); ctx.arc(X, Y, 2.2 * dpr, 0, 7); ctx.fill(); }
  ctx.font = `bold ${11 * dpr}px "Microsoft YaHei", system-ui`;
  for (const rl of roadLabels) {
    const [X, Y] = toMap(rl.x, rl.z);
    ctx.save(); ctx.translate(X, Y); ctx.rotate(rl.ang);
    ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(10,40,90,.85)'; ctx.strokeText(rl.name, 0, 4 * dpr); ctx.fillStyle = '#bfe3ff'; ctx.fillText(rl.name, 0, 4 * dpr);
    ctx.restore();
  }
  ctx.font = `${12 * dpr}px "Microsoft YaHei", system-ui`;
  for (const m of named) {
    if (!m.campus) continue;
    const [X, Y] = toMap(m.cx, m.cz);
    ctx.fillStyle = m.photos ? '#ffd400' : '#ff8450';
    ctx.beginPath(); ctx.arc(X, Y, (m.photos ? 4.5 : 2.5) * dpr, 0, 7); ctx.fill();
    if (m.kind === 'dorm') continue;
    ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(0,0,0,.75)'; ctx.strokeText(m.name, X, Y - 6 * dpr);
    ctx.fillStyle = '#fff'; ctx.fillText(m.name, X, Y - 6 * dpr);
  }
  if (bus) { const [X, Y] = toMap(bus.x, bus.z); ctx.fillStyle = '#1e6fc4'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * dpr; ctx.beginPath(); ctx.arc(X, Y, 6 * dpr, 0, 7); ctx.fill(); ctx.stroke(); }
  const [PX, PY] = toMap(P.pos.x, P.pos.z);
  ctx.save(); ctx.translate(PX, PY); ctx.rotate(-P.yaw); ctx.fillStyle = '#ffdd00'; ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.moveTo(0, -12 * dpr); ctx.lineTo(8 * dpr, 9 * dpr); ctx.lineTo(-8 * dpr, 9 * dpr); ctx.closePath(); ctx.fill(); ctx.stroke(); ctx.restore();
}
mc.addEventListener('click', (e) => {
  const dpr = mc.width / mc.clientWidth, r = mc.getBoundingClientRect();
  const X = (e.clientX - r.left) * dpr, Y = (e.clientY - r.top) * dpr;
  const x = (X - mapT.ox) / (mapImg.width * mapT.s) * W - W / 2, z = (Y - mapT.oy) / (mapImg.height * mapT.s) * D - D / 2;
  if (Math.abs(x) < W / 2 && Math.abs(z) < D / 2) { teleport(x, z); closeMap(); }
});
function renderResults() {
  const q = $('search').value.trim();
  const list = named.filter((m) => m.campus && (!q || m.name.includes(q))).sort((a, b) => a.name.localeCompare(b.name, 'zh')).slice(0, 60);
  const mlist = q ? markers.filter((m) => m.name.includes(q) || m.cat.includes(q)).slice(0, 40) : [];
  $('results').replaceChildren(...list.map((m) => {
    const b = document.createElement('button');
    b.textContent = m.photos ? `${m.name}（有实拍 ${m.photos.length} 张）` : m.name;
    b.addEventListener('click', () => { teleport(m.cx, m.cz, m.cx, m.cz); closeMap(); });
    return b;
  }), ...mlist.map((m) => {
    const b = document.createElement('button');
    b.textContent = `${m.name} · ${m.cat}`;
    b.style.borderLeft = `4px solid ${catColor(m.cat)}`;
    b.addEventListener('click', () => { teleport(m.x, m.z); closeMap(); });
    return b;
  }));
}
$('search').addEventListener('input', renderResults);
function openMap() { if (!mapImg) return; document.exitPointerLock?.(); $('bigmap').hidden = false; drawBigMap(); renderResults(); }
function closeMap() { $('bigmap').hidden = true; }

// ---------- day / night (T) ----------
function setNight(on) {
  night = on;
  scene.backgroundIntensity = on ? 0.06 : 0.85;
  scene.environmentIntensity = on ? 0.08 : 0.55;
  hemi.intensity = on ? 0.12 : 0.8;
  sun.intensity = on ? 0.35 : 2.6;
  sun.color.set(on ? '#9db4ff' : '#fff1dc');
  scene.fog.color.set(on ? '#0d1320' : '#d3dee6');
  renderer.toneMappingExposure = on ? 1.1 : 0.85;
  for (const mt of Object.values(facadeMats)) mt.emissiveIntensity = on ? 0.9 : 0;
  for (const mt of modelNightMats) mt.emissiveIntensity = on ? 0.9 : 0;
  if (lampMat) lampMat.emissiveIntensity = on ? 3 : 0;
  if (lampMat?.userData.pools) lampMat.userData.pools.visible = on;
  say(on ? '夜景：教学楼亮灯了（T 切回白天）' : '白天（T 切换夜景）', 3);
}

// ---------- 云游打卡 ----------
function toggleBook() { const b = $('book'); if (b.hidden) { document.exitPointerLock?.(); quest?.renderBook(); } b.hidden = !b.hidden; }
$('questbar').addEventListener('click', toggleBook);
$('bookClose').addEventListener('click', toggleBook);
$('bookReset').addEventListener('click', () => quest?.reset());

// ---------- main loop ----------
const clock = new THREE.Clock();
const fwd = new THREE.Vector3(), right = new THREE.Vector3(), look = new THREE.Vector3(), mv = new THREE.Vector3();
let fpsAcc = 0, fpsN = 0, fps = 0, hudT = 0, miniN = 0;

function update(dt) {
  fwd.set(-Math.sin(P.yaw), 0, -Math.cos(P.yaw));
  right.set(Math.cos(P.yaw), 0, -Math.sin(P.yaw));
  look.set(-Math.sin(P.yaw) * Math.cos(P.pitch), Math.sin(P.pitch), -Math.cos(P.yaw) * Math.cos(P.pitch));
  const f = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0) - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0) - joy.y;
  const s = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0) + joy.x;
  const run = keys.has('ShiftLeft') || keys.has('ShiftRight') || runLatch;
  const jump = keys.has('Space') || jumpReq;
  jumpReq = false;
  if (toastT > 0) toastT -= dt;

  if (bus) {
    bus.update(dt);
    if (bus.justArrived && P.ride === 'bus') say(`到站：${bus.justArrived}，按 E 下车`, 5);
  }
  if (walkers) walkers.update(dt, clock.elapsedTime);
  if (grass && !P.fly) grass.update(P.pos);
  if (quest) questNext = quest.update(dt, clock.elapsedTime, P.pos);
  if (phone) phone.update(dt);
  if (route) route.update(dt);
  if (waterMat) waterMat.normalMap.offset.set(clock.elapsedTime * 0.004, clock.elapsedTime * 0.0025);

  if (P.ride === 'bus') {
    P.pos.set(bus.x, (world?.surfaceAt || heightAt)(bus.x, bus.z), bus.z);
  } else if (P.fly) {
    const sp = run ? 120 : 40;
    mv.set(0, 0, 0).addScaledVector(look, f).addScaledVector(right, s);
    mv.y += (keys.has('Space') ? 1 : 0) - (keys.has('KeyC') || keys.has('ControlLeft') ? 1 : 0);
    if (mv.lengthSq() > 0) P.pos.addScaledVector(mv.normalize(), sp * dt);
    P.pos.y = Math.max(P.pos.y, heightAt(P.pos.x, P.pos.z) + 2);
  } else {
    const sp = (P.ride === 'ebike' ? 15 : P.ride === 'bike' ? 12 : run ? 9 : 4.5) * (stunt?.speedMul || 1);
    const prevX = P.pos.x, prevZ = P.pos.z;
    const wasWet = !!world?.waterAt && world.waterAt(prevX, prevZ) !== null && world.deckAt(prevX, prevZ) === null;
    mv.set(0, 0, 0).addScaledVector(fwd, f).addScaledVector(right, s);
    if (mv.lengthSq() > 0.0025 && !stunt?.locked && !phone?.busy) {
      const amount = Math.min(1, mv.length());
      mv.normalize();
      // sub-steps of <= 0.25 m with collision each, so fast riding cannot tunnel through thin walls
      const step = sp * amount * dt, nStep = Math.min(40, Math.max(1, Math.ceil(step / 0.25))), rr = P.ride ? 0.6 : 0.4;
      for (let i = 0; i < nStep; i++) { P.pos.addScaledVector(mv, step / nStep); if (nStep > 1) collide(P.pos, rr); }
      const target = Math.atan2(-mv.x, -mv.z);
      let d = target - avatar.rotation.y;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      avatar.rotation.y += d * Math.min(1, dt * 12);
    }
    const r = P.ride ? 0.6 : 0.4;
    collide(P.pos, r); collide(P.pos, r);
    airWall?.keep(P.pos, prevX, prevZ);         // invisible wall along the campus boundary
    if (jump && P.onGround && !P.ride) { P.vy = 6.5; P.onGround = false; }
    P.vy -= 22 * dt;
    P.pos.y += P.vy * dt;
    // rivers: cross on bridges only (stand on the deck), never wade through the riverbed
    if (!wasWet && world?.waterAt && world.waterAt(P.pos.x, P.pos.z) !== null && world.deckAt(P.pos.x, P.pos.z) === null) { P.pos.x = prevX; P.pos.z = prevZ; }
    const g = (world?.surfaceAt || heightAt)(P.pos.x, P.pos.z);
    if (P.pos.y <= g) { P.pos.y = g; P.vy = 0; P.onGround = true; }
  }
  P.pos.x = Math.max(-W / 2 + 5, Math.min(W / 2 - 5, P.pos.x));
  P.pos.z = Math.max(-D / 2 + 5, Math.min(D / 2 - 5, P.pos.z));

  avatar.position.copy(P.pos);
  bicycle.visible = P.ride === 'bike';
  ebikeMesh.visible = P.ride === 'ebike';
  rider.position.y = P.ride === 'bike' || P.ride === 'ebike' ? 0.35 : 0;
  rig.update(dt, P);
  avatar.visible = !P.fly && !P.first && P.ride !== 'bus';

  if (P.fly || (P.first && P.ride !== 'bus')) {
    camera.position.set(P.pos.x, P.pos.y + (P.fly ? 0 : P.ride ? 2.0 : 1.65), P.pos.z);
    camera.lookAt(tmpV.copy(camera.position).add(look));
  } else {
    const tgt = tmpV.set(P.pos.x, P.pos.y + (P.ride === 'bus' ? 2.4 : 1.5), P.pos.z);
    camera.position.copy(tgt).addScaledVector(look, -P.dist);
    camera.position.y = Math.max(camera.position.y, heightAt(camera.position.x, camera.position.z) + 0.4);
    camera.lookAt(tgt);
  }
  if (stunt) stunt.update(dt);   // after the camera is placed: wheelie pose, FOV / shake, smoke
  if (tour?.active) {          // guided tour drives the camera; keep the player (and the sun's shadow box) with it
    tour.update(dt, camera);
    P.pos.copy(camera.position);
    avatar.visible = false;
  }
  const focusY = P.fly ? heightAt(P.pos.x, P.pos.z) : P.pos.y;
  sun.target.position.set(P.pos.x, focusY, P.pos.z);
  sun.position.copy(sun.target.position).addScaledVector(sunDir, 500);
  sun.target.updateMatrixWorld();
}

// 流畅 / 均衡: the shadow box follows the player; while it stands still the shadow map is redrawn only every 4 (均衡) /
// 15 (流畅) frames for the bus and walkers, while moving every frame (均衡) / every other frame (流畅). 高清: every frame.
let shadowN = 0;
const shadowAt = new THREE.Vector3(Infinity, 0, 0);
function shadowTick() {
  if (tier.id === 'high') return;
  shadowN++;
  const moved = shadowAt.distanceToSquared(sun.target.position) > 0.0025;
  if ((moved && shadowN % tier.shadowEvery === 0) || shadowN % (tier.id === 'low' ? 15 : 4) === 0) {
    renderer.shadowMap.needsUpdate = true; shadowAt.copy(sun.target.position);
  }
}
const fpsGuard = createFpsGuard({ getTier: () => tier, setTier: applyTier, isAuto: () => Q.auto, say: (t, s) => say(t, s) });
function loop() {
  const dt = Math.min(clock.getDelta(), 0.05);
  update(dt);
  detail.update(camera);                       // 性能: far vegetation / hedges / fence by distance (perf.js)
  shadowTick();
  fpsGuard();
  if (composer && aoOn) composer.render(); else renderer.render(scene, camera);
  updateLabels();
  updateMarkerLabels();
  if (++miniN % 2 === 0) drawMini();
  fpsAcc += dt; fpsN++;
  hudT += dt;
  if (hudT > 0.25) {
    if (fpsAcc > 1) { fps = Math.round(fpsN / fpsAcc); fpsAcc = 0; fpsN = 0; }
    hudT = 0;
    updateNearby();
    const mode = P.fly ? '飞行俯瞰' : P.ride === 'bus' ? '乘公交' : P.ride === 'ebike' ? '骑 7ma' : P.ride === 'bike' ? '骑车' : (keys.has('ShiftLeft') || runLatch ? '跑步' : '步行');
    if (quest) {
      $('questCount').textContent = `${quest.count}/${quest.total}`;
      if (questNext) {
        const ang = Math.atan2(-questNext.dx, -questNext.dz) - P.yaw;
        $('questNext').textContent = `下一站：${questNext.name} ${questNext.d > 1000 ? (questNext.d / 1000).toFixed(1) + ' km' : Math.round(questNext.d) + ' m'}`;
        $('questArrow').textContent = '↑'; $('questArrow').style.transform = `rotate(${-ang}rad)`;
      } else { $('questNext').textContent = '全部打卡完成！按 J 看明信片'; $('questArrow').textContent = ''; }
    }
    $('status').textContent = `${mode} · ${P.first || P.fly ? '第一人称' : '第三人称'} · 海拔 ${(P.pos.y + T.base).toFixed(0)} m · ${fps} FPS · 建筑 ${buildingCount} 栋`;
  }
  requestAnimationFrame(loop);
}

// ---------- boot ----------
async function main() {
  setMsg('加载校园数据…');
  const [C, terrain] = await Promise.all([loadJSON('campus/campus.json'), loadJSON('campus/terrain.json')]);
  W = C.size[0]; D = C.size[1];
  T = terrain;
  boundary = C.boundary;
  const openings = boundary?.length ? boundaryOpenings(boundary, (C.pois || []).filter((p) => /gate/.test(p.landmark || '')), C.roads || []) : [];
  under = C.underpasses?.length ? makeUnderpasses(C.underpasses, terrainAt) : null;
  // 盘城新街 is not campus: 中苑 and 东苑 connect only through the underpass cuts
  airWall = boundary?.length ? makeAirWall(boundary, openings, { corridors: under?.corridors || [], bridge: under ? 0 : 36, apron: under ? 6 : 10 }) : null;
  zones = C.zones || [];
  setMsg('加载航拍影像…');
  const orthoUrl = tier.ortho8k && maxTex >= 8192 && !isTouch ? 'campus/ortho.jpg' : 'campus/ortho_4k.jpg';
  const [orthoTex, img] = await Promise.all([new THREE.TextureLoader().loadAsync(orthoUrl), orthoUrl === 'campus/ortho_4k.jpg' ? null : loadImage('campus/ortho_4k.jpg')]);
  orthoTex.colorSpace = THREE.SRGBColorSpace;
  orthoTex.anisotropy = aniso;
  mapImg = img || orthoTex.image;          // the 4k photo doubles as the minimap (one download)
  const ctx = { scene, heightAt, inCampus, W, D, aniso, under, terrainAt, detail, treeChunk: 300 };   // 300 m tree chunks: finer LOD / culling
  world = ctx;
  // rivers and ponds: fix each water level first, then dig the terrain grid below it so banks show. Only the ground
  // mesh is dug (renderH below); heights are queried from the undug grid and sanity.js bankApron covers the band
  // outside the banks that the dug grid triangles pulled down into a ditch (常识排查)
  const dugH = new Map();
  for (const wp of C.water || []) {
    if (wp.pts.length < 3) continue;
    wp.level = wp.pts.reduce((s2, [x, z]) => s2 + heightAt(x, z), 0) / wp.pts.length - 0.6;
    const xs = wp.pts.map((q) => q[0]), zs = wp.pts.map((q) => q[1]);
    const i0 = Math.max(0, Math.floor((Math.min(...xs) + W / 2) / W * (T.nx - 1))), i1 = Math.min(T.nx - 1, Math.ceil((Math.max(...xs) + W / 2) / W * (T.nx - 1)));
    const k0 = Math.max(0, Math.floor((Math.min(...zs) + D / 2) / D * (T.nz - 1))), k1 = Math.min(T.nz - 1, Math.ceil((Math.max(...zs) + D / 2) / D * (T.nz - 1)));
    for (let k = k0; k <= k1; k++) for (let i = i0; i <= i1; i++) {
      const x = -W / 2 + i * W / (T.nx - 1), z = -D / 2 + k * D / (T.nz - 1);
      const j = k * T.nx + i;
      if (pointInPoly(x, z, wp.pts)) dugH.set(j, Math.min(dugH.get(j) ?? T.h[j], Math.round((wp.level - 1.2) * 10)));
    }
  }
  // and the first ring of vertices outside each outline, so no grid triangle that straddles a bank rises above the
  // water inside it (the "beach" slivers); bankApron hides the ground they pull down outside the banks
  for (const j of [...dugH.keys()]) {
    const i = j % T.nx, k = (j - i) / T.nx;
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      const ii = i + a, kk = k + b, nj = kk * T.nx + ii;
      if (ii >= 0 && kk >= 0 && ii < T.nx && kk < T.nz && !dugH.has(nj)) dugH.set(nj, Math.min(T.h[nj], dugH.get(j)));
    }
  }
  // sports grounds are flat in reality: level the terrain grid under every pitch / track / court
  const flats = [...(C.sports || []).map((s) => s.obb),        // open fields (气象观测场) are level as well
    ...(C.pois || []).filter((q) => q.field).map((q) => [(q.field[0] + q.field[2]) / 2, (q.field[1] + q.field[3]) / 2, q.field[2] - q.field[0] - 20, q.field[3] - q.field[1] - 20, 0])];
  for (const [cx, cz, L, Wd, ang] of flats) {
    const ca = Math.cos(ang), sa = Math.sin(ang), idx = [];
    for (let k = 0; k < T.nz; k++) for (let i = 0; i < T.nx; i++) {
      const x = -W / 2 + i * W / (T.nx - 1) - cx, z = -D / 2 + k * D / (T.nz - 1) - cz;
      if (Math.abs(x * ca + z * sa) < L / 2 + 12 && Math.abs(-x * sa + z * ca) < Wd / 2 + 12) idx.push(k * T.nx + i);
    }
    if (!idx.length) continue;
    const mean = Math.round(idx.reduce((s2, j) => s2 + T.h[j], 0) / idx.length);
    for (const j of idx) T.h[j] = mean;
  }

  setMsg('加载天空和地面贴图…');
  const det = await loadDetailTextures(aniso);
  try {
    det.lc = await new THREE.TextureLoader().loadAsync('campus/landcover.png');
    det.lc.magFilter = det.lc.minFilter = THREE.NearestFilter; det.lc.generateMipmaps = false;
  } catch { /* land cover is optional */ }
  try {
    // 流畅: 1024 px sky (tools/hdr_half.py; 1.4 MB instead of 5.4 MB)
    const hdr = await new RGBELoader().loadAsync(tier.skyHi ? 'tex/sky.hdr' : 'tex/sky_1k.hdr').catch(() => new RGBELoader().loadAsync('tex/sky.hdr'));
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    scene.environment = pmrem.fromEquirectangular(hdr).texture;
    envRT.dispose(); pmrem.dispose();          // 性能: free the procedural-sky env map and the generator's buffers
    scene.background = hdr; scene.backgroundIntensity = 0.85; scene.environmentIntensity = 0.55;
    skyMesh.visible = false;
  } catch (e) { console.warn('sky.hdr not loaded, using procedural sky', e); }
  setMsg('生成地形、道路和水面…'); await tick();
  try {        // 0.5 m ground materials from the registered official map (tools/ground_map.py)
    det.groundMeta = await (await fetch('campus/ground_meta.json')).json();
    det.ground = await new THREE.TextureLoader().loadAsync('campus/ground.png');
    det.ground.magFilter = det.ground.minFilter = THREE.NearestFilter; det.ground.generateMipmaps = false;
  } catch { det.ground = null; det.groundMeta = null; }
  const rtex = roadTextures(aniso);
  det.tileTex = rtex.tile; det.brickTex = rtex.brick; det.stoneTex = rtex.stone; det.lite = tier.lite;
  const renderH = T.h.slice();
  for (const [j, v] of dugH) renderH[j] = Math.min(renderH[j], v);
  const nGround = scene.children.length;
  const mark = (n) => performance.mark?.(n);    // 性能: boot phases (performance.getEntriesByType('mark'))
  buildGround(ctx, { ...T, h: renderH }, orthoTex, detailTexture(aniso), det);
  const groundMesh = scene.children.slice(nGround).find((o) => o.isMesh);
  mark('ground');
  waterMat = buildWater(ctx, C.water, waterNormal(), C.roads);
  mark('water');
  if (groundMesh && dugH.size) bankApron(ctx, T, renderH, new Set(dugH.keys()), groundMesh.material, { cell: tier.apron });
  mark('apron');
  buildRoads(ctx, C.roads, rtex, det);
  mark('roads');
  if (under) { const ug = under.build(ctx, C.roads); if (ug) modelGrids.push(ug); }   // cut walls, deck / tunnel roof
  mark('underpass');
  buildJunctions(ctx, C.junctions, det);
  buildSports(ctx, C.sports);
  mark('junctions+sports');

  setMsg('生成建筑…'); await tick();
  facadeMats = facadeMaterials(aniso);
  metas = buildBuildings(ctx, C.buildings, facadeMats, orthoTex, det, rtex.roof);
  buildLandmarks(ctx, metas);
  buildEntrances(ctx, metas, C.roads);
  const poiMetas = buildPois(ctx, C.pois);
  // 性能: the procedural groups built so far (pitches, underpass walls, POIs such as the 气象观测场, landmarks) are static:
  // one draw call per material each (tagged meshes are kept for the sanity scan)
  for (const o of scene.children.slice(nGround)) if (o.isGroup) mergeStatic(o);
  named = [...metas.filter((m) => m.name), ...poiMetas];
  buildingCount = metas.filter((m) => m.kind !== 'wall').length;
  buildGrid();

  // refined landmark models from the Blender session (data/blender, web/public/models)
  if (C.models?.length) {
    setMsg('加载地标精修模型…');
    const loader = new GLTFLoader();
    const prog = progress('加载地标精修模型…', C.models.length);
    await Promise.all(C.models.map(async (md) => {
      try {
        const gltf = await loader.loadAsync(md.file);
        // ground level = lowest base of the buildings this model replaces (md.replaces), else the terrain at its origin;
        // a 120 m radius used to pick up other replaced buildings further down a slope and sank models by up to 7 m
        const own = new Set((md.replaces || []).map(String));
        const reps = metas.filter((m) => m.replaced && own.has(String(m.id)));
        const base = reps.length ? Math.min(...reps.map((m) => m.base)) : heightAt(md.x, md.z);
        gltf.scene.position.set(md.x, base, md.z);
        gltf.scene.rotation.y = THREE.MathUtils.degToRad(md.rotY || 0);
        // group GLBs (dorm zones: one child node per building, named by its id, all at y = 0): each building stands on its
        // own base, not the group's lowest one (常识排查: uphill dorms were sunk 2.5-4.4 m); before the grid and the merge
        const ownBase = new Map(reps.map((m) => [String(m.id), m.base]));
        for (const node of gltf.scene.children) if (ownBase.has(node.name)) node.position.y += ownBase.get(node.name) - base;
        texDedupe.dedupe(gltf.scene);            // 性能: shared library textures uploaded once
        gltf.scene.traverse(prepModelMesh);
        scene.add(gltf.scene);
        const g = modelGrid(gltf.scene, base, { groundAt: heightAt, y1: 2.0 });   // walking slab 0.4-2.0 m above the local ground (slopes; awnings at 2.1 m are walked under)
        if (g) { g.name = md.name; modelGrids.push(g); }
        mergeStatic(gltf.scene);                 // 性能: one draw call per material (after the collision grid is taken)
      } catch (e) { console.warn('model failed', md.file, e); } finally { prog(); }
    }));
    // outlines a loaded model stands on collide through the model's own shape instead
    for (const m of metas) if (m.replaced && m.xs && modelGrids.some((g) => coverage(g, m.xs, m.zs) > 0.5)) modelledIds.add(String(m.id));
  }
  // ordinary buildings made in Blender (data/blender/generic.json via build_campus): one GLB per 640 m chunk,
  // a node per building named by its id, origin at the footprint centroid on the ground
  if (C.generic?.length && !/[?&]generic=0/.test(location.search)) {
    setMsg('加载楼宇模型…');
    const loader = new GLTFLoader(), byId = new Map(metas.filter((m) => m.generic).map((m) => [String(m.id), m]));
    const prog = progress('加载楼宇模型…', C.generic.length);
    await Promise.all(C.generic.map(async (ch) => {
      try {
        const gltf = await loader.loadAsync(ch.file);
        gltf.scene.position.set(ch.x, 0, ch.z);
        for (const node of [...gltf.scene.children]) {
          const m = byId.get(node.name);
          if (!m) { node.visible = false; continue; }     // building no longer in the data: hide its stale model
          node.position.y = m.base;
        }
        texDedupe.dedupe(gltf.scene);
        gltf.scene.traverse(prepModelMesh);
        mergeStatic(gltf.scene);                 // 性能: one draw call per material per chunk; hidden stale nodes dropped
        scene.add(gltf.scene);
      } catch (e) { console.warn('generic chunk failed', ch.file, e); } finally { prog(); }
    }));
  }
  // common-sense placement rules (sanity.js): water / pitches / buildings + models / carriageways, surface heights
  makeClearance(ctx, { roads: C.roads, sports: C.sports, metas, modelGrids, modelledIds, junctions: C.junctions, models: C.models || [] });
  setMsg('种树、装路灯…'); await tick();
  // trees (sanity.js rules): none on pitches / courts / tracks (+2 m), in water, inside a building or model; a trunk
  // on a road or path moves up to 2 m off it (else dropped); a crown reaching > 0.5 m into a wall is narrowed to fit
  // nor on (or within 1.5 m of) the ground a Blender model paves itself (东大门 plaza / island)
  const treeOpt = { r: 0.25, sport: 2, road: 0.2, path: 0, cover: 1.5 }, treeList = [];
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
    const R = (t.length > 4 ? t[3] : t[2] * 2.3) * 1.1, d = ctx.buildingDist(t[0], t[1], Math.min(4, R));   // crowns are drawn up to 1.1x wide
    if (d < R - 0.5) {
      if (d < 0.8) continue;                          // trunk hard against a wall
      t = t.length > 4 ? [t[0], t[1], t[2], Math.max(1.0, (d + 0.4) / 1.1), ...t.slice(4)] : [t[0], t[1], Math.max(0.45, (d + 0.4) / 2.5)];
    }
    treeList.push(t);
  }
  buildTrees(ctx, treeList, tier.lite);
  lampMat = buildLamps(ctx, C.roads);
  buildRoadSigns(ctx, C.roads);      // after the models: signs keep out of buildings too (sanity.js)
  buildFlowers(ctx, C.flowers);
  markers = C.markers || [];
  buildFence(ctx, boundary, openings);      // gaps at the gates and wherever a road or path crosses the boundary
  buildCars(ctx, C.roads, markers.filter((mk) => mk.cat === '停车场'));
  walkers = createWalkers(ctx, C.roads, ...tier.walkers);   // sidewalks of main roads + a few groups at teaching-building doors
  // grass tufts, hedges, benches follow the ground the terrain shows (ground.png), else the aerial land cover
  const lcAt = det.ground && det.groundMeta ? makeGroundReader(ctx, det.ground.image, det.groundMeta) : det.lc ? makeLandcoverReader(ctx, det.lc.image) : null;
  if (tier.grass && lcAt) grass = createGrass(ctx, lcAt);
  if (lcAt) {
    buildHedges(ctx, C.roads, lcAt);
    if (tier.shrubs) buildShrubs(ctx, lcAt);    // shrub balls in planting beds (均衡 / 高清)
    buildFurniture(ctx, C.roads, lcAt);
  }
  const CHECKPOINTS = ['图书馆', '气象楼', '钟楼', '老校门', '东大门', '信息科技大楼（临江楼）', '文德楼', '尚贤楼', '见山园', '藕舫楼', '升旗广场', '雷达塔'];
  const clock = metas.find((m) => m.landmark === 'clocktower');
  const asMeta = (n) => named.find((m) => m.name === n) || (() => {
    const mk = markers.find((q) => q.name === n);   // official map landmark (e.g. 钟楼)
    return mk && { name: n, kind: 'poi', cx: mk.x, cz: mk.z, minX: 0, maxX: 0, minZ: 0, maxZ: 0, photos: n === '钟楼' ? clock?.photos : null };
  })();
  const qpts = CHECKPOINTS.map(asMeta).filter(Boolean).map((m) => {
    // put the beacon in front of the building, on the side facing the nearest road point if any
    const off = m.kind === 'poi' ? 0 : Math.max(m.maxX - m.minX, m.maxZ - m.minZ) / 2 + 8;
    const p = new THREE.Vector3(m.cx, 0, m.cz + off);
    for (let i = 0; i < 6; i++) collide(p, 3);
    return { name: m.name.replace('（临江楼）', '·临江楼'), x: p.x, z: p.z, photo: m.photos?.[0]?.file };
  });
  const NOTES = { '气象楼': '主楼 15 层、两翼 3 层，楼顶白色雷达球', '信息科技大楼·临江楼': '即信息科技大楼，北端高塔约 75 m（航拍三维重建实测）',
    '东大门': '雷丁学院东侧，靠近地铁站', '老校门': '官网地图标为“气象学院校门”，在尚贤楼与气象谷之间', '升旗广场': '国际教育学院门口',
    '雷达塔': '启明楼与长望楼之间，顶着雷达球', '钟楼': '官网地图文化景点' };
  tour = createTour({ heightAt }, qpts.map((q) => ({ ...q, note: NOTES[q.name] })), { box: $('tour'), title: $('tourTitle'), sub: $('tourSub'), img: $('tourImg'),
    onEnd: () => say('云游导览结束。按 F 降落，或继续自由飞行', 4) });
  quest = createQuest(ctx, qpts, { grid: $('stampGrid'), count: $('bookCount'), postcard: $('postcard'),
    onStamp: (it, n, total) => { say(n === total ? `打卡成功：${it.name}！全部集齐，按 J 看明信片` : `打卡成功：${it.name}（${n}/${total}）`, 4); phone?.onStamp(it, n, total); } });

  setMsg('校园小公交和 7ma 电动车就位…'); await tick();
  if (C.bus && C.bus.route.length > 1) { bus = createBus(ctx, C.bus); busRoute = C.bus.route; }
  // official road names for the big map: midpoints of the longer ways of each named road (max 3 labels per name)
  {
    const want = new Set(['正气路', '正气东路', '万象路', '盘城新街', '万家坝路', '龙山北路']), by = new Map();
    for (const r of C.roads) {
      if (!want.has(r.name)) continue;
      let L = 0; for (let i = 1; i < r.pts.length; i++) L += Math.hypot(r.pts[i][0] - r.pts[i - 1][0], r.pts[i][1] - r.pts[i - 1][1]);
      if (L < 100) continue;
      let acc = 0, k = 1;
      for (; k < r.pts.length; k++) { const d = Math.hypot(r.pts[k][0] - r.pts[k - 1][0], r.pts[k][1] - r.pts[k - 1][1]); if (acc + d >= L / 2) break; acc += d; }
      const [x0, z0] = r.pts[k - 1], [x1, z1] = r.pts[Math.min(k, r.pts.length - 1)], t = (L / 2 - acc) / (Math.hypot(x1 - x0, z1 - z0) || 1);
      let ang = Math.atan2(z1 - z0, x1 - x0); if (ang > Math.PI / 2) ang -= Math.PI; if (ang < -Math.PI / 2) ang += Math.PI;
      if (!by.has(r.name)) by.set(r.name, []);
      by.get(r.name).push({ name: r.name, x: x0 + (x1 - x0) * t, z: z0 + (z1 - z0) * t, ang, L });
    }
    for (const lst of by.values()) roadLabels.push(...lst.sort((a, b) => b.L - a.L).slice(0, 3));
  }
  // refined bus model from the Blender session, if it exists (web/public/models/bus.glb)
  if (bus) {
    try {
      const head = await fetch('models/bus.glb', { method: 'HEAD' });
      if (head.ok && (head.headers.get('content-type') || '').includes('model')) {
        const gltf = await new GLTFLoader().loadAsync('models/bus.glb');
        gltf.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
        bus.group.clear();
        bus.group.add(gltf.scene);
      }
    } catch { /* keep the procedural bus */ }
    // bus shelters at the official stops (models/bus_shelter.glb, front -z facing the road)
    const shelter = await loadOptionalGLB('models/bus_shelter.glb');
    if (shelter) {
      mergeStatic(shelter);                      // 性能: each clone draws one mesh per material
      for (const st of C.bus.stops) {
        if (st.x === undefined) continue;
        const o = shelter.clone(), x = st.x - st.ax * 1.4, z = st.z - st.az * 1.4;
        o.position.set(x, world.topAt(x, z), z); o.rotation.y = Math.atan2(-st.ax, -st.az);   // on the sidewalk surface
        o.userData.sanity = { kind: 'shelter' };
        scene.add(o);
        if (st.sign) {     // stop sign beside the shelter, not in front of it
          const sx = st.x + st.az * 2.9, sz = st.z - st.ax * 2.9;
          st.sign.position.set(sx, world.topAt(sx, sz), sz);
        }
      }
    }
  }
  const bikeGLB = await loadOptionalGLB('models/ebike_7ma.glb');
  if (bikeGLB) { setEbikeGLB(bikeGLB); ebikeMesh.clear(); for (const c of [...ebikeModel().children]) ebikeMesh.add(c); }
  if (C.ebikes) ebikes = createEbikes(ctx, C.ebikes);

  const lib = named.find((m) => m.name === '图书馆') || named.find((m) => m.campus) || { cx: 0, cz: 0 };
  // spawn: centre of the plaza in front of the library (aerial: paving x≈112–145, z≈−228…−186), facing the library;
  // 7ma rows on both sides of the plaza (data/manual/ebike_spots.json), so the player can walk or ride from the start
  const spawn = () => teleport(128.5, -206, 128.5, lib.cz);
  spawn();
  avatar.rotation.y = P.yaw;
  // start menu first: its key guard must run before the phone's Tab handler
  if (STUNTS) $('help')?.insertAdjacentHTML('beforeend', '<br>骑车时 <kbd>Shift</kbd> 飙车　按住 <kbd>空格</kbd> 翘头');
  showStartMenu({ rig, P, avatar, isTouch, stunts: STUNTS, onStart: (mode) => {
    phone?.welcome();
    if (mode === 'route') route?.start();
    else { $('start').hidden = false; say(`广场两侧停着蓝色 7ma：走过去${isTouch ? '点「扫码骑车」' : '按 E '}扫码就能骑，也可以直接步行逛`, 7); }
  } });
  stunt = STUNTS ? createStunt({ P, avatar, rider, bicycle, ebikeMesh, camera, scene, say }) : null;
  phone = createPhone({ ...ctx, P, camera, renderer, markers, named, metas, collide, say, stunt, isTouch, getRoute: () => route, ebikeSpots: C.ebikes || [],
    openMap, openBook: toggleBook, isNight: () => night, tourActive: () => !!tour?.active, quest: () => quest });
  route = createRoute({ ...ctx, P, say, named, markers, metas, collide, getBus: () => bus, isTouch, getEbikes: () => ebikes, quest: () => quest, station: (x, z) => phone?.nearestStation(x, z),
    goHome: () => {
      if (P.ride === 'ebike') { ebikes.park(P.ebikeIdx, P.pos.x, P.pos.z, avatar.rotation.y); P.ebikeIdx = -1; phone?.endEbike(); }
      if (P.ride === 'bus') leaveBus(false);
      P.ride = null; P.fly = false; spawn();
    } });
  if (import.meta.env.DEV) window.__campus = { P, teleport, heightAt, collide, interact, scene, camera, renderer, THREE, rig, get bus() { return bus; }, get ebikes() { return ebikes; }, get phone() { return phone; }, get stunt() { return stunt; }, get route() { return route; }, get airWall() { return airWall; }, modelGrids,
    world: ctx, C, sanity: (o) => scanWorld(ctx, scene, o),   // 常识排查: __campus.sanity() → { summary, issues }
    bench: { update, render: () => (composer && aoOn ? composer.render() : renderer.render(scene, camera)), sun, setNight, get composer() { return composer; } },   // 性能: one frame without rAF
    perf: { Q, detail, applyTier, get tier() { return tier; },
      // 性能基线: await __campus.perf.run('overview') → { gpuMs, cpuMs, calls, triK } (1920×1080, pixel ratio 1)
      views: {
        spawn: () => { P.fly = false; P.ride = null; P.first = false; P.dist = 7; spawn(); P.yaw = 0; P.pitch = -0.22; },
        overview: () => { P.ride = null; P.fly = true; P.pos.set(0, 650, 1250); P.yaw = 0; P.pitch = -0.5; },
        dorm: () => { P.fly = false; P.ride = null; P.first = false; P.dist = 7; teleport(-392, -236); P.yaw = Math.PI / 2; P.pitch = -0.12; },
        low: () => { P.ride = null; P.fly = true; P.pos.set(128, 120, 150); P.yaw = 0; P.pitch = -0.35; },
      },
      run(view, o) { return devBench({ renderer, camera, composer: () => composer, step: () => { update(1 / 60); detail.update(camera); shadowTick(); },
        render: () => (composer && aoOn ? composer.render() : renderer.render(scene, camera)) })(this.views[view], o); } } };
  // 性能: campus-wide hedge / shrub / fence instances in 300 m chunks, hidden beyond the tier's distance (perf.js)
  for (const o of [...scene.children]) {
    const kind = o.userData.sanity?.kind;
    if (o.isInstancedMesh && (kind === 'hedge' || kind === 'fence')) for (const part of splitInstanced(o, 300)) detail.tag(part, kind);
    else if (kind === 'sign') detail.tag(o, 'sign');     // road-name plates
  }
  compactGroups(scene);                                   // plates: 6 → 2 draw calls each
  qmenu = mountQualityMenu(document.querySelector('#hud .title') || $('hud'), {   // 画质 button on the title line
    current: tier, auto: Q.auto, detected: Q.detected, onPick: (t, o) => applyTier(t, o) });
  $('loading').remove();
  loop();
}

// shadows + night windows for Blender GLBs: glass glows, dark window areas of wall textures become an emissive map
const nightDone = new WeakSet();
function prepModelMesh(o) {
  if (!o.isMesh) return;
  o.castShadow = true; o.receiveShadow = true;
  const mt = o.material;
  if (!mt || nightDone.has(mt)) return;
  nightDone.add(mt);
  if (/glass/.test(mt.name)) { mt.emissive = new THREE.Color('#ffc977'); mt.emissiveIntensity = 0; modelNightMats.push(mt); }
  else if (/_wall|_tower|_podium|wall/.test(mt.name) && mt.map?.image) {
    const img = mt.map.image, c = document.createElement('canvas');
    c.width = Math.min(1024, img.width); c.height = Math.round(c.width * img.height / img.width);
    const x = c.getContext('2d'); x.drawImage(img, 0, 0, c.width, c.height);
    const d = x.getImageData(0, 0, c.width, c.height);
    litWindows(d, c.width, c.height, (p) => p[0] * 0.3 + p[1] * 0.59 + p[2] * 0.11 < 95, mt.name.length * 131 + c.width);
    x.putImageData(d, 0, 0);
    const em = new THREE.CanvasTexture(c); em.flipY = mt.map.flipY; em.wrapS = mt.map.wrapS; em.wrapT = mt.map.wrapT;
    mt.emissiveMap = em; mt.emissive = new THREE.Color('#ffc977'); mt.emissiveIntensity = 0; mt.needsUpdate = true;
    modelNightMats.push(mt);
  }
}

async function loadOptionalGLB(url) {
  try {
    const head = await fetch(url, { method: 'HEAD' });
    if (!head.ok || !(head.headers.get('content-type') || '').includes('model')) return null;
    const gltf = await new GLTFLoader().loadAsync(url);
    gltf.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    return gltf.scene;
  } catch { return null; }
}

main().catch((e) => { console.error(e); setMsg(`加载失败：${e.message}`); });
