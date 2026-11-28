// Keeping the visitor inside the game: an invisible wall along the campus boundary, and solid Blender models.
import * as THREE from 'three';

function inPoly(x, z, pts) {
  let s = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, zi] = pts[i], [xj, zj] = pts[j];
    if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) s = !s;
  }
  return s;
}
function nearestOnRing(x, z, r) {
  let best = Infinity, bx = x, bz = z;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, zi] = r[i], [xj, zj] = r[j];
    const ex = xi - xj, ez = zi - zj, l2 = ex * ex + ez * ez || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - xj) * ex + (z - zj) * ez) / l2));
    const qx = xj + ex * t, qz = zj + ez * t, d = Math.hypot(x - qx, z - qz);
    if (d < best) { best = d; bx = qx; bz = qz; }
  }
  return [best, bx, bz];
}

function segX(ax, az, bx, bz, cx, cz, dx, dz) {     // intersection of segments ab and cd, or null
  const d = (bx - ax) * (dz - cz) - (bz - az) * (dx - cx);
  if (Math.abs(d) < 1e-12) return null;
  const t = ((cx - ax) * (dz - cz) - (cz - az) * (dx - cx)) / d, u = ((cx - ax) * (bz - az) - (cz - az) * (bx - ax)) / d;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? [ax + (bx - ax) * t, az + (bz - az) * t] : null;
}

// ---------------------------------------------------------------- air wall
// Openings in the campus boundary: the gates, and every place a road or path crosses the boundary line
// (the fence along the boundary leaves these 14 m gaps too, life.js buildFence).
export function boundaryOpenings(rings, gates, roads) {
  const out = gates.map((g) => ({ x: g.x, z: g.z }));
  for (const rd of roads) for (let i = 0; i < rd.pts.length - 1; i++) {
    const [ax, az] = rd.pts[i], [bx, bz] = rd.pts[i + 1];
    for (const r of rings) for (let k = 0, j = r.length - 1; k < r.length; j = k++) {
      const q = segX(ax, az, bx, bz, r[j][0], r[j][1], r[k][0], r[k][1]);
      if (q && !out.some((o) => Math.hypot(o.x - q[0], o.z - q[1]) < 6)) out.push({ x: q[0], z: q[1] });
    }
  }
  return out;
}

// Walking / riding cannot cross the campus boundary (the fence line) except through an opening (within `gap` m),
// and outside the rings only the aprons in front of the openings (`apron` m) and the strip where two campus parts
// face each other across a public road (盘城新街 between 中苑 and 东苑, 22-30 m apart: within `bridge` m of both)
// can be walked. Flying is not limited.
export function makeAirWall(rings, openings, { gap = 14, apron = 10, bridge = 36, corridors = [] } = {}) {
  const near = (x, z, r) => openings.some((o) => Math.hypot(o.x - x, o.z - z) < r);
  const ok = (x, z) => {
    const d = rings.map((r) => (inPoly(x, z, r) ? 0 : nearestOnRing(x, z, r)[0]));
    if (d.some((v) => v === 0)) return true;
    if (corridors.some((c) => inPoly(x, z, c))) return true;        // underpass cuts linking campus parts
    for (let i = 0; i < d.length; i++) for (let j = i + 1; j < d.length; j++) if (d[i] <= bridge && d[j] <= bridge) return true;
    return Math.min(...d) <= apron && near(x, z, gap + apron);
  };
  const crosses = (ax, az, bx, bz) => {
    if (ax === bx && az === bz) return false;
    for (const r of rings) for (let k = 0, j = r.length - 1; k < r.length; j = k++) {
      const q = segX(ax, az, bx, bz, r[j][0], r[j][1], r[k][0], r[k][1]);
      if (q && !near(q[0], q[1], gap) && !corridors.some((c) => inPoly(q[0], q[1], c))) return true;
    }
    return false;
  };
  // teleport / landing target: kept if inside, else the closest boundary point 1.5 m inside
  const snap = (x, z) => {
    if (rings.some((r) => inPoly(x, z, r)) || ok(x, z)) return [x, z];
    let best = null;
    for (const r of rings) { const c = nearestOnRing(x, z, r); if (!best || c[0] < best[0]) best = c; }
    const [d, qx, qz] = best;
    return [qx + (qx - x) / (d || 1) * 1.5, qz + (qz - z) / (d || 1) * 1.5];
  };
  // after a move from (px, pz): slide along the wall, else step back
  const keep = (p, px, pz) => {
    if (!ok(px, pz)) { const [x, z] = snap(px, pz); p.x = x; p.z = z; return true; }   // e.g. got off the bus outside
    if (ok(p.x, p.z) && !crosses(px, pz, p.x, p.z)) return false;
    if (ok(px, p.z) && !crosses(px, pz, px, p.z)) p.x = px;
    else if (ok(p.x, pz) && !crosses(px, pz, p.x, pz)) p.z = pz;
    else { p.x = px; p.z = pz; }
    return true;
  };
  return { ok, crosses, snap, keep };
}

