// Sports facilities built to standard dimensions on the OSM / land-cover rectangles (campus.json "sports"):
// 400 m tracks with lanes, football pitches with goals, basketball / tennis / volleyball courts with hoops and nets, fences.
import * as THREE from 'three';
import { GeoBuf } from './world.js';

const white = new THREE.Color('#f4f4f0');
const LIFT = 0.16;

export function buildSports(ctx, sports) {
  if (!sports?.length) return;
  const { scene, heightAt } = ctx;
  const lines = new GeoBuf(), rubber = new GeoBuf(), posts = new GeoBuf(), fence = new GeoBuf();
  const grass = new GeoBuf(), turfA = new THREE.Color('#4f8f3c'), turfB = new THREE.Color('#5a9c45');
  const grassA = new THREE.Color('#6b8c46'), grassB = new THREE.Color('#71924b');
  const rubberC = new THREE.Color('#b9463a'), steel = new THREE.Color('#d9dcdf'), dark = new THREE.Color('#2b3138');

  for (const sp of sports) {
    const [cx, cz, L, Wd, a] = sp.obb;
    const ca = Math.cos(a), sa = Math.sin(a);
    // local (u along the long axis, v across) -> world
    const W2 = (u, v, y = LIFT) => { const x = cx + u * ca - v * sa, z = cz + u * sa + v * ca; return [x, heightAt(x, z) + y, z]; };
    const seg = (u0, v0, u1, v1, w = 0.1, buf = lines, col = white, y = LIFT) => {
      const du = u1 - u0, dv = v1 - v0, l = Math.hypot(du, dv) || 1, nu = -dv / l * w / 2, nv = du / l * w / 2;
      const A = W2(u0 + nu, v0 + nv, y), B = W2(u1 + nu, v1 + nv, y), C = W2(u1 - nu, v1 - nv, y), D = W2(u0 - nu, v0 - nv, y);
      buf.triFace(A, B, C, col, () => [0, 0]); buf.triFace(A, C, D, col, () => [0, 0]);
    };
    const poly = (pts, w = 0.1, closed = false) => { for (let i = 0; i < pts.length - (closed ? 0 : 1); i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; seg(p[0], p[1], q[0], q[1], w); } };
    const rect = (u0, v0, u1, v1, w = 0.1) => poly([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], w, true);
    const arc = (cu, cv, r, a0, a1, n = 24) => { const pts = []; for (let i = 0; i <= n; i++) { const t = a0 + (a1 - a0) * i / n; pts.push([cu + Math.cos(t) * r, cv + Math.sin(t) * r]); } return pts; };
    const box = (u, v, y0, su, sy, sv, col) => {
      const [x, , z] = W2(u, v, 0);
      posts.box(x, z, heightAt(x, z) + y0, su, sy, sv, a, col);
    };
    // artificial turf with mowing stripes, slightly larger than the pitch
    const turf = (l, w, natural = false) => {
      const n = Math.round((l + 8) / 6), su = (l + 8) / n;
      for (let k = 0; k < n; k++) {
        const u0 = -l / 2 - 4 + k * su, u1 = u0 + su, col = natural ? (k % 2 ? grassA : grassB) : k % 2 ? turfA : turfB;
        const A = W2(u0, -w / 2 - 4, LIFT - 0.04), B = W2(u1, -w / 2 - 4, LIFT - 0.04), C = W2(u1, w / 2 + 4, LIFT - 0.04), D = W2(u0, w / 2 + 4, LIFT - 0.04);
        grass.triFace(A, B, C, col, () => [0, 0]); grass.triFace(A, C, D, col, () => [0, 0]);
      }
    };
    const fenceRect = (hu, hv, h = 3) => {
      const corners = [[-hu, -hv], [hu, -hv], [hu, hv], [-hu, hv]];
      for (let i = 0; i < 4; i++) {
        const [u0, v0] = corners[i], [u1, v1] = corners[(i + 1) % 4];
        const A = W2(u0, v0, 0), B = W2(u1, v1, 0);
        const dx = B[0] - A[0], dz = B[2] - A[2], l = Math.hypot(dx, dz) || 1;
        fence.wall(A[0], A[2], B[0], B[2], Math.min(A[1], B[1]), Math.min(A[1], B[1]) + h, dz / l, -dx / l, 0, l / 2, 0, h / 2, dark);
        for (let t = 0; t <= l; t += 3) box(u0 + (u1 - u0) * t / l, v0 + (v1 - v0) * t / l, 0, 0.08, h, 0.08, dark);
      }
    };

    if (sp.kind === 'oval') {
      // IAAF 400 m: 84.39 m straights, 36.5 m inner radius, 8 lanes x 1.22 m
      const S = 84.39, R0 = 36.5, LW = 1.22, N = 8;
      const stadium = (r, n = 40) => [[-S / 2, -r], ...arc(S / 2, 0, r, -Math.PI / 2, Math.PI / 2, n), ...arc(-S / 2, 0, r, Math.PI / 2, Math.PI * 1.5, n)];
      const inner = stadium(R0 - 0.3), outer = stadium(R0 + N * LW + 0.6);
      for (let i = 0; i < inner.length; i++) {
        const j = (i + 1) % inner.length;
        const A = W2(...inner[i], LIFT - 0.02), B = W2(...outer[i], LIFT - 0.02), C = W2(...outer[j], LIFT - 0.02), D = W2(...inner[j], LIFT - 0.02);
        rubber.triFace(A, B, C, rubberC, () => [0, 0]); rubber.triFace(A, C, D, rubberC, () => [0, 0]);
      }
      for (let k = 0; k <= N; k++) poly(stadium(R0 + k * LW), 0.05, true);
      // D-zones (the curved ends inside the track) are red rubber with field-event areas (official map + school
      // photos): two grass throwing sectors in one D (中苑: south end, 西苑/东苑: north end), long-jump sand pits
      {
        const nat = /中苑/.test(sp.name || ''), C0 = W2(0, 0, LIFT - 0.06);
        for (let i = 0; i < inner.length; i++) {
          const j = (i + 1) % inner.length;
          rubber.triFace(C0, W2(...inner[i], LIFT - 0.06), W2(...inner[j], LIFT - 0.06), rubberC, () => [0, 0]);
        }
        if (!sp.has_pitch) {   // grass rectangle for the pitch
          const A = W2(-53, -35, LIFT - 0.045), B = W2(53, -35, LIFT - 0.045), C = W2(53, 35, LIFT - 0.045), D = W2(-53, 35, LIFT - 0.045);
          grass.triFace(A, B, C, nat ? grassA : turfA, () => [0, 0]); grass.triFace(A, C, D, nat ? grassA : turfA, () => [0, 0]);
        }
        // which end holds the throwing sectors: 中苑 south, the others north (z smaller)
        const zEnd = (sgn) => cz + sgn * (S / 2 + 18) * sa;
        const end = nat ? (zEnd(1) > zEnd(-1) ? 1 : -1) : (zEnd(1) < zEnd(-1) ? 1 : -1);
        for (const side of [-1, 1]) {
          const tip = [end * (S / 2 + 2), side * 6], r = 26;
          const dirU = end, dirV = side * 0.75, Ln = Math.hypot(dirU, dirV), du = dirU / Ln, dv = dirV / Ln;
          const pu = -dv, pv = du, half = Math.tan(0.30) * r;
          const Q0 = W2(tip[0], tip[1], LIFT - 0.03), Q1 = W2(tip[0] + du * r + pu * half, tip[1] + dv * r + pv * half, LIFT - 0.03), Q2 = W2(tip[0] + du * r - pu * half, tip[1] + dv * r - pv * half, LIFT - 0.03);
          grass.triFace(Q0, Q1, Q2, nat ? grassA : turfA, () => [0, 0]);
        }
        // long-jump sand pits just outside the far straight, near both ends
        const sand = new THREE.Color('#d8c39a');
        for (const u of [-S / 2 + 12, S / 2 - 12]) {
          const v0 = R0 + N * LW + 1.5, A = W2(u - 4.5, v0, LIFT - 0.01), B = W2(u + 4.5, v0, LIFT - 0.01), C = W2(u + 4.5, v0 + 3, LIFT - 0.01), D = W2(u - 4.5, v0 + 3, LIFT - 0.01);
          rubber.triFace(A, B, C, sand, () => [0, 0]); rubber.triFace(A, C, D, sand, () => [0, 0]);
        }
      }
      seg(0, R0, 0, R0 + N * LW, 0.1);                         // finish line across the home straight
      if (!sp.has_pitch) {     // infield: football pitch (中苑 is natural grass — brown in the winter aerial, a marked pitch on the official map)
        turf(100, 64, /中苑/.test(sp.name || ''));
        footballLines(seg, poly, rect, arc, 100, 64);
        goals(box, 100);
      }
    } else if (sp.kind === 'soccer') {
      const l = Math.min(L - 2, 105), w = Math.min(Wd - 2, 68);
      turf(l, w);
      footballLines(seg, poly, rect, arc, l, w);
      goals(box, l);
    } else if (sp.kind === 'track') {
      const n = Math.max(1, Math.floor(Wd / 1.22));
      for (let k = 0; k <= n; k++) seg(-L / 2 + 1, -n * 0.61 + k * 1.22, L / 2 - 1, -n * 0.61 + k * 1.22, 0.05);
    } else if (sp.kind === 'basketball' || sp.kind === 'tennis' || sp.kind === 'volleyball') {
      const cell = sp.kind === 'basketball' ? [31, 18] : sp.kind === 'tennis' ? [36.6, 18.3] : [24, 15];
      const nL = Math.max(1, Math.round(L / cell[0])), nW = Math.max(1, Math.round(Wd / cell[1]));
      const cu = L / nL, cv = Wd / nW;
      for (let i = 0; i < nL; i++) for (let j = 0; j < nW; j++) {
        const ou = -L / 2 + cu * (i + 0.5), ov = -Wd / 2 + cv * (j + 0.5);
        const S2 = (u0, v0, u1, v1, w = 0.05) => seg(ou + u0, ov + v0, ou + u1, ov + v1, w);
        const R2 = (u0, v0, u1, v1) => { S2(u0, v0, u1, v0); S2(u1, v0, u1, v1); S2(u1, v1, u0, v1); S2(u0, v1, u0, v0); };
        if (sp.kind === 'basketball') {
          const hl = 14, hw = 7.5;
          R2(-hl, -hw, hl, hw); S2(0, -hw, 0, hw);
          poly(arc(ou, ov, 1.8, 0, Math.PI * 2, 24).map(([u, v]) => [u, v]), 0.05, true);
          for (const s of [-1, 1]) {
            const bu = s * (hl - 1.575);
            R2(s * hl, -2.45, s * (hl - 5.8), 2.45);
            S2(s * hl, -6.6, s * (hl - 2.99), -6.6); S2(s * hl, 6.6, s * (hl - 2.99), 6.6);
            const a3 = Math.acos(6.6 / 6.75);
            poly(arc(ou + bu, ov, 6.75, s > 0 ? Math.PI / 2 + a3 : -Math.PI / 2 + a3, s > 0 ? Math.PI * 1.5 - a3 : Math.PI / 2 - a3, 30), 0.05);
            box(ou + s * (hl + 1.0), ov, 0, 0.18, 3.0, 0.18, steel);                       // pole
            box(ou + s * (hl - 1.2), ov, 2.9, 0.05, 1.05, 1.8, white);                      // backboard
            box(ou + s * (hl - 0.2), ov, 2.95, 1.2, 0.12, 0.12, steel);                     // arm
            box(ou + s * (hl - 1.5), ov, 3.05, 0.45, 0.03, 0.45, new THREE.Color('#e2622b')); // rim
          }
        } else if (sp.kind === 'tennis') {
          R2(-11.885, -5.485, 11.885, 5.485);
          S2(-11.885, -4.115, 11.885, -4.115); S2(-11.885, 4.115, 11.885, 4.115);
          S2(-6.4, -4.115, -6.4, 4.115); S2(6.4, -4.115, 6.4, 4.115); S2(-6.4, 0, 6.4, 0);
          netAcross(box, ou, ov, 6.4, 0.914);
        } else {
          R2(-9, -4.5, 9, 4.5); S2(0, -4.5, 0, 4.5); S2(-3, -4.5, -3, 4.5); S2(3, -4.5, 3, 4.5);
          netAcross(box, ou, ov, 5.2, 2.43);
        }
      }
      fenceRect(L / 2, Wd / 2, sp.kind === 'basketball' ? 3.5 : 4);
    }
  }
  const add = (buf, mat, shadow = false) => { if (buf.empty()) return; const m = new THREE.Mesh(buf.geometry(), mat); m.receiveShadow = true; m.castShadow = shadow; scene.add(m); };
  add(grass, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }));   // grass over the red D fill
  add(rubber, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }));
  add(lines, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }));
  add(posts, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.3 }), true);
  add(fence, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false }));
}

