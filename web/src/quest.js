// 云游打卡: visit the landmark checkpoints, collect stamps, unlock the postcard.
import * as THREE from 'three';

const KEY = 'nuist-tour-stamps-v1';
const load = () => { try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch { return new Set(); } };
const save = (s) => { try { localStorage.setItem(KEY, JSON.stringify([...s])); } catch { /* private mode */ } };

export function createQuest(ctx, points, ui) {
  const { scene, heightAt } = ctx;
  const got = load();
  const beamGeo = new THREE.CylinderGeometry(1.2, 1.2, 60, 16, 1, true).translate(0, 30, 0);
  const ringGeo = new THREE.TorusGeometry(3.2, 0.25, 8, 40).rotateX(Math.PI / 2);
  const items = points.map((p) => {
    const y = heightAt(p.x, p.z);
    const beamMat = new THREE.MeshBasicMaterial({ color: '#ffcf4a', transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide, fog: false });
    const ringMat = new THREE.MeshBasicMaterial({ color: '#ffcf4a', transparent: true, opacity: 0.9 });
    const beam = new THREE.Mesh(beamGeo, beamMat), ring = new THREE.Mesh(ringGeo, ringMat);
    beam.position.set(p.x, y, p.z); ring.position.set(p.x, y + 2.2, p.z);
    scene.add(beam, ring);
    return { ...p, y, beam, ring, beamMat, ringMat };
  });
  const paint = (it) => {
    const done = got.has(it.name);
    it.beamMat.color.set(done ? '#58d68d' : '#ffcf4a'); it.ringMat.color.set(done ? '#58d68d' : '#ffcf4a');
    it.beamMat.opacity = done ? 0.08 : 0.22;
  };
  items.forEach(paint);

  function renderBook() {
    ui.grid.replaceChildren(...items.map((it) => {
      const d = document.createElement('div');
      d.className = 'stamp' + (got.has(it.name) ? ' got' : '');
      const img = document.createElement('div');
      img.className = 'stamp-img';
      if (got.has(it.name) && it.photo) img.style.backgroundImage = `url(${it.photo})`;
      img.textContent = got.has(it.name) ? '' : '?';
      const t = document.createElement('span'); t.textContent = it.name;
      d.append(img, t);
      return d;
    }));
    ui.count.textContent = `${got.size} / ${items.length}`;
    ui.postcard.hidden = got.size < items.length;
  }
  renderBook();

  return {
    total: items.length,
    get count() { return got.size; },
    update(dt, t, pos) {
      let next = null, nd = Infinity;
      for (const it of items) {
        it.ring.rotation.y = t * 0.8;
        it.ring.position.y = it.y + 2.2 + Math.sin(t * 2 + it.x) * 0.3;
        const d = Math.hypot(it.x - pos.x, it.z - pos.z);
        if (!got.has(it.name)) {
          if (d < 15) {
            got.add(it.name); save(got); paint(it); renderBook();
            ui.onStamp(it, got.size, items.length);
          } else if (d < nd) { nd = d; next = it; }
        }
      }
      return next ? { name: next.name, d: nd, dx: next.x - pos.x, dz: next.z - pos.z } : null;
    },
    reset() { got.clear(); save(got); items.forEach(paint); renderBook(); },
    renderBook,
  };
}
