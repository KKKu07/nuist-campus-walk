// Campus shuttle bus (rideable, runs a loop with stops) and 7ma shared e-bikes (blue, rideable).
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { busSideTexture, busFrontTexture } from './textures.js';

// ---------------------------------------------------------------- bus
export function createBus(ctx, data) {
  const { scene, heightAt } = ctx;
  const route = data.route, n = route.length;
  const cum = new Float64Array(n);
  for (let i = 1; i < n; i++) cum[i] = cum[i - 1] + Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]);
  const len = cum[n - 1] + Math.hypot(route[0][0] - route[n - 1][0], route[0][1] - route[n - 1][1]);

  function at(s) {
    s = ((s % len) + len) % len;
    let lo = 0, hi = n - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (cum[mid] <= s) lo = mid; else hi = mid - 1; }
    const a = route[lo], b = route[(lo + 1) % n], segL = (lo + 1 < n ? cum[lo + 1] : len) - cum[lo] || 1;
    const t = (s - cum[lo]) / segL;
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  }

  // model: forward is -z
  const side = busSideTexture(), sideFlip = side.clone();
  sideFlip.repeat.x = -1; sideFlip.offset.x = 1; sideFlip.needsUpdate = true;
  const white = new THREE.MeshStandardMaterial({ color: '#f5f6f6', roughness: 0.45 });
  const blue = new THREE.MeshStandardMaterial({ color: '#1e6fc4', roughness: 0.45 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(2.15, 2.35, 6.2), [
    new THREE.MeshStandardMaterial({ map: sideFlip, roughness: 0.4 }), new THREE.MeshStandardMaterial({ map: side, roughness: 0.4 }),
    blue, new THREE.MeshStandardMaterial({ color: '#2b2f33' }), white, new THREE.MeshStandardMaterial({ map: busFrontTexture(), roughness: 0.35 })]);
  body.position.y = 1.55;
  const ac = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.35, 1.8), white); ac.position.set(0, 2.9, 0.6);
  const wheelGeo = new THREE.CylinderGeometry(0.4, 0.4, 0.28, 16).rotateZ(Math.PI / 2);
  const wheelMat = new THREE.MeshStandardMaterial({ color: '#1b1d1f', roughness: 0.8 });
  const g = new THREE.Group();
  g.add(body, ac);
  for (const [x, z] of [[-1.0, -2.1], [1.0, -2.1], [-1.0, 2.1], [1.0, 2.1]]) { const w = new THREE.Mesh(wheelGeo, wheelMat); w.position.set(x, 0.4, z); g.add(w); }
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  scene.add(g);

  // stop signs
  const signGeo = mergeGeometries([new THREE.CylinderGeometry(0.06, 0.06, 2.6, 6).translate(0, 1.3, 0), new THREE.BoxGeometry(0.06, 0.7, 1.1).translate(0, 2.7, 0)]);
  const signMat = new THREE.MeshStandardMaterial({ color: '#1e6fc4', roughness: 0.5 });
  for (const st of data.stops) {
    const [x, z] = at(st.s), [x2, z2] = at(st.s + 3);
    const dx = x2 - x, dz = z2 - z, l = Math.hypot(dx, dz) || 1;
    let sx = x + (-dz / l) * -4.5, sz = z + (dx / l) * -4.5;   // right-hand side of travel
    // wide roads: step out until the sign stands off the carriageway, on the sidewalk / verge (sanity.js)
    for (let k = 0; k < 14 && ctx.onRoad?.(sx, sz, null, 0.5); k++) { sx += (dz / l) * 0.5; sz -= (dx / l) * 0.5; }
    const sign = new THREE.Mesh(signGeo, signMat); sign.position.set(sx, (ctx.topAt || heightAt)(sx, sz), sz); sign.castShadow = true; sign.userData.sanity = { kind: 'busstop' }; scene.add(sign);
    st.sign = sign; st.x = sx; st.z = sz; st.ax = -dz / l; st.az = dx / l;   // (ax, az): from the stop sign towards the road
  }

  const bus = { group: g, s: data.stops[0]?.s || 0, v: 0, wait: 4, next: 1 % data.stops.length, heading: 0, stops: data.stops, len,
    justArrived: null, x: 0, z: 0 };
  bus.nextStop = () => bus.stops[bus.next]?.name || '';
  bus.update = (dt) => {
    bus.justArrived = null;
    if (bus.wait > 0) { bus.wait -= dt; bus.v = 0; }
    else {
      let target = bus.stops[bus.next].s;
      while (target < bus.s - 0.01) target += len;
      const dist = target - bus.s;
      const want = Math.min(8.5, Math.sqrt(2 * 1.4 * Math.max(dist, 0)) + 0.6);
      bus.v += Math.max(-3, Math.min(1.4, (want - bus.v) / Math.max(dt, 1e-3))) * dt;
      bus.s += Math.min(bus.v * dt, dist);
      if (dist - bus.v * dt <= 0.05) {
        bus.s = target % len; bus.v = 0; bus.wait = 7;
        bus.justArrived = bus.stops[bus.next].name;
        bus.next = (bus.next + 1) % bus.stops.length;
      }
    }
    const [x, z] = at(bus.s), [xa, za] = at(bus.s + 2.5), [xb, zb] = at(bus.s - 2.5);
    const dx = xa - xb, dz = za - zb;
    if (dx * dx + dz * dz > 0.01) {
      const want = Math.atan2(-dx, -dz);
      let d = want - bus.heading; d = Math.atan2(Math.sin(d), Math.cos(d));
      bus.heading += d * Math.min(1, dt * 3);
    }
    bus.x = x; bus.z = z;
    g.position.set(x, (ctx.topAt || ctx.surfaceAt || heightAt)(x, z), z);   // wheels on the road surface, not sunk into it
    g.rotation.y = bus.heading;
  };
  bus.update(0);
  return bus;
}

