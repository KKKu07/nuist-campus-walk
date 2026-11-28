// Things that make the campus feel inhabited: boundary railings, parked cars, students walking on the sidewalks.
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { GROUND } from './palette.js';

const hash = (x, z) => { const s = Math.sin(x * 12.9898 + z * 78.233) * 43758.5453; return s - Math.floor(s); };
const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), one = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();

// ---------------------------------------------------------------- black iron railing along the campus boundary, open at gates
export function buildFence(ctx, boundary, gates) {
  const parts = [new THREE.BoxGeometry(0.09, 1.9, 0.09).translate(0, 0.95, 0),
    new THREE.BoxGeometry(0.04, 0.05, 2.5).translate(0, 1.6, 1.25), new THREE.BoxGeometry(0.04, 0.05, 2.5).translate(0, 0.3, 1.25)];
  for (let i = 1; i < 10; i++) parts.push(new THREE.BoxGeometry(0.025, 1.4, 0.025).translate(0, 0.95, i * 0.25));
  const geo = mergeGeometries(parts);
  const spots = [];
  for (const ring of boundary) {
    for (let i = 0; i < ring.length; i++) {
      const [x0, z0] = ring[i], [x1, z1] = ring[(i + 1) % ring.length];
      const L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 0.5) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = 0; t + 2.5 <= L + 0.01; t += 2.5) {
        const x = x0 + dx * t, z = z0 + dz * t;
        if (gates.some((g) => Math.hypot(g.x - x, g.z - z) < 14)) continue;
        if (ctx.wet?.(x, z)) continue;                  // where the boundary crosses a river: no railing standing in it
        spots.push([x, z, Math.atan2(dx, dz)]);
      }
    }
  }
  const im = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: '#23272b', roughness: 0.5, metalness: 0.6 }), spots.length);
  spots.forEach(([x, z, a], i) => { p.set(x, ctx.heightAt(x, z), z); q.setFromAxisAngle(up, a); m4.compose(p, q, one); im.setMatrixAt(i, m4); });
  im.computeBoundingSphere(); im.castShadow = true; im.userData.sanity = { kind: 'fence' };
  ctx.scene.add(im);
  return spots.length;
}

