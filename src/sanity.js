// Common-sense placement (常识排查): one set of rules every builder asks before putting something down, and a
// DEV scan (__campus.sanity()) that lists what in the built scene still breaks them.
// Rules: nothing stands in water (bridge decks excepted), on a pitch / court / track, inside a building or a
// Blender model, or on a carriageway (street-parked cars excepted); low things (bins, benches, cars, bikes,
// people) stand on the surface they are on (sidewalk, bridge deck, junction patch), neither sunk into it nor
// floating above it.
import * as THREE from 'three';

const NONCAR = new Set(['footway', 'path', 'steps', 'cycleway', 'track', 'pedestrian']);

function inPoly(x, z, xs, zs) {
  let s = false;
  for (let i = 0, j = xs.length - 1; i < xs.length; j = i++) {
    if ((zs[i] > z) !== (zs[j] > z) && x < (xs[j] - xs[i]) * (z - zs[i]) / (zs[j] - zs[i]) + xs[i]) s = !s;
  }
  return s;
}
function edgeDist(x, z, xs, zs) {
  let best = Infinity;
  for (let i = 0, j = xs.length - 1; i < xs.length; j = i++) {
    const ex = xs[i] - xs[j], ez = zs[i] - zs[j], l2 = ex * ex + ez * ez || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - xs[j]) * ex + (z - zs[j]) * ez) / l2));
    best = Math.min(best, Math.hypot(xs[j] + ex * t - x, zs[j] + ez * t - z));
  }
  return best;
}
const cellKey = (i, k) => i * 100003 + k;
function gridAdd(grid, C, x0, z0, x1, z1, item) {
  for (let i = Math.floor(x0 / C); i <= Math.floor(x1 / C); i++) for (let k = Math.floor(z0 / C); k <= Math.floor(z1 / C); k++) {
    const key = cellKey(i, k);
    if (!grid.has(key)) grid.set(key, []);
    grid.get(key).push(item);
  }
}

