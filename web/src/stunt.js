// 飙车 + 翘头（卖点）：骑 7ma / 自行车时 Shift 飙车，按住空格强行翘头。总开关在 features.js（老师检查前可一键关闭）。
// 飙车感：速度逐渐拉高、视野变宽、起步时镜头一冲、贴地追尾镜头、转弯压车（人车一起侧倾、镜头往外甩）、屏幕速度线、
//   车尾蓝色光带、时速表 + 速度条、合成的电机声和风声（Web Audio，不用音频文件）。
// 翘头本身很稳，想翘多久翘多久；翘头时再按住 Shift 会把车头拉得更高（金色完美角度，里程 ×2），
// 但越拉越晃，拉太久会后翻翻车——松开 Shift 就能压回来。人和车挂在后轮着地点的旋转节点上，翘头就是绕这个点转。
import * as THREE from 'three';
import './stunt.css';

const BEST_KEY = 'nuist-wheelie-best-v2', TIP_KEY = 'nuist-wheelie-tip-v1';
const AIM = 0.55, AIM_BOOST = 0.93, FALL = 1.12, PERFECT = [0.8, 1.06], OK = [0.3, 0.8];
const K = 8, DAMP = 5.1;   // spring towards the aim angle, close to critically damped
const BOOST = { ebike: 1.6, bike: 1.3 }, BASE_FOV = 60, VMAX = 25;   // VMAX: m/s that fills the speed bar
const TRAIL_N = 44;

function smokeTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const x = c.getContext('2d'), g = x.createRadialGradient(32, 32, 2, 32, 32, 30);
  g.addColorStop(0, 'rgba(235,235,235,1)'); g.addColorStop(1, 'rgba(235,235,235,0)');
  x.fillStyle = g; x.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

