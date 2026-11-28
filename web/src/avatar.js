// 玩家角色：低多边形的“粗糙但有游戏感”小人，男生 / 女生两套，带走、跑、跳、骑车动作。
// 前方是 -z，脚底在 y = 0。只用方块和低面数球体 + flatShading，不依赖外部模型。
import * as THREE from 'three';

export const AVATARS = {
  boy: { name: '男生', skin: '#f1c39b', hair: '#1d1714', top: '#2f6fdb', top2: '#ffffff', bottom: '#2b3440', leg: '#2b3440', shoe: '#f2f2f2', bag: '#c2440e', long: false },
  girl: { name: '女生', skin: '#f6cdb0', hair: '#2b1a14', top: '#ee7d9c', top2: '#ffffff', bottom: '#2f3c63', leg: '#3a3845', shoe: '#ffffff', bag: '#f2c94c', long: true },
};
const KEY = 'nuist-avatar-v1';
export const savedAvatar = () => { try { const k = localStorage.getItem(KEY); return AVATARS[k] ? k : 'boy'; } catch { return 'boy'; } };
const remember = (k) => { try { localStorage.setItem(KEY, k); } catch { /* private mode */ } };

const box = (w, h, d, mat, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); return m; };

export function createAvatar(kind = savedAvatar()) {
  const root = new THREE.Group();
  let J = null, cur = kind;
  const pose = { lt: 0, rt: 0, lk: 0, rk: 0, la: 0, ra: 0, lz: 0, rz: 0, y: 0, lean: 0 };
  let phase = 0, lx = 0, lz = 0, v = 0, inited = false;

  function build(k) {
    root.clear();
    const c = AVATARS[k], M = (col) => new THREE.MeshStandardMaterial({ color: col, roughness: 0.85, flatShading: true });
    const skin = M(c.skin), hair = M(c.hair), top = M(c.top), top2 = M(c.top2), bottom = M(c.bottom), leg = M(c.leg), shoe = M(c.shoe), bag = M(c.bag), eye = M('#15110f');
    const hips = new THREE.Group(); hips.position.y = 0.9; root.add(hips);
    hips.add(box(0.36, 0.16, 0.22, bottom, 0, 0.02, 0));
    if (c.long) {   // pleated skirt: an 8-sided frustum
      const sk = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.31, 0.32, 8), bottom); sk.position.y = -0.1; hips.add(sk);
    }
    const legs = [-1, 1].map((s) => {
      const thigh = new THREE.Group(); thigh.position.set(s * 0.1, 0, 0); hips.add(thigh);
      thigh.add(box(0.15, 0.44, 0.17, c.long ? leg : bottom, 0, -0.22, 0));
      const knee = new THREE.Group(); knee.position.y = -0.44; thigh.add(knee);
      knee.add(box(0.14, 0.4, 0.16, c.long ? leg : bottom, 0, -0.2, 0));
      knee.add(box(0.16, 0.09, 0.27, shoe, 0, -0.42, -0.05));
      return { thigh, knee };
    });
    const torso = new THREE.Group(); torso.position.y = 0.08; hips.add(torso);
    const tw = c.long ? 0.4 : 0.46;
    torso.add(box(tw, 0.5, 0.26, top, 0, 0.25, 0));
    torso.add(box(tw * 0.55, 0.16, 0.02, top2, 0, 0.36, -0.135));   // chest print, reads as “T 恤 / 卫衣”
    torso.add(box(0.36, 0.42, 0.15, bag, 0, 0.26, 0.2));             // backpack
    torso.add(box(0.11, 0.08, 0.1, skin, 0, 0.54, 0));               // neck
    const arms = [-1, 1].map((s) => {
      const sh = new THREE.Group(); sh.position.set(s * (tw / 2 + 0.07), 0.46, 0); torso.add(sh);
      sh.add(box(0.12, 0.5, 0.13, top, 0, -0.24, 0));
      sh.add(box(0.1, 0.11, 0.11, skin, 0, -0.54, 0));
      return sh;
    });
    const head = new THREE.Group(); head.position.y = 0.58; torso.add(head);
    // face: smooth-shaded and slightly self-lit, so the low-poly facets don't read as stubble in shade
    const face = new THREE.MeshStandardMaterial({ color: c.skin, roughness: 0.8, emissive: c.skin, emissiveIntensity: 0.12 });
    const skull = new THREE.Mesh(new THREE.IcosahedronGeometry(0.19, 2), face); skull.scale.set(1, 1.08, 0.98); skull.position.y = 0.18; head.add(skull);
    for (const s of [-1, 1]) head.add(box(0.04, 0.055, 0.02, eye, s * 0.068, 0.2, -0.178));
    head.add(box(0.06, 0.018, 0.02, M('#b5524a'), 0, 0.11, -0.176));   // mouth
    head.add(box(0.41, 0.13, 0.41, hair, 0, 0.34, 0.01));              // hair cap
    head.add(box(0.41, 0.09, 0.06, hair, 0, 0.28, -0.18));             // fringe
    head.add(box(0.41, 0.24, 0.1, hair, 0, 0.22, 0.16));               // back of the head
    for (const s of [-1, 1]) head.add(box(0.05, 0.16, 0.3, hair, s * 0.19, 0.24, 0.02));
    if (c.long) {
      head.add(box(0.38, 0.46, 0.1, hair, 0, 0.02, 0.18));             // long hair down the back
      const tail = box(0.12, 0.3, 0.12, hair, 0, 0.18, 0.3); tail.rotation.x = 0.5; head.add(tail);
      head.add(box(0.1, 0.06, 0.06, M('#e84a6a'), 0, 0.33, 0.24));     // hair tie
    }
    root.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = false; } });   // no self-shadow: hair shadows read as a beard
    J = { hips, legs, arms, torso, head };
  }
  build(cur);

  // P: the player state from main.js (pos, ride, onGround, fly)
  function update(dt, P) {
    const raw = Math.hypot(P.pos.x - lx, P.pos.z - lz) / Math.max(dt, 1e-3);
    if (!inited) { inited = true; lx = P.pos.x; lz = P.pos.z; }
    lx = P.pos.x; lz = P.pos.z;
    v += (Math.min(raw, 30) - v) * Math.min(1, dt * 8);
    const riding = P.ride === 'bike' || P.ride === 'ebike';
    const t = { lt: 0, rt: 0, lk: 0, rk: 0, la: 0, ra: 0, lz: 0.06, rz: -0.06, y: 0, lean: 0 };
    if (riding) {
      phase += dt * (P.ride === 'bike' ? Math.min(v, 12) * 0.9 : 0);
      const pd = P.ride === 'bike' ? Math.sin(phase) * 0.35 : 0;
      Object.assign(t, { lt: 1.35 + pd, rt: 1.35 - pd, lk: -1.25 - pd * 0.6, rk: -1.25 + pd * 0.6, la: 1.05, ra: 1.05, lz: 0.12, rz: -0.12, y: -0.33, lean: 0.22 });
    } else if (!P.onGround && !P.fly) {
      Object.assign(t, { lt: 0.6, rt: -0.25, lk: -0.9, rk: -0.3, la: -0.4, ra: 0.5, lz: 0.5, rz: -0.5 });
    } else if (v > 0.4) {
      const run = v > 6, a = Math.min(1, v / 4.5) * (run ? 0.95 : 0.6);
      phase += dt * (run ? 11 : 1.7 * v + 1.5);
      const s = Math.sin(phase);
      Object.assign(t, { lt: s * a, rt: -s * a, lk: -Math.max(0, -s) * a * 1.4, rk: -Math.max(0, s) * a * 1.4,
        la: -s * a * 0.9, ra: s * a * 0.9, y: Math.abs(Math.cos(phase)) * 0.04 * a, lean: run ? 0.18 : 0.05 });
    } else {
      phase += dt * 1.6;
      t.la = Math.sin(phase) * 0.03; t.ra = -t.la;
    }
    const k = Math.min(1, dt * 14);
    for (const key of Object.keys(pose)) pose[key] += (t[key] - pose[key]) * k;
    const [L, R] = J.legs, [AL, AR] = J.arms;
    L.thigh.rotation.x = pose.lt; R.thigh.rotation.x = pose.rt; L.knee.rotation.x = pose.lk; R.knee.rotation.x = pose.rk;
    AL.rotation.x = pose.la; AR.rotation.x = pose.ra; AL.rotation.z = -pose.lz; AR.rotation.z = -pose.rz;
    J.hips.position.y = 0.9 + pose.y; J.torso.rotation.x = -pose.lean;
    J.head.rotation.x = pose.lean * 0.6;
  }

  return {
    root, update,
    get kind() { return cur; },
    setKind(k) { if (!AVATARS[k] || k === cur) return; cur = k; remember(k); build(k); },
  };
}
