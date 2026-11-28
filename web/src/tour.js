// 云游导览: a guided flight over the landmark checkpoints — orbit each one with a caption card, then glide to the next.
import * as THREE from 'three';

const ease = (u) => u * u * (3 - 2 * u);

export function createTour(ctx, stops, ui) {
  const { heightAt } = ctx;
  const ORBIT = 10, R = 95, H = 48;
  let active = false, i = 0, phase = 'fly', t = 0, dur = 1, theta = 0;
  const from = new THREE.Vector3(), fromLook = new THREE.Vector3(), cam = new THREE.Vector3(), lookAt = new THREE.Vector3();

  // nearest-neighbour order starting from the stop closest to where the tour begins
  function order(x, z) {
    const left = [...stops], out = [];
    let cx = x, cz = z;
    while (left.length) {
      let k = 0, bd = Infinity;
      left.forEach((s, j) => { const d = Math.hypot(s.x - cx, s.z - cz); if (d < bd) { bd = d; k = j; } });
      const s = left.splice(k, 1)[0];
      out.push(s); cx = s.x; cz = s.z;
    }
    return out;
  }
  let route = stops;
  const target = (s) => new THREE.Vector3(s.x, heightAt(s.x, s.z) + 14, s.z);
  const orbitPos = (s, th) => new THREE.Vector3(s.x + Math.sin(th) * R, heightAt(s.x, s.z) + H, s.z + Math.cos(th) * R);

  function caption(s) {
    ui.title.textContent = s.name;
    ui.sub.textContent = `云游导览 · 第 ${i + 1} / ${route.length} 站${s.note ? ' · ' + s.note : ''}`;
    if (s.photo) { ui.img.src = s.photo; ui.img.hidden = false; } else ui.img.hidden = true;
    ui.box.hidden = false;
  }
  function startLeg(camera) {
    const s = route[i];
    from.copy(camera.position);
    camera.getWorldDirection(fromLook).multiplyScalar(60).add(camera.position);
    // approach from the side we are coming from, so the orbit starts where the flight ends
    theta = Math.atan2(from.x - s.x, from.z - s.z);
    const end = orbitPos(s, theta);
    dur = Math.min(14, Math.max(4, from.distanceTo(end) / 70));
    phase = 'fly'; t = 0;
    ui.box.hidden = true;
  }
  return {
    get active() { return active; },
    start(camera) {
      if (!stops.length) return;
      route = order(camera.position.x, camera.position.z);
      active = true; i = 0;
      startLeg(camera);
    },
    stop() { active = false; ui.box.hidden = true; },
    update(dt, camera) {
      if (!active) return;
      t += dt;
      const s = route[i];
      if (phase === 'fly') {
        const u = ease(Math.min(1, t / dur)), end = orbitPos(s, theta);
        cam.lerpVectors(from, end, u);
        cam.y += Math.sin(Math.PI * u) * Math.min(60, from.distanceTo(end) * 0.12);
        lookAt.lerpVectors(fromLook, target(s), Math.min(1, u * 1.4));
        if (t >= dur) { phase = 'orbit'; t = 0; caption(s); }
      } else {
        const th = theta + t * 0.22;
        cam.copy(orbitPos(s, th));
        lookAt.copy(target(s));
        if (t >= ORBIT) {
          i++;
          if (i >= route.length) { active = false; ui.box.hidden = true; ui.onEnd?.(); return; }
          theta = th;
          startLeg(camera);
          return;
        }
      }
      cam.y = Math.max(cam.y, heightAt(cam.x, cam.z) + 20);
      camera.position.copy(cam);
      camera.lookAt(lookAt);
    },
  };
}