function footballLines(seg, poly, rect, arc, l, w) {
  const hl = l / 2, hw = w / 2;
  rect(-hl, -hw, hl, hw, 0.12); seg(0, -hw, 0, hw, 0.12);
  poly(arc(0, 0, 9.15, 0, Math.PI * 2, 40), 0.12, true);
  for (const s of [-1, 1]) {
    rect(s * hl, -20.16, s * (hl - 16.5), 20.16, 0.12);
    rect(s * hl, -9.16, s * (hl - 5.5), 9.16, 0.12);
    const cu = s * (hl - 11), a0 = Math.acos(5.5 / 9.15);
    poly(arc(cu, 0, 9.15, s > 0 ? Math.PI - a0 : -a0, s > 0 ? Math.PI + a0 : a0, 16), 0.12);
  }
}

function goals(box, l) {
  const post = new THREE.Color('#ffffff');
  for (const s of [-1, 1]) {
    const u = s * (l / 2);
    box(u, -3.66, 0, 0.12, 2.44, 0.12, post); box(u, 3.66, 0, 0.12, 2.44, 0.12, post);
    box(u, 0, 2.38, 0.12, 0.12, 7.44, post);
    box(u + s * 1.0, 0, 0.0, 0.05, 1.6, 7.3, new THREE.Color('#dfe3e6'));   // back net (thin panel)
  }
}

function netAcross(box, ou, ov, half, h) {
  const c = new THREE.Color('#2a2d31');
  box(ou, ov - half, 0, 0.1, h + 0.1, 0.1, c); box(ou, ov + half, 0, 0.1, h + 0.1, 0.1, c);
  box(ou, ov, h - 0.9, 0.03, 0.9, half * 2, new THREE.Color('#3a3f45'));
}