// ---------------------------------------------------------------- parked cars: rows at the official map's parking spots + some along roads
export function buildCars(ctx, roads, parkings) {
  const spots = [], stalls = [], pads = [];
  const nearestRoad = (x, z) => {
    let best = null;
    for (const r of roads) {
      if (r.w < 5) continue;
      for (let i = 0; i < r.pts.length - 1; i++) {
        const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1];
        const ex = x1 - x0, ez = z1 - z0, l2 = ex * ex + ez * ez || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - x0) * ex + (z - z0) * ez) / l2));
        const d = Math.hypot(x - x0 - ex * t, z - z0 - ez * t);
        if (!best || d < best.d) best = { d, x: x0 + ex * t, z: z0 + ez * t, ex, ez, w: r.w, sw: r.sw ?? (r.w >= 7 ? 2.4 : 0), rd: r };
      }
    }
    return best;
  };
  for (const pk of parkings) {
    const r = nearestRoad(pk.x, pk.z);
    if (!r || r.d > 70) continue;
    const L = Math.hypot(r.ex, r.ez) || 1, dx = r.ex / L, dz = r.ez / L, nx = -dz, nz = dx;
    const side = (pk.x - r.x) * nx + (pk.z - r.z) * nz > 0 ? 1 : -1, off = r.w / 2 + r.sw + 0.5;
    const n = 6 + Math.floor(hash(pk.x, pk.z) * 8);
    for (let i = 0; i < n; i++) {
      const t = (i - n / 2) * 2.6;           // nose-in parking bays beyond the sidewalk, 2.6 x 5.2 m
      const cx = r.x + dx * t + nx * side * (off + 2.6), cz = r.z + dz * t + nz * side * (off + 2.6);
      if (ctx.onRoad?.(cx, cz, null, 0.5)) continue;
      // the whole 2.6 x 5.2 m bay clear of water, pitches, buildings and any other road or path (sanity.js)
      const fx = r.x + dx * t + nx * side * off, fz = r.z + dz * t + nz * side * off;
      if (ctx.blockedBy && [1.2, 2.6, 4.0].some((o) => ctx.blockedBy(fx + nx * side * o, fz + nz * side * o, { r: 1.1, road: 0, path: 0, self: r.rd }))) continue;
      if (hash(t, pk.x) > 0.2) spots.push([cx, cz, Math.atan2(nx, nz)]);   // ~80 % of bays occupied
      for (const e of [-1.3, 1.3]) stalls.push([r.x + dx * (t + e) + nx * side * off, r.z + dz * (t + e) + nz * side * off, nx * side, nz * side]);
      pads.push([r.x + dx * t + nx * side * off, r.z + dz * t + nz * side * off, nx * side, nz * side]);
    }
    stalls.push(null);
  }
  for (const r of roads) {
    if (r.w < 6 || /^(motorway|trunk|primary|secondary|tertiary)$/.test(r.kind) || !ctx.inCampus(r.pts[0][0], r.pts[0][1])) continue;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1];
      const L = Math.hypot(x1 - x0, z1 - z0); if (L < 8) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = 6; t < L - 6; t += 6.5) {
        const h = hash(x0 + t, z0 - t);
        if (h > 0.12 || r.w < 7) continue;
        const o = r.w / 2 - 1.1, cx = x0 + dx * t - dz * o, cz = z0 + dz * t + dx * o;
        if (ctx.onRoad?.(cx, cz, r, 4)) continue;          // not inside a junction
        if ((ctx.waterAt && ctx.waterAt(cx, cz) !== null) || ctx.blockedBy?.(cx, cz, { r: 1.0, road: false, sport: false })) continue;   // no parking on bridges or in buildings
        spots.push([cx, cz, Math.atan2(dx, dz), 1]);    // 4th = kerbside (on the carriageway)
      }
    }
  }
  // painted bay lines (white, 5.2 m deep) under the parking rows
  const lp = [];
  for (const st of stalls) {
    if (!st) continue;
    const [x, z, nx, nz] = st, tx = -nz * 0.06, tz = nx * 0.06;
    const P = (o, s2) => { const px = x + nx * o + tx * s2, pz = z + nz * o + tz * s2; return [px, ctx.heightAt(px, pz) + 0.24, pz]; };
    const a0 = P(0, -1), a1 = P(0, 1), b0 = P(5.2, -1), b1 = P(5.2, 1);
    lp.push(...a0, ...b0, ...a1, ...a1, ...b0, ...b1);
  }
  // concrete bay pads so the rows never sit on lawn
  const pp = [];
  for (const [x, z, nx, nz] of pads) {
    const tx = -nz, tz = nx;
    const P = (o, s2) => { const px = x + nx * o + tx * s2, pz = z + nz * o + tz * s2; return [px, ctx.heightAt(px, pz) + 0.21, pz]; };
    const a0 = P(-0.1, -1.32), a1 = P(-0.1, 1.32), b0 = P(5.4, -1.32), b1 = P(5.4, 1.32);
    pp.push(...a0, ...b0, ...a1, ...a1, ...b0, ...b1);
  }
  if (pp.length) {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pp, 3)); g.computeVertexNormals();
    const pm = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: '#7d7f80', roughness: 0.9, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    pm.receiveShadow = true; ctx.scene.add(pm);
  }
  if (lp.length) {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(lp, 3)); g.computeVertexNormals();
    const lm = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: '#e8e8e2', roughness: 0.7, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }));
    lm.receiveShadow = true; ctx.scene.add(lm);
  }
  const body = new THREE.BoxGeometry(1.8, 0.75, 4.4).translate(0, 0.62, 0);
  const cabin = mergeGeometries([new THREE.BoxGeometry(1.6, 0.6, 2.3).translate(0, 1.27, 0.15),
    new THREE.CylinderGeometry(0.33, 0.33, 1.86, 12).rotateZ(Math.PI / 2).translate(0, 0.33, 1.4),
    new THREE.CylinderGeometry(0.33, 0.33, 1.86, 12).rotateZ(Math.PI / 2).translate(0, 0.33, -1.4)]);
  const bm = new THREE.InstancedMesh(body, new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.35, metalness: 0.4 }), spots.length);
  const cm = new THREE.InstancedMesh(cabin, new THREE.MeshStandardMaterial({ color: '#1d2329', roughness: 0.15, metalness: 0.5 }), spots.length);
  const palette = ['#f2f2f0', '#c9ccd0', '#1c1f24', '#8a8f96', '#b3261e', '#2c4f86', '#f2f2f0', '#c9ccd0', '#5b3a29'];
  const c = new THREE.Color();
  spots.forEach(([x, z, a, kerb], i) => {      // bay rows stand on their 0.21 m pads, kerbside cars on the road surface
    p.set(x, kerb ? (ctx.topAt || ctx.heightAt)(x, z) : ctx.heightAt(x, z) + 0.21, z); q.setFromAxisAngle(up, a); m4.compose(p, q, one);
    bm.setMatrixAt(i, m4); cm.setMatrixAt(i, m4); bm.setColorAt(i, c.set(palette[Math.floor(hash(x, z) * palette.length)]));
  });
  for (const m of [bm, cm]) { m.computeBoundingSphere(); m.castShadow = true; m.receiveShadow = true; ctx.scene.add(m); }
  bm.userData.sanity = { kinds: spots.map((s2) => (s2[3] ? 'streetcar' : 'car')) };   // sanity.js scan: bay rows vs kerbside
  return spots.length;
}

