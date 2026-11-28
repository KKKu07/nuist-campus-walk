// 性能：画质分档（流畅 / 均衡 / 高清）、按设备自动选档、按距离隐藏远处细节、合并静态模型、帧率过低自动降档。
// 游戏（main.js）和展示版（showcase.js）共用。选档存本机 localStorage 'nuist-quality'；地址加 ?q=low|mid|high 临时指定。
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';

// pr: devicePixelRatio cap (touch devices use prTouch) · shadow: sun shadow map size · shadowEvery: redraw the shadow map
// every n frames · ao: GTAO contact shadows · lite: 2-lobe tree crowns without leaf cards · shrubs / grass: shrub balls and
// grass tufts · apron: bank apron cell (m) · lod: scale on every distance in DIST · walkers: [people, door groups] ·
// ortho8k: full-resolution aerial photo · skyHi: 2048 px sky HDR (else 1024 px)
export const TIERS = {
  low: { id: 'low', name: '流畅', pr: 1, prTouch: 1.25, shadow: 1024, shadowEvery: 2, ao: false, lite: true, shrubs: false, grass: false, apron: 2, lod: 0.35, walkers: [40, 8], ortho8k: false, skyHi: false },
  mid: { id: 'mid', name: '均衡', pr: 1.5, prTouch: 1.5, shadow: 2048, shadowEvery: 1, ao: false, lite: false, shrubs: true, grass: true, apron: 1, lod: 0.6, walkers: [70, 12], ortho8k: false, skyHi: true },
  high: { id: 'high', name: '高清', pr: 2, prTouch: 2, shadow: 4096, shadowEvery: 1, ao: true, lite: false, shrubs: true, grass: true, apron: 0.5, lod: 1, walkers: [90, 14], ortho8k: true, skyHi: true },
};
const ORDER = ['low', 'mid', 'high'];
// distances (m, at lod 1) beyond which a detail is hidden; far tree crowns take over where full crowns stop
export const DIST = { cards: 500, trunk: 600, crown: 1000, hedge: 900, fence: 900, sign: 400 };
const RANGE = { cards: [DIST.cards, 0], trunk: [DIST.trunk, 0], crown: [DIST.crown, 0], crownFar: [Infinity, DIST.crown], hedge: [DIST.hedge, 0], fence: [DIST.fence, 0], sign: [DIST.sign, 0] };

const KEY = 'nuist-quality', AUTO_KEY = 'nuist-quality-auto';   // the player's choice · a tier the fps guard dropped to
const ls = (k, v) => {
  try { if (v === undefined) return localStorage.getItem(k); if (v) localStorage.setItem(k, v); else localStorage.removeItem(k); } catch { /* private mode */ }
  return null;
};
const store = { get: () => ls(KEY), set: (v) => { ls(KEY, v || null); ls(AUTO_KEY, null); } };

// guess a tier from the GPU name, touch, CPU cores and memory; integrated graphics and phones start low, discrete GPUs high
export function detectTier(renderer, isTouch) {
  let gpu = '';
  try {
    const gl = renderer.getContext(), e = gl.getExtension('WEBGL_debug_renderer_info');
    gpu = String(gl.getParameter(e ? e.UNMASKED_RENDERER_WEBGL : gl.RENDERER) || '');
  } catch { /* unknown GPU */ }
  const g = gpu.toLowerCase(), cores = navigator.hardwareConcurrency || 4, mem = navigator.deviceMemory || 8;
  let t = 'mid';
  if (/swiftshader|llvmpipe|softpipe|basic render|software/.test(g)) t = 'low';
  else if (isTouch) t = 'low';                                                   // phones and tablets
  else if (/intel/.test(g)) t = /arc|iris\(r\) xe|iris xe|iris\(r\) plus|iris plus/.test(g) ? 'mid' : 'low';   // HD / UHD → low
  else if (/geforce|rtx|gtx|quadro|nvidia|radeon rx|radeon pro|firepro/.test(g)) t = /\bmx ?\d|gt \d{3}\b|\d{3}m\b/.test(g) ? 'mid' : 'high';
  else if (/radeon|amd|apple|mali|adreno/.test(g)) t = 'mid';                     // AMD / Apple integrated
  if ((cores <= 4 || mem <= 4) && t !== 'low') t = t === 'high' ? 'mid' : 'low';
  return { tier: t, gpu };
}