// ---------------------------------------------------------------- 7ma shared e-bikes
// A Blender GLB (models/ebike_7ma.glb, front -z, origin on the ground) replaces the box model when present:
// its meshes are merged per material so the 70+ parked bikes stay a handful of instanced draw calls.
let GLB = null;
export function setEbikeGLB(root) {
  root.updateMatrixWorld(true);
  const byMat = new Map();
  root.traverse((o) => {
    if (!o.isMesh) return;
    const g = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
    g.applyMatrix4(o.matrixWorld);
    for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k);
    if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    const m = Array.isArray(o.material) ? o.material[0] : o.material;
    if (!byMat.has(m)) byMat.set(m, []);
    byMat.get(m).push(g);
  });
  const parts = {}, mats = {};
  let i = 0;
  for (const [m, gs] of byMat) { const k = 'm' + i++; parts[k] = mergeGeometries(gs); mats[k] = m; }
  if (i) GLB = { parts, mats };
}
function ebikeParts() {
  if (GLB) return GLB.parts;
  const blue = mergeGeometries([
    new THREE.BoxGeometry(0.36, 0.42, 1.25).translate(0, 0.55, 0.02),
    new THREE.BoxGeometry(0.3, 0.5, 0.18).translate(0, 0.75, -0.55),
    new THREE.BoxGeometry(0.38, 0.12, 0.5).translate(0, 0.42, 0.55),
  ]);
  const dark = mergeGeometries([
    new THREE.BoxGeometry(0.3, 0.1, 0.48).translate(0, 0.84, 0.28),
    new THREE.BoxGeometry(0.62, 0.05, 0.05).translate(0, 1.08, -0.6),
    new THREE.BoxGeometry(0.06, 0.4, 0.06).translate(0, 0.9, -0.6),
    new THREE.TorusGeometry(0.26, 0.07, 8, 18).rotateY(Math.PI / 2).translate(0, 0.3, -0.6),
    new THREE.TorusGeometry(0.26, 0.07, 8, 18).rotateY(Math.PI / 2).translate(0, 0.3, 0.62),
  ]);
  const basket = new THREE.BoxGeometry(0.4, 0.24, 0.3).translate(0, 0.92, -0.82);
  return { blue, dark, basket };
}
const EBIKE_MATS = () => GLB ? GLB.mats : ({
  blue: new THREE.MeshStandardMaterial({ color: '#1677e5', roughness: 0.45 }),
  dark: new THREE.MeshStandardMaterial({ color: '#202326', roughness: 0.7 }),
  basket: new THREE.MeshStandardMaterial({ color: '#e9eef3', roughness: 0.6 }),
});