// ---------------------------------------------------------------- students walking along campus sidewalks
export function createWalkers(ctx, roads, count, groups = 14) {
  // students walk only on the sidewalks of the main campus roads (roads that have sidewalks), and only along
  // stretches that are inside the campus and not over water (no walking into the river from a bridge or bank)
  const PUBLIC = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary']);
  const wet = (x, z) => ctx.waterAt && ctx.waterAt(x, z) !== null && !(ctx.deckAt && ctx.deckAt(x, z) !== null);
  const paths = [];
  for (const r of roads) {
    if (!(r.sw > 0) || r.w < 6 || PUBLIC.has(r.kind) || r.pts.length < 2) continue;
    const cum = [0];
    for (let i = 1; i < r.pts.length; i++) cum.push(cum[i - 1] + Math.hypot(r.pts[i][0] - r.pts[i - 1][0], r.pts[i][1] - r.pts[i - 1][1]));
    const len = cum[cum.length - 1], off = r.w / 2 + 0.18 + (r.sw - 0.18) / 2;
    const at = (s, side) => {
      let k = 0;
      while (k < cum.length - 2 && cum[k + 1] < s) k++;
      const [x0, z0] = r.pts[k], [x1, z1] = r.pts[k + 1], L = cum[k + 1] - cum[k] || 1, f = (s - cum[k]) / L;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      return [x0 + (x1 - x0) * f - dz * off * side, z0 + (z1 - z0) * f + dx * off * side];
    };
    for (const side of [-1, 1]) {        // usable stretches of this sidewalk, at least 30 m long
      let a = -1;
      for (let s = 0; s <= len + 1; s += 1) {
        const ok = s <= len && (() => { const [x, z] = at(Math.min(s, len), side); return ctx.inCampus(x, z) && !wet(x, z) && !ctx.inBuilding?.(x, z, 0.3); })();
        if (ok && a < 0) a = s;
        if (!ok && a >= 0) { if (s - 1 - a >= 30) paths.push({ pts: r.pts, cum, len, off, side, a, b: s - 1 }); a = -1; }
      }
    }
  }
  if (!paths.length) return null;
  const body = new THREE.CapsuleGeometry(0.22, 0.75, 3, 8).translate(0, 0.62, 0);
  const head = new THREE.SphereGeometry(0.15, 10, 8).translate(0, 1.36, 0);
  // a few small groups (2-3) standing in front of teaching-building entrances (world.js buildEntrances -> ctx.doors)
  const doors = (ctx.doors || []).filter((d) => (d.kind === 'teach' || d.kind === 'hall') && d.name && !wet(d.x, d.z)
    && !ctx.blockedBy?.(d.x, d.z, { r: 1.6, road: 0 }));     // not inside another building / model or out on the carriageway
  const standers = [];
  for (let g = 0; g < Math.min(groups, doors.length); g++) {
    const d = doors[Math.floor(hash(g * 5.3, 1.7) * doors.length)];
    if (standers.some((s) => Math.hypot(s.x - d.x, s.z - d.z) < 1)) continue;
    const n = 2 + (hash(g, 4.4) > 0.6 ? 1 : 0), tx = -d.nz, tz = d.nx;
    for (let k = 0; k < n; k++) {
      const u = (k - (n - 1) / 2) * 0.9, v = (k % 2) * 0.5;
      const x = d.x + tx * u + d.nx * v, z = d.z + tz * u + d.nz * v;
      standers.push({ x, z, face: Math.atan2(-(d.x - x) + tx * 0.01, -(d.z - z) + tz * 0.01) + (k - 1) * 0.8, sc: 0.92 + hash(g, k) * 0.16 });
    }
  }
  const total = count + standers.length;
  const bm = new THREE.InstancedMesh(body, new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.8 }), total);
  const hm = new THREE.InstancedMesh(head, new THREE.MeshStandardMaterial({ color: '#2a211c', roughness: 0.7 }), total);
  const clothes = ['#2a5ea8', '#e8e8e8', '#1f1f1f', '#b33b3b', '#6c8f4e', '#e0b04a', '#7d5aa6', '#3b8fa3', '#d97a9c'];
  const c = new THREE.Color();
  const ws = [];
  for (let i = 0; i < count; i++) {
    const r = hash(i * 7.1, i * 3.3), path = paths[Math.floor(r * paths.length)];
    ws.push({ path, s: path.a + hash(i, 2 * i) * (path.b - path.a), dir: hash(3 * i, i) > 0.5 ? 1 : -1, v: 1.1 + hash(i, 5) * 0.6,
      sc: 0.92 + hash(i, 11) * 0.16 });
    bm.setColorAt(i, c.set(clothes[i % clothes.length]));
  }
  for (let j = 0; j < standers.length; j++) {
    const s = standers[j], i = count + j;
    bm.setColorAt(i, c.set(clothes[(j * 5 + 2) % clothes.length]));
    p.set(s.x, (ctx.topAt || ctx.surfaceAt || ctx.heightAt)(s.x, s.z), s.z); q.setFromAxisAngle(up, s.face); m4.compose(p, q, new THREE.Vector3().setScalar(s.sc));
    bm.setMatrixAt(i, m4); hm.setMatrixAt(i, m4);
  }
  for (const m of [bm, hm]) { m.castShadow = true; m.frustumCulled = false; ctx.scene.add(m); }
  bm.userData.sanity = { kind: 'person' };
  const sc = new THREE.Vector3();
  return {
    update(dt, t) {
      ws.forEach((w, i) => {
        w.s += w.v * w.dir * dt;
        if (w.s < w.path.a || w.s > w.path.b) { w.dir = -w.dir; w.s = Math.max(w.path.a, Math.min(w.path.b, w.s)); }
        const { pts, cum } = w.path;
        let k = 0;
        while (k < cum.length - 2 && cum[k + 1] < w.s) k++;
        const [x0, z0] = pts[k], [x1, z1] = pts[k + 1], L = cum[k + 1] - cum[k] || 1, f = (w.s - cum[k]) / L;
        const dx = (x1 - x0) / L, dz = (z1 - z0) / L, o = w.path.off * w.path.side;
        const x = x0 + (x1 - x0) * f - dz * o, z = z0 + (z1 - z0) * f + dx * o;
        p.set(x, (ctx.topAt || ctx.surfaceAt || ctx.heightAt)(x, z) + Math.abs(Math.sin(t * 6 + i)) * 0.04, z);   // on the sidewalk, not sunk into it
        q.setFromAxisAngle(up, Math.atan2(-dx * w.dir, -dz * w.dir));
        sc.setScalar(w.sc);
        m4.compose(p, q, sc);
        bm.setMatrixAt(i, m4); hm.setMatrixAt(i, m4);
      });
      bm.instanceMatrix.needsUpdate = true; hm.instanceMatrix.needsUpdate = true;
    },
  };
}