// the tier to start with: ?q= in the address, else the player's saved choice, else the detected one
// 用户决定（2026-11-27）：默认一律「高清」= 原版最好的画质，电脑和手机都一样；流畅 / 均衡只作为以后的选项：
// 不按设备自动选档、不自动降档、不显示画质按钮。以后真遇到性能问题，把 TIER_OPTIONS 改成 true 即恢复。
// 测试用：地址加 ?q=low|mid|high 仍可临时指定。
export const TIER_OPTIONS = false;
export function chooseTier(renderer, isTouch) {
  const det = detectTier(renderer, isTouch);
  const q = new URLSearchParams(location.search).get('q');
  if (!TIER_OPTIONS) return { tier: TIERS[TIERS[q] ? q : 'high'], auto: false, detected: det.tier, gpu: det.gpu };
  const saved = store.get(), dropped = ls(AUTO_KEY);
  const autoId = TIERS[dropped] && ORDER.indexOf(dropped) < ORDER.indexOf(det.tier) ? dropped : det.tier;
  const id = TIERS[q] ? q : TIERS[saved] ? saved : autoId;
  return { tier: TIERS[id], auto: !TIERS[q] && !TIERS[saved], detected: det.tier, gpu: det.gpu };
}
export const pixelRatio = (tier, isTouch) => Math.min(devicePixelRatio || 1, isTouch ? tier.prTouch : tier.pr);

// ---------------------------------------------------------------- distance culling
// track(obj, far, near): obj is drawn while near * lod <= d < far * lod, d = camera distance to its bounding sphere
export function createDetail() {
  const items = [], sph = new THREE.Sphere(), box = new THREE.Box3(), last = new THREE.Vector3(Infinity, 0, 0);
  let lod = 1, n = 0, dirty = true;
  const sphereOf = (o) => {
    o.updateWorldMatrix(true, false);
    if (o.isInstancedMesh) { if (!o.boundingSphere) o.computeBoundingSphere(); return sph.copy(o.boundingSphere).applyMatrix4(o.matrixWorld).clone(); }
    if (o.isMesh) { if (!o.geometry.boundingSphere) o.geometry.computeBoundingSphere(); return sph.copy(o.geometry.boundingSphere).applyMatrix4(o.matrixWorld).clone(); }
    return box.setFromObject(o).getBoundingSphere(new THREE.Sphere());
  };
  return {
    // sphere: measure from this (world-space) sphere instead of obj's own, so swapped LOD pairs switch at the same place
    track(obj, far = Infinity, near = 0, sphere = null) { items.push({ obj, s: sphere ? sphere.clone() : sphereOf(obj), far, near }); dirty = true; },
    tag(obj, kind, sphere = null) { const r = RANGE[kind]; if (r) this.track(obj, r[0], r[1], sphere); },   // builders: 'crown', 'cards', ...
    sphereOf,
    setLod(k) { lod = k; dirty = true; },
    get lod() { return lod; },
    update(camera) {
      const p = camera.position;
      if (!dirty && (++n % 12) && p.distanceToSquared(last) < 16) return;    // every 12 frames, or after moving 4 m
      dirty = false; last.copy(p);
      for (const it of items) {
        const d = Math.max(0, p.distanceTo(it.s.center) - it.s.radius);
        it.obj.visible = d >= it.near * lod && d < it.far * lod;
      }
    },
  };
}