// ---------------------------------------------------------------- solid models
// Occupancy grid of a model at walking height (0.4-2.2 m above its base): cells its surfaces pass through,
// gaps up to ~1 m closed, and everything enclosed by them (the inside of the building) solid.
// groundAt(x, z): measure the slab from the local ground instead of the model base (models spread over a slope,
// e.g. 东大门 / the food street: paving 0.2 m above the ground must not count as a wall where the ground rises).
export function modelGrid(root, base, { cell = 0.5, y0 = 0.4, y1 = 2.2, groundAt = null } = {}) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty() || (!groundAt && box.max.y < base + y0)) return null;
  const x0 = box.min.x - 3 * cell, z0 = box.min.z - 3 * cell;
  const nx = Math.ceil((box.max.x - x0) / cell) + 4, nz = Math.ceil((box.max.z - z0) / cell) + 4;
  if (nx * nz > 6e6) return null;
  const occ = new Uint8Array(nx * nz);
  const lo = groundAt ? y0 : base + y0, hi = groundAt ? y1 : base + y1, planes = [lo, (lo + hi) / 2, hi];
  const mark = (x, z) => {
    const i = Math.floor((x - x0) / cell), k = Math.floor((z - z0) / cell);
    if (i >= 0 && i < nx && k >= 0 && k < nz) occ[k * nx + i] = 1;
  };
  const line = (ax, az, bx, bz) => {
    const n = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / (cell * 0.4)));
    for (let s = 0; s <= n; s++) mark(ax + (bx - ax) * s / n, az + (bz - az) * s / n);
  };
  const fill = (a, b, c) => {          // flat-ish triangle inside the slab: fill its footprint
    const mnx = Math.min(a.x, b.x, c.x), mxx = Math.max(a.x, b.x, c.x), mnz = Math.min(a.z, b.z, c.z), mxz = Math.max(a.z, b.z, c.z);
    const area = (b.x - a.x) * (c.z - a.z) - (c.x - a.x) * (b.z - a.z);
    if (Math.abs(area) < 1e-6) { line(a.x, a.z, b.x, b.z); line(b.x, b.z, c.x, c.z); return; }
    for (let z = mnz; z <= mxz + cell * 0.5; z += cell * 0.5) for (let x = mnx; x <= mxx + cell * 0.5; x += cell * 0.5) {
      const w0 = ((b.x - x) * (c.z - z) - (c.x - x) * (b.z - z)) / area, w1 = ((c.x - x) * (a.z - z) - (a.x - x) * (c.z - z)) / area;
      if (w0 >= -0.02 && w1 >= -0.02 && w0 + w1 <= 1.02) mark(x, z);
    }
    line(a.x, a.z, b.x, b.z); line(b.x, b.z, c.x, c.z); line(c.x, c.z, a.x, a.z);
  };
  const tri = (a, b, c) => {
    const ymn = Math.min(a.y, b.y, c.y), ymx = Math.max(a.y, b.y, c.y);
    if (ymx < lo || ymn > hi) return;
    if (ymn >= lo && ymx <= hi) { fill(a, b, c); return; }
    for (const y of planes) {          // slice by horizontal planes: a segment per crossing
      const q = [];
      for (const [p1, p2] of [[a, b], [b, c], [c, a]]) {
        if ((p1.y - y) * (p2.y - y) > 0 || p1.y === p2.y) continue;
        const t = (y - p1.y) / (p2.y - p1.y);
        q.push([p1.x + (p2.x - p1.x) * t, p1.z + (p2.z - p1.z) * t]);
      }
      if (q.length >= 2) line(q[0][0], q[0][1], q[1][0], q[1][1]);
    }
  };
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), m = new THREE.Matrix4(), im = new THREE.Matrix4();
  root.traverse((o) => {
    if (!o.isMesh || !o.visible || !o.geometry?.attributes?.position) return;
    const pos = o.geometry.attributes.position, idx = o.geometry.index, n = idx ? idx.count : pos.count;
    const count = o.isInstancedMesh ? o.count : 1;
    for (let inst = 0; inst < count; inst++) {
      m.copy(o.matrixWorld);
      if (o.isInstancedMesh) { o.getMatrixAt(inst, im); m.multiply(im); }
      for (let t = 0; t + 2 < n; t += 3) {
        const i0 = idx ? idx.getX(t) : t, i1 = idx ? idx.getX(t + 1) : t + 1, i2 = idx ? idx.getX(t + 2) : t + 2;
        a.fromBufferAttribute(pos, i0).applyMatrix4(m); b.fromBufferAttribute(pos, i1).applyMatrix4(m); c.fromBufferAttribute(pos, i2).applyMatrix4(m);
        if (groundAt) { a.y -= groundAt(a.x, a.z); b.y -= groundAt(b.x, b.z); c.y -= groundAt(c.x, c.z); }
        tri(a, b, c);
      }
    }
  });
  // close small gaps (dilate 1 cell), flood the outside from the border, the rest is solid
  const closed = new Uint8Array(nx * nz);
  for (let k = 1; k < nz - 1; k++) for (let i = 1; i < nx - 1; i++) {
    const j = k * nx + i;
    if (occ[j] || occ[j - 1] || occ[j + 1] || occ[j - nx] || occ[j + nx]) closed[j] = 1;
  }
  const out = new Uint8Array(nx * nz), stack = [];
  for (let i = 0; i < nx; i++) { stack.push(i, (nz - 1) * nx + i); }
  for (let k = 0; k < nz; k++) { stack.push(k * nx, k * nx + nx - 1); }
  while (stack.length) {
    const j = stack.pop();
    if (out[j] || closed[j]) continue;
    out[j] = 1;
    const i = j % nx, k = (j / nx) | 0;
    if (i > 0) stack.push(j - 1); if (i < nx - 1) stack.push(j + 1);
    if (k > 0) stack.push(j - nx); if (k < nz - 1) stack.push(j + nx);
  }
  const solid = new Uint8Array(nx * nz);
  let nSolid = 0;
  for (let k = 1; k < nz - 1; k++) for (let i = 1; i < nx - 1; i++) {
    const j = k * nx + i;
    if (out[j]) continue;
    // a cell added only by the gap-closing dilation stays walkable where it faces the outside
    if (!occ[j] && closed[j] && (out[j - 1] || out[j + 1] || out[j - nx] || out[j + nx])) continue;
    solid[j] = 1; nSolid++;
  }
  if (!nSolid) return null;
  return { x0, z0, nx, nz, cell, solid, top: box.max.y, minX: x0, maxX: x0 + nx * cell, minZ: z0, maxZ: z0 + nz * cell };
}