// Sets ctx.inSport / inBuilding / buildingDist / wet / onSurface / topAt / blockedBy / clear.
// Call once the buildings and the Blender models are in (model grids decide where a model stands).
export function makeClearance(ctx, { roads = [], sports = [], metas = [], modelGrids = [], modelledIds = new Set(), junctions = [] } = {}) {
  const { heightAt } = ctx;
  // pitches, courts and tracks: oriented boxes
  const obbs = sports.map(({ obb: [cx, cz, L, Wd, a] }) => ({ cx, cz, hl: L / 2, hw: Wd / 2, c: Math.cos(a), s: Math.sin(a) }));
  ctx.inSport = (x, z, m = 0) => obbs.some((o) => {
    const dx = x - o.cx, dz = z - o.cz;
    return Math.abs(dx * o.c + dz * o.s) < o.hl + m && Math.abs(-dx * o.s + dz * o.c) < o.hw + m;
  });

  // buildings: footprints, except outlines a loaded Blender model stands on (its own occupancy grid is used)
  const BC = 20, bgrid = new Map(), PAD = 4;
  for (const m of metas) {
    if (!m.xs || m.kind === 'poi' || (m.replaced && modelledIds.has(String(m.id)))) continue;
    gridAdd(bgrid, BC, m.minX - PAD, m.minZ - PAD, m.maxX + PAD, m.maxZ + PAD, m);
  }
  const gridDist = (g, x, z, max) => {        // distance from (x, z) to the nearest solid cell of a model grid, up to max
    if (x < g.minX - max || x > g.maxX + max || z < g.minZ - max || z > g.maxZ + max) return Infinity;
    const c = g.cell, fi = Math.floor((x - g.x0) / c), fk = Math.floor((z - g.z0) / c), w = Math.ceil(max / c);
    let best = Infinity;
    for (let k = fk - w; k <= fk + w; k++) for (let i = fi - w; i <= fi + w; i++) {
      if (i < 0 || k < 0 || i >= g.nx || k >= g.nz || !g.solid[k * g.nx + i]) continue;
      const cx0 = g.x0 + i * c, cz0 = g.z0 + k * c;
      const d = Math.hypot(x - Math.max(cx0, Math.min(cx0 + c, x)), z - Math.max(cz0, Math.min(cz0 + c, z)));
      if (d < best) best = d;
    }
    return best;
  };
  // distance to the nearest building wall or model (0 inside), searched up to max (<= PAD)
  ctx.buildingDist = (x, z, max = PAD) => {
    let best = Infinity;
    for (const m of bgrid.get(cellKey(Math.floor(x / BC), Math.floor(z / BC))) || []) {
      if (x < m.minX - max || x > m.maxX + max || z < m.minZ - max || z > m.maxZ + max) continue;
      if (inPoly(x, z, m.xs, m.zs)) return 0;
      best = Math.min(best, edgeDist(x, z, m.xs, m.zs));
    }
    for (const g of modelGrids) best = Math.min(best, gridDist(g, x, z, max));
    return best;
  };
  ctx.inBuilding = (x, z, m = 0) => ctx.buildingDist(x, z, Math.max(m, 0.01)) <= m;

  ctx.wet = (x, z) => !!ctx.waterAt && ctx.waterAt(x, z) !== null && !(ctx.deckAt && ctx.deckAt(x, z) !== null);

  // every road and path surface: carriageway + sidewalks (same widths as world.js buildRoads), footpaths
  const RC = 16, rgrid = new Map();
  for (const r of roads) {
    const car = !NONCAR.has(r.kind) && r.w >= 5.5, sw = car ? (r.sw ?? (r.w >= 7 ? 2.4 : 0)) : 0;
    const lift = 0.16 + Math.min(r.w, 18) * 0.006, hw = r.w / 2, pad = hw + sw + 2;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [ax, az] = r.pts[i], [bx, bz] = r.pts[i + 1];
      gridAdd(rgrid, RC, Math.min(ax, bx) - pad, Math.min(az, bz) - pad, Math.max(ax, bx) + pad, Math.max(az, bz) + pad, { r, ax, az, bx, bz, hw, sw, lift });
    }
  }
  const segD = (e, x, z) => {
    const dx = e.bx - e.ax, dz = e.bz - e.az, l2 = dx * dx + dz * dz;
    const t = l2 ? Math.max(0, Math.min(1, ((x - e.ax) * dx + (z - e.az) * dz) / l2)) : 0;
    return Math.hypot(e.ax + dx * t - x, e.az + dz * t - z);
  };
  // the road whose surface (carriageway + sidewalks, or footpath) comes within m of (x, z), other than self
  ctx.onSurface = (x, z, m = 0, self = null) => {
    for (const e of rgrid.get(cellKey(Math.floor(x / RC), Math.floor(z / RC))) || []) {
      if (e.r !== self && segD(e, x, z) < e.hw + e.sw + m) return e.r;
    }
    return null;
  };
  // top of whatever is underfoot: terrain, road / sidewalk surface, junction patch or bridge deck
  const jgrid = new Map();
  for (const j of junctions) gridAdd(jgrid, RC, j.x - j.r, j.z - j.r, j.x + j.r, j.z + j.r, j);
  // underpasses (underpass.js): heightAt already gives the cut floor inside a cut; a public road crossing over it has
  // its own deck / ramp levels (under.upperAt), which count only outside the cut footprint, so the bus and people
  // in the cut stay on its floor under the deck
  const under = ctx.under, corridors = under?.corridors || [];
  const cxs = corridors.map((p) => p.map((q) => q[0])), czs = corridors.map((p) => p.map((q) => q[1]));
  ctx.inCut = (x, z, m = 0) => corridors.some((_, i) => inPoly(x, z, cxs[i], czs[i]) || (m > 0 && edgeDist(x, z, cxs[i], czs[i]) < m));
  ctx.topAt = (x, z) => {
    const deck = ctx.deckAt ? ctx.deckAt(x, z) : null, g = heightAt(x, z);
    let y = deck !== null && deck > g ? deck : g;
    if (deck !== null) return y;                   // the deck lookup already gives the walking surface on bridges
    const cut = under ? under.cutAt(x, z) !== null : false;
    for (const e of rgrid.get(cellKey(Math.floor(x / RC), Math.floor(z / RC))) || []) {
      const up = under ? under.upperAt(e.r, x, z) : null;
      if (up !== null && cut) continue;
      const d = segD(e, x, z), base = up ?? g;
      if (d < e.hw) y = Math.max(y, base + e.lift);
      else if (d < e.hw + e.sw) y = Math.max(y, base + e.lift + 0.15);
    }
    for (const j of jgrid.get(cellKey(Math.floor(x / RC), Math.floor(z / RC))) || []) {
      if (Math.hypot(x - j.x, z - j.z) < j.r) y = Math.max(y, g + 0.3);     // world.js buildJunctions follows the terrain
    }
    return y;
  };

  // why (x, z) is no place for an object of radius r, or null. Margins: false = rule off.
  //   sport: extra margin around pitches; road: margin beyond the carriageway of any road but `self`;
  //   path: margin beyond any road / path surface incl. sidewalks (but `self`)
  //   cut: keep out of underpass cuts (walls, ramps, the trench under the deck; people may walk through)
  ctx.blockedBy = (x, z, { r = 0, water = true, sport = 0, building = true, road = 0, path = false, self = null, cut = true } = {}) => {
    if (water && ctx.wet(x, z)) return 'water';
    if (cut && corridors.length && ctx.inCut(x, z, r)) return 'underpass';
    if (sport !== false && ctx.inSport(x, z, r + sport)) return 'sport';
    if (building && ctx.inBuilding(x, z, r)) return 'building';
    if (road !== false && ctx.onRoad?.(x, z, self, r + road)) return 'road';
    if (path !== false && ctx.onSurface(x, z, r + path, self)) return 'path';
    return null;
  };
  ctx.clear = (x, z, opt) => !ctx.blockedBy(x, z, opt);
  ctx.sanityRoads = roads;
  return ctx;
}