// split a campus-wide InstancedMesh into cell x cell chunks so frustum and distance culling work per chunk
export function splitInstanced(mesh, cell = 300) {
  const parent = mesh.parent, n = mesh.count;
  if (!parent || n < 64) return [mesh];
  const m4 = new THREE.Matrix4(), c = new THREE.Color(), buckets = new Map();
  for (let i = 0; i < n; i++) {
    mesh.getMatrixAt(i, m4);
    const k = `${Math.floor(m4.elements[12] / cell)},${Math.floor(m4.elements[14] / cell)}`;
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(i);
  }
  if (buckets.size < 2) return [mesh];
  const out = [];
  for (const idx of buckets.values()) {
    const im = new THREE.InstancedMesh(mesh.geometry, mesh.material, idx.length);
    idx.forEach((j, i) => {
      mesh.getMatrixAt(j, m4); im.setMatrixAt(i, m4);
      if (mesh.instanceColor) { mesh.getColorAt(j, c); im.setColorAt(i, c); }
    });
    Object.assign(im, { castShadow: mesh.castShadow, receiveShadow: mesh.receiveShadow, renderOrder: mesh.renderOrder, frustumCulled: mesh.frustumCulled, name: mesh.name });
    im.userData = mesh.userData;
    im.computeBoundingSphere();
    parent.add(im);
    out.push(im);
  }
  parent.remove(mesh);
  mesh.dispose();
  return out;
}