const isSolid = (g, i, k) => i >= 0 && i < g.nx && k >= 0 && k < g.nz && g.solid[k * g.nx + i] === 1;

// push a circle of radius r at p out of the solid cells
export function collideGrid(g, p, r) {
  if (p.x < g.minX - r || p.x > g.maxX + r || p.z < g.minZ - r || p.z > g.maxZ + r || p.y > g.top - 0.3) return;
  const c = g.cell;
  const fi = Math.floor((p.x - g.x0) / c), fk = Math.floor((p.z - g.z0) / c);
  if (isSolid(g, fi, fk)) {            // deep inside (e.g. teleported in): go to the nearest free cell
    const [x, z] = freeSpot(g, p.x, p.z);
    p.x = x; p.z = z;
    return;
  }
  const i0 = Math.floor((p.x - r - g.x0) / c), i1 = Math.floor((p.x + r - g.x0) / c);
  const k0 = Math.floor((p.z - r - g.z0) / c), k1 = Math.floor((p.z + r - g.z0) / c);
  for (let k = k0; k <= k1; k++) for (let i = i0; i <= i1; i++) {
    if (!isSolid(g, i, k)) continue;
    const cx0 = g.x0 + i * c, cz0 = g.z0 + k * c;
    const qx = Math.max(cx0, Math.min(cx0 + c, p.x)), qz = Math.max(cz0, Math.min(cz0 + c, p.z));
    const d = Math.hypot(p.x - qx, p.z - qz);
    if (d < r && d > 1e-6) { p.x += (p.x - qx) / d * (r - d); p.z += (p.z - qz) / d * (r - d); }
  }
}