// ---------------------------------------------------------------- river / pond banks
// The ground mesh is the 10 m terrain grid with every vertex inside a water outline dug below the water; the grid
// triangles that straddle a bank then slope down outside it as well, a ditch up to ~2 m deep behind the embankment
// where bank trees and lamps stood below the water line. Heights are queried from the undug grid (main.js), and this
// apron lays that undug surface, in the ground's own material, over the band where the two differ, outside the water
// outlines only (corners inside an outline drop just under the water, behind the embankment wall).
// T: undug grid {nx, nz, h}; renderH: the dug heights the ground mesh was built from; dug: set of dug vertex indices.
export function bankApron(ctx, T, renderH, dug, mat, { cell = 0.5 } = {}) {
  const { W, D } = ctx, { nx, nz } = T, gw = W / (nx - 1), gd = D / (nz - 1);
  const interp = (h, x, z) => {
    const gx = (x + W / 2) / W * (nx - 1), gz = (z + D / 2) / D * (nz - 1);
    const i = Math.max(0, Math.min(nx - 2, Math.floor(gx))), k = Math.max(0, Math.min(nz - 2, Math.floor(gz)));
    const fx = Math.min(1, Math.max(0, gx - i)), fz = Math.min(1, Math.max(0, gz - k));
    const ha = h[k * nx + i], hd = h[k * nx + i + 1], hb = h[(k + 1) * nx + i], hc = h[(k + 1) * nx + i + 1];
    return (fx + fz <= 1 ? ha + (hd - ha) * fx + (hb - ha) * fz : hc + (hb - hc) * (1 - fx) + (hd - hc) * (1 - fz)) / 10;
  };
  // only around dug vertices that have an undug neighbour can the rendered ground differ outside the water
  const cells = new Set(), CW = Math.ceil(W / cell) + 2;
  for (const j of dug) {
    const i = j % nx, k = (j / nx) | 0;
    let edge = false;
    for (let a = -1; a <= 1 && !edge; a++) for (let b = -1; b <= 1; b++) {
      const ii = i + a, kk = k + b;
      if (ii >= 0 && kk >= 0 && ii < nx && kk < nz && !dug.has(kk * nx + ii)) { edge = true; break; }
    }
    if (!edge) continue;
    const xc = -W / 2 + i * gw, zc = -D / 2 + k * gd;
    for (let sx = Math.floor((xc - gw + W / 2) / cell); sx < Math.ceil((xc + gw + W / 2) / cell); sx++)
      for (let sz = Math.floor((zc - gd + D / 2) / cell); sz < Math.ceil((zc + gd + D / 2) / cell); sz++) cells.add(sz * CW + sx);
  }
  const vid = new Map(), pos = [], uv = [], idx = [];
  const vert = (sx, sz) => {
    const key = sz * CW + sx;
    let v = vid.get(key);
    if (v !== undefined) return v;
    const x = -W / 2 + sx * cell, z = -D / 2 + sz * cell, lv = ctx.waterAt ? ctx.waterAt(x, z) : null;
    v = pos.length / 3; vid.set(key, v);
    pos.push(x, lv === null ? interp(T.h, x, z) + 0.02 : Math.min(interp(T.h, x, z), lv - 0.35), z);
    uv.push((x + W / 2) / W, (D / 2 - z) / D);            // the ground PlaneGeometry's uv (aerial photo)
    return v;
  };
  for (const key of cells) {
    const sx = key % CW, sz = (key - sx) / CW, x = -W / 2 + (sx + 0.5) * cell, z = -D / 2 + (sz + 0.5) * cell;
    if (ctx.waterAt && ctx.waterAt(x, z) !== null) continue;
    let diff = 0;
    for (const [a, b] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
      const px = -W / 2 + (sx + a) * cell, pz = -D / 2 + (sz + b) * cell;
      diff = Math.max(diff, interp(T.h, px, pz) - interp(renderH, px, pz));
    }
    if (diff < 0.03) continue;
    const v00 = vert(sx, sz), v10 = vert(sx + 1, sz), v01 = vert(sx, sz + 1), v11 = vert(sx + 1, sz + 1);
    idx.push(v00, v01, v10, v10, v01, v11);                 // same winding as the ground (normals up)
  }
  if (!idx.length) return null;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, mat);
  m.receiveShadow = true;
  ctx.scene.add(m);
  return m;
}