// ---------------------------------------------------------------- grass tufts near the player, only on lawn (class 1)
// cls(x, z): ground class reader (makeGroundReader: the ground material map the terrain shows; or land cover).
// Never on a pitch / court / track, a road or path surface, or inside a building (sanity.js rules).
export function createGrass(ctx, cls, max = 9000) {
  const lawn = (x, z) => cls(x, z) === 1 && !ctx.inSport?.(x, z, 1) && !ctx.onSurface?.(x, z, 0.3) && !ctx.inBuilding?.(x, z, 0) && !ctx.inCut?.(x, z, 0.5) && !ctx.onModel?.(x, z, 0.3);   // nor in an underpass cut or on a model's own plaza / lawn
  const blades = [];
  for (let k = 0; k < 6; k++) {
    const a = k / 6 * Math.PI * 2 + 0.3, lean = 0.12 + (k % 3) * 0.05, h = 0.28 + (k % 2) * 0.12;
    const g = new THREE.BufferGeometry();
    const bx = Math.cos(a) * 0.05, bz = Math.sin(a) * 0.05;
    g.setAttribute('position', new THREE.Float32BufferAttribute([bx - Math.sin(a) * 0.03, 0, bz + Math.cos(a) * 0.03, bx + Math.sin(a) * 0.03, 0, bz - Math.cos(a) * 0.03,
      Math.cos(a) * lean, h, Math.sin(a) * lean], 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.4, 1.36, 1.12], 3));   // x lawn palette
    // normals straight up: lit like the lawn under them, so a tuft reads as taller grass, not a dark weed
    g.setAttribute('normal', new THREE.Float32BufferAttribute([0, 1, 0, 0, 1, 0, 0, 1, 0], 3));
    blades.push(g);
  }
  const geo = mergeGeometries(blades);
  const mat = new THREE.MeshStandardMaterial({ color: GROUND.lawn, vertexColors: true, side: THREE.DoubleSide, roughness: 0.9 });
  const im = new THREE.InstancedMesh(geo, mat, max);
  im.frustumCulled = false; im.receiveShadow = true; im.userData.sanity = { kind: 'grass' };
  ctx.scene.add(im);
  let cx = 1e9, cz = 1e9;
  const sc = new THREE.Vector3();
  return {
    update(pos) {
      if (Math.hypot(pos.x - cx, pos.z - cz) < 8) return;
      cx = pos.x; cz = pos.z;
      const R = 45, step = 1.5;
      let n = 0;
      for (let gz = Math.floor((cz - R) / step); gz <= (cz + R) / step && n < max; gz++) {
        for (let gx = Math.floor((cx - R) / step); gx <= (cx + R) / step && n < max; gx++) {
          for (let s = 0; s < 2 && n < max; s++) {
            const h = hash(gx * 3.1 + s, gz * 7.7 - s);
            const x = (gx + h) * step, z = (gz + hash(gz + s, gx) ) * step;
            if ((x - cx) ** 2 + (z - cz) ** 2 > R * R || !lawn(x, z)) continue;
            p.set(x, ctx.heightAt(x, z) - 0.02, z); q.setFromAxisAngle(up, h * 6.28); sc.setScalar(0.45 + h * 0.4);
            m4.compose(p, q, sc); im.setMatrixAt(n++, m4);
          }
        }
      }
      im.count = n;
      im.instanceMatrix.needsUpdate = true;
    },
  };
}

