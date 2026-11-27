// Grade-separated crossings (data/manual/underpasses.json via campus.json "underpasses"): a campus road sinks into a
// walled cut and passes under a public road, which stays at grade (tunnel) or rises onto a bridge deck.
//   cutAt(x, z)        lowered surface inside a cut (null elsewhere): wraps the game's heightAt
//   upperAt(r, x, z)   surface of the crossing public road over / near the cut (null elsewhere): used by buildRoads
//   segments           cut centre-line pieces [ax, az, bx, bz, half] for the ground shader (terrain not drawn there)
//   corridors          plan polygons of the cuts (air wall: the only links between the campus parts)
//   build(ctx)         walls, railings, floor, deck slab / tunnel roof, banner, canopies; returns a collision grid
import * as THREE from 'three';
import { GeoBuf } from './world.js';

function project(x, z, prof) {          // nearest point on the profile polyline: distance, interpolated y, along-position
  let best = null, acc = 0;
  for (let i = 0; i < prof.length - 1; i++) {
    const [ax, az, ay] = prof[i], [bx, bz, by] = prof[i + 1];
    const ex = bx - ax, ez = bz - az, L = Math.hypot(ex, ez) || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / (L * L)));
    const d = Math.hypot(ax + ex * t - x, az + ez * t - z);
    if (!best || d < best.d) best = { d, y: ay + (by - ay) * t, s: acc + t * L, t, i, nx: -ez / L, nz: ex / L, qx: ax + ex * t, qz: az + ez * t };
    acc += L;
  }
  return best;
}


// both faces of a vertical quad a-b, each with the normal its winding implies
function wall2(buf, ax, az, bx, bz, y0, y1, col) {
  const dx = bx - ax, dz = bz - az, l = Math.hypot(dx, dz) || 1;
  buf.wall(ax, az, bx, bz, y0, y1, dz / l, -dx / l, 0, 0, 0, 0, col);
  buf.wall(bx, bz, ax, az, y0, y1, -dz / l, dx / l, 0, 0, 0, 0, col);
}