// ---------------------------------------------------------------- static model merging
// one draw call per material (and attribute layout) instead of one per Blender object; hidden nodes are dropped
const toFloat = (a, size = a.itemSize) => {
  const out = new Float32Array(a.count * size);
  for (let i = 0; i < a.count; i++) for (let k = 0; k < size; k++) out[i * size + k] = a.getComponent(i, k);
  return new THREE.BufferAttribute(out, size);
};
export function mergeStatic(root) {
  root.updateMatrixWorld(true);
  const inv = root.matrixWorld.clone().invert(), groups = new Map(), drop = [], m = new THREE.Matrix4();
  const shown = (o) => { for (let p = o; p && p !== root.parent; p = p.parent) if (!p.visible) return false; return true; };
  root.traverse((o) => {
    if (!o.isMesh || o.isInstancedMesh || o.isSkinnedMesh || o.morphTargetInfluences || Array.isArray(o.material) || o.userData.sanity) return;
    if (!shown(o)) { drop.push(o); return; }
    const g = o.geometry;
    const key = `${o.material.uuid}|${Object.keys(g.attributes).sort().join(',')}|${!!g.index}|${o.castShadow}|${o.receiveShadow}|${o.renderOrder}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(o);
  });
  let before = 0, after = 0;
  for (const list of groups.values()) {
    before += list.length;
    if (list.length < 2) { after++; continue; }
    const geos = list.map((o) => {
      const src = o.geometry, gg = new THREE.BufferGeometry();
      for (const [name, a] of Object.entries(src.attributes)) gg.setAttribute(name, toFloat(a));
      if (src.index) gg.setIndex(src.index.clone());
      m.multiplyMatrices(inv, o.matrixWorld);
      gg.applyMatrix4(m);
      if (m.determinant() < 0 && gg.index) {             // mirrored object: keep the faces facing out
        const ix = gg.index.array;
        for (let i = 0; i < ix.length; i += 3) { const t = ix[i + 1]; ix[i + 1] = ix[i + 2]; ix[i + 2] = t; }
      }
      return gg;
    });
    const merged = mergeGeometries(geos, false);
    geos.forEach((g) => g.dispose());
    if (!merged) { after += list.length; continue; }
    const o0 = list[0], mesh = new THREE.Mesh(merged, o0.material);
    Object.assign(mesh, { castShadow: o0.castShadow, receiveShadow: o0.receiveShadow, renderOrder: o0.renderOrder, name: `merged:${o0.material.name || ''}` });
    root.add(mesh);
    for (const o of list) drop.push(o);
    after++;
  }
  for (const o of drop) o.parent?.remove(o);
  // empty nodes left behind cost a matrix update each frame: remove them
  const prune = (o) => { for (const ch of [...o.children]) prune(ch); if (o !== root && !o.isMesh && !o.children.length && !o.isLight && !o.isCamera) o.parent?.remove(o); };
  prune(root);
  return { before, after };
}

// Blender GLBs each embed their own copy of shared library textures (glass_dark, concrete, …: ~400 textures, ~80
// distinct): keep one texture per (name, size, sampling, 24x24 pixel hash), so each image is uploaded to the GPU once
export function createTextureDedupe() {
  const seen = new Map(), cv = document.createElement('canvas');
  cv.width = cv.height = 24;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const hashOf = (img) => {
    try {
      cx.clearRect(0, 0, 24, 24); cx.drawImage(img, 0, 0, 24, 24);
      const d = cx.getImageData(0, 0, 24, 24).data; let h = 2166136261;
      for (let i = 0; i < d.length; i++) h = Math.imul(h ^ d[i], 16777619);
      return h >>> 0;
    } catch { return Math.random(); }               // unreadable: never shared
  };
  let dropped = 0;
  const canon = (t) => {
    const im = t.image;
    if (!im || !t.name || !(im.width > 0)) return t;
    const key = `${t.name}|${im.width}x${im.height}|${t.colorSpace}|${t.wrapS},${t.wrapT}|${t.flipY}|${t.channel}|${t.repeat.x},${t.repeat.y},${t.offset.x},${t.offset.y}|${hashOf(im)}`;
    const c = seen.get(key);
    if (!c) { seen.set(key, t); return t; }
    if (c !== t) { dropped++; t.dispose(); }
    return c;
  };
  return {
    dedupe(root) {
      root.traverse((o) => {
        if (!o.isMesh) return;
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          for (const k of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'alphaMap', 'bumpMap']) if (m[k]?.isTexture) m[k] = canon(m[k]);
        }
      });
    },
    get dropped() { return dropped; },
  };
}

// multi-material meshes (e.g. road-name plates: 4 edge faces + 2 name faces) draw once per geometry group; join
// neighbouring groups that use the same material on every mesh sharing the geometry (6 → 2 draw calls per plate)
export function compactGroups(root) {
  const byGeo = new Map();
  root.traverse((o) => { if (o.isMesh && Array.isArray(o.material) && o.geometry.groups.length > 1) { if (!byGeo.has(o.geometry)) byGeo.set(o.geometry, []); byGeo.get(o.geometry).push(o); } });
  let saved = 0;
  for (const [g, meshes] of byGeo) {
    const gr = [...g.groups].sort((a, b) => a.start - b.start), out = [{ ...gr[0] }];
    for (const x of gr.slice(1)) {
      const last = out[out.length - 1];
      if (last.start + last.count === x.start && meshes.every((o) => o.material[last.materialIndex] === o.material[x.materialIndex])) last.count += x.count;
      else out.push({ ...x });
    }
    if (out.length < gr.length) { saved += (gr.length - out.length) * meshes.length; g.clearGroups(); for (const x of out) g.addGroup(x.start, x.count, x.materialIndex); }
  }
  return saved;
}

// ---------------------------------------------------------------- frame-rate guard
// while the tier was picked automatically: after warm-up, if the visible page runs below minFps for a 5 s window, drop one
// tier (at most twice), and remember it for the next visit
export function createFpsGuard({ getTier, setTier, isAuto, say, minFps = 24 }) {
  let t0 = 0, frames = 0, start = 0, drops = 0, prev = 0;
  return function tick() {
    const now = performance.now();
    // hidden tab, or a > 1 s hitch (shader compile, alert, tab switch): restart the window
    if (document.visibilityState !== 'visible' || !prev || now - prev > 1000) { prev = now; t0 = 0; frames = 0; return; }
    prev = now;
    if (!isAuto() || drops >= 2) return;
    if (!start) start = now;
    if (now - start < 2500) return;                       // warm-up after load / a tier change: textures uploaded
    if (!t0) { t0 = now; frames = 0; return; }
    frames++;
    if (now - t0 < 5000) return;
    const fps = frames * 1000 / (now - t0);
    t0 = 0; frames = 0;
    const i = ORDER.indexOf(getTier().id);
    if (fps < minFps && i > 0) {
      drops++; start = 0;
      ls(AUTO_KEY, ORDER[i - 1]);
      setTier(TIERS[ORDER[i - 1]], { auto: true });
      say?.(`画面有点卡（约 ${Math.round(fps)} 帧/秒），已自动切到「${TIERS[ORDER[i - 1]].name}」画质，可在左上角「画质」里改回`, 6);
    }
  };
}

// ---------------------------------------------------------------- DEV benchmark
// GPU time (EXT_disjoint_timer_query_webgl2), CPU submit time, draw calls and triangles of n frames at a fixed view,
// rendered without requestAnimationFrame (works in a hidden tab). step() = one game update; render() = one frame.
export function devBench({ renderer, camera, step, render, composer = () => null }) {
  const gl = renderer.getContext(), ext = gl.getExtension('EXT_disjoint_timer_query_webgl2');
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const med = (a) => { const b = a.filter(Number.isFinite).sort((x, y) => x - y); return b.length ? +b[Math.floor(b.length / 2)].toFixed(2) : NaN; };
  return async function run(setView, { n = 24, w = 1920, h = 1080, pr = 1 } = {}) {
    if (renderer.domElement.width !== Math.round(w * pr) || renderer.getPixelRatio() !== pr) {
      renderer.setPixelRatio(pr); renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
      composer()?.setPixelRatio(pr); composer()?.setSize(w, h);
    }
    setView();
    for (let i = 0; i < 6; i++) { step(); render(); }
    gl.finish();
    const auto = renderer.info.autoReset, fr = [];
    renderer.info.autoReset = false;
    for (let i = 0; i < n; i++) {
      step(); renderer.info.reset();
      const q = ext && gl.createQuery();
      if (q) gl.beginQuery(ext.TIME_ELAPSED_EXT, q);
      const c0 = performance.now(); render(); const cpu = performance.now() - c0;
      if (q) gl.endQuery(ext.TIME_ELAPSED_EXT);
      gl.finish();
      fr.push({ q, cpu, calls: renderer.info.render.calls, tris: renderer.info.render.triangles });
    }
    renderer.info.autoReset = auto;
    for (let k = 0; k < 40 && fr.some((f) => f.q); k++) {
      await sleep(25);
      for (const f of fr) if (f.q && gl.getQueryParameter(f.q, gl.QUERY_RESULT_AVAILABLE)) { f.gpu = gl.getQueryParameter(f.q, gl.QUERY_RESULT) / 1e6; gl.deleteQuery(f.q); f.q = null; }
    }
    return { gpuMs: med(fr.map((f) => f.gpu)), cpuMs: med(fr.map((f) => f.cpu)), calls: med(fr.map((f) => f.calls)), triK: Math.round(med(fr.map((f) => f.tris)) / 1000) };
  };
}

// ---------------------------------------------------------------- quality menu
// a small "画质 ▾" button (appended to `host`) opening 自动 / 流畅 / 均衡 / 高清; onPick(tier, { auto }) applies it live.
// Some parts (tree detail, shrubs, grass, aerial resolution) are built at load: the menu offers a reload for them.
export function mountQualityMenu(host, { current, auto, detected, onPick }) {
  if (!TIER_OPTIONS) return { set() {} };            // hidden for now (see TIER_OPTIONS)
  if (!document.getElementById('qm-style')) {
    const st = document.createElement('style');
    st.id = 'qm-style';
    st.textContent = `.qm{display:inline-block;pointer-events:auto;font:inherit;vertical-align:middle}
.qm>button{border:0;border-radius:999px;padding:2px 9px;margin-left:8px;background:rgba(255,255,255,.16);color:inherit;font:inherit;font-size:12px;font-weight:400;line-height:1.6;cursor:pointer;white-space:nowrap}
.qm>button:hover{background:rgba(255,255,255,.28)}
.qm-pop{position:fixed;z-index:80;width:min(250px,calc(100vw - 24px));background:rgba(16,24,22,.95);border-radius:10px;padding:8px;box-shadow:0 6px 24px rgba(0,0,0,.35);display:grid;gap:4px;color:#eef3f0;font-weight:400;letter-spacing:0}
.qm-pop[hidden]{display:none}
.qm-pop button{text-align:left;border:0;border-radius:6px;padding:7px 10px;background:rgba(255,255,255,.08);color:inherit;font:inherit;font-size:13px;line-height:1.4;cursor:pointer}
.qm-pop button:hover{background:rgba(255,255,255,.2)}.qm-pop button.on{background:rgba(255,176,112,.32)}
.qm-pop small{display:block;color:#b3c1bb;font-size:11px;margin-top:1px}.qm-pop p{margin:4px 2px 0;font-size:11px;color:#b3c1bb;line-height:1.5}`;
    document.head.appendChild(st);
  }
  const DESC = { low: '旧电脑、手机：画面简化，最流畅', mid: '普通笔记本：关掉环境光遮蔽，远处简化', high: '独立显卡：全部效果' };
  const wrap = document.createElement('span'), btn = document.createElement('button'), pop = document.createElement('div');
  wrap.className = 'qm'; btn.type = 'button'; pop.className = 'qm-pop'; pop.hidden = true;
  wrap.append(btn); host.appendChild(wrap); document.body.appendChild(pop);
  const built = current;                     // what was built at load (tree detail, shrubs, grass, aerial photo)
  let cur = current, isAuto = auto;
  const label = () => { btn.textContent = `画质 ${cur.name}${isAuto ? '·自动' : ''} ▾`; };
  const place = () => {                      // under the button, kept on screen
    const r = btn.getBoundingClientRect(), w = pop.offsetWidth || 250;
    pop.style.left = `${Math.max(12, Math.min(r.left, innerWidth - w - 12))}px`;
    const below = r.bottom + 6, h = pop.offsetHeight || 260;
    pop.style.top = `${below + h < innerHeight - 8 ? below : Math.max(8, r.top - h - 6)}px`;
  };
  const render = () => {
    pop.replaceChildren();
    const item = (txt, sub, on, fn) => {
      const b = document.createElement('button'), s = document.createElement('small');
      b.type = 'button'; b.className = on ? 'on' : ''; s.textContent = sub; b.append(txt, s);
      b.onclick = (e) => { e.stopPropagation(); b.blur(); fn(); };   // blur: keys (WASD, space) go back to the game
      pop.appendChild(b);
    };
    item(`自动（本机建议：${TIERS[detected].name}）`, '按显卡自动选择，卡顿时自动降一档', isAuto, () => pick(null));
    for (const id of ORDER) item(TIERS[id].name, DESC[id], !isAuto && cur.id === id, () => pick(TIERS[id]));
    if (cur.lite !== built.lite || cur.shrubs !== built.shrubs || cur.ortho8k !== built.ortho8k || cur.apron !== built.apron) {
      const p = document.createElement('p'); p.textContent = '树木细节、灌木草丛、航拍清晰度要刷新页面后才完全生效。';
      const r = document.createElement('button'); r.type = 'button'; r.textContent = '现在刷新'; r.onclick = () => location.reload();
      pop.append(p, r);
    }
    place();
  };
  const pick = (t) => {
    const next = t || TIERS[detected];
    store.set(t ? t.id : null);
    isAuto = !t; cur = next; label(); render();
    onPick(next, { auto: isAuto });
  };
  btn.onclick = (e) => { e.stopPropagation(); btn.blur(); pop.hidden = !pop.hidden; if (!pop.hidden) render(); };
  addEventListener('pointerdown', (e) => { if (!wrap.contains(e.target) && !pop.contains(e.target)) pop.hidden = true; });
  addEventListener('resize', () => { if (!pop.hidden) place(); });
  for (const el of [wrap, pop]) for (const ev of ['pointerdown', 'mousedown', 'click', 'wheel', 'touchstart']) el.addEventListener(ev, (e) => e.stopPropagation(), { passive: true });
  label();
  return {
    set(t, { auto: a = isAuto } = {}) { cur = t; isAuto = a; label(); if (!pop.hidden) render(); },
  };
}