// ---------------------------------------------------------------- land-cover lookup shared by grass / hedges
export function makeLandcoverReader(ctx, lcImage) {
  const c = document.createElement('canvas');
  c.width = lcImage.width; c.height = lcImage.height;
  const x2 = c.getContext('2d', { willReadFrequently: true });
  x2.drawImage(lcImage, 0, 0);
  const px = x2.getImageData(0, 0, c.width, c.height).data, LW = c.width, LH = c.height;
  return (x, z) => { const i = Math.floor(x + ctx.W / 2), j = Math.floor(z + ctx.D / 2); return i < 0 || j < 0 || i >= LW || j >= LH ? 0 : px[(j * LW + i) * 4]; };
}
// the 0.5 m ground material map (campus/ground.png + ground_meta.json, tools/ground_map.py) read at 1 m: what the
// ground actually shows (1 lawn, 2 planting, 5 water, 6-8 track / turf / court, 10 building, ...)
export function makeGroundReader(ctx, img, meta) {
  const c = document.createElement('canvas');
  c.width = Math.ceil(img.width / 2); c.height = Math.ceil(img.height / 2);
  const x2 = c.getContext('2d', { willReadFrequently: true });
  x2.imageSmoothingEnabled = false;                 // nearest sample: class ids must not blend
  x2.drawImage(img, 0, 0, c.width, c.height);
  const d = x2.getImageData(0, 0, c.width, c.height).data, LW = c.width, LH = c.height, cls = new Uint8Array(LW * LH);
  for (let i = 0; i < cls.length; i++) cls[i] = d[i * 4];
  const sx = meta.m_per_px * img.width / LW, sz = meta.m_per_px * img.height / LH;
  return (x, z) => { const i = Math.floor((x - meta.x0) / sx), j = Math.floor((z - meta.z0) / sz); return i < 0 || j < 0 || i >= LW || j >= LH ? 0 : cls[j * LW + i]; };
}