// share of a footprint (xs, zs) that a model grid covers (solid within 2 m): decides which outlines a model replaces
export function coverage(g, xs, zs) {
  let mnx = Infinity, mxx = -Infinity, mnz = Infinity, mxz = -Infinity;
  for (let i = 0; i < xs.length; i++) { mnx = Math.min(mnx, xs[i]); mxx = Math.max(mxx, xs[i]); mnz = Math.min(mnz, zs[i]); mxz = Math.max(mxz, zs[i]); }
  if (mxx < g.minX || mnx > g.maxX || mxz < g.minZ || mnz > g.maxZ) return 0;
  const pts = xs.length ? Array.from(xs, (x, i) => [x, zs[i]]) : [];
  const near = (x, z) => {
    const fi = Math.floor((x - g.x0) / g.cell), fk = Math.floor((z - g.z0) / g.cell), w = Math.ceil(2 / g.cell);
    for (let k = fk - w; k <= fk + w; k++) for (let i = fi - w; i <= fi + w; i++) if (isSolid(g, i, k)) return true;
    return false;
  };
  let n = 0, hit = 0;
  const step = Math.max(1, Math.min(mxx - mnx, mxz - mnz) / 8);
  for (let z = mnz + step / 2; z < mxz; z += step) for (let x = mnx + step / 2; x < mxx; x += step) {
    if (!inPoly(x, z, pts)) continue;
    n++; if (near(x, z)) hit++;
  }
  return n ? hit / n : 0;
}

export function freeSpot(g, x, z) {
  const c = g.cell, fi = Math.floor((x - g.x0) / c), fk = Math.floor((z - g.z0) / c);
  for (let rad = 1; rad < 200; rad++) {
    let best = null;
    for (let k = fk - rad; k <= fk + rad; k++) for (let i = fi - rad; i <= fi + rad; i++) {
      if (Math.max(Math.abs(i - fi), Math.abs(k - fk)) !== rad || isSolid(g, i, k)) continue;
      if (isSolid(g, i - 1, k) || isSolid(g, i + 1, k) || isSolid(g, i, k - 1) || isSolid(g, i, k + 1)) continue;
      const d = (i - fi) ** 2 + (k - fk) ** 2;
      if (!best || d < best[0]) best = [d, i, k];
    }
    if (best) return [g.x0 + (best[1] + 0.5) * c, g.z0 + (best[2] + 0.5) * c];
  }
  return [x, z];
}