// motor whine + wind, synthesized; starts on the first click / key press (browsers block audio before that)
function createRideAudio() {
  let ac = null, n = null;
  const start = () => {
    if (ac) { if (ac.state === 'suspended') ac.resume().catch(() => {}); return; }
    try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch { return; }
    const master = ac.createGain(); master.gain.value = 0.5; master.connect(ac.destination);
    const motor = ac.createOscillator(); motor.type = 'sawtooth'; motor.frequency.value = 80;
    const motor2 = ac.createOscillator(); motor2.type = 'triangle'; motor2.frequency.value = 160;
    const mf = ac.createBiquadFilter(); mf.type = 'lowpass'; mf.frequency.value = 700; mf.Q.value = 3;
    const mg = ac.createGain(); mg.gain.value = 0;
    motor.connect(mf); motor2.connect(mf); mf.connect(mg); mg.connect(master);
    const len = ac.sampleRate * 2, buf = ac.createBuffer(1, len, ac.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    const noise = ac.createBufferSource(); noise.buffer = buf; noise.loop = true;
    const wf = ac.createBiquadFilter(); wf.type = 'bandpass'; wf.Q.value = 0.6; wf.frequency.value = 500;
    const wg = ac.createGain(); wg.gain.value = 0;
    noise.connect(wf); wf.connect(wg); wg.connect(master);
    motor.start(); motor2.start(); noise.start();
    n = { master, motor, motor2, mf, mg, wf, wg, buf };
  };
  addEventListener('pointerdown', start);
  addEventListener('keydown', start);
  return {
    set(v, riding, boost, wheelie) {
      if (!n) return;
      const t = ac.currentTime, on = riding && !document.hidden;
      const s = Math.min(1, v / VMAX);
      n.motor.frequency.setTargetAtTime(70 + s * 260 + (boost ? 40 : 0), t, 0.12);
      n.motor2.frequency.setTargetAtTime(140 + s * 520 + (wheelie ? 60 : 0), t, 0.12);
      n.mf.frequency.setTargetAtTime(500 + s * 1800, t, 0.15);
      n.mg.gain.setTargetAtTime(on ? 0.02 + s * 0.05 + (boost ? 0.02 : 0) : 0, t, 0.2);
      n.wf.frequency.setTargetAtTime(300 + s * 1500, t, 0.2);
      n.wg.gain.setTargetAtTime(on ? Math.max(0, s - 0.25) * 0.22 : 0, t, 0.25);
    },
    thump(strength = 1) {   // front wheel landing / crash
      if (!n || document.hidden) return;
      const src = ac.createBufferSource(); src.buffer = n.buf;
      const f = ac.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 260;
      const g = ac.createGain(), t = ac.currentTime;
      g.gain.setValueAtTime(0.35 * strength, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.25 + 0.25 * strength);
      src.connect(f); f.connect(g); g.connect(n.master); src.start(t, Math.random()); src.stop(t + 0.6);
    },
  };
}

export function createStunt({ P, avatar, rider, bicycle, ebikeMesh, camera, scene, say }) {
  const tilt = new THREE.Group(), inner = new THREE.Group();
  tilt.add(inner);
  for (const o of [rider, bicycle, ebikeMesh]) inner.add(o);   // add() detaches them from the avatar
  avatar.add(tilt);
  const audio = createRideAudio();

  let best = { t: 0, m: 0 };
  try { best = { t: 0, m: 0, ...JSON.parse(localStorage.getItem(BEST_KEY) || '{}') }; } catch { /* private mode */ }
  let keyHeld = false, touchHeld = false, shiftKey = false;
  let mode = 'idle', th = 0, om = 0, t = 0, dist = 0, perfectM = 0, tb = 0, ft = 0, side = 1, ph = [0, 0, 0];
  let cam = 0, lx = 0, lz = 0, v = 0, mul = 1, curRide = null, endShow = 0, fovOwned = false, shake = 0, rearZ = 0.55;
  let roll = 0, lastYaw = 0, kick = 0, wasBoost = false, trailOn = 0;

  // ---- HUD: speedometer + speed bar while riding, wheelie timer / balance bar while wheeling ----
  const hud = document.createElement('div');
  hud.id = 'wheelie'; hud.hidden = true;
  hud.innerHTML = '<div class="wh-spd"><b>0</b><small>km/h</small><em></em><span></span></div><div class="wh-bar"><i></i></div>'
    + '<div class="wh-w" hidden><b></b><div class="wb"><i class="wz"></i><i class="wp"></i><i class="wn"></i></div><span></span></div>';
  document.body.appendChild(hud);
  const spdB = hud.querySelector('.wh-spd b'), spdS = hud.querySelector('.wh-spd span'), spdE = hud.querySelector('.wh-spd em'), barI = hud.querySelector('.wh-bar i');
  const wBox = hud.querySelector('.wh-w'), wT = wBox.querySelector('b'), wS = wBox.querySelector('span'), needle = hud.querySelector('.wn');
  const pct = (a) => `${a / FALL * 100}%`;
  hud.querySelector('.wz').style.cssText = `left:${pct(OK[0])};width:${pct(OK[1] - OK[0])}`;
  hud.querySelector('.wp').style.cssText = `left:${pct(PERFECT[0])};width:${pct(PERFECT[1] - PERFECT[0])}`;
  const fx = document.createElement('div');
  fx.id = 'speedfx';
  document.body.appendChild(fx);

  // ---- rear-tyre smoke ----
  const smokeTex = smokeTexture(), puffs = [];
  for (let i = 0; i < 36; i++) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: smokeTex, transparent: true, depthWrite: false, opacity: 0 }));
    s.visible = false; scene.add(s); puffs.push({ s, life: 0 });
  }
  let puffI = 0, puffAcc = 0;
  const tmp = new THREE.Vector3(), tgt = new THREE.Vector3();
  function puff() {
    const p = puffs[puffI++ % puffs.length];
    avatar.localToWorld(tmp.set((Math.random() - 0.5) * 0.3, 0.15, rearZ + 0.25));
    p.s.position.copy(tmp); p.life = 1; p.s.visible = true;
  }

  // ---- blue light trail from the tail light while flat out (additive ribbon, fades along its length) ----
  const trailPos = new Float32Array(TRAIL_N * 2 * 3), trailCol = new Float32Array(TRAIL_N * 2 * 3), hist = [];
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setAttribute('color', new THREE.BufferAttribute(trailCol, 3));
  const idx = [];
  for (let i = 0; i < TRAIL_N - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  trailGeo.setIndex(idx);
  const trail = new THREE.Mesh(trailGeo, new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false }));
  trail.frustumCulled = false; trail.visible = false;
  scene.add(trail);
  const TC = new THREE.Color('#3fb4ff');
  function drawTrail(dt, want) {
    trailOn += ((want ? 1 : 0) - trailOn) * Math.min(1, dt * (want ? 4 : 2));
    if (trailOn < 0.02) { trail.visible = false; hist.length = 0; return; }
    avatar.updateMatrixWorld(true);
    inner.localToWorld(tmp.set(0, 0.72, rearZ + 0.12));
    hist.unshift(tmp.clone());
    if (hist.length > TRAIL_N) hist.length = TRAIL_N;
    for (let i = 0; i < TRAIL_N; i++) {
      const p = hist[Math.min(i, hist.length - 1)], f = i < hist.length ? (1 - i / TRAIL_N) ** 1.6 * trailOn : 0, w = 0.07 * (1 - i / TRAIL_N) + 0.01;
      trailPos.set([p.x, p.y + w, p.z, p.x, p.y - w, p.z], i * 6);
      trailCol.set([TC.r * f, TC.g * f, TC.b * f, TC.r * f, TC.g * f, TC.b * f], i * 6);
    }
    trailGeo.attributes.position.needsUpdate = true; trailGeo.attributes.color.needsUpdate = true;
    trail.visible = true;
  }

  // ---- input (own listeners; main.js keeps Space = jump on foot) ----
  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.code === 'Space') keyHeld = true;
    if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') shiftKey = true;
  });
  addEventListener('keyup', (e) => {
    if (e.code === 'Space') keyHeld = false;
    if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') shiftKey = false;
  });
  addEventListener('blur', () => { keyHeld = touchHeld = shiftKey = false; });
  const jumpBtn = document.querySelector('#tbtns [data-act="jump"]'), runBtn = document.querySelector('#tbtns [data-act="run"]');
  if (jumpBtn) {   // touch: "跳" becomes a hold-to-wheelie button while riding
    jumpBtn.addEventListener('pointerdown', () => { touchHeld = true; });
    for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) jumpBtn.addEventListener(ev, () => { touchHeld = false; });
  }
  const boosting = () => shiftKey || !!runBtn?.classList.contains('on');

  function pivotFor(ride) {
    rearZ = 0.55;
    if (ride === 'ebike') {
      const box = new THREE.Box3();
      ebikeMesh.traverse((o) => { if (o.isMesh) { o.geometry.computeBoundingBox(); box.union(o.geometry.boundingBox); } });
      if (!box.isEmpty()) rearZ = Math.max(0.3, box.max.z - 0.3);
    }
    tilt.position.set(0, 0, rearZ); inner.position.set(0, 0, -rearZ);
  }

  function finish(fell) {
    hud.classList.remove('bad', 'perfect');
    const score = Math.round(dist + perfectM);
    if (fell) { mode = 'fall'; ft = 0; side = Math.random() < 0.5 ? -1 : 1; shake = 0.6; audio.thump(1.4); say('翻车了！完美角度别拉太久，晃起来就松开 Shift 压回来', 3); }
    else { mode = 'idle'; audio.thump(0.6); shake = Math.max(shake, 0.12); }
    if (t >= 0.6) {
      const recT = t > best.t, recM = score > best.m;
      if (recT || recM) { best = { t: Math.max(best.t, t), m: Math.max(best.m, score) }; try { localStorage.setItem(BEST_KEY, JSON.stringify(best)); } catch { /* ignore */ } }
      wT.textContent = `${fell ? '翻车 · ' : ''}翘头 ${t.toFixed(1)} s · ${score} m${recT || recM ? ' · 新纪录！' : ''}`;
      wS.textContent = `最佳 ${best.t.toFixed(1)} s · ${best.m} m`;
      endShow = 2.5;
    } else wBox.hidden = true;
  }

  function resetIdle() {
    mode = 'idle'; th = 0; om = 0; roll = 0; tilt.rotation.set(0, 0, 0); wBox.hidden = true; endShow = 0;
    hud.classList.remove('bad', 'perfect');
  }

  // chase camera, run after main.js placed the camera: closer and lower at speed, swung out on turns,
  // FOV opens with speed (+ a punch when the boost kicks in), slight shake; in a wheelie it swings to the side
  function chaseCam(dt, boost) {
    const k = Math.max(0, Math.min(1, (v - 10) / 16));
    camera.fov += (BASE_FOV + k * 16 + kick - camera.fov) * Math.min(1, dt * 5);
    camera.updateProjectionMatrix(); fovOwned = true;
    if (P.first) return;
    tgt.set(P.pos.x, P.pos.y + 1.5, P.pos.z);
    camera.position.lerp(tgt, 0.12 * k);
    camera.position.y = Math.max(P.pos.y + 1.2, camera.position.y - 0.25 * k);
    const sideways = roll * 1.6 * Math.min(1, v / 12);   // swing to the outside of the turn
    camera.position.x += Math.cos(P.yaw) * sideways; camera.position.z -= Math.sin(P.yaw) * sideways;
    cam += ((mode === 'wheelie' || mode === 'fall') ? 1 : -1) * dt * 2.2; cam = Math.max(0, Math.min(1, cam));
    if (cam > 0) {   // stunt cam: swing to the side so the lifted front wheel reads clearly
      const e = cam * cam * (3 - 2 * cam), a = 0.42 * e, dx = camera.position.x - tgt.x, dz = camera.position.z - tgt.z;
      camera.position.x = tgt.x + dx * Math.cos(a) + dz * Math.sin(a); camera.position.z = tgt.z - dx * Math.sin(a) + dz * Math.cos(a);
      camera.position.y = Math.max(camera.position.y, P.pos.y + 2.1 * e);   // stay above railings and hedges
      tgt.y = P.pos.y + 1.1;
    }
    camera.lookAt(tgt);
    const amp = shake + (mode === 'wheelie' ? 0.025 : 0) + k * (boost ? 0.04 : 0.02);
    if (amp > 0.001) camera.position.add(tmp.set((Math.random() - 0.5) * amp, (Math.random() - 0.5) * amp, (Math.random() - 0.5) * amp));
  }

  function update(dt) {
    const ride = (P.ride === 'ebike' || P.ride === 'bike') && !P.fly ? P.ride : null;
    const raw = Math.hypot(P.pos.x - lx, P.pos.z - lz) / Math.max(dt, 1e-3);
    lx = P.pos.x; lz = P.pos.z;
    v += (Math.min(raw, 60) - v) * Math.min(1, dt * 5);
    let dyaw = avatar.rotation.y - lastYaw; dyaw = Math.atan2(Math.sin(dyaw), Math.cos(dyaw)); lastYaw = avatar.rotation.y;
    if (jumpBtn) { const lab = ride ? '翘头' : '跳'; if (jumpBtn.textContent !== lab) jumpBtn.textContent = lab; }
    if (runBtn) { const lab = ride ? '飙车' : '跑'; if (runBtn.textContent !== lab) runBtn.textContent = lab; }
    if (ride !== curRide) { curRide = ride; if (ride) pivotFor(ride); else resetIdle(); }

    // smoke always fades out, even after getting off
    for (const p of puffs) {
      if (!p.s.visible) continue;
      p.life -= dt * 1.25;
      if (p.life <= 0) { p.s.visible = false; continue; }
      p.s.position.y += dt * 0.7;
      p.s.scale.setScalar(0.5 + (1 - p.life) * 1.8);
      p.s.material.opacity = p.life * 0.5;
    }

    const photo = document.body.classList.contains('photo-mode');
    if (!ride) {
      mul += (1 - mul) * Math.min(1, dt * 4);
      hud.hidden = true; fx.style.opacity = '0'; document.body.classList.remove('stunt-hud');
      if (fovOwned && !photo) { camera.fov = BASE_FOV; camera.updateProjectionMatrix(); fovOwned = false; }
      audio.set(0, false, false, false);
      drawTrail(dt, false);
      return;
    }
    const boost = boosting() && mode !== 'fall';
    const held = keyHeld || touchHeld;
    if (boost && !wasBoost && v > 5) { kick = 9; shake = Math.max(shake, 0.1); }   // the boost punches in
    wasBoost = boost;
    kick = Math.max(0, kick - dt * 14);
    shake = Math.max(0, shake - dt * 1.2);

    // 飙车: ease the speed multiplier (main.js multiplies its ride speed by it)
    const wantMul = mode === 'fall' ? 0.15 : (boost ? BOOST[ride] : 1) * (mode === 'wheelie' ? 1.08 : 1);
    mul += (wantMul - mul) * Math.min(1, dt * (wantMul > mul ? 0.9 : 2.5));

    // lean into turns: roll with turn rate × speed (less while wheeling)
    const rollWant = Math.max(-0.42, Math.min(0.42, (dyaw / Math.max(dt, 1e-3)) * Math.min(1.6, v / 12) * 0.16)) * (mode === 'wheelie' ? 0.5 : 1);
    roll += (rollWant - roll) * Math.min(1, dt * 6);

    if (!photo) {
      chaseCam(dt, boost);
      fx.style.opacity = String(Math.max(0, Math.min(0.9, (v - 15) / 9)));
    }
    audio.set(v, true, boost, mode === 'wheelie');
    drawTrail(dt, (boost && v > 9) || (mode === 'wheelie' && v > 6));
    hud.hidden = photo;
    document.body.classList.toggle('stunt-hud', !photo);
    const kmh = Math.round(v * 3.6);
    spdB.textContent = String(kmh);
    spdE.textContent = kmh >= 80 ? '极速' : '';
    barI.style.width = `${Math.min(100, v / VMAX * 100)}%`;
    const tch = document.body.classList.contains('touch'), kB = tch ? '飙车键' : 'Shift', kW = tch ? '按住翘头键' : '按住空格';
    spdS.textContent = mode === 'wheelie' ? (boost ? '完美角度要稳住！' : `${kB} 拉高车头`) : boost ? `飙车中 · ${kW}翘头` : `${kB} 飙车 · ${kW}翘头`;
    hud.classList.toggle('boost', boost);

    if (mode === 'fall') {
      ft += dt;
      const a = Math.min(1, ft / 0.35), b = ft > 1.5 ? Math.max(0, 1 - (ft - 1.5) / 0.5) : 1;
      th = Math.max(0, th - dt * 3);
      tilt.rotation.x = th; tilt.rotation.z = side * 1.3 * a * b;
      if (ft > 2.0) { mode = 'idle'; th = 0; om = 0; roll = 0; tilt.rotation.set(0, 0, 0); }
      if (endShow > 0 && (endShow -= dt) <= 0) wBox.hidden = true;
      return;
    }

    if (mode === 'idle' && held && v > 4) {
      mode = 'wheelie'; t = 0; dist = 0; perfectM = 0; tb = 0; om = 1.5; ph = [Math.random() * 6, Math.random() * 6, Math.random() * 6];
      wBox.hidden = false; endShow = 0;
      let seen = false;
      try { seen = !!localStorage.getItem(TIP_KEY); localStorage.setItem(TIP_KEY, '1'); } catch { /* ignore */ }
      if (!seen) say('翘头！按住 Shift 拉到金色完美角度，里程翻倍。（游戏动作，现实骑车请勿模仿）', 5);
    }

    if (mode === 'wheelie') {
      t += dt; tb = boost ? tb + dt : Math.max(0, tb - dt * 2);
      const noise = Math.sin(t * 1.3 + ph[0]) * 0.6 + Math.sin(t * 2.9 + ph[1]) * 0.4 + Math.sin(t * 0.7 + ph[2]) * 0.5;
      const wob = boost ? 0.06 + tb * 0.035 : 0.04;   // full-throttle wheelies get shakier the longer you hold them
      let acc = held ? K * ((boost ? AIM_BOOST : AIM) + noise * wob - th) - DAMP * om : -10 - 2 * om;
      if (held && v < 2) acc -= 6;   // no wheelie standing still
      om += acc * dt; th += om * dt;
      if (th > FALL) { finish(true); return; }
      if (th <= 0) { th = 0; om = 0; finish(false); return; }
      const step = v * dt, perfect = th >= PERFECT[0] && th <= PERFECT[1];
      dist += step; if (perfect) perfectM += step;
      tilt.rotation.x = th; tilt.rotation.z = roll;
      puffAcc += dt * (v > 6 ? 26 : 8);
      while (puffAcc > 1) { puffAcc--; puff(); }
      wT.textContent = `翘头 ${t.toFixed(1)} s · ${Math.round(dist + perfectM)} m${perfect ? ' · 完美 ×2' : ''}`;
      wS.textContent = `最佳 ${best.t.toFixed(1)} s · ${best.m} m`;
      needle.style.left = pct(Math.min(th, FALL));
      hud.classList.toggle('perfect', perfect);
      hud.classList.toggle('bad', th > PERFECT[1] || th < OK[0]);
      return;
    }

    // idle: tiny lift when Space is held standing still, settle back otherwise; lean into turns
    th += ((held ? 0.1 : 0) - th) * Math.min(1, dt * 10);
    tilt.rotation.x = th; tilt.rotation.z = roll;
    if (endShow > 0 && (endShow -= dt) <= 0) wBox.hidden = true;
  }

  return {
    update,
    get speedMul() { return mul; },
    get locked() { return mode === 'fall'; },
    get active() { return mode === 'wheelie'; },
    get best() { return best.t; },
    get bestDist() { return best.m; },
  };
}