// ---------------------------------------------------------------- 绿篱 / 灌木 (地表观感 2026-11-27): clipped shrubs of the usual
// campus kinds, one look shared by hedges and shrub balls: a leafy pattern projected in world space (no stretched
// UVs), shaded base, and one of four colours: 小叶黄杨 / 海桐 dark green, 金叶女贞 yellow-green, 红花檵木 purple-red
let LEAFY = null;
function leafyMaterial() {
  if (LEAFY) return LEAFY;
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const x = c.getContext('2d');
  x.fillStyle = '#8c8c8c'; x.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 1100; i++) {
    const v = 105 + hash(i, i * 0.37) * 150 | 0;
    x.fillStyle = `rgb(${v},${v},${v})`;
    x.beginPath(); x.ellipse(hash(i, 1.7) * 128, hash(2.3, i) * 128, 2.5 + hash(i, 9) * 3, 1.2 + hash(9, i) * 1.8, hash(i, 3) * 3.14, 0, 6.29); x.fill();
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4;
  const m = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: 0.9 });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.leafMap = { value: t };
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vLW;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n#ifdef USE_INSTANCING\nvLW = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;\n#else\nvLW = (modelMatrix * vec4(transformed, 1.0)).xyz;\n#endif');
    // (x + 0.8y, z + 0.6y - 0.5x) is two-dimensional on the top and on every side face
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vLW;\nuniform sampler2D leafMap;')
      .replace('#include <color_fragment>', '#include <color_fragment>\n  diffuseColor.rgb *= texture2D(leafMap, vec2(vLW.x + vLW.y * 0.8, vLW.z + vLW.y * 0.6 - vLW.x * 0.5) / 0.7).r * 1.75;');
  };
  LEAFY = m; return m;
}
const SHRUB_C = ['#3b5a2a', '#3b5a2a', '#46652f', '#7c8a33', '#5e2f33'];
function shrubColour(c, v, j) {
  c.set(SHRUB_C[Math.min(SHRUB_C.length - 1, Math.floor(v * SHRUB_C.length))]);
  return c.multiplyScalar(0.92 + 0.16 * j);
}
// shrub balls (球形灌木) in the planting beds (ground class 2) along their edges with paths and plazas, a few inside
// the beds; kept off roads, paths, buildings, water and pitches (sanity.js). Desktop only.
export function buildShrubs(ctx, lcAt, { step = 2.3 } = {}) {
  const PAVED = new Set([3, 4, 11, 12, 13, 14]), spots = [];
  const { W, D } = ctx;
  for (let z = -D / 2 + step / 2; z < D / 2; z += step) for (let x = -W / 2 + step / 2; x < W / 2; x += step) {
    const jx = x + (hash(x, z) - 0.5) * step * 0.8, jz = z + (hash(z, x) - 0.5) * step * 0.8;
    if (lcAt(jx, jz) !== 2) continue;
    const edge = [[2.6, 0], [-2.6, 0], [0, 2.6], [0, -2.6]].some(([dx, dz]) => PAVED.has(lcAt(jx + dx, jz + dz)));
    if (hash(jx * 1.3, jz * 0.7) > (edge ? 0.55 : 0.06)) continue;
    if (ctx.blockedBy?.(jx, jz, { r: 0.9, sport: 1, road: 0.4, path: 0.3, cover: 0.3 })) continue;   // cover: not on a model's own plaza / island (常识排查)
    spots.push([jx, jz]);
  }
  const geo = new THREE.IcosahedronGeometry(1, 1), pos = geo.attributes.position, col = [];
  for (let i = 0; i < pos.count; i++) {            // a bit lumpy, flat-bottomed, shaded underneath
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i), k = 1 + 0.08 * Math.sin(x * 5.1 + z * 3.7) * Math.sin(y * 4.3 - x * 2.2);
    pos.setXYZ(i, x * k, Math.max(-0.35, y) * k + 0.35, z * k);
    const v = 0.6 + 0.5 * Math.min(1, Math.max(0, (y + 0.35) / 1.35)); col.push(v, v, v);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  const CH = 600, groups = new Map(), c = new THREE.Color(), sc = new THREE.Vector3();
  for (const sp of spots) {
    const key = `${Math.floor((sp[0] + W / 2) / CH)},${Math.floor((sp[1] + D / 2) / CH)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(sp);
  }
  for (const list of groups.values()) {
    const im = new THREE.InstancedMesh(geo, leafyMaterial(), list.length);
    list.forEach(([x, z], i) => {
      const h = hash(z * 0.7, x * 1.1), r = 0.45 + 0.45 * h;
      // the same kind for a bed (8 m patch), some variety inside
      const v = hash(Math.floor(x / 8) + 0.5, Math.floor(z / 8) + 0.5) * 0.8 + hash(x * 2.1, z) * 0.2;
      p.set(x, ctx.heightAt(x, z) - 0.05, z); q.setFromAxisAngle(up, h * 6.28); sc.set(r, r * (0.75 + 0.15 * h), r);
      m4.compose(p, q, sc); im.setMatrixAt(i, m4); im.setColorAt(i, shrubColour(c, v, h));
    });
    im.computeBoundingSphere(); im.receiveShadow = true; im.userData.sanity = { kind: 'hedge' };   // no shadow pass: low, mostly under trees (~0.5 ms saved)
    ctx.scene.add(im);
  }
  return spots.length;
}

// ---------------------------------------------------------------- clipped hedges just outside the sidewalks of campus roads, only on lawns
export function buildHedges(ctx, roads, lcAt) {
  const spots = [], doors = ctx.doors || [];
  for (const r of roads) {
    const sw = r.sw ?? (r.w >= 7 ? 2.4 : 0);
    if (r.w < 6 || !sw) continue;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1], L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 6) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L, o = r.w / 2 + sw + 0.7;
      for (let t = 3; t < L - 3; t += 2.9) for (const s of [-1, 1]) {
        const x = x0 + dx * t - dz * o * s, z = z0 + dz * t + dx * o * s;
        const cl = lcAt(x, z);
        if (!((cl === 1 || cl === 2) && ctx.inCampus(x, z) && !ctx.onRoad?.(x, z, r, 1.5))) continue;
        // the 3 m hedge (both ends too) keeps off water, pitches, buildings and every other road or path it would
        // block, and leaves building entrances open (sanity.js)
        if (ctx.blockedBy && [-1.4, 0, 1.4].some((u) => ctx.blockedBy(x + dx * u, z + dz * u, { r: 0.45, road: false, path: 0, cover: 0.3 }))) continue;
        if (doors.some((d) => Math.hypot(d.x - x, d.z - z) < 6)) continue;
        spots.push([x, z, Math.atan2(dx, dz), hash(r.pts[0][0] * 0.13 + i * 7.1 + s, r.pts[0][1] * 0.17)]);   // variety per run
      }
    }
  }
  const geo = new THREE.BoxGeometry(0.9, 0.85, 3.0, 2, 2, 4).translate(0, 0.42, 0);
  const pos = geo.attributes.position, col = [];
  for (let i = 0; i < pos.count; i++) {            // clipped hedge: rounded top edges, slightly irregular
    let x = pos.getX(i), y = pos.getY(i);
    if (y > 0.8 && Math.abs(x) > 0.4) { x *= 0.82; y -= 0.07; }
    pos.setX(i, x * (1 + (hash(i, y) - 0.5) * 0.12)); pos.setY(i, y * (1 + (hash(y, i) - 0.5) * 0.08));
    const v = 0.62 + 0.5 * Math.min(1, y / 0.85); col.push(v, v, v);       // shaded base, sunlit top
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.computeVertexNormals();
  const im = new THREE.InstancedMesh(geo, leafyMaterial(), spots.length), c = new THREE.Color();
  spots.forEach(([x, z, a, v], i) => {
    p.set(x, ctx.heightAt(x, z), z); q.setFromAxisAngle(up, a); m4.compose(p, q, one); im.setMatrixAt(i, m4);
    im.setColorAt(i, shrubColour(c, v, hash(x, z)));
  });
  im.computeBoundingSphere(); im.castShadow = true; im.receiveShadow = true; im.userData.sanity = { kind: 'hedge' };
  ctx.scene.add(im);
  return spots.length;
}

// ---------------------------------------------------------------- street furniture: benches beside footpaths, litter bins on sidewalks
export function buildFurniture(ctx, roads, lcAt) {
  const benches = [], bins = [];
  const NONCAR = new Set(['footway', 'path', 'pedestrian', 'cycleway']);
  const ok = (x, z) => { const c = lcAt(x, z); return c !== 5 && c !== 10 && ctx.inCampus(x, z) && !ctx.onRoad?.(x, z, null, 0.8) && !(ctx.waterAt && ctx.waterAt(x, z) !== null); };
  for (const r of roads) {
    const path = NONCAR.has(r.kind), sw = r.sw ?? 0;
    if (!path && !(sw > 0)) continue;
    const step = path ? 34 : 46;
    let acc = step / 2, side = 1;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1], L = Math.hypot(x1 - x0, z1 - z0);
      if (L < 0.1) continue;
      const dx = (x1 - x0) / L, dz = (z1 - z0) / L;
      for (let t = acc; t < L; t += step) {
        const o = path ? r.w / 2 + 0.9 : r.w / 2 + sw - 0.45;
        const x = x0 + dx * t - dz * o * side, z = z0 + dz * t + dx * o * side;
        // benches (1.8 m) keep off other paths too; bins stand on their own sidewalk (sanity.js)
        const free = !ctx.blockedBy?.(x, z, path ? { r: 0.5, road: false, path: 0, self: r } : { r: 0.25, road: false });
        if (ok(x, z) && free) (path ? benches : bins).push([x, z, Math.atan2(side * dz, -side * dx)]);   // seat (+z) faces the path
        side = -side;
      }
      acc = (acc - L) % step; if (acc < 0) acc += step;
    }
  }
  const wood = new THREE.MeshStandardMaterial({ color: '#8a5a36', roughness: 0.8 }), metal = new THREE.MeshStandardMaterial({ color: '#3a3f44', roughness: 0.5, metalness: 0.6 });
  const seat = mergeGeometries([0, 1, 2].map((k) => new THREE.BoxGeometry(1.8, 0.04, 0.11).translate(0, 0.45, -0.15 + k * 0.15))
    .concat([0, 1].map((k) => new THREE.BoxGeometry(1.8, 0.1, 0.03).rotateX(-0.2).translate(0, 0.66 + k * 0.16, -0.27 - k * 0.03))));
  const legs = mergeGeometries([-0.75, 0.75].flatMap((u) => [new THREE.BoxGeometry(0.05, 0.45, 0.42).translate(u, 0.225, -0.05),
    new THREE.BoxGeometry(0.05, 0.42, 0.04).rotateX(-0.2).translate(u, 0.66, -0.3)]));
  const binBody = new THREE.CylinderGeometry(0.24, 0.21, 0.82, 12).translate(0, 0.41, 0);
  const binTop = new THREE.CylinderGeometry(0.26, 0.26, 0.08, 12).translate(0, 0.86, 0);
  const binMat = new THREE.MeshStandardMaterial({ color: '#2e6b4a', roughness: 0.6, metalness: 0.2 });
  const place = (geo, mat, list, kind) => {
    if (!list.length) return;
    const im = new THREE.InstancedMesh(geo, mat, list.length);
    list.forEach(([x, z, a], i) => { p.set(x, (ctx.topAt || ctx.heightAt)(x, z), z); q.setFromAxisAngle(up, a); m4.compose(p, q, one); im.setMatrixAt(i, m4); });
    im.computeBoundingSphere(); im.castShadow = true; im.receiveShadow = true; ctx.scene.add(im);
    if (kind) im.userData.sanity = { kind };
  };
  place(seat, wood, benches, 'bench'); place(legs, metal, benches); place(binBody, binMat, bins, 'bin'); place(binTop, metal, bins);
  return { benches: benches.length, bins: bins.length };
}