// ---------------------------------------------------------------- DEV scan of the built scene
// Builders tag their meshes with userData.sanity = { kind, dy?, R? }; dy = height of the instance origin above
// the object's foot, R = crown radius at scale 1 (trees). Rules per kind: placement options + height check.
const RULES = {
  tree: { o: { r: 0.25, road: 0.2, path: 0 }, h: 'ground' },
  crown: { o: null },                                   // crown vs walls, checked separately
  flower: { o: { r: 0.2, road: 0.2, path: 0 }, h: 'ground' },
  lamp: { o: { r: 0.1, road: 0.05 }, h: 'top' },
  glamp: { o: { r: 0.1, road: 0.1, path: 0.05 }, h: 'top' },
  sign: { o: { r: 0.1, road: 0.1 }, h: 'top' },
  hedge: { o: { r: 0.45, road: 0.3, path: 0 }, h: 'ground' },
  bench: { o: { r: 0.5, road: 0.2, path: 0 }, h: 'top', low: true },
  bin: { o: { r: 0.25, road: 0.05 }, h: 'top', low: true },
  car: { o: { r: 1.2, road: 0, path: 0 }, h: 'pad', low: true },
  streetcar: { o: { r: 1.0, road: false }, h: 'top', low: true },
  ebike: { o: { r: 0.4, road: 0 }, h: 'top', low: true },
  person: { o: { r: 0.25, road: false, cut: false }, h: 'top', low: true },
  fence: { o: { r: 0, road: false, building: false, sport: false }, h: 'ground' },
  shelter: { o: { r: 1.0, road: 0 }, h: 'top', low: true },
  busstop: { o: { r: 0.1, road: 0 }, h: 'top' },
  grass: { o: { r: 0, road: false, path: 0, sport: 0 }, h: 'ground' },
};