export function makeUnderpasses(list, terrainAt) {
  const ups = (list || []).filter((u) => u.profile?.length >= 2).map((u) => {
    const prof = u.profile.map(([x, z, y]) => [x, z, y ?? terrainAt(x, z)]);
    // along-position where the cut floor starts (the lowest profile point first reached from the start)
    let acc = 0, sLow = 0, low = Infinity;
    for (let i = 0; i < prof.length; i++) {
      if (i) acc += Math.hypot(prof[i][0] - prof[i - 1][0], prof[i][1] - prof[i - 1][1]);
      if (prof[i][2] < low - 1e-6) { low = prof[i][2]; sLow = acc; }
    }
    // cover = the two tunnel mouths [[x, z], [x, z]]: roofed between them, ground carried over the top
    const cov = u.cover?.length === 2 ? u.cover.map(([x, z]) => project(x, z, prof).s).sort((a, b) => a - b) : null;
    return { ...u, prof, sLow, floorY: low, cov, upper: new Set((u.upper || []).map(String)) };
  });
  const inCov = (u, s) => !!u.cov && s >= u.cov[0] && s <= u.cov[1];
  // centre-line point, floor level and unit direction at along-position s
  const alongAt = (P, s) => {
    let acc = 0;
    for (let i = 0; i < P.length - 1; i++) {
      const L = Math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]);
      if (s <= acc + L || i === P.length - 2) {
        const f = Math.max(0, Math.min(1, (s - acc) / L));
        return [P[i][0] + (P[i + 1][0] - P[i][0]) * f, P[i][1] + (P[i + 1][1] - P[i][1]) * f, P[i][2] + (P[i + 1][2] - P[i][2]) * f, (P[i + 1][0] - P[i][0]) / L, (P[i + 1][1] - P[i][1]) / L];
      }
      acc += L;
    }
    return null;
  };
  // wide stairs either side of the ramp (正气路桥洞): from the floor at the bottom of the ramp up to the ground at the
  // cut's outer edge, `slope` rise per metre, 0.16 m risers; flat landing once the ground is reached
  const stairY = (u, p, x, z) => {
    const st = u.stairs, roadY = p.y;
    if (!st || p.d <= st.road || p.s >= u.sLow) return roadY;
    const side = (x - p.qx) * p.nx + (z - p.qz) * p.nz >= 0 ? 1 : -1;
    const g = terrainAt(p.qx + p.nx * u.half * side, p.qz + p.nz * u.half * side);   // ground at the cut's outer edge
    const h = Math.min(g, u.floorY + (u.sLow - p.s) * (st.slope || 0.45));
    return Math.max(roadY, u.floorY + 0.16 * Math.floor((h - u.floorY) / 0.16));
  };
  const cutAt = (x, z) => {
    for (const u of ups) {
      const p = project(x, z, u.prof);
      const beyond = (p.t === 0 && p.i === 0) || (p.t === 1 && p.i === u.prof.length - 2);   // past either end of the cut
      if (p.d <= u.half && !beyond) return u.stairs ? stairY(u, p, x, z) : p.y;
    }
    return null;
  };
  // the public road over a cut: deck level across the cut, ramps of `grade` on both sides; a tunnel keeps the ground
  const upperAt = (r, x, z) => {
    for (const u of ups) {
      if (!u.upper.has(String(r.id))) continue;
      const p = project(x, z, u.prof), reach = u.half + 2;
      const raw = terrainAt(x, z);
      if (u.deck == null) continue;          // tunnel: the road keeps following the terrain (buildRoads uses terrainAt)
      const y = u.deck - (u.grade || 0.04) * Math.max(0, p.d - reach);
      if (y > raw + 0.05) return y;
      if (p.d < reach) return raw;
    }
    return null;
  };
  const segments = [], corridors = [];
  for (const u of ups) {
    // ground shader holes along the open parts of the cut (the roofed stretch keeps its ground)
    for (let i = 0, acc = 0; i < u.prof.length - 1; i++) {
      const [ax, az] = u.prof[i], [bx, bz] = u.prof[i + 1], L = Math.hypot(bx - ax, bz - az);
      const parts = u.cov ? [[acc, Math.min(acc + L, u.cov[0])], [Math.max(acc, u.cov[1]), acc + L]] : [[acc, acc + L]];
      for (const [s0, s1] of parts) {
        if (s1 - s0 < 0.05) continue;
        const f0 = (s0 - acc) / L, f1 = (s1 - acc) / L;
        segments.push([ax + (bx - ax) * f0, az + (bz - az) * f0, ax + (bx - ax) * f1, az + (bz - az) * f1, u.half + 0.25]);
      }
      acc += L;
    }
    const L = [], R = [];
    for (let i = 0; i < u.prof.length; i++) {
      const a = u.prof[Math.max(0, i - 1)], b = u.prof[Math.min(u.prof.length - 1, i + 1)];
      const ex = b[0] - a[0], ez = b[1] - a[1], l = Math.hypot(ex, ez) || 1, nx = -ez / l, nz = ex / l, w = u.half + 0.4;
      L.push([u.prof[i][0] + nx * w, u.prof[i][1] + nz * w]); R.push([u.prof[i][0] - nx * w, u.prof[i][1] - nz * w]);
    }
    corridors.push([...L, ...R.reverse()]);
  }

  // is (x, z) under the crossing public road (its carriageway + sidewalks)?
  const underUpper = (u, roads, x, z) => roads.some((r) => u.upper.has(String(r.id)) && r.pts.some((q, i) => {
    if (i === r.pts.length - 1) return false;
    const [ax, az] = q, [bx, bz] = r.pts[i + 1], ex = bx - ax, ez = bz - az, l2 = ex * ex + ez * ez || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2));
    return Math.hypot(ax + ex * t - x, az + ez * t - z) < r.w / 2 + (r.sw || 0) + 0.8;
  }));

  function build(ctx, roads) {
    const { scene } = ctx;
    const wall = new GeoBuf(), floor = new GeoBuf(), rail = new GeoBuf(), slab = new GeoBuf(), glass = new GeoBuf(), para = new GeoBuf(), pergola = new GeoBuf();
    const concrete = new THREE.Color('#c9c5bc'), floorC = new THREE.Color('#a9a59d'), railC = new THREE.Color('#d7d9da'), slabC = new THREE.Color('#b8b3a8');
    const glassC = new THREE.Color('#8fb8c8'), frameC = new THREE.Color('#5d6670');
    const solid = [];                              // wall sample points for collision
    let top = -1e9;
    for (const u of ups) {
      const P = u.prof;
      // cumulative positions every 1 m along the profile
      const samples = [];
      for (let i = 0, acc = 0; i < P.length - 1; i++) {
        const [ax, az, ay] = P[i], [bx, bz, by] = P[i + 1], L = Math.hypot(bx - ax, bz - az), n = Math.max(1, Math.ceil(L));
        const nx = -(bz - az) / L, nz = (bx - ax) / L;
        for (let k = 0; k < n + (i === P.length - 2 ? 1 : 0); k++) samples.push([ax + (bx - ax) * k / n, az + (bz - az) * k / n, ay + (by - ay) * k / n, nx, nz, acc + L * k / n]);
        acc += L;
      }
      // floor strip across the whole cut (under the road surface), and the two side walls + railings
      for (let k = 0; k < samples.length - 1; k++) {
        const [x0, z0, y0, nx, nz, s0] = samples[k], [x1, z1, y1, , , s1] = samples[k + 1], h = u.half;
        const fh = u.stairs && k < u.sLow ? u.stairs.road : h;     // beside the stairs the floor strip is the road only
        floor.triFace([x0 + nx * fh, y0 + 0.02, z0 + nz * fh], [x1 + nx * fh, y1 + 0.02, z1 + nz * fh], [x1 - nx * fh, y1 + 0.02, z1 - nz * fh], floorC, () => [0, 0]);
        floor.triFace([x0 + nx * fh, y0 + 0.02, z0 + nz * fh], [x1 - nx * fh, y1 + 0.02, z1 - nz * fh], [x0 - nx * fh, y0 + 0.02, z0 - nz * fh], floorC, () => [0, 0]);
        const roofed = inCov(u, (s0 + s1) / 2);
        if (roofed) {                                   // tunnel roof between the mouths, just under the ground surface
          const g = Math.min(terrainAt(x0 + nx * h, z0 + nz * h), terrainAt(x0 - nx * h, z0 - nz * h), terrainAt(x1 + nx * h, z1 + nz * h), terrainAt(x1 - nx * h, z1 - nz * h));
          const w = h + 0.4, c = (x, z, sd, yy) => [x + nx * w * sd, yy, z + nz * w * sd];
          for (const yy of [g - 0.75, g - 0.05]) {
            slab.triFace(c(x0, z0, 1, yy), c(x1, z1, 1, yy), c(x1, z1, -1, yy), slabC, () => [0, 0]);
            slab.triFace(c(x0, z0, 1, yy), c(x1, z1, -1, yy), c(x0, z0, -1, yy), slabC, () => [0, 0]);
          }
        }
        for (const s of [1, -1]) {
          const ax = x0 + nx * h * s, az = z0 + nz * h * s, bx = x1 + nx * h * s, bz = z1 + nz * h * s;
          const ga = terrainAt(ax, az), gb = terrainAt(bx, bz), deep = Math.max(ga - y0, gb - y1);
          const covered = roofed || underUpper(u, roads, (ax + bx) / 2, (az + bz) / 2);
          const lid = covered ? (u.deck != null ? u.deck - 1.0 : Math.min(ga, gb) - 0.7) : null;
          const ta = covered ? lid : ga + (deep > 0.6 ? 1.1 : 0.05), tb = covered ? lid : gb + (deep > 0.6 ? 1.1 : 0.05);
          if (deep < 0.12 && !covered) continue;
          wall2(wall, ax, az, bx, bz, Math.min(y0, y1) - 0.4, Math.max(ta, tb), concrete);
          if (!covered && deep > 0.6) {                     // stainless railing on top of the wall
            const g = Math.max(ga, gb);
            if (k % 2 === 0) rail.box(ax, az, g + 0.05, 0.06, 1.05, 0.06, 0, railC);
            wall2(rail, ax, az, bx, bz, g + 0.98, g + 1.08, railC);
          }
          if (deep > 0.4 || covered) { solid.push([ax, az], [(ax + bx) / 2, (az + bz) / 2]); top = Math.max(top, ta, tb); }
        }
      }
      // wide stairs on both sides of the ramp: 0.36 m treads stepping up to the landing, railing along the road edge
      if (u.stairs) {
        const st = u.stairs, wid = u.half - st.road, stepC = new THREE.Color('#bfbab0');
        const at = (s) => {                       // centre-line point and direction at along-position s
          let acc = 0;
          for (let i = 0; i < P.length - 1; i++) {
            const L = Math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]);
            if (s <= acc + L || i === P.length - 2) {
              const f = Math.max(0, Math.min(1, (s - acc) / L));
              return [P[i][0] + (P[i + 1][0] - P[i][0]) * f, P[i][1] + (P[i + 1][1] - P[i][1]) * f, P[i][2] + (P[i + 1][2] - P[i][2]) * f, (P[i + 1][0] - P[i][0]) / L, (P[i + 1][1] - P[i][1]) / L];
            }
            acc += L;
          }
          return null;
        };
        for (let s = 0.18; s < u.sLow; s += 0.36) {
          const [cx, cz, ry, dx, dz] = at(s), nx = -dz, nz = dx;
          for (const sd of [1, -1]) {
            const mx = cx + nx * (st.road + wid / 2) * sd, mz = cz + nz * (st.road + wid / 2) * sd;
            const hy = cutAt(mx, mz);
            if (hy == null || hy - ry < 0.08) continue;
            slab.box(mx, mz, u.floorY - 0.3, 0.37, hy - u.floorY + 0.3, wid, Math.atan2(dz, dx), stepC);
            if (hy - ry > 0.25) {
              const ex = cx + nx * st.road * sd, ez = cz + nz * st.road * sd;
              wall2(rail, ex - dx * 0.18, ez - dz * 0.18, ex + dx * 0.18, ez + dz * 0.18, hy + 0.98, hy + 1.08, railC);
              if (Math.round(s / 0.36) % 4 === 0) rail.box(ex, ez, hy, 0.06, 1.05, 0.06, 0, railC);
              solid.push([ex, ez]); top = Math.max(top, hy + 1.1);
            }
          }
        }
      }
      // deck slab (bridge) or tunnel roof under the public road, spanning the cut
      for (const r of roads) {
        if (!u.upper.has(String(r.id))) continue;
        for (let i = 0; i < r.pts.length - 1; i++) {
          const [ax, az] = r.pts[i], [bx, bz] = r.pts[i + 1], L = Math.hypot(bx - ax, bz - az);
          // one continuous slab: soffit + top ribbons and the two fascias, in 1 m pieces over the cut
          const ux = (bx - ax) / L, uz = (bz - az) / L, nx = -uz, nz = ux, w = (r.w + 2 * (r.sw || 0) + 1.2) / 2, th = u.deck != null ? 1.0 : 0.7;
          for (let t = 0; t < L; t += 1) {
            const t1 = Math.min(L, t + 1), x0 = ax + ux * t, z0 = az + uz * t, x1 = ax + ux * t1, z1 = az + uz * t1;
            const pp = project((x0 + x1) / 2, (z0 + z1) / 2, P);
            if (pp.d > u.half + 1.2 || (u.cov && pp.s > u.cov[0] - 0.5 && pp.s < u.cov[1] + 0.5)) continue;   // roofed stretch has its own slab
            const y = (u.deck != null ? u.deck : Math.min(terrainAt(x0, z0), terrainAt(x1, z1))) - 0.05, yb = y - th;
            const c = (x, z, s, yy) => [x + nx * w * s, yy, z + nz * w * s];
            for (const yy of [yb, y]) {
              slab.triFace(c(x0, z0, 1, yy), c(x1, z1, 1, yy), c(x1, z1, -1, yy), slabC, () => [0, 0]);
              slab.triFace(c(x0, z0, 1, yy), c(x1, z1, -1, yy), c(x0, z0, -1, yy), slabC, () => [0, 0]);
            }
            for (const s of [1, -1]) slab.wall(x0 + nx * w * s, z0 + nz * w * s, x1 + nx * w * s, z1 + nz * w * s, yb, y, nx * s, nz * s, 0, 0, 0, 0, slabC);
          }
        }
      }
      // raised public road (bridge approaches): retaining walls down to the ground, concrete parapets on the deck
      if (u.deck != null) for (const r of roads) {
        if (!u.upper.has(String(r.id))) continue;
        const ehw = r.w / 2 + (r.sw || 0) + 0.15;
        for (let i = 0; i < r.pts.length - 1; i++) {
          const [ax, az] = r.pts[i], [bx, bz] = r.pts[i + 1], L = Math.hypot(bx - ax, bz - az), ux = (bx - ax) / L, uz = (bz - az) / L, nx = -uz, nz = ux;
          for (let t = 0; t < L; t += 1) {
            const x0 = ax + ux * t, z0 = az + uz * t, t1 = Math.min(L, t + 1), x1 = ax + ux * t1, z1 = az + uz * t1;
            const y0 = upperAt(r, x0, z0), y1 = upperAt(r, x1, z1);
            if (y0 == null || y1 == null) continue;
            const inCut = project((x0 + x1) / 2, (z0 + z1) / 2, P).d < u.half + 0.3, ytop = Math.max(y0, y1) + 0.3;
            for (const s of [1, -1]) {
              const ex0 = x0 + nx * ehw * s, ez0 = z0 + nz * ehw * s, ex1 = x1 + nx * ehw * s, ez1 = z1 + nz * ehw * s;
              const g = Math.min(terrainAt(ex0, ez0), terrainAt(ex1, ez1));
              if (!inCut && ytop - g > 0.4) {
                wall2(wall, ex0, ez0, ex1, ez1, g - 0.3, ytop, concrete);
              }
              if (inCut || ytop - g > 1.2) {
                wall2(para, ex0, ez0, ex1, ez1, ytop, ytop + 1.1, slabC);
              }
            }
          }
        }
      }
      // blue banner panels on both faces of the bridge (user photo: 全面推进一流特色研究型大学建设)
      if (u.deck != null && u.banner) {
        const c = document.createElement('canvas'); c.width = 1024; c.height = 96;
        const x2 = c.getContext('2d'); x2.fillStyle = '#1d4f9c'; x2.fillRect(0, 0, 1024, 96);
        x2.fillStyle = '#ffffff'; x2.font = 'bold 58px "Microsoft YaHei", sans-serif'; x2.textAlign = 'center'; x2.textBaseline = 'middle'; x2.fillText(u.banner, 512, 50);
        const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
        // where the public road crosses the cut's centre line: a banner on each outer face of the deck
        for (const r of roads) if (u.upper.has(String(r.id))) for (let i = 0; i < r.pts.length - 1; i++) {
          const [ax, az] = r.pts[i], [bx, bz] = r.pts[i + 1], L = Math.hypot(bx - ax, bz - az);
          for (let t = 0; t <= L; t += 0.5) {
            const x = ax + (bx - ax) * t / L, z = az + (bz - az) * t / L, p = project(x, z, P);
            if (p.d > 0.3) continue;
            const half = r.w / 2 + (r.sw || 0) + 0.65, ux = (bx - ax) / L, uz = (bz - az) / L;
            for (const s of [1, -1]) {        // face normal = across the public road, panel runs along it over the cut
              const m = new THREE.Mesh(new THREE.PlaneGeometry(2 * u.half, 2.0), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.7 }));
              m.position.set(x - uz * half * s, u.deck - 0.25, z + ux * half * s);
              m.rotation.y = Math.atan2(-uz, ux) + (s < 0 ? Math.PI : 0);     // text faces outward on both sides
              scene.add(m);
            }
            t = L + 1;
          }
        }
      }
      // tunnel mouths: a concrete headwall over each opening, coping a little above the ground (video: box portals)
      if (u.cov) for (const [k, sd] of [[0, -1], [1, 1]]) {
        const [cx, cz, , dx, dz] = alongAt(P, u.cov[k]), nx = -dz, nz = dx, h = u.half + 0.4;
        const g = Math.min(terrainAt(cx + nx * u.half, cz + nz * u.half), terrainAt(cx - nx * u.half, cz - nz * u.half));
        const ox = dx * 0.3 * sd, oz = dz * 0.3 * sd;            // 0.6 m thick, centred on the mouth
        for (const o of [-1, 1]) wall2(wall, cx + nx * h + ox * o, cz + nz * h + oz * o, cx - nx * h + ox * o, cz - nz * h + oz * o, g - 0.75, g + 0.45, concrete);
        wall2(wall, cx + nx * h - ox, cz + nz * h - oz, cx + nx * h + ox, cz + nz * h + oz, g - 0.75, g + 0.45, concrete);
        wall2(wall, cx - nx * h - ox, cz - nz * h - oz, cx - nx * h + ox, cz - nz * h + oz, g - 0.75, g + 0.45, concrete);
        const q = (a, b, c2) => slab.triFace(a, b, c2, slabC, () => [0, 0]);
        const A = [cx + nx * h - ox, g + 0.45, cz + nz * h - oz], B = [cx + nx * h + ox, g + 0.45, cz + nz * h + oz];
        const C2 = [cx - nx * h + ox, g + 0.45, cz - nz * h + oz], D2 = [cx - nx * h - ox, g + 0.45, cz - nz * h - oz];
        q(A, B, C2); q(A, C2, D2);
      }
      // timber pergola with wisteria over the sloping approach (official video: 紫藤长廊 down to the pedestrian tunnel)
      if (u.pergola?.length >= 2) {
        const wood = new THREE.Color('#6b4a33'), bloom = [new THREE.Color('#bb9ce6'), new THREE.Color('#a585d8'), new THREE.Color('#7fa35a'), new THREE.Color('#d2bff0')];
        const Q = u.pergola, ph = u.half - 0.3, H = 3.0, leaf = new THREE.Color('#5f8f45');
        const posts = [];                                   // [x, z, floor y, dx, dz] every 2.4 m along the pergola line
        for (let i = 0; i < Q.length - 1; i++) {
          const [ax, az] = Q[i], [bx, bz] = Q[i + 1], L = Math.hypot(bx - ax, bz - az), dx = (bx - ax) / L, dz = (bz - az) / L;
          for (let t = i ? 2.4 : 0; t <= L + 0.01; t += 2.4) { const x = ax + dx * t, z = az + dz * t; posts.push([x, z, cutAt(x, z) ?? terrainAt(x, z), dx, dz]); }
        }
        posts.forEach(([x, z, fy, dx, dz], n) => {
          const nx = -dz, nz = dx, ang = Math.atan2(dz, dx), by = fy + H;
          for (const sd of [1, -1]) pergola.box(x + nx * ph * sd, z + nz * ph * sd, fy, 0.22, H, 0.22, ang, wood);      // posts
          pergola.box(x, z, by, 0.14, 0.2, 2 * ph + 0.8, ang, wood);                                                   // cross beam
          const nb = posts[n + 1];
          if (!nb) return;
          const mx = (x + nb[0]) / 2, mz = (z + nb[1]) / 2, my = (fy + nb[2]) / 2 + H, seg = Math.hypot(nb[0] - x, nb[1] - z);
          for (const sd of [1, -1]) pergola.box(mx + nx * ph * sd, mz + nz * ph * sd, my + 0.2, seg, 0.14, 0.12, ang, wood); // side purlins
          pergola.box(mx, mz, my + 0.34, seg + 0.2, 0.22, 2 * ph + 1.4, ang, n % 3 === 1 ? leaf : bloom[n % 2 ? 0 : 3]);   // flowering roof
          for (let j = 0; j < 12; j++) {                                                                                // hanging racemes
            const f = ((n * 5 + j * 7) % 11) / 10 - 0.5, g = ((n * 3 + j * 5) % 7) / 6;
            const hx = mx + nx * f * 2 * ph * 0.95 + dx * (g - 0.5) * seg, hz = mz + nz * f * 2 * ph * 0.95 + dz * (g - 0.5) * seg;
            const len = 0.35 + 0.25 * ((n + j) % 3);
            pergola.box(hx, hz, my + 0.3 - len, 0.16, len, 0.16, ang + j, bloom[(n + j) % 4 === 2 ? 1 : (n + j) % 4]);
          }
        });
      }
      // glass canopies over the tunnel stairs
      for (const [cx, cz, h0] of u.canopies || []) {
        const p = project(cx, cz, P), g = terrainAt(cx, cz) + (h0 || 0), ang = Math.atan2(-p.nx, p.nz);   // along the cut
        glass.box(cx, cz, g + 2.8, 9, 0.12, 2 * u.half + 1.5, ang, glassC);
        for (const [a, b] of [[-4.3, -1], [4.3, -1], [-4.3, 1], [4.3, 1]]) {
          const ox = Math.cos(ang) * a - Math.sin(ang) * b * (u.half + 0.6), oz = Math.sin(ang) * a + Math.cos(ang) * b * (u.half + 0.6);
          glass.box(cx + ox, cz + oz, g, 0.15, 2.8, 0.15, ang, frameC);
        }
      }
    }
    const add = (b, mat) => { if (b.empty()) return; const m = new THREE.Mesh(b.geometry(), mat); m.castShadow = true; m.receiveShadow = true; scene.add(m); };
    add(wall, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }));            // both faces are built
    add(para, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 }));
    add(floor, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 }));
    add(rail, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.3, metalness: 0.7 }));
    add(slab, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide }));
    add(glass, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.1, metalness: 0.2, transparent: true, opacity: 0.55 }));
    add(pergola, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, side: THREE.DoubleSide }));   // the roof is seen from below
    // collision grid along the walls (bounds.js collideGrid format)
    if (!solid.length) return null;
    const cell = 0.5, xs = solid.map((q) => q[0]), zs = solid.map((q) => q[1]);
    const x0 = Math.min(...xs) - 2, z0 = Math.min(...zs) - 2, nx = Math.ceil((Math.max(...xs) - x0) / cell) + 4, nz = Math.ceil((Math.max(...zs) - z0) / cell) + 4;
    const g = new Uint8Array(nx * nz);
    for (const [x, z] of solid) { const i = Math.floor((x - x0) / cell), k = Math.floor((z - z0) / cell); if (i >= 0 && i < nx && k >= 0 && k < nz) g[k * nx + i] = 1; }
    return { x0, z0, nx, nz, cell, solid: g, top, minX: x0, maxX: x0 + nx * cell, minZ: z0, maxZ: z0 + nz * cell, name: 'underpass walls' };
  }

  const isUpper = (r) => ups.some((u) => u.upper.has(String(r.id)));
  // inside a tunnel-type cut (no sidewalks there: pedestrians use their own tunnel)
  const inTunnel = (x, z) => ups.some((u) => {
    if (u.deck != null) return false;
    const p = project(x, z, u.prof), beyond = (p.t === 0 && p.i === 0) || (p.t === 1 && p.i === u.prof.length - 2);
    return p.d <= u.half && !beyond;
  });
  return { list: ups, cutAt, upperAt, isUpper, inTunnel, segments, corridors, build };
}