export function createEbikes(ctx, spots) {
  const { scene, heightAt } = ctx;
  const parts = ebikeParts(), mats = EBIKE_MATS();
  const meshes = Object.keys(parts).map((k) => new THREE.InstancedMesh(parts[k], mats[k], spots.length));
  // a station (row of bikes < 2 m apart) that stands inside a building / model, in water or on a carriageway moves
  // as a whole to the nearest spot where every bike is clear; spots are updated in place so the phone's 停车点
  // clusters follow (sanity.js)
  if (ctx.blockedBy) {
    // bike centre >= 1 m off a carriageway edge (a 1.8 m bike parked across the kerb must not reach into the lane);
    // cover: not on a model's plaza / island
    const opt = { r: 0.5, road: 0.5, sport: false, cover: 0.3 }, groups = [];
    spots.forEach((s, i) => {
      if (!i || Math.hypot(s[0] - spots[i - 1][0], s[1] - spots[i - 1][1]) > 2) groups.push([]);
      groups[groups.length - 1].push(s);
    });
    for (const grp of groups) {
      if (!grp.some((s) => ctx.blockedBy(s[0], s[1], opt))) continue;
      // up to 24 m: the 中苑美食城 row sits between the rebuilt GLB and the road, the first clear spot is 18 m away
      search: for (let rr = 1; rr <= 24; rr++) for (let k = 0; k < 16; k++) {
        const ox = Math.cos(k * Math.PI / 8) * rr, oz = Math.sin(k * Math.PI / 8) * rr;
        if (grp.every((s) => !ctx.blockedBy(s[0] + ox, s[1] + oz, opt))) { for (const s of grp) { s[0] += ox; s[1] += oz; } break search; }
      }
    }
  }
  const list = spots.map(([x, z, a]) => ({ x, z, a, used: false }));
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), p = new THREE.Vector3(), one = new THREE.Vector3(1, 1, 1), zero = new THREE.Vector3(0, 0, 0);
  const write = (i) => {
    const b = list[i];
    // surfaceAt: a bike returned on a bridge sits on the deck, not on the riverbed below
    p.set(b.x, (ctx.topAt || ctx.surfaceAt || heightAt)(b.x, b.z), b.z); q.setFromAxisAngle(up, b.a); m4.compose(p, q, b.used ? zero : one);
    for (const m of meshes) { m.setMatrixAt(i, m4); m.instanceMatrix.needsUpdate = true; }
  };
  list.forEach((_, i) => write(i));
  for (const m of meshes) { m.castShadow = true; m.receiveShadow = true; m.computeBoundingSphere(); scene.add(m); }
  meshes[0].userData.sanity = { kind: 'ebike' };
  return {
    list,
    nearest(x, z, maxD = 3) {
      let best = -1, bd = maxD;
      list.forEach((b, i) => { if (!b.used) { const d = Math.hypot(b.x - x, b.z - z); if (d < bd) { bd = d; best = i; } } });
      return best;
    },
    take(i) { list[i].used = true; write(i); },
    park(i, x, z, a) { Object.assign(list[i], { x, z, a, used: false }); write(i); for (const m of meshes) m.computeBoundingSphere(); },
  };
}

// the e-bike the avatar sits on while riding
export function ebikeModel() {
  const parts = ebikeParts(), mats = EBIKE_MATS(), g = new THREE.Group();
  for (const k of Object.keys(parts)) { const m = new THREE.Mesh(parts[k], mats[k]); m.castShadow = true; g.add(m); }
  return g;
}