export function scanWorld(ctx, scene, { limit = 30 } = {}) {
  const counts = {}, issues = [];
  const m4 = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  const add = (kind, why, x, z, extra = {}) => {
    const c = counts[kind] ||= { n: 0 };
    c[why] = (c[why] || 0) + 1;
    if ((c[why] || 0) <= limit) issues.push({ kind, why, x: +x.toFixed(1), z: +z.toFixed(1), ...extra });
  };
  let rot = 0;                         // yaw of the instance being visited
  const visit = (kind, tag, x, y, z, sc) => {
    const rule = RULES[kind];
    if (!rule) return;
    (counts[kind] ||= { n: 0 }).n++;
    if (kind === 'crown') {           // crown radius vs the nearest wall: > 0.8 m inside a wall reads as clipping
      const R = (tag.R || 2) * sc, d = ctx.buildingDist(x, z, Math.min(4, R));
      if (d < R - 0.8) add(kind, 'building', x, z, { R: +R.toFixed(1), d: +d.toFixed(1) });
      return;
    }
    const why = ctx.blockedBy(x, z, rule.o);
    if (why) { add(kind, why, x, z); return; }
    if (tag.arm && rot) {               // street lamp: the head (local -z, arm m out) must hang over a carriageway
      const hx = x - Math.sin(rot) * tag.arm, hz = z - Math.cos(rot) * tag.arm;
      if (!ctx.onRoad?.(hx, hz, null, 0.5)) { add(kind, 'facing', x, z); return; }
    }
    const foot = y - (tag.dy || 0);
    const expect = rule.h === 'ground' ? ctx.heightAt(x, z) : rule.h === 'pad' ? ctx.heightAt(x, z) + 0.21 : ctx.topAt(x, z);
    const deck = ctx.deckAt ? ctx.deckAt(x, z) : null;
    if (deck !== null && foot < deck - 0.4 && rule.h !== 'ground') add(kind, 'under-deck', x, z, { dy: +(foot - deck).toFixed(2) });
    else if (foot > expect + 0.12) add(kind, 'float', x, z, { dy: +(foot - expect).toFixed(2) });
    else if (rule.low && foot < expect - 0.1) add(kind, 'buried', x, z, { dy: +(foot - expect).toFixed(2) });
  };
  scene.traverse((o) => {
    const tag = o.userData?.sanity;
    if (!tag) return;
    if (o.isInstancedMesh) {
      for (let i = 0; i < o.count; i++) {
        o.getMatrixAt(i, m4); m4.decompose(p, q, s);
        if (s.x < 1e-3) continue;               // hidden instance (e.g. a 7ma in use)
        rot = 2 * Math.atan2(q.y, q.w);         // instances only turn about y
        visit(tag.kinds ? tag.kinds[i] : tag.kind, tag, p.x, p.y, p.z, s.x);   // kinds: one kind per instance
      }
    } else {
      o.getWorldPosition(p); rot = o.rotation.y;
      visit(tag.kind, tag, p.x, p.y, p.z, 1);
    }
  });
  // roads / paths running through a building or model (centre line every 2 m, campus only): one issue per road
  // with the length inside
  for (const r of ctx.sanityRoads || []) {
    if (r.w < 2) continue;
    let inside = 0, at = null;
    for (let i = 0; i < r.pts.length - 1; i++) {
      const [x0, z0] = r.pts[i], [x1, z1] = r.pts[i + 1], L = Math.hypot(x1 - x0, z1 - z0), n = Math.max(1, Math.ceil(L / 2));
      for (let k = 0; k <= n; k++) {
        const x = x0 + (x1 - x0) * k / n, z = z0 + (z1 - z0) * k / n;
        if (ctx.inCampus(x, z) && !ctx.inCut(x, z, 1) && ctx.inBuilding(x, z, 0)) { inside += L / n; at ||= [x, z]; }   // a road in a cut runs between its walls
      }
    }
    (counts.road ||= { n: 0 }).n++;
    if (inside >= 2) add('road', 'building', at[0], at[1], { id: r.id, type: r.kind, w: r.w, m: Math.round(inside) });
  }
  const summary = Object.fromEntries(Object.entries(counts).map(([k, c]) => [k, c]));
  return { summary, issues };
}
