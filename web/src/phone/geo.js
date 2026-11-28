// 目标点：按名字找楼（楼的轮廓）或官网点位（点位所在的楼，没有就用点本身），算到楼边的距离、放光柱的位置、照片地名。
// phone.js 和 route.js 共用。
export function inside(m, x, z) {
  if (x < m.minX || x > m.maxX || z < m.minZ || z > m.maxZ) return false;
  let r = false;
  for (let i = 0, j = m.xs.length - 1; i < m.xs.length; j = i++) {
    if ((m.zs[i] > z) !== (m.zs[j] > z) && x < (m.xs[j] - m.xs[i]) * (z - m.zs[i]) / (m.zs[j] - m.zs[i]) + m.xs[i]) r = !r;
  }
  return r;
}
export function nearestEdge(m, x, z) {
  let best = Infinity, bx = m.cx, bz = m.cz;
  for (let i = 0, j = m.xs.length - 1; i < m.xs.length; j = i++) {
    const ax = m.xs[j], az = m.zs[j], ex = m.xs[i] - ax, ez = m.zs[i] - az, l2 = ex * ex + ez * ez || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - ax) * ex + (z - az) * ez) / l2)), qx = ax + ex * t, qz = az + ez * t;
    const d = (x - qx) ** 2 + (z - qz) ** 2;
    if (d < best) { best = d; bx = qx; bz = qz; }
  }
  return [bx, bz, Math.sqrt(best)];
}

export function makeTargets({ named, markers, metas, collide }) {
  const cache = new Map();
  function tgt(name) {
    if (cache.has(name)) return cache.get(name);
    let t = null;
    const m = named.find((o) => o.name === name && o.xs);
    if (m) t = { name, meta: m, x: m.cx, z: m.cz };
    else {
      const mk = markers.find((o) => o.name === name);
      if (mk) t = { name, meta: metas.find((o) => o.xs && o.kind !== 'wall' && inside(o, mk.x, mk.z)) || null, x: mk.x, z: mk.z };
    }
    cache.set(name, t);
    return t;
  }
  const tdist = (t, x, z) => (t.meta ? (inside(t.meta, x, z) ? 0 : nearestEdge(t.meta, x, z)[2]) : Math.hypot(t.x - x, t.z - z));
  function beaconAt(t, x, z) {
    if (!t.meta) return [t.x, t.z];
    const [qx, qz, d] = nearestEdge(t.meta, x, z);
    const dx = d > 0.1 ? (x - qx) / d : 0, dz = d > 0.1 ? (z - qz) / d : 1;
    const p = { x: qx + dx * 3, y: 0, z: qz + dz * 3 };
    for (let i = 0; i < 4; i++) collide(p, 1.5);
    return [p.x, p.z];
  }
  function placeName(x, z) {
    let best = null, bd = 60;
    for (const m of named) {
      if (!m.campus || !m.xs || Math.abs(m.cx - x) > 200 || Math.abs(m.cz - z) > 200) continue;
      const d = inside(m, x, z) ? 0 : nearestEdge(m, x, z)[2];
      if (d < bd) { bd = d; best = m.name; }
    }
    if (best) return best;
    let mk = null, md = 40;
    for (const m of markers) { const d = Math.hypot(m.x - x, m.z - z); if (d < md) { md = d; mk = m.name; } }
    return mk || '南京信息工程大学';
  }
  return { tgt, tdist, beaconAt, placeName };
}
